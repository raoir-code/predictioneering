"""Offline source-grounded audit and human review queue for scientific paper profiles.

No API or network calls. Does not alter original PDF text or model-extracted profiles.
Flags are conservative *review prompts*, not automated entailment judgments.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys

from .paper_profiles import VERSION, cleaned, prepare
from .pdf_text import DEFAULT_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile_evidence_reviews (
 root TEXT NOT NULL, relpath TEXT NOT NULL, pdf_sha256 TEXT NOT NULL,
 profile_version TEXT NOT NULL, model TEXT NOT NULL, evidence_id TEXT NOT NULL,
 decision TEXT NOT NULL CHECK(decision IN ('approved','rejected','needs_revision')),
 reviewer_note TEXT NOT NULL, reviewed_at TEXT NOT NULL,
 PRIMARY KEY(root,relpath,pdf_sha256,profile_version,model,evidence_id)
);
CREATE INDEX IF NOT EXISTS profile_evidence_reviews_file
 ON profile_evidence_reviews(root,relpath,pdf_sha256);
"""
DECISIONS = ("approved", "rejected", "needs_revision")
NUMBERS = re.compile(r"(?<![A-Za-z])\b\d+(?:\.\d+)?%?\b")
THEORY_LANGUAGE = re.compile(
    r"\b(?:comparative statics?|equilibrium|model implies|"
    r"model predicts|simulation(?:s)?|proposition|theory predicts)\b", re.I
)
VISUAL = re.compile(r"\b(?:table|figure|fig\.)\s*\d+", re.I)
FORMAL = {"formal_model", "assumption"}
CATEGORIES = ("formal_model", "assumption", "mechanism", "empirical_finding")
SIMULATION_CUE = re.compile(
    r"\b(?:simulations?|simulated|simulate[ds]?|computational experiments?)\b",
    re.I
)
PRIOR_WORK_CUE = re.compile(
    r"\b(?:prior|previous|earlier|existing)\s+(?:work|research|studies|findings|literature)\b"
    r"|\b(?:citing|cites|reexamines|revisits)\s+\w+",
    re.I
)

def evidence_source_type_hint(kind, claim, quote):
    """Conservative *candidate* origin, not a correction or scientific validation.

    Prefer positive cues in the original claim or quote over speculative
    classification from nearby unrelated paragraphs.
    """
    if kind != "empirical_finding":
        return "not_applicable"
    if SIMULATION_CUE.search(claim) or SIMULATION_CUE.search(quote):
        return "simulation_result_candidate"
    if PRIOR_WORK_CUE.search(claim):
        return "prior_literature_result_candidate"
    return "finding_origin_unresolved"


def open_audit_db(path):
    db = prepare(path)
    db.executescript(SCHEMA)
    return db

def load_profile(db, selector):
    """Exactly one *current* profile; ambiguous selectors refuse to choose."""
    selector = selector.strip().casefold()
    if not selector:
        raise ValueError("Supply a nonempty --file selector")
    rows = db.execute(
        """SELECT p.root,p.relpath,p.pdf_sha256,p.version,p.model,p.title,
                  p.profile_json
           FROM paper_profiles p
           JOIN pdf_text_documents d
             ON d.root=p.root AND d.relpath=p.relpath
           JOIN pdf_files i
             ON i.root=p.root AND i.relpath=p.relpath
           WHERE p.version=? AND d.status='ok'
             AND p.pdf_sha256=d.sha256 AND p.pdf_sha256=i.sha256
           ORDER BY p.root,p.relpath""", (VERSION,)
    ).fetchall()
    found = [row for row in rows if selector in row["relpath"].casefold()
             or selector in row["title"].casefold()]
    if not found:
        raise ValueError("No current profile matches. Run paper_profiles show first.")
    if len(found) > 1:
        raise ValueError("Ambiguous --file selector: " + "; ".join(
            row["relpath"] for row in found[:10]))
    return found[0], json.loads(found[0]["profile_json"])

def source_pages(db, row):
    return {int(p["page_num"]): p["text"] for p in db.execute(
        """SELECT page_num,text FROM pdf_text_pages
           WHERE root=? AND relpath=? ORDER BY page_num""",
        (row["root"], row["relpath"])
    )}

def context_for(text, quote, radius=240):
    """Return human-readable context around a verified PDF-page quote."""
    page, fragment = cleaned(text), cleaned(quote)
    at = page.find(fragment) if fragment else -1
    if at < 0:
        return None
    left, right = max(0, at-radius), min(len(page), at+len(fragment)+radius)
    return ("…" if left else "") + page[left:right] + ("…" if right<len(page) else "")

def assessment(item, page_text):
    """Heuristic warnings. Only page-string fidelity can be checked deterministically."""
    claim = item.get("claim") or ""
    quote = item.get("quote") or ""
    kind = item.get("kind") or ""
    context = context_for(page_text or "", quote)
    source_type_hint = evidence_source_type_hint(kind, claim, quote)
    warnings = []
    if source_type_hint == "simulation_result_candidate":
        warnings.append("simulation_result_not_observational_finding")
    elif source_type_hint == "prior_literature_result_candidate":
        warnings.append("reported_prior_result_not_original_empirical_test")
    if context is None:
        warnings.append("quote_not_found_on_claimed_pdf_page")
    if len(cleaned(quote)) < 65:
        warnings.append("short_quote_may_not_substantiate_full_claim")
    if kind == "empirical_finding" and THEORY_LANGUAGE.search(claim):
        warnings.append("possible_theory_or_simulation_mislabeled_empirical")
    if VISUAL.search(claim):
        warnings.append("table_or_figure_requires_original_pdf_inspection")
    if kind == "formal_model":
        warnings.append("formal_result_requires_equation_payoff_and_proof_check")
    if kind == "assumption" and re.search(r"\b(?:payoff|probability|signal|stage)\b", claim, re.I):
        warnings.append("formal_assumption_requires_symbol_definition_check")
    claim_numbers = set(NUMBERS.findall(claim))
    # H1/H2 and Proposition 1 are theoretical labels, not estimated magnitudes.
    normalized_claim = re.sub(r"\b(?:H|Proposition)\s*\d+\b", "", claim, flags=re.I)
    claim_numbers = set(NUMBERS.findall(normalized_claim))
    nearby_numbers = set(NUMBERS.findall(context or ""))
    if kind in {"empirical_finding","research_design"} and claim_numbers - nearby_numbers:
        warnings.append("numeric_detail_not_shown_in_local_quote_context")
    if context is None:
        priority = 100
    else:
        priority = (
            25 * int(kind == "formal_model")
            + 18 * int("possible_theory_or_simulation_mislabeled_empirical" in warnings)
            + 18 * int("simulation_result_not_observational_finding" in warnings)
            + 12 * int("reported_prior_result_not_original_empirical_test" in warnings)
            + 15 * int("table_or_figure_requires_original_pdf_inspection" in warnings)
            + 12 * int("numeric_detail_not_shown_in_local_quote_context" in warnings)
            + 8 * int("formal_assumption_requires_symbol_definition_check" in warnings)
            + 5 * int("short_quote_may_not_substantiate_full_claim" in warnings)
        )
    return {
        "evidence_id": item["evidence_id"],
        "pdf_page": item["page"], "kind": kind,
        "claim": claim, "verified_quote": quote,
        "quote_found_on_original_indexed_page": context is not None,
        "source_context": context, "warnings": warnings, "priority": priority,
        "source_type_hint": source_type_hint,
        "source_type_hint_is_human_verified": False,
    }

def audits(db, row, profile):
    pages = source_pages(db, row)
    output = []
    for e in profile["evidence"]:
        result = assessment(e, pages.get(e["page"]))
        output.append(result)
    reviews = {r["evidence_id"]: dict(r) for r in db.execute(
        """SELECT evidence_id,decision,reviewer_note,reviewed_at
           FROM profile_evidence_reviews
           WHERE root=? AND relpath=? AND pdf_sha256=? AND profile_version=?
             AND model=?""",
        (row["root"], row["relpath"], row["pdf_sha256"], row["version"], row["model"])
    )}
    for a in output:
        saved = reviews.get(a["evidence_id"])
        a["review_status"] = saved["decision"] if saved else "not_reviewed"
        if saved:
            a["reviewer_note"] = saved["reviewer_note"]
            a["reviewed_at"] = saved["reviewed_at"]
    return output

def pick_queue(queue, limit, stratified=False):
    if not stratified:
        return queue[:limit]
    # Reproducible round-robin review sample spanning types of claims.
    categories = (
        "formal_model", "assumption", "empirical_finding", "mechanism",
        "research_design", "theory", "hypothesis", "limitation", "research_question",
    )
    grouped = {kind: [item for item in queue if item["kind"] == kind] for kind in categories}
    result = []
    while len(result) < limit:
        progressed = False
        for kind in categories:
            if grouped[kind] and len(result) < limit:
                result.append(grouped[kind].pop(0))
                progressed = True
        if not progressed:
            break
    return result

def report(database, file, limit=15, only_unreviewed=True, stratified=False):
    if not 1 <= limit <= 200:
        raise ValueError("--limit must be from 1 to 200")
    with closing(open_audit_db(database)) as db:
        row, profile = load_profile(db, file)
        cards = audits(db, row, profile)
    count = Counter(a["review_status"] for a in cards)
    risks = Counter(flag for a in cards for flag in a["warnings"])
    queue = [a for a in cards if a["review_status"] == "not_reviewed"] if only_unreviewed else cards
    queue.sort(key=lambda a: (-a["priority"], a["pdf_page"], a["evidence_id"]))
    return {
        "paper": profile["title"], "file": profile["file"],
        "pdf_sha256": row["pdf_sha256"], "model": row["model"],
        "evidence_total": len(cards),
        "human_reviews": dict(count), "warning_counts": dict(risks),
        "source_quote_mismatches": sum(not a["quote_found_on_original_indexed_page"]
                                       for a in cards),
        "queue_total": len(queue), "queue": pick_queue(queue, limit, stratified),
        "scientific_verdict": "not_verified",
        "note": ("Page-level quotation matching checks presence, NOT inference or "
                 "entailment. Flags and risk ordering are heuristics. "
                 "Read the original PDF, especially equations and tables."),
    }

def mark(database, file, evidence_id, decision, note, confirmed=False):
    if decision not in DECISIONS:
        raise ValueError("Invalid decision")
    if decision == "approved" and not confirmed:
        raise ValueError(
            "Approving a claim requires --confirm-source-reviewed after opening the PDF")
    with closing(open_audit_db(database)) as db:
        row, profile = load_profile(db, file)
        candidates = [e for e in profile["evidence"] if e["evidence_id"] == evidence_id]
        if len(candidates) != 1:
            raise ValueError("Evidence ID does not uniquely match current paper profile")
        e = candidates[0]
        current_page = db.execute(
            """SELECT text FROM pdf_text_pages WHERE root=? AND relpath=? AND page_num=?""",
            (row["root"], row["relpath"], e["page"])
        ).fetchone()
        info = assessment(e, current_page[0] if current_page else None)
        if decision == "approved" and not info["quote_found_on_original_indexed_page"]:
            raise ValueError("Cannot approve: source quote is not found on its PDF page")
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with db:
            db.execute(
                """INSERT OR REPLACE INTO profile_evidence_reviews
                (root,relpath,pdf_sha256,profile_version,model,evidence_id,
                 decision,reviewer_note,reviewed_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (row["root"], row["relpath"], row["pdf_sha256"], row["version"],
                 row["model"], evidence_id, decision, note.strip(), stamp)
            )
        return {"file": row["relpath"], "evidence_id": evidence_id,
                "decision": decision, "reviewed_at": stamp,
                "note": "Human annotation stored locally; no model profile overwritten."}

def model_packet(database, file, limit=18, radius=360):
    """Local *source* excerpts around formal propositions/assumptions, never invented math."""
    if not 1 <= limit <= 100:
        raise ValueError("--limit must be 1-100")
    with closing(open_audit_db(database)) as db:
        row, profile = load_profile(db, file)
        cards = audits(db, row, profile)
        selected = [a for a in cards if a["kind"] in FORMAL
                    or (a["kind"] == "mechanism" and a["priority"] >= 5)]
        selected.sort(key=lambda a: (a["pdf_page"], a["kind"], a["evidence_id"]))
        selected = selected[:limit]
        pages = source_pages(db, row)
        for card in selected:
            card["source_context"] = context_for(
                pages.get(card["pdf_page"], ""), card["verified_quote"], radius=radius
            )
    return {
        "paper": profile["title"], "file": profile["file"],
        "pdf_sha256": row["pdf_sha256"], "model": row["model"],
        "candidate_source_cards": selected,
        "review_fields": {
            key: "NOT YET VERIFIED AGAINST ORIGINAL TYPESET PDF"
            for key in (
                "players_and_objectives", "states_and_timing", "actions_and_offers",
                "information_and_beliefs", "payoff_functions", "transition_probabilities",
                "equilibrium_concept", "propositions_and_conditions",
                "comparative_statics", "scope_and_counterexamples"
            )
        },
        "note": ("This is an evidence packet for reconstructing the model, "
                 "NOT a mathematical reconstruction. Formulae, diagrams and tables "
                 "must be inspected in the typeset original."),
    }

def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline profile QC; no API calls")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit", help="Risk-prioritized local evidence review queue")
    audit.add_argument("--file", required=True)
    audit.add_argument("--limit", type=int, default=15)
    audit.add_argument("--include-reviewed", action="store_true")
    audit.add_argument("--stratified", action="store_true",
                       help="Deterministic sample across claim types instead of only high risk")
    model = sub.add_parser("model-packet", help="Source-page packet for math review")
    model.add_argument("--file", required=True)
    model.add_argument("--limit", type=int, default=18)
    human = sub.add_parser("mark", help="Human review of an evidence item")
    human.add_argument("--file", required=True)
    human.add_argument("--evidence-id", required=True)
    human.add_argument("--decision", choices=DECISIONS, required=True)
    human.add_argument("--note", default="")
    human.add_argument("--confirm-source-reviewed", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            result = report(args.db, args.file, args.limit,
                            not args.include_reviewed, args.stratified)
        elif args.command == "model-packet":
            result = model_packet(args.db, args.file, args.limit)
        else:
            result = mark(args.db, args.file, args.evidence_id,
                          args.decision, args.note, args.confirm_source_reviewed)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, sqlite3.Error, KeyError) as exc:
        print("Profile audit failed safely: " + str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())

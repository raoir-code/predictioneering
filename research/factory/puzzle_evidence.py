"""Offline bridge: Puzzle Finder cards -> diverse, page-linked literature evidence.

Does not call models, prove novelty, or automatically approve a puzzle. Source
quotes remain in local private database; optional output stays in ignored inbox.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

from .__main__ import HOME, load, save, timestamp
from .pdf_text import DEFAULT_DB
from .theory_catalog import search, terms


def diversified(hits, *, limit=12, max_per_paper=3):
    """Round-robin over ranked sources, retaining each paper's best hits."""
    if not 1 <= limit <= 100 or not 1 <= max_per_paper <= 20:
        raise ValueError("limit must be 1-100; max_per_paper must be 1-20")
    grouped = defaultdict(list)
    seen = set()
    for item in hits:
        key = (item["file"], item["pdf_sha256"], item["evidence_id"])
        if key in seen:
            continue
        seen.add(key)
        grouped[(item["file"], item["pdf_sha256"])].append(item)
    for group in grouped.values():
        group.sort(key=lambda h: (-h["score"], h["pdf_page"], h["evidence_id"]))
    papers = sorted(grouped, key=lambda p: (-grouped[p][0]["score"], p[0]))
    selected = []
    for ix in range(max_per_paper):
        for paper in papers:
            if ix < len(grouped[paper]) and len(selected) < limit:
                selected.append(grouped[paper][ix])
        if len(selected) >= limit:
            break
    return selected


def assemble(database=DEFAULT_DB, *, home=HOME, puzzle_id=None,
             spec_path=None, queries=None, limit=12, max_per_paper=3,
             approved_only=False):
    if puzzle_id and spec_path:
        raise ValueError("Choose a puzzle ID or a research spec, not both")
    subject = None
    source = None
    if puzzle_id:
        if not re.fullmatch(r"[a-f0-9]{16}", puzzle_id):
            raise ValueError("Puzzle ID must contain 16 lowercase hex characters")
        path = Path(home) / "projects" / (puzzle_id + ".json")
        source = load(path)
        if source.get("id") != puzzle_id:
            raise ValueError("Puzzle file ID does not match request")
        subject = {
            "puzzle_id": puzzle_id, "title": source.get("title"),
            "status": source.get("status"),
            "human_approved": source.get("status") == "approved_for_literature_review",
        }
        if not queries:
            queries = [source.get("title", ""), source.get("candidate_mechanism", "")]
    elif spec_path:
        source = load(Path(spec_path))
        subject = {
            "spec_id": source.get("id"),
            "research_question": source.get("research_question"),
            "human_approved": False,
        }
        if not queries:
            queries = source.get("search_queries") or [source.get("research_question", "")]
    if not queries:
        raise ValueError("Supply --query, --puzzle, or --spec")
    if isinstance(queries, str):
        queries = [queries]
    queries = [q.strip() for q in queries if isinstance(q, str) and terms(q)]
    queries = list(dict.fromkeys(queries))[:4]
    if not queries:
        raise ValueError("No substantive search terms in supplied queries")
    if not 1 <= limit <= 100 or not 1 <= max_per_paper <= 20:
        raise ValueError("limit must be 1-100; max_per_paper must be 1-20")
    merged = {}
    stats = []
    for query in queries:
        result = search(database, query, limit=100, approved_only=approved_only)
        stats.append({
            "query": query, "retrieved_candidate_matches": result["evidence_hits"],
            "profiles_matching": result["profiles_matching"],
        })
        for hit in result["results"]:
            key = (hit["file"], hit["pdf_sha256"], hit["evidence_id"])
            if key in merged:
                merged[key]["matched_queries"].append(query)
                merged[key]["score"] = max(merged[key]["score"], hit["score"])
            else:
                merged[key] = dict(hit, matched_queries=[query])
    citations = diversified(list(merged.values()), limit=limit,
                            max_per_paper=max_per_paper)
    return {
        "status": "offline_candidate_literature_evidence",
        "subject": subject or {"type": "ad_hoc_search", "human_approved": False},
        "queries": stats,
        "total_unique_candidates_in_retrieved_pool": len(merged),
        "distinct_papers_in_retrieved_pool": len(set(h["file"] for h in merged.values())),
        "papers_in_selected": len(set(h["file"] for h in citations)),
        "max_per_paper": max_per_paper,
        "selected_evidence": citations,
        "novelty_verified": False,
        "scientific_verdict": "not_verified",
        "next_gate": (
            "Inspect the most relevant complete original articles and "
            "approve evidence/novelty before claiming a publishable gap."
        ),
        "note": (
            "Source diversity enforced. Results cover ONLY already-profiled local "
            "PDFs; metadata-only and unprofiled literature are not searched. "
            "Quotes are matched, not interpretations or proof. Approved-only "
            "filters to explicit human review decisions."
        ),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Offline puzzle -> diverse PDF evidence bridge")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--home", type=Path, default=HOME)
    select = p.add_mutually_exclusive_group()
    select.add_argument("--puzzle", help="16-character ID from research.factory list")
    select.add_argument("--spec", type=Path, help="Literature project JSON specification")
    p.add_argument("--query", action="append", help="Up to 4 search queries; repeatable")
    p.add_argument("--limit", type=int, default=12)
    p.add_argument("--max-per-paper", type=int, default=3)
    p.add_argument("--approved-only", action="store_true")
    p.add_argument("--save", action="store_true",
                   help="Save private result in research/inbox/records")
    args = p.parse_args(argv)
    try:
        output = assemble(args.db, home=args.home, puzzle_id=args.puzzle,
                          spec_path=args.spec, queries=args.query, limit=args.limit,
                          max_per_paper=args.max_per_paper,
                          approved_only=args.approved_only)
        if args.save:
            scope = json.dumps(
                {"subject": output["subject"], "queries": output["queries"],
                 "model_review": args.approved_only}, sort_keys=True
            )
            digest = hashlib.sha256(scope.encode()).hexdigest()[:16]
            dest = args.home / "inbox" / "records" / ("puzzle_evidence_" + digest + ".json")
            save(dest, dict(output, saved_at=timestamp()))
            output["saved_private_record"] = str(dest)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError,
            json.JSONDecodeError) as exc:
        print("Puzzle evidence bridge failed safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

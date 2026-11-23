"""Claude-assisted, human-reviewed formal derivation DRAFTS, not a theorem prover.

Requires an approved scientific architecture and an offline formal work order.
Never signs/produces the formal_model stage, hypotheses or publication claims.
Every API call requires explicit evidence-share consent and a budget guard.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import urllib.error
import urllib.request

from . import formal_workbench as wb
from . import theory_fabricator as theory
from . import review_workflow as gates

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "formal_derivation_draft_v1"
FIELDS = (
    "setup", "bellman_equations", "candidate_equilibrium",
    "parameter_domains", "offpath_deviation_checks",
    "constant_power_recovery", "holiday_power_results",
    "falsification_checks",
)
SYSTEM = """You are a rigorous formal IR theorist. Draft a mathematical
derivation, NOT a certified proof. A previously human-approved blueprint
defines the game: do not silently add players, move types, commitment,
war costs, audience costs, private information, or a new calendar mechanism.
Distinguish verified algebra in the supplied benchmark from conjectures.
Derive best-response and Bellman conditions carefully. Attempt an exact
characterization of the finite deterministic holiday cycle where possible.
If unable, state the missing mathematical step and propose a counterexample
or finite-state numerical falsification test. Show off-path incentives.
Do not claim novelty, general theorems or publication readiness without proof.
Produce a COMPACT first-pass mathematical draft, not a comprehensive treatise.
Target <= 3500 output tokens total, hard ceiling 4500; this is an OUTPUT
COMPLETENESS constraint. Keep each of the eight string sections to at most
180 words; use 3-5 proof steps, each at most 100 words; list 2-6 gaps.
Derive the critical Bellman conditions and at least one falsifiable
conditional result. State unsolved regions as UNSOLVED rather than enumerating
all 16 policy cases in prose. Longer details belong in later focused revisions.
Return exactly ONE COMPLETE JSON object, no Markdown fences or remarks, no
preface or appendix. Finish the object with a closing brace.
Fields: schema=formal_derivation_draft_v1; setup, bellman_equations,
candidate_equilibrium, parameter_domains, offpath_deviation_checks,
constant_power_recovery, holiday_power_results, falsification_checks
are concise strings; proof_steps is a list of {claim,argument,domain} objects;
unresolved_gaps is a nonempty list of strings. Never invent citations."""


class ClaudeDraftError(ValueError):
    def __init__(self, message, *, raw, usage=None, model=None):
        super().__init__(message)
        self.raw = raw
        self.usage = usage or {}
        self.model = model


def directory(home, project):
    return wb.outdir(home, project) / "derivations"


def validate(candidate):
    if not isinstance(candidate, dict) or candidate.get("schema") != SCHEMA:
        raise ValueError("Expected formal_derivation_draft_v1 JSON object")
    clean = {key: candidate[key] for key in FIELDS if key in candidate}
    if len(clean) != len(FIELDS):
        raise ValueError("Claude formal draft lacks required game/proof sections")
    for key, value in clean.items():
        theory.reasonable("derivation." + key, value, minimum=25, maximum=20000)
    steps = candidate.get("proof_steps")
    if not isinstance(steps, list) or not 2 <= len(steps) <= 30:
        raise ValueError("Formal draft needs 2–30 explicit, falsifiable proof steps")
    clean["proof_steps"] = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError("Every formal proof step must be an object")
        clean["proof_steps"].append({
            key: theory.reasonable("proof_steps." + key, step.get(key),
                                   minimum=10, maximum=5000)
            for key in ("claim", "argument", "domain")
        })
    gaps = candidate.get("unresolved_gaps")
    if not isinstance(gaps, list) or not gaps:
        raise ValueError("Formal draft must explicitly acknowledge unresolved proof gaps")
    clean["unresolved_gaps"] = [
        theory.reasonable("unresolved mathematical question", x,
                          minimum=8, maximum=1500)
        for x in gaps
    ]
    clean["schema"] = SCHEMA
    clean["status"] = "CLAUDE_DERIVATION_UNVERIFIED_REQUIRES_PROOF_AUDIT"
    clean["mathematically_certified"] = False
    clean["general_equilibrium_proven"] = False
    clean["novelty_verified"] = False
    return clean


def source_bundle(home, project, *, feedback=None):
    blueprint, signed = wb.approved_blueprint(home, project)
    work_order = wb.outdir(home, project) / "MODEL_CONTRACT.json"
    baseline = wb.outdir(home, project) / "CONSTANT_POWER_BENCHMARK.json"
    if not work_order.is_file() or not baseline.is_file():
        raise ValueError("Run formal_workbench prepare PROJECT before requesting a proof draft")
    contract = json.loads(work_order.read_text(encoding="utf-8"))
    if contract.get("approved_blueprint_sha256") != signed["blueprint_sha256"]:
        raise ValueError("Formal work order is stale; cannot draft against old game")
    benchmark = json.loads(baseline.read_text(encoding="utf-8"))
    # Send only the scientific specification; never model claims of human proof
    # or the whole cumulative revision chain as a prompt.
    keys = ("schema", "baseline", "innovation", "mechanism",
            "proof_plan", "source_caveats")
    bundle = {
        "blueprint_sha256": signed["blueprint_sha256"],
        "blueprint": {key: blueprint[key] for key in keys if key in blueprint},
        "contract": contract,
        "symbolic_constant_power_benchmark": benchmark,
        "warning": "Blueprint approval is architecture-only. "
                   "Numerical examples and benchmark identities do not prove the holiday model.",
    }
    if feedback is not None:
        previous = directory(home, project) / "PROOF_DRAFT.json"
        if not previous.is_file():
            raise ValueError("Cannot revise formal derivation before drafting one")
        prior = json.loads(previous.read_text(encoding="utf-8"))
        if prior.get("approved_blueprint_sha256") != signed["blueprint_sha256"]:
            raise ValueError("Existing derivation is for a different approved blueprint")
        bundle["researcher_feedback"] = theory.reasonable(
            "formal revision feedback", feedback, minimum=20, maximum=5000)
        bundle["previous_proof_sha256"] = gates.file_sha(previous)
        bundle["previous_unverified_candidate"] = {
            key: prior[key] for key in (*FIELDS, "proof_steps", "unresolved_gaps")
            if key in prior
        }
    return bundle


def anthropic_transport(bundle, model, key, max_tokens):
    prompt = ("Produce a concise and complete 8-section JSON DRAFT as specified. "
              "Aim for 2500–3500 output tokens TOTAL; you are not expected to "
              "solve every holiday-game parameter region in one call. "
              "Give mathematically checkable derivations and label unproved "
              "results unresolved, not established. "
              "Use the approved game; do not modify its timing or mechanism. "
              "Only mathematically establish results you can derive and check; "
              "otherwise label them conjectures. "
              "Input specification, with benchmark, source limitations and "
              "optional researcher revision instructions:\n" +
              json.dumps(bundle, ensure_ascii=False))
    body = json.dumps({
        "model": model, "max_tokens": max_tokens, "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}]
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("Anthropic returned HTTP " + str(exc.code)) from exc
    raw = "\n".join(item.get("text", "") for item in answer.get("content", [])
                    if item.get("type") == "text").strip()
    if answer.get("stop_reason") == "max_tokens":
        raise ClaudeDraftError(
            "Claude formal draft was cut off at the output-token cap",
            raw=raw, usage=answer.get("usage", {}), model=answer.get("model"))
    if raw.startswith("```"):
        raw = raw.partition("\n")[2].rsplit("```", 1)[0].strip()
    try:
        candidate, pos = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError as exc:
        raise ClaudeDraftError(
            "Claude formal draft was not parseable JSON: " + exc.msg,
            raw=raw, usage=answer.get("usage", {}), model=answer.get("model")) from exc
    extra = raw[pos:].strip()
    if extra.startswith("{") or extra.startswith("["):
        raise ClaudeDraftError(
            "Claude returned multiple JSON documents; choose neither automatically",
            raw=raw, usage=answer.get("usage", {}), model=answer.get("model"))
    return candidate, answer.get("usage", {}), answer.get("model"), extra


def draft(home, project, *, candidate_file=None, feedback=None,
          share=False, model=None, key=None,
          input_rate=None, output_rate=None, max_usd=None,
          max_tokens=12000, transport=anthropic_transport):
    bundle = source_bundle(home, project, feedback=feedback)
    root = directory(home, project)
    if candidate_file is None:
        if not share:
            raise ValueError("Explicit --confirm-share-evidence required before paid Claude call")
        if not model or not key:
            raise ValueError("Provide model and ANTHROPIC_API_KEY")
        for field, amount in (("input-rate", input_rate),
                              ("output-rate", output_rate),
                              ("max-usd", max_usd)):
            if type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0:
                raise ValueError("Provide a positive, finite " + field)
        if not 512 <= max_tokens <= 20000:
            raise ValueError("Output token cap must be between 512 and 20000")
        estimate = (
            2*len(json.dumps(bundle, ensure_ascii=False).encode("utf-8")) * input_rate
            + max_tokens * output_rate
        )/1_000_000
        if estimate > max_usd:
            raise ValueError("Conservative API estimate exceeds --max-usd; "
                             "lower max tokens or change explicitly approved budget")
    root.mkdir(parents=True, exist_ok=True)
    if candidate_file is None:
        try:
            payload, usage, actual_model, trailing = transport(
                bundle, model, key, max_tokens)
        except ClaudeDraftError as exc:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            saved = root / "attempts" / ("CLAUDE_FORMAL_PARTIAL_" + stamp + ".txt")
            theory.write(saved, exc.raw)
            theory.write(saved.with_suffix(".diagnostic.json"), {
                "error": str(exc), "model": exc.model or model,
                "approved_blueprint_sha256": bundle["blueprint_sha256"],
                "previous_proof_sha256": bundle.get("previous_proof_sha256"),
                "feedback": bundle.get("researcher_feedback"),
                "usage": exc.usage,
                "status": "REJECTED_UNREVIEWED",
            })
            raise ValueError(str(exc) + "; saved original response to " + str(saved) +
                             "; previous draft unchanged") from exc
        origin = "claude_api"
        cost = (int(usage.get("input_tokens", 0))*input_rate+
                int(usage.get("output_tokens", 0))*output_rate)/1_000_000
        original = root / "attempts" / ("CLAUDE_FORMAL_" +
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        theory.write(original, payload)
    else:
        payload = json.loads(Path(candidate_file).read_text(encoding="utf-8"))
        actual_model, trailing, cost, origin = None, "", 0.0, "offline_candidate"
        original = Path(candidate_file)
    try:
        checked = validate(payload)
    except ValueError as exc:
        raise ValueError("Claude formal draft failed structural checks: " + str(exc) +
                         ". Original response retained at " + str(original) +
                         ". No proof approval or stage transition.") from exc
    previous = root / "PROOF_DRAFT.json"
    if feedback is not None:
        if gates.file_sha(previous) != bundle["previous_proof_sha256"]:
            raise ValueError("Formal draft changed during generation; refuse to overwrite")
    if previous.is_file():
        archive = root / "history" / gates.file_sha(previous)[:16]
        archive.mkdir(parents=True, exist_ok=True)
        for name in ("PROOF_DRAFT.json", "PROOF_REVIEW.md"):
            old = root / name
            if old.is_file() and not (archive / name).exists():
                shutil.copyfile(old, archive / name)
    checked["approved_blueprint_sha256"] = bundle["blueprint_sha256"]
    checked["generation"] = {
        "origin": origin, "model": actual_model,
        "estimated_charge_usd": round(cost, 6),
        "parent_draft_sha256": bundle.get("previous_proof_sha256"),
        "researcher_feedback": bundle.get("researcher_feedback"),
        "discarded_trailing_text": trailing[:8000],
        "original_response": str(original),
    }
    theory.write(previous, checked)
    text = [
        "# Formal Model worker — mathematical draft awaiting proof audit",
        "",
        "**Status:** UNVERIFIED candidate. No global equilibrium, source novelty, "
        "or hypotheses are approved.",
        "",
        "**Blueprint:** " + bundle["blueprint_sha256"],
        "**Claude:** " + str(actual_model or origin),
        "**Estimated cost:** $" + str(round(cost, 6)),
    ]
    if feedback:
        text.extend(["", "## Requested changes", "", feedback])
    for heading, field in (
        ("Game assumptions", "setup"),
        ("Bellman system", "bellman_equations"),
        ("Candidate equilibrium", "candidate_equilibrium"),
        ("Parameter regions", "parameter_domains"),
        ("Off-path and deviations", "offpath_deviation_checks"),
        ("Constant-power benchmark", "constant_power_recovery"),
        ("Holiday effects (unverified)", "holiday_power_results"),
        ("Falsification checks", "falsification_checks"),
    ):
        text.extend(["", "## " + heading, "", checked[field]])
    text.extend(["", "## Proof steps — all require independent audit", ""])
    for i, step in enumerate(checked["proof_steps"], 1):
        text.extend([
            str(i) + ". **Claim:** " + step["claim"],
            "   Argument: " + step["argument"],
            "   Domain: " + step["domain"],
        ])
    text.extend(["", "## Unresolved mathematical and evidentiary gaps", ""])
    text.extend("- " + item for item in checked["unresolved_gaps"])
    text.extend(["", "**Human decision:** revise the derivation or submit it for "
                      "independent mathematical verification. This tool can never "
                      "approve a proof or submit formal_model.", ""])
    theory.write(root / "PROOF_REVIEW.md", "\n".join(text))
    return {
        "status": "UNVERIFIED_FORMAL_DRAFT_REQUIRES_HUMAN_PROOF_AUDIT",
        "review": str(root / "PROOF_REVIEW.md"),
        "path": str(previous),
        "approved_blueprint_sha256": bundle["blueprint_sha256"],
        "estimated_charge_usd": round(cost, 6),
        "network_or_paid_api_calls": int(candidate_file is None),
        "formal_model_submitted": False,
    }


def recover(home, project, *, source=None):
    """Safely replay a COMPLETE JSON draft from saved cut-off API response.

    Rejects incomplete/ambiguous outputs without a paid call or changing
    an earlier draft. Maintains exact signed-blueprint and parent-draft pins.
    """
    bundle = source_bundle(home, project)
    base = directory(home, project)
    attempts = base / "attempts"
    if source is None:
        paths = sorted(attempts.glob("CLAUDE_FORMAL_PARTIAL_*.txt"))
        if not paths:
            raise ValueError("No saved partial Claude formal response exists")
        path = paths[-1]
    else:
        path = Path(source).expanduser().resolve()
        if (path.parent != attempts.resolve() or not
                path.name.startswith("CLAUDE_FORMAL_PARTIAL_") or
                path.suffix != ".txt"):
            raise ValueError("Recovery source must be CLAUDE_FORMAL_PARTIAL_*.txt "
                             "inside this project's saved attempts directory")
    if not path.is_file() or path.stat().st_size > 400_000:
        raise ValueError("Saved formal response is missing or too large")
    diagnostic = path.with_suffix(".diagnostic.json")
    if not diagnostic.is_file():
        raise ValueError("Cannot recover an attempt with no saved diagnostic")
    meta = json.loads(diagnostic.read_text(encoding="utf-8"))
    if meta.get("status") != "REJECTED_UNREVIEWED":
        raise ValueError("This saved attempt is not an unreviewed rejected response")
    if meta.get("approved_blueprint_sha256") != bundle["blueprint_sha256"]:
        raise ValueError("Claude attempt was generated for a different approved blueprint")
    existing = base / "PROOF_DRAFT.json"
    parent = meta.get("previous_proof_sha256")
    if parent is None and existing.exists():
        raise ValueError("A formal draft now exists; cannot overwrite with an older "
                         "first-draft response. Archive/review history first.")
    if parent is not None and (not existing.exists() or
                                gates.file_sha(existing) != parent):
        raise ValueError("Formal derivation parent SHA differs from the failed revision")
    raw = path.read_text(encoding="utf-8").strip()
    parsed = raw
    if parsed.startswith("```"):
        parsed = parsed.partition("\n")[2]
    try:
        payload, end = json.JSONDecoder().raw_decode(parsed.lstrip())
    except json.JSONDecodeError as exc:
        raise ValueError("Saved partial is incomplete JSON (" + exc.msg +
                         "); cannot safely recover. Use a new concise draft; "
                         "this check made zero paid calls.") from exc
    extra = parsed.lstrip()[end:].strip()
    if extra.startswith("```"):
        extra = extra[3:].strip()
    if extra.startswith(("{", "[")):
        raise ValueError("Saved partial contains multiple JSON structures, "
                         "so recovery cannot select one automatically")
    checked = validate(payload)
    saved_candidate = path.with_name("RECOVERED_" + path.stem + ".json")
    if not saved_candidate.exists():
        theory.write(saved_candidate, checked)
    result = draft(
        home, project, candidate_file=saved_candidate,
        feedback=meta.get("feedback"))
    current = base / "PROOF_DRAFT.json"
    normalized = json.loads(current.read_text(encoding="utf-8"))
    normalized["generation"].update({
        "origin": "recovered_saved_claude_response",
        "model": meta.get("model"),
        "original_response": str(path),
        "original_usage": meta.get("usage"),
        "discarded_trailing_text": extra[:8000],
        "warning": "The original truncated API call may have incurred a charge; "
                   "offline recovery incurred zero additional API charges.",
    })
    theory.write(current, normalized)
    result["status"] = "RECOVERED_UNVERIFIED_FORMAL_DRAFT"
    result["network_or_paid_api_calls"] = 0
    result["original_response"] = str(path)
    return result


def review(home, project, *, share, model, key, input_rate, output_rate,
           max_usd, max_tokens=12000, ask=input, output=print,
           transport=anthropic_transport):
    root = directory(home, project)
    file = root / "PROOF_DRAFT.json"
    if not file.is_file():
        raise ValueError("No formal proof candidate yet; run draft first")
    for _ in range(50):
        current = json.loads(file.read_text(encoding="utf-8"))
        output("\nHere's Claude's unverified mathematical draft:")
        output("Claim: " + " ".join(current["candidate_equilibrium"].split())[:350])
        output("Gaps: " + "; ".join(current["unresolved_gaps"])[:400])
        output("Full review: " + str(root / "PROOF_REVIEW.md"))
        output("What should I change? Type feedback, SHOW, or QUIT. "
               "APPROVE cannot certify a mathematical proof.")
        try:
            answer = ask("> ").strip()
        except EOFError:
            return {"status": "UNVERIFIED_DRAFT_AWAITING_PROOF_AUDIT"}
        if answer.upper() in ("QUIT", "EXIT", ""):
            return {"status": "UNVERIFIED_DRAFT_AWAITING_PROOF_AUDIT"}
        if answer.upper() == "SHOW":
            output((root / "PROOF_REVIEW.md").read_text(encoding="utf-8"))
            continue
        if answer.upper() in ("APPROVE", "GOOD", "NEXT"):
            output("A Claude draft cannot be certified by this command. "
                   "Independent algebra/equilibrium and scholarly review is required.")
            continue
        if answer.startswith("@"):
            answer = Path(answer[1:]).expanduser().read_text(encoding="utf-8")
        result = draft(
            home, project, feedback=answer, share=share, model=model, key=key,
            input_rate=input_rate, output_rate=output_rate,
            max_usd=max_usd, max_tokens=max_tokens, transport=transport)
        output("Revised unverified proof candidate; estimated $" +
               str(result["estimated_charge_usd"]) + ".")
    return {"status": "SESSION_LIMIT_REACHED_UNVERIFIED"}


def main(argv=None):
    p = argparse.ArgumentParser(description="Claude proof drafts, NEVER automatic scientific proof approval")
    p.add_argument("--home", type=Path, default=ROOT)
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("draft", "revise", "review"):
        d = sub.add_parser(command)
        d.add_argument("project")
        d.add_argument("--confirm-share-evidence", action="store_true")
        d.add_argument("--model", default=os.getenv("CLAUDE_MODEL"))
        d.add_argument("--input-rate", type=float)
        d.add_argument("--output-rate", type=float)
        d.add_argument("--max-usd", type=float)
        d.add_argument("--max-tokens", type=int, default=12000)
        if command == "draft":
            d.add_argument("--candidate", type=Path)
        if command == "revise":
            d.add_argument("--feedback-file", type=Path, required=True)
    recovery = sub.add_parser("recover", help="Try offline replay of a complete saved cut-off Claude draft")
    recovery.add_argument("project")
    recovery.add_argument("--from-file", type=Path)
    args = p.parse_args(argv)
    try:
        if args.command == "recover":
            print(json.dumps(recover(args.home, args.project,
                                     source=args.from_file), indent=2))
            return 0
        opts = {
            "share": args.confirm_share_evidence, "model": args.model,
            "key": os.getenv("ANTHROPIC_API_KEY"),
            "input_rate": args.input_rate, "output_rate": args.output_rate,
            "max_usd": args.max_usd, "max_tokens": args.max_tokens,
        }
        if args.command == "review":
            result = review(args.home, args.project, **opts)
        elif args.command == "revise":
            result = draft(args.home, args.project,
                           feedback=args.feedback_file.read_text(encoding="utf-8"),
                           **opts)
        else:
            result = draft(args.home, args.project, candidate_file=args.candidate, **opts)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print("Formal reasoner stopped safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

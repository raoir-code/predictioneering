"""Prepare a focused, source-pinned human proof-review request from the numeric audit.

No Claude call, theorem certification, formal_model submission, or silent
approval. Use the generated feedback with formal_reasoner review via @path.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import formal_workbench as wb
from . import formal_solver as solver
from . import review_workflow as gates
from . import theory_fabricator as theory

ROOT = Path(__file__).resolve().parents[1]


def prepare(home, project):
    _, signature = wb.approved_blueprint(home, project)
    sha = signature["blueprint_sha256"]
    base = wb.outdir(home, project)
    proof_path = base / "derivations" / "PROOF_DRAFT.json"
    audit_path = base / "FORMAL_SOLVER_AUDIT.json"
    if not proof_path.is_file() or not audit_path.is_file():
        raise ValueError("Need both the saved unverified Claude draft and the "
                         "completed offline solver audit first")
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    proof_sha = gates.file_sha(proof_path)
    if (proof.get("approved_blueprint_sha256") != sha or
            audit.get("approved_blueprint_sha256") != sha or
            audit.get("unverified_proof_draft_sha256") != proof_sha):
        raise ValueError("Signed blueprint, mathematical draft or solver audit "
                         "changed; rerun formal_solver audit before preparing feedback")
    if audit.get("status") not in (solver.STATUS_OK, solver.STATUS_FAIL):
        raise ValueError("No recognizable completed offline numeric audit")

    sample = audit.get("known_multiple_example", {})
    example = sample.get("parameters", {})
    result = sample.get("result", {})
    cycle = example.get("calendar_cycle", [])
    masks = result.get("pure_mpe_masks", [])
    if not cycle or not masks or result.get("contradiction_count", 1):
        raise ValueError("Known multiple-equilibrium numerical example is incomplete "
                         "or inconsistent; inspect the audit before requesting a proof")
    selection = solver.selection_bounds(cycle, masks)
    params = ", ".join(
        name + "=" + str(example.get(name)) for name in
        ("p0", "d_A", "d_B", "delta", "c_A", "c_B"))
    request = (
        "Focused MATHEMATICAL PROOF AUDIT, not approval or a new game. "
        "Preserve the human-approved bilateral-attack, one-period-offer "
        "bargaining blueprint and its payoffs/tie breaks. "
        "Review the prior UNVERIFIED derivation. The offline solver "
        "enumerated " + str(audit.get("total_policy_masks_enumerated")) +
        " short-cycle policy patterns in " +
        str(audit.get("total_synthetic_cases")) + " synthetic cases: " +
        str(audit.get("contradiction_cases")) + " numerical contradictions, " +
        str(audit.get("multiple_pure_mpe_cases")) + " multiple-equilibrium "
        "cases and " + str(audit.get("no_pure_mpe_cases")) +
        " no-pure cases. These are TESTS, NOT PROOFS.\n\n"
        "Tasks, in priority order:\n"
        "1. Prove or refute the necessary-and-sufficient war-set fixed-point "
        "Theorem 1 for every finite deterministic cycle, N>=1, allowing repeated "
        "states. Explicitly check B's minimal acceptance threshold, offers "
        "x=0 and x=1, ties, off-path B attacks, feasible A preemption and "
        "the s_k next-war-lag definition in BOTH peaceful and war phases. "
        "Provide equations for the one-shot deviations.\n"
        "2. Audit the small-power-variation unique-peace Proposition 3, "
        "constant-power uniqueness, and patient-player result. Supply "
        "rigorous bounds and flag any unjustified inequality or limit.\n"
        "3. Try to PROVE pure phase-Markov MPE existence for every admissible "
        "finite calendar; alternatively give an explicit admissible "
        "counterexample. Zero failures in random tests does not prove "
        "existence. If unresolved, mark UNSOLVED.\n"
        "4. Analyze equilibrium-selection uncertainty without inventing "
        "a selection rule: an example with " + params + " on phases " +
        " -> ".join(cycle) + " has candidate war masks " + str(masks) +
        ". From phase 0, possible onset lags are " +
        str(selection["first_phase_possible_war_lags"]) +
        " (never means perpetual peace). Explain exactly which holiday/war "
        "timing predictions hold ACROSS ALL pure MPE and which cannot be "
        "inferred without selection; give set-valued predictions when needed.\n"
        "5. Distinguish A-driven from B-driven war, and correct any "
        "overstatement that B-driven war must be on an A-holiday: the "
        "necessary condition is a fall in B's next-period power, which "
        "might also occur before a B-holiday. Distinguish on-path first "
        "war from irrelevant later war phases after absorption.\n"
        "End with an exact list of proved statements, counterexamples, "
        "conditional/set-valued empirical predictions and UNRESOLVED gaps. "
        "Avoid claims of source novelty, global uniqueness, certified proof, "
        "or publishability. Do not edit source data or sign formal_model."
    )
    if len(request) > 4500:
        raise ValueError("Focused feedback unexpectedly exceeds safe model input")
    feedback = base / "FORMAL_PROOF_FEEDBACK.txt"
    theory.write(feedback, request + "\n")
    metadata = {
        "status": "TARGETED_HUMAN_REVIEW_FEEDBACK_PREPARED_NOT_PROOF",
        "approved_blueprint_sha256": sha,
        "unverified_proof_draft_sha256": proof_sha,
        "numeric_audit_sha256": gates.file_sha(audit_path),
        "input": str(audit_path),
        "feedback": str(feedback),
        "illustrative_first_phase_selection": selection,
        "network_or_paid_api_calls": 0,
        "formal_model_submitted": False,
    }
    theory.write(base / "FORMAL_PROOF_FEEDBACK_META.json", metadata)
    return {
        "status": metadata["status"],
        "feedback": str(feedback),
        "example_first_phase_possible_onset_lags": selection[
            "first_phase_possible_war_lags"],
        "next_step": "In formal_reasoner review, enter @" + str(feedback),
        "network_or_paid_api_calls": 0,
        "formal_model_submitted": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Prepare targeted human mathematical proof audit from private solver evidence")
    p.add_argument("project")
    p.add_argument("--home", type=Path, default=ROOT)
    args = p.parse_args(argv)
    try:
        result = prepare(args.home, args.project)
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print("Proof-review brief stopped safely: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

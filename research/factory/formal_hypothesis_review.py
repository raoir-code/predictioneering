"""Prepare researcher-facing hypothesis screening from a pinned war-set model.

Necessary conditions for war do not imply a signed marginal effect on observed
incidence. This creates no predictions, approvals, external calls or payments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import finite_war_set_handoff as handoff
from . import formal_solver
from . import formal_workbench as wb
from . import theory_fabricator as theory
from . import review_workflow as gates

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "war_set_hypothesis_review_v1"


def prepare(home, project):
    base = wb.outdir(home, project)
    candidate = base / "FORMAL_MODEL_HANDOFF_CANDIDATE.json"
    if not candidate.is_file():
        raise ValueError("No unsigned formal-model candidate; run finite_war_set_handoff first")
    model = json.loads(candidate.read_text(encoding="utf-8"))
    if model.get("schema") != handoff.SCHEMA:
        raise ValueError("The formal model is not a finite war-set handoff")
    evidence = handoff.source_check(home, project, model)
    sample = evidence.get("known_multiple_example", {})
    parameters = sample.get("parameters", {})
    result = sample.get("result", {})
    masks = result.get("pure_mpe_masks", [])
    cycle = parameters.get("calendar_cycle", [])
    if (not cycle or 0 not in masks or not any(mask != 0 for mask in masks)
            or result.get("contradiction_count") != 0):
        raise ValueError("Saved multiple-equilibrium example is unavailable or inconsistent")
    selection = formal_solver.selection_bounds(cycle, masks)
    restrictions = [
        {
            "id": "R1",
            "type": "selection_invariant_structural_restriction",
            "claim": "If war-win probability is constant across phases (D=0) and costs are positive, the only pure phase-Markov equilibrium is perpetual peace.",
            "scientific_status": "Claim argued in the unverified proof; checked numerically, not independently certified",
            "data_obstacle": "A holiday indicator is not D. Test requires power variation across phases and an explicit model of background conflict causes.",
        },
        {
            "id": "R2",
            "type": "selection_invariant_sufficient_condition",
            "claim": "The revised bound D < min{(1-delta)^2*c_A/delta, (1-delta)*(1-p_max)/delta} is sufficient for unique all-peace pure MPE.",
            "scientific_status": "Sufficient, not necessary; tested numerically but not independently certified",
            "data_obstacle": "Requires war-win probabilities, discounting and costs. Failure of the bound does not imply war.",
        },
        {
            "id": "R3",
            "type": "necessary_condition_conditional_on_war_type",
            "claim": "At an A-driven war phase, a higher B win probability must occur at some later phase before the next prescribed war.",
            "scientific_status": "Necessary condition only, no unconditional effect sign",
            "data_obstacle": "Observed initiator identity need not reveal A-driven incentives; future power is not captured by a holiday dummy.",
        },
        {
            "id": "R4",
            "type": "necessary_condition_conditional_on_war_type",
            "claim": "B-driven war requires B's next-phase war-win probability to fall; this need not occur on A's holiday.",
            "scientific_status": "Necessary condition only, not an increased incidence prediction",
            "data_obstacle": "Requires observation or credible estimation of future military power and responder incentives.",
        },
        {
            "id": "R5",
            "type": "equilibrium_selection_dependent_example",
            "claim": "In the saved four-phase parameter example, an initial ordinary phase admits war at the next A-holiday phase or perpetual peace.",
            "scientific_status": "Exact example only; no distribution of equilibrium choices supplied",
            "data_obstacle": "Does not imply a positive average holiday-war association in observed historical dyads.",
        },
    ]
    blockers = [
        "No unconditional signed marginal effect on historical war incidence follows without further structure or selection assumptions",
        "General pure-MPE existence remains unsolved, and multiple equilibria are possible",
        "A model war set does not specify probabilities of equilibrium selection or of observed onset",
        "Historical holiday calendars must be reconciled for both countries, including overlap, timing and year-specific holidays",
        "A directed day-level interstate onset risk panel must be constructed and independently validated",
        "MID or other source files must be checked for date granularity and actor-direction coding before committing to the outcome",
        "Prespecify how confounding, holidays correlated with seasonality, and military power proxies will be handled",
    ]
    summary = {
        "schema": SCHEMA,
        "status": "RESEARCHER_REVIEW_REQUIRED_NO_EMPIRICAL_HYPOTHESIS_APPROVED",
        "formal_model_candidate_sha256": gates.file_sha(candidate),
        "signed_blueprint_sha256": model["source_pins"]["blueprint_sha256"],
        "proof_draft_sha256": model["source_pins"]["proof_draft_sha256"],
        "numeric_audit_sha256": model["source_pins"]["numeric_audit_sha256"],
        "numeric_contradictions": evidence["contradiction_cases"],
        "numeric_multiple_equilibria": evidence["multiple_pure_mpe_cases"],
        "illustrative_onset_lags_from_phase_zero": selection["first_phase_possible_war_lags"],
        "logical_restrictions_for_review": restrictions,
        "signed_empirical_hypotheses": 0,
        "signed_average_holiday_war_effect": None,
        "scientific_blockers": blockers,
        "requires_researcher": [
            "Independently audit the theorem and conditions as applied to this game",
            "Specify a measurable estimand grounded in a mathematically valid implication",
            "Supply hypothesis direction and mapping only when defensible; preserve conditional scope",
            "Keep formal-model submission and separate human signoff explicit",
        ],
        "automatic_approvals": False,
        "network_or_paid_api_calls": 0,
    }
    out_json = base / "HYPOTHESIS_REVIEW.json"
    out_md = base / "HYPOTHESIS_REVIEW.md"
    theory.write(out_json, summary)
    lines = [
        "# Holy Days: theory-to-empirics hypothesis screening", "",
        "Status: human scientific review required. No empirical hypothesis is approved.", "",
        "The game supplies logical restrictions and conditional war sets, not an",
        "unconditional sign for the average historical effect of holidays on onset.",
        "A regression coefficient cannot be inferred from multiplicity alone.", "",
        "## Restrictions to review", "",
    ]
    for row in restrictions:
        lines += [
            "### " + row["id"] + ": " + row["type"].replace("_", " "), "",
            row["claim"], "",
            "Status: " + row["scientific_status"], "",
            "Measurement obstacle: " + row["data_obstacle"], "",
        ]
    lines += [
        "## Equilibrium-selection illustration", "",
        "Pure war-set masks: " + str(masks) +
        "; possible onset lags from phase zero: " +
        str(selection["first_phase_possible_war_lags"]) + ".", "",
        "These alternatives do not define an observable war frequency.", "",
        "## Unresolved empirical requirements", "",
    ]
    lines.extend("- " + x for x in blockers)
    lines += [
        "", "## Next gate", "",
        "Do not populate hypotheses with a positive holiday coefficient just",
        "to satisfy the current single-treatment adapter. First choose an",
        "observable estimand grounded in a valid restriction and specify",
        "the equilibrium selection assumptions (if any).", "",
        "The separate formal-model candidate remains unsigned and incomplete.",
        "No model submission, approval, data retrieval or billable call occurred.", "",
    ]
    theory.write(out_md, "\n".join(lines))
    return {
        "status": summary["status"],
        "review": str(out_md),
        "json": str(out_json),
        "logical_restrictions": len(restrictions),
        "signed_empirical_hypotheses": 0,
        "formal_model_submitted": False,
        "network_or_paid_api_calls": 0,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Source-pinned, no-API theory-to-empirics review")
    p.add_argument("project")
    p.add_argument("--home", type=Path, default=ROOT)
    args = p.parse_args(argv)
    try:
        result = prepare(args.home, args.project)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("Hypothesis review stopped safely: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

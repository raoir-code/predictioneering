"""Offline falsification harness for the unverified Holy Days Markov equilibrium draft.

Enumerates every pure war/peace mask for short deterministic calendars,
including repeated holiday states. Compares the candidate's analytical
fixed-point prediction with the independent, direct Bellman/deviation
calculator in formal_workbench. This is a NUMERICAL audit, not proof,
equilibrium selection, an empirical calendar or permission to publish.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
import sys

from . import formal_workbench as wb
from . import review_workflow as gates
from . import theory_fabricator as theory

ROOT = Path(__file__).resolve().parents[1]
STATUS_OK = "NUMERICAL_CROSSCHECK_PASSED_NOT_MATHEMATICAL_PROOF"
STATUS_FAIL = "CLAUDE_EQUILIBRIUM_CLAIM_CONTRADICTED_REQUIRES_REVIEW"
CASE_LIMIT = 2000
DEFAULT_MAX_PHASES = 8
TOL = 1e-7


def theorem_predicate(values, cycle, p, mask, *, tol=TOL):
    """Independently calculate the draft's war-set fixed-point test.

    Do NOT use the workbench's candidate evaluation or incentive residuals
    to calculate this prediction. The two implementations are compared below.
    """
    n = len(cycle)
    d = values["delta"]
    cost = values["c_A"] + values["c_B"]
    w = [p[h] / (1.0 - d) - values["c_B"] for h in cycle]
    war = [bool(mask & (1 << i)) for i in range(n)]
    vb = []
    for k in range(n):
        if war[k]:
            vb.append(w[k])
        elif any(war):
            steps = next(j for j in range(1, n + 1) if war[(k + j) % n])
            vb.append(max(d**j * w[(k+j) % n] for j in range(steps + 1)))
        else:
            vb.append(max(0.0, max(d**j*w[(k+j) % n] for j in range(n))))
    minima = [max(0.0, w[k]-d*vb[(k+1) % n]) for k in range(n)]
    checks = []
    for k in range(n):
        steps = (next(j for j in range(1, n+1) if war[(k+j) % n])
                 if any(war) else math.inf)
        discount = d**steps if math.isfinite(steps) else 0.0
        phi = max(w[k], d*vb[(k+1) % n])
        # Candidate counterfactual: buy peace now, follow policy from k+1.
        advantage = (1.0-discount)*cost - (phi-w[k])
        feasible = minima[k] <= 1 + tol
        # A chooses peace on ties. Exclude near-indifferent war candidates.
        peace_preferred = feasible and advantage >= -tol
        if war[k]:
            policy_ok = not peace_preferred
        else:
            policy_ok = peace_preferred
        checks.append({
            "phase_index": k,
            "war": war[k],
            "next_war_lag": steps if math.isfinite(steps) else None,
            "minimum_offer": minima[k],
            "counterfactual_peace_advantage_A": advantage,
            "B_driven_if_war": bool(war[k] and not feasible),
            "A_driven_if_war": bool(war[k] and feasible and advantage < -tol),
            "policy_ok": policy_ok,
        })
    return {
        "equilibrium_by_draft_fixed_point": all(c["policy_ok"] for c in checks),
        "B_values": vb,
        "phases": checks,
    }


def selection_bounds(cycle, equilibrium_masks):
    """Set-valued onset timing across *all enumerated pure* MPEs.

    No equilibrium selection, probabilities or empirical forecast is inferred.
    A mask encodes WAR in that phase; war is absorbing, so only the first
    phase encountered on a path is an observable onset.
    """
    n = len(cycle)
    if n == 0:
        raise ValueError("Selection analysis requires a nonempty calendar")
    if not equilibrium_masks:
        return {
            "classification_from_first_phase": "NO_PURE_EQUILIBRIUM_FOUND",
            "first_phase_possible_war_lags": [],
            "first_phase_invariant": False,
            "per_start_phase": [],
        }
    by_phase = []
    for k, h in enumerate(cycle):
        lags = set()
        for mask in equilibrium_masks:
            onset = next((lag for lag in range(n)
                          if mask & (1 << ((k + lag) % n))), None)
            lags.add(onset)
        ordered = sorted(lag for lag in lags if lag is not None)
        if None in lags:
            ordered.append("never")
        if lags == {None}:
            classification = "PEACE_IN_ALL_PURE_EQUILIBRIA"
        elif len(lags) == 1:
            classification = "SAME_WAR_TIMING_IN_ALL_PURE_EQUILIBRIA"
        elif None in lags:
            classification = "PEACE_OR_WAR_DEPENDS_ON_EQUILIBRIUM_SELECTION"
        else:
            classification = "WAR_OCCURS_BUT_TIMING_DEPENDS_ON_EQUILIBRIUM_SELECTION"
        by_phase.append({
            "phase_index": k,
            "state": h,
            "possible_first_war_lags": ordered,
            "classification": classification,
            "selection_invariant": len(lags) == 1,
        })
    first = by_phase[0]
    return {
        "classification_from_first_phase": first["classification"],
        "first_phase_possible_war_lags": first["possible_first_war_lags"],
        "first_phase_invariant": first["selection_invariant"],
        "per_start_phase": by_phase,
    }


def audit_case(case, sha, *, tol=TOL):
    values, cycle, probs = wb.validate_case(case, sha)
    n = len(cycle)
    d = values["delta"]
    p_by_phase = [probs[h] for h in cycle]
    issues = []
    valid_masks = []
    masks_checked = 0
    boundaries = 0
    for mask in range(1 << n):
        predicted = theorem_predicate(values, cycle, probs, mask, tol=tol)
        direct = wb.policy_candidate(values, cycle, probs, mask, tol=tol)
        masks_checked += 1
        actual = direct["passes_numeric_sequential_rationality"]
        expected = predicted["equilibrium_by_draft_fixed_point"]
        if expected != actual:
            issues.append({
                "type": "fixed_point_disagreement",
                "war_mask": mask,
                "theorem": expected, "direct_best_responses": actual,
                "residual": direct["max_best_response_or_Bellman_residual"],
            })
        for k, row in enumerate(direct["calendar_policy"]):
            if abs(predicted["B_values"][k] - row["value_B"]) > 10*tol:
                issues.append({
                    "type": "Bellman_value_B_disagreement",
                    "war_mask": mask, "phase": k,
                })
            phase = predicted["phases"][k]
            if (abs(phase["minimum_offer"] -
                    row["minimal_acceptable_offer_to_B"]) > 10*tol):
                issues.append({"type": "offer_disagreement", "war_mask": mask,
                               "phase": k})
            if (abs(phase["counterfactual_peace_advantage_A"]) < tol or
                    abs(phase["minimum_offer"] - 1.0) < tol):
                boundaries += 1
        if actual:
            valid_masks.append(mask)
            for phase in predicted["phases"]:
                k = phase["phase_index"]
                if phase["B_driven_if_war"] and not p_by_phase[k] > p_by_phase[(k+1)%n]:
                    issues.append({
                        "type": "B_driven_necessary_condition_fails",
                        "war_mask": mask, "phase": k,
                    })
                if phase["A_driven_if_war"]:
                    lag = phase["next_war_lag"]
                    if lag is None or not any(
                            p_by_phase[(k+j) % n] > p_by_phase[k]
                            for j in range(1, lag+1)):
                        issues.append({
                            "type": "A_driven_necessary_condition_fails",
                            "war_mask": mask, "phase": k,
                        })
    # Draft Proposition 3: sufficient small-amplitude uniqueness.
    amplitude = max(p_by_phase) - min(p_by_phase)
    sufficient = amplitude < min(
        (1-d)**2 * values["c_A"],
        (1-d) * (1-max(p_by_phase)) / d)
    if sufficient and valid_masks != [0]:
        issues.append({"type": "small_amplitude_unique_peace_claim_fails",
                       "valid_masks": valid_masks})
    # Test the separate all-peace C1/C2 characterization, without
    # constructing validity from the same workbench predicate.
    w = [x/(1-d)-values["c_B"] for x in p_by_phase]
    b = theorem_predicate(values, cycle, probs, 0, tol=tol)
    c1 = all(phase["minimum_offer"] <= 1+tol for phase in b["phases"])
    c2 = all(
        max((d**j*w[(k+j)%n]-w[k] for j in range(1, n)),
            default=-math.inf) <= values["c_A"]+values["c_B"]+tol
        for k in range(n))
    if (0 in valid_masks) != (c1 and c2):
        issues.append({"type": "all_peace_C1_C2_disagreement"})
    return {
        "calendar_cycle": list(cycle),
        "parameters": values,
        "masks_checked": masks_checked,
        "pure_mpe_masks": valid_masks,
        "pure_mpe_count": len(valid_masks),
        "equilibrium_selection_bounds": selection_bounds(cycle, valid_masks),
        "A_peace_tie_boundary_checks": boundaries,
        "proposition_3_bound_holds": sufficient,
        "contradictions": issues[:20],
        "contradiction_count": len(issues),
    }


def sample_case(rng, sha, max_phases):
    p0 = rng.uniform(0.1, 0.9)
    n = rng.randint(1, max_phases)
    # Frequent repeated states; not an empirical calendar.
    cycle = [rng.choice(wb.STATES) for _ in range(n)]
    # Sample both small-effect and large-effect regimes.
    effect_scale = rng.choice((0.005, 0.05, 0.3, 0.85))
    return {
        "schema": wb.CASE_SCHEMA, "blueprint_sha256": sha,
        "delta": rng.choice((0.2, 0.5, 0.75, 0.9, 0.98, 0.995)),
        "p0": p0,
        "d_A": rng.uniform(0.0, effect_scale * p0),
        "d_B": rng.uniform(0.0, effect_scale * (1-p0)),
        "c_A": math.exp(rng.uniform(math.log(0.01), math.log(2.0))),
        "c_B": math.exp(rng.uniform(math.log(0.01), math.log(2.0))),
        "calendar_cycle": cycle,
        "status": "SYNTHETIC_FALSIFICATION_CASE_NO_EMPIRICAL_CONTENT",
    }


def audit(home, project, *, cases=400, seed=20261123, max_phases=8,
          case_path=None):
    _, approved = wb.approved_blueprint(home, project)
    sha = approved["blueprint_sha256"]
    if not 1 <= cases <= CASE_LIMIT:
        raise ValueError("Random synthetic case count must be between 1 and " +
                         str(CASE_LIMIT))
    if not 1 <= max_phases <= min(wb.MAX_EXHAUSTIVE_PHASES, 10):
        raise ValueError("Audit max phases must be 1–10 to bound enumeration cost")
    draft = wb.outdir(home, project) / "derivations" / "PROOF_DRAFT.json"
    proof_sha = None
    if draft.is_file():
        data = json.loads(draft.read_text(encoding="utf-8"))
        if data.get("approved_blueprint_sha256") != sha:
            raise ValueError("Draft and signed blueprint differ; cannot audit stale model")
        proof_sha = gates.file_sha(draft)
    rng = random.Random(seed)
    inputs = []
    if case_path is not None:
        inputs.append(json.loads(Path(case_path).read_text(encoding="utf-8")))
    # Reproduce Claude's worked example, a known multiple-equilibrium case,
    # and a constant-power benchmark even if no random cases hit them.
    for p0, da, db, d, ca, cb in (
            (0.5, 0.1, 0.1, 0.9, 0.5, 0.5),
            (0.4, 0.2, 0.1, 0.7, 0.1, 0.3),
            (0.5, 0.0, 0.0, 0.9, 0.2, 0.3)):
        inputs.append({
            "schema": wb.CASE_SCHEMA, "blueprint_sha256": sha,
            "p0": p0, "d_A": da, "d_B": db, "delta": d,
            "c_A": ca, "c_B": cb,
            "calendar_cycle": list(wb.STATES),
        })
    inputs.extend(sample_case(rng, sha, max_phases) for _ in range(cases))
    total_masks = 0
    contradictions = []
    no_pure = []
    multiple = []
    pure = []
    proposition_3 = 0
    ties = 0
    first_phase_selection_ambiguous = 0
    for idx, case in enumerate(inputs):
        result = audit_case(case, sha)
        total_masks += result["masks_checked"]
        ties += result["A_peace_tie_boundary_checks"]
        proposition_3 += int(result["proposition_3_bound_holds"])
        if result["contradictions"]:
            contradictions.append({"case_index": idx, **result})
        count = result["pure_mpe_count"]
        if count and not result["equilibrium_selection_bounds"]["first_phase_invariant"]:
            first_phase_selection_ambiguous += 1
        if count == 0:
            no_pure.append({"case_index": idx, "case": case})
        elif count == 1:
            pure.append(idx)
        else:
            multiple.append({"case_index": idx, "case": case,
                             "war_masks": result["pure_mpe_masks"]})
    status = STATUS_FAIL if contradictions else STATUS_OK
    payload = {
        "status": status,
        "scientific_classification": "UNVERIFIED_NUMERIC_FALSIFICATION_ONLY",
        "approved_blueprint_sha256": sha,
        "unverified_proof_draft_sha256": proof_sha,
        "seed": seed, "random_case_count": cases,
        "total_synthetic_cases": len(inputs),
        "total_policy_masks_enumerated": total_masks,
        "unique_pure_mpe_cases": len(pure),
        "multiple_pure_mpe_cases": len(multiple),
        "first_phase_outcome_or_timing_ambiguous_cases": first_phase_selection_ambiguous,
        "no_pure_mpe_cases": len(no_pure),
        "first_phase_outcome_or_timing_ambiguous_cases": first_phase_selection_ambiguous,
        "proposition_3_bound_cases": proposition_3,
        "near_tie_policy_checks": ties,
        "contradiction_cases": len(contradictions),
        "contradiction_examples": contradictions[:3],
        "multiple_equilibrium_examples": multiple[:3],
        "no_pure_examples": no_pure[:3],
        "known_hand_example": {
            "parameters": inputs[0],
            "result": audit_case(inputs[0], sha),
            "expected_pure_mpe_masks": [7],
        },
        "known_multiple_example": {
            "parameters": inputs[1],
            "result": audit_case(inputs[1], sha),
            "expected_pure_mpe_masks": [0, 6],
        },
        "constraints": [
            "Only phase-indexed pure Markov strategies; mixed and non-Markov equilibria excluded",
            "No theorem proved even if no contradictions found",
            "Finite deterministic cycles with at most 12 phases (random max <= 10)",
            "Theoretical fixed point and direct Bellman checks share the declared game",
            "No annual-scale calendar, data harmonization, equilibrium selection, or causal claim",
            "Human review required; no formal_model submission or automatic approval",
        ],
        "network_or_paid_api_calls": 0,
    }
    dest = wb.outdir(home, project)
    dest.mkdir(parents=True, exist_ok=True)
    report = dest / "FORMAL_SOLVER_AUDIT.json"
    theory.write(report, payload)
    review = dest / "FORMAL_SOLVER_AUDIT.md"
    lines = [
        "# Holy Days: numerical falsification audit (NOT a proof)",
        "",
        "**Status:** " + status,
        "**Approved architecture:** " + sha,
        "**Unverified draft SHA:** " + str(proof_sha),
        "**Reproducible RNG seed:** " + str(seed),
        "**Synthetic parameter/calendar cases:** " + str(len(inputs)),
        "**Pure policy masks independently compared:** " + str(total_masks),
        "**Cases with exactly one pure MPE:** " + str(len(pure)),
        "**Cases with multiple pure MPE:** " + str(len(multiple)),
        "**Cases whose onset timing depends on pure-equilibrium selection (starting at phase 0):** " + str(first_phase_selection_ambiguous),
        "**Cases with no pure MPE:** " + str(len(no_pure)),
        "**Theorem contradictions detected:** " + str(len(contradictions)),
        "**Near-tie phase checks (conservative):** " + str(ties),
        "",
        "## Worked example from Claude",
        "Expected war mask 7 (ordinary, A_holiday, B_holiday); computed masks: " +
        str(payload["known_hand_example"]["result"]["pure_mpe_masks"]),
        "",
        "## Multiple-equilibrium illustration",
        "Expected masks 0 and 6; computed masks: " +
        str(payload["known_multiple_example"]["result"]["pure_mpe_masks"]),
        "Here mask 0 = peace in all phases, and 6 = war in A_holiday and B_holiday.",
        "",
        "## Contradictions / unresolved scientific work",
    ]
    if contradictions:
        lines.append("At least one candidate failed a fixed-point, Bellman, or necessary-condition test. Examine JSON examples before revising.")
    else:
        lines.append("No contradiction found in the sampled finite parameter cases; this does NOT prove the propositions.")
    if no_pure:
        lines.append("Numerical no-pure cases occurred; inspect JSON for mixed-equilibrium follow-up.")
    lines += ["", "## Limits", ""]
    lines.extend("- " + x for x in payload["constraints"])
    theory.write(review, "\n".join(lines) + "\n")
    return {
        "status": status,
        "report": str(report), "review": str(review),
        "total_synthetic_cases": len(inputs),
        "total_policy_masks_enumerated": total_masks,
        "multiple_pure_mpe_cases": len(multiple),
        "no_pure_mpe_cases": len(no_pure),
        "contradiction_cases": len(contradictions),
        "blueprint_sha256": sha,
        "network_or_paid_api_calls": 0,
        "formal_model_submitted": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Offline numerical falsification of an UNVERIFIED bargaining proof")
    p.add_argument("--home", type=Path, default=ROOT)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("audit")
    a.add_argument("project")
    a.add_argument("--cases", type=int, default=400)
    a.add_argument("--seed", type=int, default=20261123)
    a.add_argument("--max-phases", type=int, default=DEFAULT_MAX_PHASES)
    a.add_argument("--case", type=Path)
    args = p.parse_args(argv)
    try:
        result = audit(args.home, args.project, cases=args.cases,
                       seed=args.seed, max_phases=args.max_phases,
                       case_path=args.case)
        print(json.dumps(result, indent=2))
        return 0 if result["contradiction_cases"] == 0 else 2
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print("Formal solver audit stopped safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

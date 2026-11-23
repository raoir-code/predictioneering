"""Signed-blueprint, offline numerical workbench for Holy Days repeated bargaining.

This is NOT a general analytical solver and NOT a theorem prover. It enumerates
pure stationary Markov policy candidates for an explicitly supplied, finite
deterministic calendar at specified parameters. Numerical equilibrium checks
are conditional, not a proof of global existence, uniqueness or comparative
statics. No API calls, automatic approvals, or formal_model submissions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

from . import theory_fabricator as theory
from . import review_workflow as gates

ROOT = Path(__file__).resolve().parents[1]
STATES = ("ordinary", "A_holiday", "B_holiday", "both_holiday")
CONTRACT_SCHEMA = "holy_days_formal_contract_v1"
CASE_SCHEMA = "holiday_bargaining_numeric_case_v1"
STATUS = "NUMERICAL_PURE_MARKOV_CANDIDATES_ONLY_NO_GENERAL_PROOF"


def outdir(home, project):
    return theory.folder(home, project).parent / "formal_workbench"


def approved_blueprint(home, project):
    """Require an exact signed architecture and unchanged approved source pins."""
    home = Path(home).expanduser().resolve()
    dest = theory.folder(home, project)
    draft = dest / "THEORY_BLUEPRINT.json"
    signature = dest / "BLUEPRINT_APPROVAL.json"
    if not draft.is_file() or not signature.is_file():
        raise ValueError("First review and APPROVE the theory blueprint; cannot run formal diagnostics")
    current = json.loads(draft.read_text(encoding="utf-8"))
    signature_data = json.loads(signature.read_text(encoding="utf-8"))
    theory.validate(current)
    if signature_data.get("blueprint_sha256") != gates.file_sha(draft):
        raise ValueError("Approval signature does not match the current blueprint")
    pins = theory.source_pins(theory.source_inputs(home, project))
    if signature_data.get("upstream") != pins or current.get("upstream") != pins:
        raise ValueError("Approved puzzle/literature changed; blueprint is stale")
    # Explicit adapter contract: we only know how to solve this one conventional
    # fixed-proposer game. A new blueprint needs a separately audited adapter.
    innovation = current["innovation"]
    if set(innovation["state_values"]) != set(STATES) or len(innovation["state_values"]) != 4:
        raise ValueError("This adapter requires the four specified holiday calendar values")
    rules = current["baseline"]["canonical_rules"].lower()
    if ("attack" not in rules or "accept" not in rules or
            "there is no reject action" not in rules or
            "one-period agreement" not in rules):
        raise ValueError("Blueprint's game protocol differs from this adapter: "
                         "requires bilateral Attack/Accept and one-period settlements "
                         "without a Reject action. Review or write a new solver adapter.")
    return current, signature_data


def constant_power_benchmark_proof():
    """Symbolically verify a stationary peaceful equilibrium for constant p.

    This is a theorem about one particular stationary equilibrium in the
    single-state benchmark, NOT proof of unique/all equilibria or holiday game.
    """
    import sympy as sp
    p, d, ca, cb = sp.symbols("p delta c_A c_B", positive=True)
    x_binding = p-(1-d)*cb
    war_b = p/(1-d)-cb
    war_a = (1-p)/(1-d)-ca
    b_gap = sp.simplify(x_binding/(1-d)-war_b)
    a_gap_binding = sp.simplify((1-x_binding)/(1-d)-war_a)
    a_gap_zero = sp.simplify(1/(1-d)-war_a)
    expected_a_gap_binding = ca+cb
    expected_a_gap_zero = p/(1-d)+ca
    if (b_gap != 0 or
            sp.simplify(a_gap_binding-expected_a_gap_binding) != 0 or
            sp.simplify(a_gap_zero-expected_a_gap_zero) != 0):
        raise ValueError("Symbolic baseline incentive identities failed")
    return {
        "status": "CONSTANT_POWER_STATIONARY_MPE_EXISTENCE_BENCHMARK_ONLY",
        "domain": "0<p<1, 0<delta<1, c_A>0, c_B>0; p constant",
        "candidate_offer": "x*=max(0,p-(1-delta)*c_B)",
        "offpath_B_response": "Accept iff x+delta*x*/(1-delta) >= p/(1-delta)-c_B",
        "A_offer": "A proposes x*, the smallest nonnegative share accepted by B",
        "B_incentive_gap_if_binding": str(b_gap),
        "A_peace_minus_war_if_binding": str(a_gap_binding),
        "A_peace_minus_war_if_zero_offer": str(a_gap_zero),
        "reasoning": [
            "For x*>0, B's stationary continuation x*/(1-delta) "
            "equals war payoff; B accepts at equality.",
            "For x*=0, p/(1-delta)-c_B <= 0 and B accepts a zero offer.",
            "On either branch A strictly prefers the smallest feasible "
            "accepted offer to attacking; B's off-path attack is sequentially rational.",
            "The stationary policy therefore forms a peaceful Markov-perfect "
            "equilibrium for constant power and stated tie-breaking.",
        ],
        "holiday_equilibrium_proven": False,
        "other_SPE_classified": False,
    }


def numerical_case_template(blueprint_sha):
    return {
        "schema": CASE_SCHEMA,
        "status": "USER_MUST_SPECIFY_PARAMETERS_AND_CALENDAR",
        "blueprint_sha256": blueprint_sha,
        "delta": None,
        "p0": None,
        "d_A": None,
        "d_B": None,
        "c_A": None,
        "c_B": None,
        "calendar_cycle": [],
        "caveat": "Choose illustrative or empirically justified values. A cycle is "
                  "a hypothetical exogenous transition, not an empirical holiday calendar.",
    }


def prepare(home, project):
    blueprint, signed = approved_blueprint(home, project)
    dest = outdir(home, project)
    dest.mkdir(parents=True, exist_ok=True)
    sha = signed["blueprint_sha256"]
    # Preserve an earlier parameter template instead of overwriting researcher edits.
    template = dest / "PARAMETER_CASE_TEMPLATE.json"
    if template.exists():
        old = json.loads(template.read_text(encoding="utf-8"))
        if old.get("blueprint_sha256") != sha:
            raise ValueError("Parameter template is pinned to an older architecture. "
                             "Archive it manually before creating a new one.")
    else:
        theory.write(template, numerical_case_template(sha))
    contract = {
        "schema": CONTRACT_SCHEMA,
        "project": project,
        "approved_blueprint_sha256": sha,
        "mechanics": {
            "peaceful_state": "Each period A chooses Attack or one-period offer x in [0,1]",
            "responder": "B chooses Accept or Attack after offer",
            "settlement": "Accept gives (1-x,x) this period, both retain war next period",
            "war": "Absorbing lottery determined by current p(h); costs c_A,c_B",
            "proposer": "A, fixed across all states",
            "state": "Public, exogenous, deterministic cycle specified by researcher",
            "payoffs": "W_B(h)=p(h)/(1-delta)-c_B; W_A(h)=(1-p(h))/(1-delta)-c_A",
            "B_acceptance": "x+delta*V_B(next)>=W_B(h)",
            "A_preference": "max{W_A(h), 1-x+delta*V_A(next)}",
            "tie_break": "Accept for B, peace for A",
        },
        "source": "Researcher-approved architecture; this contract is a conditional numerical adapter.",
        "equilibrium_proven": False,
        "novelty_verified": False,
        "supported_case": "Finite deterministic cycle, all four states exactly once, "
                          "homogeneous discount, war no initiator advantage",
        "not_supported": [
            "general symbolic parameter regions",
            "non-Markov SPE and punishment paths",
            "stochastic/Markov holiday transitions",
            "mixed strategy equilibria",
            "uniqueness and global comparative statics",
            "actual holiday date calendar or interstate empirical data",
        ],
    }
    theory.write(dest / "MODEL_CONTRACT.json", contract)
    review = (
        "# Formal Model Workbench — architecture to proof\n\n"
        "**Signed blueprint:** " + sha + "\n\n"
        "**Scientific status:** No analytical equilibrium has been proved.\n\n"
        "## The chosen game\n\n"
        "Each period A may attack or offer B share x in [0,1]. B may accept "
        "the ONE-PERIOD allocation or attack. Acceptance resumes bargaining "
        "next period; neither actor commits to lasting peace. War is absorbing, "
        "with its lottery fixed by the current holiday state.\n\n"
        "## Exact one-period incentive inequalities\n\n"
        "W_B(h)=p(h)/(1-delta)-c_B and W_A(h)=(1-p(h))/(1-delta)-c_A. "
        "Let S_i(h)=V_i(next(h)). B accepts iff "
        "x+delta*S_B(h) >= W_B(h); A can buy peace at minimal "
        "m(h)=max(0,W_B(h)-delta*S_B(h)) when m(h)<=1. "
        "A then compares 1-m(h)+delta*S_A(h) against W_A(h). "
        "These statements describe sequential best replies **conditional on "
        "candidate continuation values**, not a solved fixed point.\n\n"
        "## Proof obligations still open\n\n"
        "Find all equilibrium continuation values and feasible policies across "
        "the FULL admissible parameter domain; verify every deviation and "
        "off-path strategy, prove limiting behavior as d_A,d_B->0, study "
        "non-Markov SPE and timing/initiator ambiguities, and audit prior "
        "literature. The numerical checker only studies specified examples.\n\n"
        "## Researcher inputs\n\n"
        "The calendar ordering is NOT in the blueprint. Fill "
        "`PARAMETER_CASE_TEMPLATE.json` with an explicit calendar cycle and "
        "all six numeric parameters, then run `formal_workbench check`. "
        "Alternatively `demo` uses stated synthetic values for a smoke test.\n"
    )
    theory.write(dest / "FORMAL_WORK_ORDER.md", review)
    baseline = constant_power_benchmark_proof()
    theory.write(dest / "CONSTANT_POWER_BENCHMARK.json", baseline)
    theory.write(dest / "CONSTANT_POWER_BENCHMARK.md",
                 "# Stationary constant-power benchmark\n\n"
                 "This is a **restricted benchmark theorem**, NOT the solution "
                 "to the holiday game.\n\n"
                 "Assume " + baseline["domain"] + ". The stationary minimal "
                 "acceptable offer is `" + baseline["candidate_offer"] + "`.\n\n"
                 "B's acceptance incentive gap when the constraint binds: "
                 "`" + baseline["B_incentive_gap_if_binding"] + "`. "
                 "A's peace-minus-war gap is `" +
                 baseline["A_peace_minus_war_if_binding"] +
                 "` when B's war constraint binds, or `" +
                 baseline["A_peace_minus_war_if_zero_offer"] +
                 "` when the optimal share is zero. "
                 "Both A gaps are positive under the declared domain.\n\n"
                 "This proves the existence of a peaceful **stationary "
                 "Markov** equilibrium in the constant-power benchmark, "
                 "assuming the stated tie-breaking. It does NOT prove global "
                 "uniqueness, all SPE, or results with shifting holiday power.\n")
    return {
        "status": "FORMAL_WORK_ORDER_PREPARED_NOT_SOLVED",
        "contract": str(dest / "MODEL_CONTRACT.json"),
        "review": str(dest / "FORMAL_WORK_ORDER.md"),
        "constant_power_benchmark": str(dest / "CONSTANT_POWER_BENCHMARK.md"),
        "parameter_template": str(template),
        "blueprint_sha256": sha,
        "network_or_paid_api_calls": 0,
    }


def validate_case(case, required_sha):
    if not isinstance(case, dict) or case.get("schema") != CASE_SCHEMA:
        raise ValueError("Expected explicit holiday_bargaining_numeric_case_v1 JSON")
    if case.get("blueprint_sha256") != required_sha:
        raise ValueError("Numeric case is pinned to a different approved blueprint SHA")
    keys = ("delta", "p0", "d_A", "d_B", "c_A", "c_B")
    values = {}
    for key in keys:
        x = case.get(key)
        if type(x) not in (int, float) or not math.isfinite(x):
            raise ValueError("Specify finite numeric " + key + " explicitly")
        values[key] = float(x)
    delta, p0, d_a, d_b, c_a, c_b = (values[key] for key in keys)
    if not (0 < delta < 1):
        raise ValueError("delta must lie strictly between 0 and 1")
    if not (d_a >= 0 and d_b >= 0 and c_a > 0 and c_b > 0):
        raise ValueError("d_A and d_B must be nonnegative (zero recovers the "
                         "benchmark); c_A and c_B must be strictly positive")
    p = {
        "ordinary": p0,
        "A_holiday": p0 + d_b,
        "B_holiday": p0 - d_a,
        "both_holiday": p0,
    }
    if not all(0 < val < 1 for val in p.values()):
        raise ValueError("All state-dependent war probabilities must lie in (0,1)")
    cycle = case.get("calendar_cycle")
    if not isinstance(cycle, list) or len(cycle) != len(STATES) or set(cycle) != set(STATES):
        raise ValueError("Specify each holiday state exactly once in the ordered deterministic cycle")
    if not all(isinstance(item, str) for item in cycle):
        raise ValueError("Calendar states must be strings")
    return values, cycle, p


def policy_candidate(values, cycle, probabilities, war_mask, *, tol=1e-9):
    """Exactly evaluate one declared pure stationary Markov war/peace policy.

    This solves value equations under that policy and checks unilateral
    deviations. It does not establish an all-parameter-domain theorem.
    """
    n = len(cycle)
    delta = values["delta"]
    w_b = [probabilities[h] / (1-delta)-values["c_B"] for h in cycle]
    w_a = [(1-probabilities[h])/(1-delta)-values["c_A"] for h in cycle]
    war = [bool(war_mask & (1 << i)) for i in range(n)]
    vb = []
    for i in range(n):
        if war[i]:
            vb.append(w_b[i])
            continue
        if any(war):
            future_war = next(k for k in range(1, n+1) if war[(i+k) % n])
            vb.append(max((delta**k)*w_b[(i+k) % n]
                          for k in range(future_war+1)))
        else:
            # In a fully peaceful deterministic cycle B can defer war
            # forever for zero flow. Repeating a positive war prospect after
            # a complete cycle cannot improve its discounted value.
            vb.append(max(0.0, *(delta**k*w_b[(i+k) % n] for k in range(n))))
    minima = [max(0.0, w_b[i]-delta*vb[(i+1) % n]) for i in range(n)]
    x = [None if war[i] else minima[i] for i in range(n)]
    va = []
    for i in range(n):
        if war[i]:
            va.append(w_a[i])
        elif any(war):
            future_war = next(k for k in range(1, n+1) if war[(i+k) % n])
            value = sum(delta**k*(1-minima[(i+k) % n])
                        for k in range(future_war))
            value += delta**future_war*w_a[(i+future_war) % n]
            va.append(value)
        else:
            value = sum(delta**k*(1-minima[(i+k) % n])
                        for k in range(n))
            va.append(value / (1-delta**n))
    rows = []
    max_gap = 0.0
    for i, h in enumerate(cycle):
        following = (i+1) % n
        peaceful_payoff = (
            1-minima[i]+delta*va[following]
            if minima[i] <= 1+tol else None
        )
        if war[i]:
            deviation_gain = (
                max(0.0, peaceful_payoff-w_a[i])
                if peaceful_payoff is not None else 0.0
            )
            bellman_a = abs(va[i]-w_a[i])
            bellman_b = abs(vb[i]-w_b[i])
        else:
            deviation_gain = max(0.0, w_a[i]-va[i], minima[i]-1)
            bellman_a = abs(va[i] - (1-minima[i]+delta*va[following]))
            bellman_b = abs(vb[i] - max(w_b[i], delta*vb[following]))
        max_gap = max(max_gap, deviation_gain, bellman_a, bellman_b)
        rows.append({
            "state": h, "policy": "WAR" if war[i] else "PEACE",
            "war_probability_B": probabilities[h],
            "war_value_A": w_a[i], "war_value_B": w_b[i],
            "value_A": va[i], "value_B": vb[i],
            "minimal_acceptable_offer_to_B": minima[i],
            "offer_if_peace": x[i],
            "A_deviation_gain": deviation_gain,
            "Bellman_residual_A": bellman_a,
            "Bellman_residual_B": bellman_b,
        })
    return {
        "war_mask": war_mask,
        "calendar_policy": rows,
        "max_best_response_or_Bellman_residual": max_gap,
        "passes_numeric_sequential_rationality": max_gap <= tol,
    }


def analyze(case, sha):
    values, cycle, probabilities = validate_case(case, sha)
    candidates = [
        policy_candidate(values, cycle, probabilities, mask)
        for mask in range(1 << len(cycle))
    ]
    verified = [item for item in candidates if item["passes_numeric_sequential_rationality"]]
    return {
        "schema": "holiday_bargaining_numeric_diagnostic_v1",
        "status": STATUS,
        "equilibrium_proven": False,
        "general_parameter_regions_proven": False,
        "global_uniqueness_proven": False,
        "empirical_hypotheses_derived": False,
        "blueprint_sha256": sha,
        "case": case,
        "checked_pure_stationary_policies": len(candidates),
        "valid_numeric_pure_markov_candidates": len(verified),
        "candidates": verified,
        "all_policy_residuals": [
            {"war_mask": x["war_mask"],
             "max_best_response_or_Bellman_residual": x["max_best_response_or_Bellman_residual"]}
            for x in candidates
        ],
        "scientific_limits": [
            "This calculation is at one parameter point and exogenous finite calendar cycle",
            "Does not check non-Markov or mixed-strategy equilibria",
            "Does not establish analytic parameter ranges or infer war onset from holiday data",
            "First-mover attack identity is not separately identified without initiator advantage",
            "Do not treat numeric examples as a formal-model approval or a testable empirical result",
        ],
        "network_or_paid_api_calls": 0,
    }


def check(home, project, case_path, *, label="case"):
    blueprint, signature = approved_blueprint(home, project)
    case = json.loads(Path(case_path).read_text(encoding="utf-8"))
    result = analyze(case, signature["blueprint_sha256"])
    dest = outdir(home, project)
    dest.mkdir(parents=True, exist_ok=True)
    safe_label = gates.safe_project(str(label).lower())
    output = dest / (safe_label.upper() + "_NUMERIC_DIAGNOSTIC.json")
    theory.write(output, result)
    review = dest / (safe_label.upper() + "_REVIEW.md")
    lines = [
        "# Formal bargaining: finite-state numerical diagnostics",
        "",
        "**Scientific status:** NOT a theorem, NOT a complete equilibrium proof.",
        "",
        "**Blueprint SHA:** " + signature["blueprint_sha256"],
        "**Parameter case:** " + str(case_path),
        "**Deterministic illustrative cycle:** " + " → ".join(result["case"]["calendar_cycle"]),
        "",
        "**Pure stationary policies enumerated:** " + str(result["checked_pure_stationary_policies"]),
        "**Numerically consistent policies:** " + str(result["valid_numeric_pure_markov_candidates"]),
        "",
    ]
    if not result["candidates"]:
        lines.append("No pure stationary candidate passed at this parameter point. "
                     "This is NOT a nonexistence theorem: review model/tolerances "
                     "and consider mixed or history-dependent strategies.")
    for cand in result["candidates"]:
        lines += [
            "## Candidate policy " + str(cand["war_mask"]),
            "Maximum Bellman/incentive residual: " +
            format(cand["max_best_response_or_Bellman_residual"], ".4g"),
        ]
        for row in cand["calendar_policy"]:
            lines.append("- " + row["state"] + ": " + row["policy"] +
                         ("; B offer " + format(row["offer_if_peace"], ".5f")
                          if row["offer_if_peace"] is not None else "") +
                         "; B war win p=" + format(row["war_probability_B"], ".3f"))
    lines += ["", "## Unresolved research obligations", ""]
    lines.extend("- " + item for item in result["scientific_limits"])
    theory.write(review, "\n".join(lines) + "\n")
    return {
        "status": STATUS,
        "diagnostic": str(output),
        "review": str(review),
        "valid_numeric_pure_markov_candidates": result["valid_numeric_pure_markov_candidates"],
        "approved_blueprint_sha256": signature["blueprint_sha256"],
        "network_or_paid_api_calls": 0,
    }


def demo(home, project):
    """A clearly labeled synthetic parameter point for smoke testing only."""
    blueprint, signature = approved_blueprint(home, project)
    params = {
        "schema": CASE_SCHEMA, "status": "SYNTHETIC_ILLUSTRATION_NOT_EMPIRICAL",
        "blueprint_sha256": signature["blueprint_sha256"],
        "delta": 0.9, "p0": 0.5, "d_A": 0.15, "d_B": 0.15,
        "c_A": 0.25, "c_B": 0.25,
        "calendar_cycle": list(STATES),
        "caveat": "Artificial cycle and arbitrary parameters. No empirical support.",
    }
    dest = outdir(home, project)
    dest.mkdir(parents=True, exist_ok=True)
    path = theory.write(dest / "DEMO_SYNTHETIC_CASE.json", params)
    return check(home, project, path, label="DEMO_SYNTHETIC")


def main(argv=None):
    p = argparse.ArgumentParser(description="Offline numeric bargaining workbench, NOT a theorem prover")
    p.add_argument("--home", type=Path, default=ROOT)
    sub = p.add_subparsers(dest="command", required=True)
    start = sub.add_parser("prepare", help="Create signed architecture-to-proof work order")
    start.add_argument("project")
    d = sub.add_parser("demo", help="Analyze one explicitly synthetic game")
    d.add_argument("project")
    c = sub.add_parser("check", help="Analyze a researcher-supplied numeric parameter case")
    c.add_argument("project")
    c.add_argument("--case", type=Path, required=True)
    c.add_argument("--label", default="case")
    args = p.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.home, args.project)
        elif args.command == "demo":
            result = demo(args.home, args.project)
        else:
            result = check(args.home, args.project, args.case, label=args.label)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print("Formal workbench stopped safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

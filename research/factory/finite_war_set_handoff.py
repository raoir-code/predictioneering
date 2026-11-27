"""Handoff contract for a finite-calendar, set-valued pure Markov war game.

The previous paper_sprint contract required a differentiable equilibrium.
A set of war-phase masks has no canonical derivative or unique war probability.
This adapter preserves that distinction and requires reviewable predictions
before the empirical factory can consume the model. No approvals or API calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import formal_workbench as wb
from . import theory_fabricator as theory
from . import review_workflow as gates

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "finite_war_set_formal_model_v1"
FORM = "set_valued_pure_phase_markov"
SCOPES = ("selection_invariant", "conditional_on_equilibrium")
SIGNS = ("positive", "negative", "zero", "nonzero")

def _text(value, label, *, min_chars=12):
    if not isinstance(value, str) or len(value.strip()) < min_chars:
        raise ValueError(label + " requires a substantive reviewable statement")
    return value.strip()

def validate(model):
    """Check the contract, NOT the general existence theorem or predictions."""
    if not isinstance(model, dict) or model.get("schema") != SCHEMA:
        raise ValueError("Expected the finite-war-set model schema")
    if model.get("equilibrium_form") != FORM:
        raise ValueError("Model must explicitly represent set-valued pure phase-Markov equilibria")
    if model.get("game_protocol") != "fixed_A_proposer_B_accept_or_attack_one_period_agreements":
        raise ValueError("Model must retain the approved one-period bargaining protocol")
    if model.get("players") != ["A", "B"]:
        raise ValueError("Game players or proposer identity changed")
    if model.get("solution_concept") != "pure_phase_markov_mpe":
        raise ValueError("Only the separately audited pure phase-Markov concept is supported")
    if model.get("general_pure_existence_proven") is not False:
        raise ValueError("General pure-MPE existence remains UNSOLVED; do not assert it")
    if model.get("unique_equilibrium_assumed") is not False:
        raise ValueError("No unconditional uniqueness or equilibrium selection permitted")
    if model.get("selection_rule_provided") is not False:
        raise ValueError("No unsupported equilibrium-selection rule permitted")
    for field in ("title", "equilibrium_argument", "off_path_argument",
                  "source_proof_limitations", "war_set_test"):
        _text(model.get(field), field, min_chars=24)
    if not isinstance(model.get("unresolved_gaps"), list) or len(model["unresolved_gaps"]) < 2:
        raise ValueError("Record unresolved mathematical and empirical gaps explicitly")
    for gap in model["unresolved_gaps"]:
        _text(gap, "unresolved gap")
    refs = model.get("source_pins", {})
    if (not isinstance(refs, dict) or
            not all(isinstance(refs.get(key), str) and len(refs[key]) == 64
                    and all(c in "0123456789abcdef" for c in refs[key])
                    for key in ("blueprint_sha256", "proof_draft_sha256",
                                "numeric_audit_sha256"))):
        raise ValueError("Missing exact signed architecture / math draft / audit source hashes")
    hypotheses = model.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        raise ValueError("Researcher must supply at least one defensible, reviewable prediction")
    result = []
    ids = set()
    mapping = None
    for item in hypotheses:
        if not isinstance(item, dict):
            raise ValueError("Hypothesis must be a structured object")
        ident = item.get("id")
        if not isinstance(ident, str) or not ident.isidentifier() or ident in ids:
            raise ValueError("Hypothesis IDs must be distinct safe identifiers")
        ids.add(ident)
        scope = item.get("scope")
        if scope not in SCOPES:
            raise ValueError("Every hypothesis must declare selection-invariant or conditional scope")
        direction = item.get("sign")
        if direction not in SIGNS:
            raise ValueError("An empirical signed prediction is required; do not forge a derivative")
        statement = _text(item.get("prediction"), ident + " prediction", min_chars=24)
        justification = _text(item.get("formal_basis"), ident + " formal basis", min_chars=40)
        condition = _text(item.get("conditions"), ident + " identification conditions", min_chars=24)
        p = item.get("empirical_mapping")
        if not isinstance(p, dict) or not all(
                isinstance(p.get(k), str) and p[k].isidentifier()
                for k in ("predictor", "outcome")):
            raise ValueError("Specify valid predictor and outcome variable names")
        pair = (p["predictor"], p["outcome"])
        if mapping is None:
            mapping = pair
        elif mapping != pair:
            raise ValueError("Current single-treatment design supports one consistent predictor/outcome mapping")
        result.append({
            "id": ident, "prediction": statement, "sign": direction,
            "scope": scope, "conditions": condition,
            "formal_basis": justification, "empirical_mapping": dict(p),
        })
    return result

def source_check(home, project, model):
    """Reject stale or mismatched private proof and numeric audit artifacts."""
    from . import formal_reasoner
    _, signed = wb.approved_blueprint(home, project)
    theory.require_blueprint(home, project, model)
    pins = model["source_pins"]
    if pins["blueprint_sha256"] != signed["blueprint_sha256"]:
        raise ValueError("Model's signed architecture source pin differs")
    base = wb.outdir(home, project)
    proof = base / "derivations" / "PROOF_DRAFT.json"
    audit = base / "FORMAL_SOLVER_AUDIT.json"
    if not proof.is_file() or not audit.is_file():
        raise ValueError("Mathematical draft and latest numerical audit required")
    if (pins["proof_draft_sha256"] != gates.file_sha(proof) or
            pins["numeric_audit_sha256"] != gates.file_sha(audit)):
        raise ValueError("Formal-model source pins are stale; rerun audit and regenerate handoff")
    draft = json.loads(proof.read_text(encoding="utf-8"))
    formal_reasoner.validate(draft)
    details = json.loads(audit.read_text(encoding="utf-8"))
    if (draft.get("approved_blueprint_sha256") != signed["blueprint_sha256"] or
            details.get("approved_blueprint_sha256") != signed["blueprint_sha256"] or
            details.get("unverified_proof_draft_sha256") != pins["proof_draft_sha256"]):
        raise ValueError("Numeric audit is not tied to this approved blueprint and math draft")
    if details.get("status") != "NUMERICAL_CROSSCHECK_PASSED_NOT_MATHEMATICAL_PROOF":
        raise ValueError("Unresolved numerical contradictions require review")
    if (details.get("no_pure_mpe_cases") is None or
            details.get("contradiction_cases") != 0 or
            details.get("multiple_pure_mpe_cases", 0) < 1):
        raise ValueError("Expected auditable multiplicity and zero contradictory cases")
    return details

def checks(model):
    validated = validate(model)
    return {
        "formal_check_passed": True,
        "check_type": FORM,
        "derivatives": [],
        "all_derivative_signs_verified": None,
        "equilibrium_optimality_verified": False,
        "general_pure_existence_proven": False,
        "hypothesis_count": len(validated),
        "selection_conditional_hypotheses": sum(
            h["scope"] == "conditional_on_equilibrium" for h in validated),
        "caution": (
            "ONLY source pinning/structure checked. No derivative is defined "
            "for war-set membership. Claim signs, equilibrium existence, "
            "onset timing and data mappings require separate human verification."
        ),
    }

def hypotheses(model):
    return [{
        "id": h["id"], "prediction": h["prediction"], "sign": h["sign"],
        "scope": h["scope"], "conditions": h["conditions"],
        "formal_basis": h["formal_basis"],
    } for h in validate(model)]

def prepare(home, project):
    """Write a deliberately INCOMPLETE private template, never submit it."""
    _, sig = wb.approved_blueprint(home, project)
    base = wb.outdir(home, project)
    proof = base / "derivations" / "PROOF_DRAFT.json"
    audit = base / "FORMAL_SOLVER_AUDIT.json"
    if not proof.is_file() or not audit.is_file():
        raise ValueError("Finish the unverified math draft and offline audit first")
    source = json.loads(proof.read_text(encoding="utf-8"))
    evidence = json.loads(audit.read_text(encoding="utf-8"))
    if (source.get("approved_blueprint_sha256") != sig["blueprint_sha256"] or
            evidence.get("unverified_proof_draft_sha256") != gates.file_sha(proof) or
            evidence.get("contradiction_cases") != 0):
        raise ValueError("Source evidence is stale; rerun formal_solver audit")
    architecture, _ = wb.approved_blueprint(home, project)
    model = {
        "schema": SCHEMA,
        "title": "Holy Days and War: Conditional Equilibria in Repeated Bargaining",
        "equilibrium_form": FORM,
        "game_protocol": "fixed_A_proposer_B_accept_or_attack_one_period_agreements",
        "players": ["A", "B"],
        "solution_concept": "pure_phase_markov_mpe",
        "theory_blueprint_sha256": sig["blueprint_sha256"],
        "baseline_game_family": architecture["baseline"]["family"],
        "one_change_summary": architecture["innovation"]["one_sentence_change"],
        "source_pins": {
            "blueprint_sha256": sig["blueprint_sha256"],
            "proof_draft_sha256": gates.file_sha(proof),
            "numeric_audit_sha256": gates.file_sha(audit),
        },
        "general_pure_existence_proven": False,
        "unique_equilibrium_assumed": False,
        "selection_rule_provided": False,
        "equilibrium_argument": source.get("candidate_equilibrium", ""),
        "off_path_argument": source.get("offpath_deviation_checks", ""),
        "war_set_test": source.get("bellman_equations", ""),
        "source_proof_limitations": source.get("parameter_domains", ""),
        "unresolved_gaps": source.get("unresolved_gaps", []),
        "hypotheses": [],
        "notice": "INCOMPLETE WORKING DRAFT. Supply defensible hypotheses and "
                  "inspect the whole proof before submitting for human approval.",
    }
    dest = base / "FORMAL_MODEL_HANDOFF_CANDIDATE.json"
    # No overwrite of researcher work.
    if dest.exists():
        existing = json.loads(dest.read_text(encoding="utf-8"))
        if existing.get("source_pins") != model["source_pins"]:
            raise ValueError("Existing handoff candidate has different proof/audit pins; "
                             "archive it manually before preparing a new one")
    else:
        theory.write(dest, model)
    return {
        "status": "INCOMPLETE_SET_VALUED_FORMAL_MODEL_CANDIDATE",
        "candidate": str(dest), "hypotheses_required": True,
        "auto_approved": False, "formal_model_submitted": False,
        "network_or_paid_api_calls": 0,
    }

def main(argv=None):
    p = argparse.ArgumentParser(description="Prepare a set-valued formal-model handoff; no approval or paid API")
    p.add_argument("project")
    p.add_argument("--home", type=Path, default=ROOT)
    args = p.parse_args(argv)
    try:
        result = prepare(args.home, args.project)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("Formal-model handoff stopped safely: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

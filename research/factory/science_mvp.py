"""Human-gated scientific MVP adapters; no automatic scientific approvals.

Complements the existing puzzle/literature workers and frozen analysis/Overleaf
adapters without copying private datasets into Git. No paid API or web access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

from . import paper_sprint, prototype, review_workflow as gates, finite_war_set_handoff as war_set

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("puzzle", "diagnosis", "literature", "novelty", "formal_model",
          "hypotheses", "data", "design", "analysis", "validation", "manuscript", "qc")
SUPPORTED = {"novelty", "formal_model", "hypotheses", "data", "design",
             "analysis", "validation", "manuscript", "qc"}


def text_file(path):
    p = Path(path).expanduser().resolve()
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 1_000_000:
        raise ValueError("Missing, symlinked or oversized researcher-supplied text")
    return p.read_text(encoding="utf-8")


def draft(home, project, stage):
    return Path(home).resolve() / "inbox" / "raw" / "scientific_stages" / project / stage


def write(path, content):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        content = json.dumps(content, indent=2, ensure_ascii=False) + "\n"
    p.write_text(content, encoding="utf-8")
    return p


def approved_artifact(home, project, stage, name):
    state = gates.load(home, project)
    gates.require_approved(home, project, stage)
    a = [x for x in state["stages"][stage]["artifacts"] if x["name"] == name]
    if len(a) != 1:
        raise ValueError("Approved " + stage + " must include exactly one " + name)
    p = gates.location(home, project) / a[0]["snapshot"]
    if not p.is_file() or gates.file_sha(p) != a[0]["sha256"]:
        raise ValueError("Human-approved artifact changed or disappeared")
    return p


def approved_model(home, project):
    return paper_sprint.load(approved_artifact(home, project, "formal_model",
                                              "formal_model.json"))


def derived_hypotheses(model):
    if model.get("schema") == war_set.SCHEMA:
        return [{key: row[key] for key in ("id", "prediction", "sign")}
                for row in war_set.hypotheses(model)]
    h = paper_sprint.hypotheses_from_model(model)["hypotheses"]
    return [{"id": row["id"], "prediction": row["prediction"], "sign": row["sign"]}
            for row in h]


def match_hypotheses(home, project, spec):
    frozen = json.loads(approved_artifact(home, project, "hypotheses",
                                          "hypotheses.json").read_text(encoding="utf-8"))
    expected = frozen.get("hypotheses")
    supplied = spec.get("hypotheses", [])
    if expected != supplied:
        raise ValueError("Study hypotheses differ from the approved formal-model derivatives")


def model_checks(model, spec=None):
    # A discrete war-set is not a differentiable equilibrium expression.
    # Do not fabricate an equilibrium expression to satisfy a symbolic API.
    if model.get("schema") == war_set.SCHEMA:
        checks = war_set.checks(model)
        if spec is not None:
            expected = derived_hypotheses(model)
            if spec.get("hypotheses") != expected:
                raise ValueError("Empirical hypotheses differ from the signed set-valued model")
            predictors = {(h["empirical_mapping"]["predictor"],
                           h["empirical_mapping"]["outcome"])
                          for h in model["hypotheses"]}
            if predictors != {(spec["design"]["treatment"], spec["design"]["outcome"])}:
                raise ValueError("Empirical design does not match the discrete game's variable mapping")
        return checks
    # The existing paper sprint checks derivatives conditional on an ASSERTED
    # equilibrium; a valid derivative is not a best-response proof.
    if spec is None:
        hypotheses = derived_hypotheses(model)
        mapping = model["comparative_statics"][0]["empirical_mapping"]
        spec = {"hypotheses": hypotheses,
                "design": {"treatment": mapping["predictor"],
                           "outcome": mapping["outcome"]}}
    checks = paper_sprint.check_model(model, spec)
    if not checks["all_derivative_signs_verified"]:
        raise ValueError("At least one asserted comparative-static sign is not symbolically verified")
    if model.get("normal_form_2x2") is not None:
        from . import two_by_two_game
        checks["normal_form_2x2_audit"] = two_by_two_game.verify(model)
    checks["formal_check_passed"] = True
    checks["check_type"] = "conditional_symbolic_derivative"
    return checks


def check_panel_integrity(spec, frame):
    """Conservative optional guardrails for directed dyad-day datasets.

    A self-declared direction flag is NOT independent coding validation.
    """
    cfg = spec.get("research_integrity_checks", {})
    if not isinstance(cfg, dict):
        raise ValueError("research_integrity_checks must be an object")
    if not cfg:
        return {"status": "not_specified", "independent_direction_audit": False}
    d = spec["design"]
    unit, when, outcome = d.get("unit"), d["time"], d["outcome"]
    result = {"status": "researcher_declared_panel_checks_passed",
              "independent_direction_audit": False,
              "checks": []}
    if cfg.get("unique_unit_date", False):
        if not unit or unit not in frame.columns:
            raise ValueError("Unit ID required for dyad-day uniqueness")
        if bool(frame.duplicated([unit, when]).any()):
            raise ValueError("Duplicate unit-date rows; event counts must be aggregated into one at-risk day")
        result["checks"].append("one_row_per_unit_date")
    if cfg.get("complete_unit_daily_panel", False):
        if not unit or unit not in frame.columns:
            raise ValueError("Unit ID required to verify daily risk-set completeness")
        for _, sample in frame.groupby(unit):
            distinct = sample[when].nunique()
            expected = (sample[when].max() - sample[when].min()).days + 1
            if distinct != expected:
                raise ValueError("Missing unit-day observations; unobserved days cannot silently become zeros")
        result["checks"].append("continuous_dates_within_each_observed_unit_span")
    if cfg.get("require_directed_attack_attribution", False):
        direction = cfg.get("direction_verified_column")
        if not isinstance(direction, str) or direction not in frame.columns:
            raise ValueError("Missing researcher-audited direction verification column")
        positive = frame.loc[frame[outcome] > 0]
        if positive.empty:
            raise ValueError("Cannot validate directed event attribution: no attack days observed")
        if not positive[direction].eq(1).all():
            raise ValueError("Unverified or ambiguous attacking actor; directed interstate panel blocked")
        result["checks"].append("positive_attack_days_researcher_flagged_direction_verified")
    if not result["checks"]:
        raise ValueError("research_integrity_checks present but no scientific guard enabled")
    return result


def produce(home, project, stage, *, model_path=None, spec_path=None,
            assessment_path=None):
    home = Path(home).expanduser().resolve()
    if stage not in SUPPORTED:
        raise ValueError("Unsupported stage; use existing puzzle/literature starter")
    gates.require_ready(home, project, stage)
    profile = gates.load(home, project).get("gate_profile", "legacy")
    dest = draft(home, project, stage)
    if stage == "novelty":
        if assessment_path is None:
            raise ValueError("Supply --assessment with a researcher-written, source-checked contribution memo")
        content = text_file(assessment_path)
        if len(content.strip()) < 250:
            raise ValueError("Contribution memo too short; compare closely related original work")
        parent_token = gates.require_approved(home, project, "literature")
        output = write(dest / "CONTRIBUTION_ASSESSMENT.md",
            "# Candidate contribution — human review required\n\n" + content +
            "\n\n---\nLiterature approval token: " + parent_token +
            "\nOriginal-paper citations, scope and contrary findings require human checking.\n")
        files = [output]
        summary = "Researcher-supplied literature contribution assessment; NOT independently verified novelty"
    elif stage == "formal_model":
        if model_path is None:
            raise ValueError("Supply --model with a proposed, explicitly argued game model JSON")
        model = paper_sprint.load(model_path)
        if profile == "mvp10":
            from . import theory_fabricator
            theory_fabricator.require_blueprint(home, project, model)
        if model.get("schema") == war_set.SCHEMA:
            war_set.source_check(home, project, model)
        checks = model_checks(model)
        if model.get("schema") == war_set.SCHEMA:
            screening = (
                "# Finite war-set model — structural screening, NOT theorem verification\n\n"
                "**No derivative has been calculated or invented.**\n\n"
                "The human-supplied predictions are explicitly scoped as "
                "selection-invariant or conditional on equilibrium selection.\n"
                "Conditional claims: " +
                str(checks["selection_conditional_hypotheses"]) + "\n\n"
                "**NOT VERIFIED:** general pure-MPE existence, mathematical "
                "necessity/sufficiency beyond the numerical audit, equilibrium "
                "selection, empirical identification, literature novelty or signed "
                "hypothesis interpretation.\n\n"
                "Human review is REQUIRED before proceeding.\n"
            )
        else:
            screening = (
                "# Formal model screening\n\n" +
                "Symbolic derivative signs (conditional on asserted equilibrium): " +
                str(checks["all_derivative_signs_verified"]) + "\n\n" +
                "\n".join("- " + x["id"] + ": d/d" + x["parameter"] +
                          " = " + x["derivative_sympy"] + " (" +
                          x["expected_sign"] + ")"
                          for x in checks["derivatives"]) +
                "\n\n**NOT VERIFIED:** complete equilibrium classification, parameter admissibility, "
                "empirical mapping, and novelty. Researcher must check all.\n" +
                (("2x2 payoff-matrix indifference: " +
                  checks["normal_form_2x2_audit"]["status"] + "\n" +
                  "Attacker mixing p = " +
                  checks["normal_form_2x2_audit"]["row_player_first_action_probability"] + "\n" +
                  "Defender mixing q = " +
                  checks["normal_form_2x2_audit"]["column_player_first_action_probability"] + "\n")
                 if "normal_form_2x2_audit" in checks else "")
            )
        files = [write(dest / "formal_model.json", model),
                 write(dest / "FORMAL_CHECKS.md", screening)]
        if profile == "mvp10":
            from . import theory_fabricator
            agreed = theory_fabricator.folder(home, project) / "THEORY_BLUEPRINT.json"
            files.append(write(dest / "THEORY_BLUEPRINT.json",
                               json.loads(agreed.read_text(encoding="utf-8"))))
            signature = theory_fabricator.folder(home, project) / "BLUEPRINT_APPROVAL.json"
            files.append(write(dest / "THEORY_BLUEPRINT_APPROVAL.json",
                               json.loads(signature.read_text(encoding="utf-8"))))
        summary = "Approved architecture -> researcher-supplied game and conditional checks; equilibrium UNPROVEN"
    elif stage == "hypotheses":
        model = approved_model(home, project)
        checks = model_checks(model)
        h = derived_hypotheses(model)
        files = [write(dest / "hypotheses.json", {"hypotheses": h,
            "formal_model_sha256": gates.file_sha(approved_artifact(
                home, project, "formal_model", "formal_model.json")),
            "formal_check_type": checks["check_type"],
            "conditional_derivative_signs_verified": checks["all_derivative_signs_verified"],
            "selection_conditional_predictions": (
                checks.get("selection_conditional_hypotheses", 0)),
            "mechanism_and_empirical_mapping_independently_verified": False})]
        summary = "Hypotheses derived from approved game comparative statics, pending substantive human review"
    elif stage == "data":
        if profile == "mvp10":
            if spec_path is not None:
                raise ValueError("MVP data uses the approved design study.json; omit --spec")
            path = approved_artifact(home, project, "design", "study.json")
        else:
            if spec_path is None:
                raise ValueError("Supply --spec referring to the proposed study and accessible local CSV")
            path = Path(spec_path).expanduser().resolve()
        spec = prototype.validate_spec(prototype.read_json(path))
        match_hypotheses(home, project, spec)
        source = prototype.data_file(spec, path)
        if not source.is_file() or source.is_symlink():
            raise ValueError("Private study CSV missing or symlinked; cannot approve data")
        # Check actual columns, date validity, outcome family and distinct observations.
        frame, diagnostics = prototype.read_data(spec, source)
        integrity = check_panel_integrity(spec, frame)
        manifest = {"data_sha256": gates.file_sha(source),
                    "research_panel_integrity": integrity,
                    "data_file_name": source.name, "rows": len(frame),
                    "diagnostics": diagnostics,
                    "redistribution_allowed": spec["data"]["redistribution_allowed"],
                    "synthetic": spec["data"]["synthetic"],
                    "status": "observed_data_profile_not_measurement_validation",
                    "private_source_data_included": False,
                    "researcher_must_verify": ["dataset origin/license", "event definitions",
                         "actor direction", "measurement", "selection", "calendar accuracy"]}
        files = [write(dest / "data_manifest.json", manifest)]
        summary = "Local dataset schema, row diagnostics and SHA256; substantive measurement audit outstanding"
    elif stage == "design":
        if spec_path is None:
            raise ValueError("Supply --spec with prespecified identification and model mappings")
        path = Path(spec_path).expanduser().resolve()
        spec = prototype.validate_spec(prototype.read_json(path))
        match_hypotheses(home, project, spec)
        source = prototype.data_file(spec, path)
        if profile == "mvp10":
            # Research design is prespecified before procurement. Any currently
            # present CSV may inform feasibility but is not yet human-approved.
            expected = "PENDING_DATA_APPROVAL"
        else:
            expected = gates.data_hash_from_approved_manifest(home, project)
            if not source.is_file() or gates.file_sha(source) != expected:
                raise ValueError("Dataset changed since human data approval")
        model = approved_model(home, project)
        checks = model_checks(model, spec)
        if not checks["formal_check_passed"]:
            raise ValueError("Formal model mechanical check failed")
        if checks["check_type"] == war_set.FORM and checks["selection_conditional_hypotheses"]:
            condition = spec["design"].get("equilibrium_scope_conditions")
            if not isinstance(condition, str) or len(condition.strip()) < 50:
                raise ValueError(
                    "Design with selection-conditional war-set predictions requires "
                    "an explicit, substantive equilibrium_scope_conditions field; "
                    "do not assume unconditional war probabilities")
        # Automatically reference the signed novelty approval; do not ask the
        # researcher to certify the same decision twice in study.json.
        upstream = "literature" if profile == "mvp10" else "novelty"
        approval = gates.load(home, project)["stages"][upstream].get("approval")
        if not approval:
            raise ValueError("No human-signed literature/contribution assessment")
        spec["novelty_review"] = {
            "status": "approved", "reviewer": approval["reviewer"],
            "notes": "Human-signed " + upstream + " screening: " +
                     approval["token"][:24] + "; candidate contribution ONLY, not independently confirmed.",
            "scope": "preliminary_screen_only"}
        # A frozen study.json lives in an immutable snapshot directory, so
        # relative CSV paths would silently resolve against the wrong folder.
        # Record a local, private absolute source path; never upload the spec
        # or source CSV to the public repository.
        spec["data"]["csv_path"] = str(source.resolve())
        files = [write(dest / "study.json", spec),
                 write(dest / "DESIGN_REVIEW.md",
                    "# Prespecified research design\n\n" +
                    "Estimator: " + spec["design"]["method"] +
                    "; family: " + spec["design"]["family"] +
                    "; outcome: " + spec["design"]["outcome"] +
                    "; predictor: " + spec["design"]["treatment"] + "\n\n" +
                    "Data SHA256: " + expected + "\n\n" +
                    "**Identification not established by code.** Human must assess " +
                    "confounding, treatment timing, parallel trends or continuity " +
                    "where applicable, clustering, alternative designs and falsifiers.\n" +
                    ("**Data not yet approved.** Procurement and hash verification follow design signoff.\n"
                     if profile == "mvp10" else ""))]
        summary = "Prespecified empirical study matched to human-approved theory and data; causal assumptions unverified"
    elif stage == "analysis":
        if spec_path is not None:
            raise ValueError("Analysis uses only human-approved frozen study.json; do not pass a new spec")
        spec_file = approved_artifact(home, project, "design", "study.json")
        return gates.produce(home, project, "analysis", spec_file=spec_file)
    elif stage == "validation":
        frozen = gates.load(home, project)["stages"]["analysis"]
        gates.require_approved(home, project, "analysis")
        names = {x["name"]: x["sha256"] for x in frozen["artifacts"]}
        analysis_dir = gates.location(home, project).parent / "stage_outputs" / "analysis"
        for name in ("results.json", "QC_REPORT.json", "replication_manifest.json", "state.json"):
            p = analysis_dir / name
            if not p.is_file() or gates.file_sha(p) != names.get(name):
                raise ValueError("Analysis artifact mutated since human approval: " + name)
        source_spec = approved_artifact(home, project, "design", "study.json")
        spec = prototype.validate_spec(prototype.read_json(source_spec))
        data = prototype.data_file(spec, source_spec)
        if not data.is_file() or gates.file_sha(data) != gates.data_hash_from_approved_manifest(home, project):
            raise ValueError("Validation data source differs from frozen approved dataset")
        result = prototype.read_json(analysis_dir / "results.json")
        qc = prototype.read_json(analysis_dir / "QC_REPORT.json")
        audit = {"status": "frozen_analysis_provenance_verified_NOT_independent_replication",
                 "analysis_source_sha256": names, "data_sha256": gates.file_sha(data),
                 "study_id": result.get("study_id"),
                 "original_qc": qc,
                 "identification_independently_verified": False,
                 "predictive_out_of_sample_independently_verified": False,
                 "human_must_check": ["sample splits and temporal leakage", "standard errors",
                       "effect identification", "robustness", "alternative specifications"]}
        files = [write(dest / "VALIDATION_AUDIT.json", audit)]
        summary = "Approved analysis data/hash checks; independent scientific validation still required"
    elif stage == "manuscript":
        if spec_path is not None or model_path is not None:
            raise ValueError("Manuscript uses only human-approved frozen spec/model")
        spec_file = approved_artifact(home, project, "design", "study.json")
        # Source snapshot is immutable and hash-identical to approved formal_model.
        model_file = approved_artifact(home, project, "formal_model", "formal_model.json")
        return gates.produce(home, project, "manuscript",
                             spec_file=spec_file, model_file=model_file)
    else:  # qc
        gates.require_approved(home, project, "manuscript")
        stage_output = gates.location(home, project).parent / "stage_outputs" / "manuscript"
        package = stage_output / "overleaf"
        manifest = prototype.read_json(package / "PACKAGE_MANIFEST.json")
        qc = prototype.read_json(package / "PAPER_QC.json")
        for name, expected in manifest.get("included_sha256", {}).items():
            fp = package / name
            if not fp.is_file() or gates.file_sha(fp) != expected:
                raise ValueError("Overleaf package file changed after packaging: " + name)
        archives = list(stage_output.glob("*_OVERLEAF_DRAFT.zip"))
        if len(archives) != 1:
            raise ValueError("Exactly one generated Overleaf draft required")
        with zipfile.ZipFile(archives[0]) as z:
            entries = z.namelist()
            if not entries or any(name.startswith("/") or ".." in Path(name).parts for name in entries):
                raise ValueError("Overleaf ZIP contains invalid or unsafe paths")
            if "main.tex" not in entries or "references.bib" not in entries:
                raise ValueError("Overleaf ZIP missing main manuscript or bibliography")
        audit = {"status": "PACKAGE_INTEGRITY_CHECKED_NOT_SCIENTIFIC_QC",
                 "archive_sha256": gates.file_sha(archives[0]),
                 "unmet_scientific_qc": qc.get("unmet", []),
                 "independent_original_source_verification": False,
                 "independent_equilibrium_proof": False,
                 "independent_replication": False,
                 "human_final_review": False}
        files = [write(dest / "FINAL_QC_AUDIT.json", audit),
                 write(dest / "FINAL_QC_REPORT.md",
                       "# Paper factory quality control\n\nPackage hashes and ZIP structure: checked.\n\n" +
                       "**Paper is NOT submission-ready.** Open scientific gates:\n\n" +
                       "\n".join("- " + str(x) for x in audit["unmet_scientific_qc"]) +
                       "\n\nIndependent scholarly review and replication are still required.\n")]
        summary = "Overleaf artifact integrity and explicit outstanding scientific quality-control tasks"
    return gates.submit(home, project, stage, files, summary)


def status(home, project):
    state = gates.overview(home, project)
    ready = [x for x in state["ready_stages"] if x in SUPPORTED]
    pending = [x for x in state["awaiting_human"]]
    return {"project": project, "ready_for_worker": ready,
            "awaiting_human": pending,
            "current_literature_approved": next(
                x["status"] == "approved" for x in state["stages"] if x["stage"] == "literature"),
            "workflow_stages": [{"stage": x["stage"], "status": x["status"]}
                                for x in state["stages"]],
            "hint": ("Review the submitted packet and approve/revise" if pending else
                     "Use produce STAGE with required --assessment, --model or --spec"),
            "network_or_paid_api_calls": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Guarded scientific stages into Overleaf")
    parser.add_argument("--home", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status")
    s.add_argument("project")
    b = sub.add_parser("produce")
    b.add_argument("project")
    b.add_argument("stage", choices=sorted(SUPPORTED))
    b.add_argument("--model", type=Path)
    b.add_argument("--spec", type=Path)
    b.add_argument("--assessment", type=Path)
    args = parser.parse_args(argv)
    try:
        result = (status(args.home, args.project) if args.command == "status" else
                  produce(args.home, args.project, args.stage, model_path=args.model,
                          spec_path=args.spec, assessment_path=args.assessment))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile) as exc:
        print("Scientific MVP stopped safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Reusable Predictioneering paper-factory prototype (research only).

No network/API calls or publication actions. From a reviewed research specification
and local CSV, generate theory/design worksheets, statistical estimates, temporal
out-of-sample checks, a candid manuscript draft, and replication metadata.
Unsupported scientific claims are blocked explicitly, never invented.

CLI: python -m research.factory.prototype demo|plan|run|status
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import tempfile

VERSION = "research-factory-prototype-0.1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = ROOT / "projects" / "factory_runs"
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SLUG = re.compile(r"^[a-z][a-z0-9_-]{2,62}$")
FAMILIES = {"gaussian", "binomial", "poisson"}
DESIGNS = {"association", "did", "rdd"}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     delete=False) as handle:
        tmp = Path(handle.name)
        handle.write(text)
    os.replace(tmp, path)


def write_json(path: Path, content: dict) -> None:
    atomic_text(path, json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def read_json(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Specification must be a JSON object")
    return result


def identifiers(items, field: str) -> list[str]:
    if not isinstance(items, list) or any(not isinstance(v, str) or not IDENT.fullmatch(v) for v in items):
        raise ValueError(f"{field} must be a list of safe CSV column names")
    if len(set(items)) != len(items):
        raise ValueError(f"{field} has duplicates")
    return items


def nonempty_text(obj: dict, name: str, length: int = 5000) -> str:
    value = obj.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > length:
        raise ValueError(f"{name} must be nonempty text (<= {length} characters)")
    return value.strip()


def validate_spec(spec: dict) -> dict:
    """Return a copy with validated types; never infer a missing estimand."""
    if not isinstance(spec, dict):
        raise ValueError("Study must be a JSON object")
    s = json.loads(json.dumps(spec))
    if not isinstance(s.get("id"), str) or not SLUG.fullmatch(s["id"]):
        raise ValueError("id must be a lowercase, safe slug (3-63 characters)")
    for key in ("title", "research_question", "mechanism"):
        nonempty_text(s, key)
    hypotheses = s.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses or len(hypotheses) > 20:
        raise ValueError("hypotheses must contain 1-20 explicitly supplied hypotheses")
    for h in hypotheses:
        if not isinstance(h, dict):
            raise ValueError("Each hypothesis must be an object")
        nonempty_text(h, "id", 40)
        nonempty_text(h, "prediction")
        if h.get("sign") not in ("positive", "negative", "nonzero", "unspecified"):
            raise ValueError("Hypothesis sign must be positive, negative, nonzero or unspecified")
    if len(set(h["id"] for h in hypotheses)) != len(hypotheses):
        raise ValueError("Hypothesis IDs must be unique")
    data = s.get("data")
    if not isinstance(data, dict):
        raise ValueError("data object is required")
    nonempty_text(data, "csv_path")
    if data.get("redistribution_allowed") not in (True, False):
        raise ValueError("data.redistribution_allowed must be explicit true/false")
    if data.get("synthetic") not in (True, False):
        raise ValueError("data.synthetic must be explicit true/false")
    design = s.get("design")
    if not isinstance(design, dict) or design.get("method") not in DESIGNS or design.get("family") not in FAMILIES:
        raise ValueError("design.method and design.family must be supported")
    necessary = ["outcome", "treatment", "time"]
    if design["method"] == "did":
        necessary += ["post", "unit"]
    if design["method"] == "rdd":
        necessary += ["running"]
        if not isinstance(design.get("cutoff"), (float, int)) or isinstance(design["cutoff"], bool):
            raise ValueError("RDD requires numeric cutoff")
        if not isinstance(design.get("bandwidth"), (float, int)) or design["bandwidth"] <= 0:
            raise ValueError("RDD requires a positive numeric bandwidth")
    for key in necessary:
        if not isinstance(design.get(key), str) or not IDENT.fullmatch(design[key]):
            raise ValueError(f"design.{key} must be a safe column name")
    controls = identifiers(design.get("controls", []), "design.controls")
    fes = identifiers(design.get("fixed_effects", []), "design.fixed_effects")
    cluster = design.get("cluster")
    if cluster is not None and (not isinstance(cluster, str) or not IDENT.fullmatch(cluster)):
        raise ValueError("design.cluster must be a CSV column name or null")
    if design["outcome"] == design["treatment"] or design["outcome"] in controls:
        raise ValueError("Outcome cannot be a predictor")
    if design["treatment"] in controls or design["treatment"] in fes:
        raise ValueError("Treatment cannot be repeated in controls/fixed effects")
    if design["method"] == "did" and (design["post"] in controls or design["post"] in fes):
        raise ValueError("DID post variable cannot be repeated in controls/fixed effects")
    if len(controls) > 15 or len(fes) > 4:
        raise ValueError("Prototype limit: 15 controls and 4 FE columns")
    fraction = design.get("holdout_fraction", 0.25)
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not 0.1 <= fraction <= 0.4:
        raise ValueError("holdout_fraction must lie between 0.1 and 0.4")
    review = s.get("novelty_review")
    if not isinstance(review, dict) or review.get("status") not in ("pending", "approved", "demo_only"):
        raise ValueError("novelty_review.status must be pending, approved, or demo_only")
    if review["status"] == "approved":
        nonempty_text(review, "reviewer", 160)
        nonempty_text(review, "notes", 1000)
    if review["status"] == "demo_only" and not data["synthetic"]:
        raise ValueError("demo_only novelty review permitted only for synthetic data")
    prior = s.get("literature", [])
    if not isinstance(prior, list) or any(not isinstance(x, dict) or not x.get("title") for x in prior):
        raise ValueError("literature must be an array of cited source metadata, not invented references")
    if len(prior) > 100:
        raise ValueError("Prototype supports up to 100 source records")
    return s


def data_file(spec: dict, spec_file: Path) -> Path:
    path = Path(spec["data"]["csv_path"]).expanduser()
    return path.resolve() if path.is_absolute() else (spec_file.parent / path).resolve()


def plan(spec_file: Path) -> dict:
    spec = validate_spec(read_json(spec_file))
    source = data_file(spec, spec_file)
    pending = spec["novelty_review"]["status"] == "pending"
    return {
        "version": VERSION, "id": spec["id"], "title": spec["title"],
        "data_exists": source.is_file(), "novelty_review_pending": pending,
        "stages": ["input_validation", "theory_workbook", "design_workbook",
                   "statistical_estimation", "out_of_sample_validation",
                   "manuscript_draft", "replication_manifest", "quality_report"],
        "ready_to_run": source.is_file() and not pending,
        "blockers": (["Independent human novelty approval required"] if pending else []) +
                    ([] if source.is_file() else ["Data CSV not found locally"]),
        "warnings": ["Pipeline can generate research artifacts, not establish model truth or novelty",
                     "Analysis is descriptive until causal assumptions are independently defended"],
        "network_or_paid_api_calls": 0,
    }


def framing(spec: dict) -> tuple[str, str]:
    d = spec["design"]
    theory = [
        f"# Theory workbook — {spec['title']}", "",
        "**Status: hypothesis specification, NOT a formally solved equilibrium or verified contribution.**", "",
        "## Puzzle", spec["research_question"], "", "## Proposed mechanism", spec["mechanism"], "",
        "## Supplied, falsifiable hypotheses", "",
    ]
    for h in spec["hypotheses"]:
        theory.append(f"- **{h['id']}** ({h['sign']}): {h['prediction']}")
    theory.extend(["", "## Proof/identification obligations", "",
                   "- Derive comparative statics from an explicit payoff or causal model; not attempted automatically.",
                   "- State who moves, what is observed, and the timing of treatment and outcome.",
                   "- Specify equilibrium selection or potential-outcome assumptions and falsifiers.",
                   "- Check closest prior work in full text; automated metadata alone cannot establish novelty.", ""])
    design = [f"# Research design workbook — {spec['title']}", "",
              "**Status: user-supplied design; candidate estimand, not identification proof.**", "",
              f"- Method: `{d['method']}`; outcome family: `{d['family']}`.",
              f"- Outcome: `{d['outcome']}`; treatment: `{d['treatment']}`.",
              f"- Time: `{d['time']}`; unit: `{d.get('unit', 'not specified')}`.",
              f"- Controls: {', '.join(d.get('controls', [])) or 'none'}.",
              f"- Fixed effects: {', '.join(d.get('fixed_effects', [])) or 'none'}.",
              f"- Cluster: `{d.get('cluster') or 'HC3 robust'}`.", "",
              "## Threats and required diagnostics", "",
              "- Measurement validity, selection, confounding, seasonality and reporting lag.",
              "- Temporal leakage and distribution shift in future observations.",
              "- Multiple hypotheses and specification/search multiplicity.",
              "- No automatic causal claim from a statistically significant coefficient.", ""]
    if d["method"] == "did":
        design.extend(["- **DiD:** parallel trends, staggered timing, anticipation and composition need independent scrutiny."])
    elif d["method"] == "rdd":
        design.extend(["- **RDD:** manipulate/bunching near cutoff, bandwidth sensitivity and continuity require independent checks."])
    else:
        design.extend(["- **Association:** absent an identification argument, estimates are correlational."])
    return "\n".join(theory) + "\n", "\n".join(design) + "\n"


def read_data(spec: dict, source: Path):
    import numpy as np
    import pandas as pd
    d = spec["design"]
    df = pd.read_csv(source, low_memory=False)
    raw_rows = len(df)
    if len(df) < 60 or len(df) > 1_000_000:
        raise ValueError("Data must have 60-1,000,000 observations for prototype")
    required = {d["outcome"], d["treatment"], d["time"], *d.get("controls", []),
                *d.get("fixed_effects", [])}
    for key in ("cluster", "unit", "post", "running"):
        if d.get(key):
            required.add(d[key])
    missing = required - set(df.columns)
    if missing:
        raise ValueError("Missing required data columns: " + ", ".join(sorted(missing)))
    # DATE ONLY. No random train/test leakage and no arbitrary date parsing.
    when = pd.to_datetime(df[d["time"]], errors="coerce", format="%Y-%m-%d")
    if when.isna().any():
        raise ValueError("All time values must be ISO YYYY-MM-DD dates")
    df[d["time"]] = when
    numeric = {d["outcome"], d["treatment"], *d.get("controls", [])}
    if d["method"] == "did":
        numeric.add(d["post"])
    if d["method"] == "rdd":
        numeric.add(d["running"])
    for key in numeric:
        df[key] = pd.to_numeric(df[key], errors="coerce")
    bad = df[list(numeric)].isna().any(axis=1)
    n_dropped = int(bad.sum())
    df = df.loc[~bad].copy()
    if len(df) < 50:
        raise ValueError("Insufficient complete data after missing-value exclusions")
    if d["family"] == "binomial" and not set(df[d["outcome"]].unique()).issubset({0, 1}):
        raise ValueError("Binomial outcome must contain only 0/1")
    if d["family"] == "poisson" and (df[d["outcome"]].lt(0).any() or
                                       not np.all(np.equal(np.mod(df[d["outcome"]], 1), 0))):
        raise ValueError("Poisson outcome must be nonnegative integer counts")
    if d["method"] == "did":
        for key in (d["treatment"], d["post"]):
            if not set(df[key].unique()).issubset({0, 1}):
                raise ValueError("DiD treatment and post must be binary 0/1")
        if df.groupby([d["treatment"], d["post"]]).size().shape[0] < 4:
            raise ValueError("DiD requires observations in all four treatment/post cells")
    if d["method"] == "rdd":
        bw, cut = float(d["bandwidth"]), float(d["cutoff"])
        df = df.loc[(df[d["running"]] - cut).abs() <= bw].copy()
        if len(df) < 50:
            raise ValueError("RDD bandwidth leaves fewer than 50 observations")
        df["_rdd_running_centered"] = df[d["running"]] - cut
        df["_rdd_above"] = (df["_rdd_running_centered"] >= 0).astype(int)
        # Discontinuity design must align treatment with cutoff; fuzzy RDD unsupported.
        if not (df[d["treatment"]] == df["_rdd_above"]).all():
            raise ValueError("Only sharp RDD supported: treatment must equal threshold indicator")
        if df["_rdd_above"].nunique() < 2:
            raise ValueError("RDD needs observations on both sides of cutoff")
    return df, {"loaded_rows": int(raw_rows),
                "dropped_missing_numeric_rows": n_dropped,
                "analysis_rows": int(len(df)),
                "unique_dates": int(df[d["time"]].nunique()),
                "data_sha256": digest(source.read_bytes())}


def formula_for(spec: dict, *, predictive: bool = False):
    d = spec["design"]
    controls = list(d.get("controls", []))
    if d["method"] == "association":
        contrast = d["treatment"]
        terms = [contrast] + controls
    elif d["method"] == "did":
        contrast = f"{d['treatment']}:{d['post']}"
        terms = [contrast] + controls
        if not predictive:
            terms.extend([f"C({d['unit']})", f"C({d['time']})"])
    else:
        contrast = "_rdd_above"
        terms = [contrast, "_rdd_running_centered", "_rdd_above:_rdd_running_centered"] + controls
    if not predictive and d["method"] != "did":
        terms.extend("C(" + fe + ")" for fe in d.get("fixed_effects", []))
    return d["outcome"] + " ~ " + " + ".join(dict.fromkeys(terms)), contrast


def family_obj(name: str):
    import statsmodels.api as sm
    return {"gaussian": sm.families.Gaussian,
            "binomial": sm.families.Binomial,
            "poisson": sm.families.Poisson}[name]()


def to_numeric_result(value):
    v = float(value)
    return float(f"{v:.8g}") if math.isfinite(v) else None


def analysis(spec: dict, frame, qc: dict) -> dict:
    import numpy as np
    import statsmodels.formula.api as smf
    d = spec["design"]
    formula, contrast = formula_for(spec)
    cluster = d.get("cluster")
    options = {"cov_type": "HC3"}
    clusters = None
    warning = []
    if cluster:
        clusters = int(frame[cluster].nunique())
        if clusters >= 10:
            options = {"cov_type": "cluster", "cov_kwds": {"groups": frame[cluster]}}
        else:
            warning.append("Fewer than 10 clusters; reported HC3 only, not clustered inference")
    try:
        model = smf.glm(formula, data=frame, family=family_obj(d["family"]))
        result = model.fit(maxiter=250, disp=0, **options)
        if contrast not in result.params.index or not np.isfinite(result.params[contrast]):
            raise ValueError("No identified treatment coefficient")
        if int(np.linalg.matrix_rank(result.model.exog)) < result.model.exog.shape[1]:
            warning.append("Design matrix is rank-deficient; coefficient interpretation may be unstable")
        beta, se = float(result.params[contrast]), float(result.bse[contrast])
        if not (math.isfinite(beta) and math.isfinite(se) and se > 0):
            raise ValueError("Coefficient or standard error is not finite")
        ci = [beta-1.96*se, beta+1.96*se]
        output = {
            "status": "estimated_association_not_causal", "formula": formula,
            "family": d["family"], "method": d["method"],
            "contrast": contrast, "coefficient": to_numeric_result(beta),
            "standard_error": to_numeric_result(se),
            "confidence_interval_95": [to_numeric_result(x) for x in ci],
            "p_value_exploratory": to_numeric_result(result.pvalues[contrast]),
            "sample_n": int(len(frame)), "cluster_count": clusters,
            "variance": options["cov_type"],
            "warnings": warning + ["No multiplicity correction or causal identification proof"],
        }
        if d["family"] in ("binomial", "poisson"):
            output["exp_coefficient"] = to_numeric_result(math.exp(max(min(beta, 700), -700)))
        return output
    except (ValueError, ArithmeticError, RuntimeError, np.linalg.LinAlgError) as exc:
        return {"status": "estimation_failed", "reason": type(exc).__name__ + ": " + str(exc)[:350],
                "formula": formula, "warnings": warning}


def temporal_validation(spec: dict, frame) -> dict:
    """Train strictly before test; compare predictive model with train-only mean."""
    import numpy as np
    import pandas as pd
    import statsmodels.formula.api as smf
    d = spec["design"]
    if d["method"] != "association":
        return {"status": "not_implemented_for_design", "reason":
                "Predictive validation for DiD/RDD needs a design-specific estimand and holdout; not faked"}
    unique = sorted(frame[d["time"]].unique())
    if len(unique) < 20:
        return {"status": "insufficient_temporal_coverage", "n_unique_dates":len(unique)}
    split = int(len(unique) * (1 - d.get("holdout_fraction", 0.25)))
    boundary = unique[split]
    train = frame.loc[frame[d["time"]] < boundary].copy()
    test = frame.loc[frame[d["time"]] >= boundary].copy()
    if len(train) < 30 or len(test) < 10:
        return {"status": "insufficient_train_or_holdout", "train_n":len(train),"test_n":len(test)}
    model_formula, _ = formula_for(spec, predictive=True)
    outcome = d["outcome"]
    try:
        fitted = smf.glm(model_formula, data=train, family=family_obj(d["family"])).fit(maxiter=200,disp=0)
        pred = np.asarray(fitted.predict(test), dtype=float)
        if not np.all(np.isfinite(pred)):
            raise ValueError("Nonfinite predictions")
        base = np.full(len(test), float(train[outcome].mean()))
        observed = test[outcome].to_numpy(dtype=float)
        if d["family"] == "binomial":
            pred = np.clip(pred,0,1)
            metric="brier"
            score=lambda p:float(np.mean((observed-p)**2))
        elif d["family"] == "poisson":
            pred = np.maximum(pred,1e-9)
            base = np.maximum(base,1e-9)
            metric="mean_poisson_deviance"
            def score(p):
                return float(2*np.mean(np.where(observed>0,observed*np.log(np.maximum(observed,1e-9)/p),0)-(observed-p)))
        else:
            metric="rmse"
            score=lambda p:float(np.sqrt(np.mean((observed-p)**2)))
        s_model,s_base=score(pred),score(base)
        return {"status":"holdout_scored","metric":metric,
                "train_n":int(len(train)),"test_n":int(len(test)),
                "train_last_date":str(pd.Timestamp(train[d["time"]].max()).date()),
                "test_first_date":str(pd.Timestamp(test[d["time"]].min()).date()),
                "model_score":to_numeric_result(s_model),
                "train_mean_baseline_score":to_numeric_result(s_base),
                "score_improvement_over_baseline":to_numeric_result(s_base-s_model),
                "model_better_than_baseline":bool(s_model < s_base),
                "warnings":["Temporal split is not spatial/actor holdout or proof of generalization",
                            "Predictive model intentionally omits fixed effects for unseen time categories",
                            "A no-leakage assertion still requires independent variable provenance review"],
                }
    except (ValueError, ArithmeticError, RuntimeError, np.linalg.LinAlgError) as exc:
        return {"status":"predictive_fit_failed","reason":type(exc).__name__+": "+str(exc)[:350]}


def markdown_table(estimate: dict, heldout: dict) -> str:
    if estimate.get("status") != "estimated_association_not_causal":
        return "Estimation failed: no quantitative result is asserted."
    lines = ["| Quantity | Estimate |", "| --- | ---: |",
             f"| Treatment contrast | `{estimate['contrast']}` |",
             f"| Model coefficient | {estimate['coefficient']} |",
             f"| Robust standard error | {estimate['standard_error']} |",
             f"| Exploratory p-value | {estimate['p_value_exploratory']} |",
             f"| 95% CI | {estimate['confidence_interval_95']} |",
             f"| Observations | {estimate['sample_n']} |"]
    if heldout.get("status") == "holdout_scored":
        lines.extend(["",f"Out-of-sample {heldout['metric']}: {heldout['model_score']} vs ",
                      f"{heldout['train_mean_baseline_score']} for a train-mean baseline."])
    return "\n".join(lines)


def render_manuscript(spec, fit, holdout, data_qc) -> str:
    bibliography = spec.get("literature", [])
    text = [f"# {spec['title']}", "",
            "**AUTOMATED RESEARCH DRAFT — NOT A SUBMISSION-READY OR PEER-REVIEWED PAPER.**", "",
            "## Abstract (descriptive placeholder)", "",
            f"We examine: {spec['research_question']}",
            f"The proposed (unverified) mechanism is: {spec['mechanism']}",
            f"The design uses a {spec['design']['method']} {spec['design']['family']} model;",
            "findings below are observational/model-dependent and do not establish causality.", "",
            "## 1. Introduction and research puzzle", spec['research_question'], "",
            "## 2. Related literature and novelty limits", "",
            "The following references were supplied in the specification; their relevance, full texts and claims require human verification.", ""]
    if bibliography:
        for i,ref in enumerate(bibliography,1):
            text.append(f"{i}. {ref.get('authors','Author unprovided')} ({ref.get('year','n.d.')}). *{ref['title']}*. {ref.get('doi',ref.get('url','Source location unprovided'))}.")
    else:
        text.append("**No verified references supplied. Cannot claim novelty or literature coverage.**")
    text.extend(["", "## 3. Theory and hypotheses", "",
                 "The mechanism is a hypothesis, not an equilibrium derivation.", ""])
    for h in spec['hypotheses']:
        text.append(f"**{h['id']}** ({h['sign']}): {h['prediction']}")
    text.extend(["", "## 4. Data and design", "",
                 f"Outcome: `{spec['design']['outcome']}`; treatment: `{spec['design']['treatment']}`.",
                 f"Observations analyzed: {data_qc['analysis_rows']}. Missing numeric rows removed: {data_qc['dropped_missing_numeric_rows']}.",
                 "Data source and sampling must be described from the original provenance documents; none is fabricated here.", "",
                 "## 5. Results (exploratory)", "",
                 markdown_table(fit,holdout), "",
                 "## 6. Interpretation and robustness gaps", "",
                 "Even when a coefficient differs from zero, identifying assumptions, selection, measurement, alternative explanations and multiple-testing corrections remain unresolved.", "",
                 "## 7. Conclusion and forecasting implications", "",
                 "A defensible substantive conclusion requires human scientific review, additional specifications and external replication.", "",
                 "## Replication and research integrity", "",
                 "See `replication_manifest.json` for the data hash, run command, code version, and reproducibility conditions.",
                 "This draft must not be submitted or treated as an empirical finding without human approval.", ""])
    return "\n".join(text)


def gate_report(spec, fit, holdout, qc) -> dict:
    checks={
        "human_novelty_review":spec['novelty_review']['status']=='approved',
        "non_synthetic_data":not spec['data']['synthetic'],
        "statistical_estimation_completed":fit.get('status')=='estimated_association_not_causal',
        "temporal_oos_completed":holdout.get('status')=='holdout_scored',
        "bibliography_provided":bool(spec.get('literature')),
        "source_data_located_and_hashed":bool(qc.get('data_sha256')),
        "causal_identification_independently_approved":False,
        "formal_theory_derivation_verified":False,
        "replication_independently_executed":False,
        "human_manuscript_review":False,
    }
    return {
        "status":"draft_not_publication_ready", "passes":checks,
        "unmet_gates":[k for k,v in checks.items() if not v],
        "disclaimer":"These are workflow gates, not a numerical paper quality score",
    }


def run(spec_file: Path, *, destination: Path | None = None, force: bool = False) -> dict:
    spec_file = spec_file.expanduser().resolve()
    spec = validate_spec(read_json(spec_file))
    p = plan(spec_file)
    if not p['ready_to_run']:
        return {"status":"blocked_before_analysis","plan":p}
    source = data_file(spec,spec_file)
    target = Path(destination).expanduser().resolve() if destination else DEFAULT_RUNS / spec['id']
    # Only write under local research/projects/ or an explicitly user-supplied --out.
    if target.exists() and not target.is_dir():
        raise ValueError("Output destination is not a directory")
    signature = digest((VERSION+digest(spec_file.read_bytes())+digest(source.read_bytes())).encode('utf-8'))
    previous=target/'state.json'
    if previous.is_file() and not force:
        cached=read_json(previous)
        if cached.get('signature')==signature and cached.get('status')=='prototype_complete':
            return {"status":"reused_cached_run","path":str(target),
                    "data_rows":cached.get('analysis_rows'),"quality":cached.get('quality')}
    target.mkdir(parents=True,exist_ok=True)
    state={"version":VERSION,"id":spec['id'],"signature":signature,
           "status":"processing","started_utc":datetime.now(timezone.utc).isoformat()}
    write_json(previous,state)
    try:
        theory,design=framing(spec)
        atomic_text(target/'theory_workbook.md',theory)
        atomic_text(target/'design_workbook.md',design)
        frame,qc=read_data(spec,source)
        state['analysis_rows']=qc['analysis_rows'];state['status']='estimating'
        write_json(previous,state)
        fit=analysis(spec,frame,qc)
        heldout=temporal_validation(spec,frame)
        results={"study_id":spec['id'],"data_quality":qc,"model":fit,
                 "predictive_validation":heldout,
                 "scientific_status":"exploratory_prototype_not_causal"}
        write_json(target/'results.json',results)
        manuscript=render_manuscript(spec,fit,heldout,qc)
        atomic_text(target/'MANUSCRIPT_DRAFT.md',manuscript)
        quality=gate_report(spec,fit,heldout,qc)
        write_json(target/'QC_REPORT.json',quality)
        atomic_text(target/'QC_REPORT.md',"# Research Factory quality gate\n\n"+
                    "\n".join(f"- [{'x' if v else ' '}] {k}" for k,v in quality['passes'].items())+"\n")
        # Raw data are deliberately NOT copied, even when some sources could be shared.
        replication={
            "version":VERSION,"source_spec":str(spec_file),"source_data":str(source),
            "data_sha256":qc['data_sha256'],"redistribution_allowed":spec['data']['redistribution_allowed'],
            "source_data_included":False,
            "command":f"python -m research.factory.prototype run '{spec_file}' --out '{target}' --force",
            "environment":"Install research/requirements.txt; run in the research branch",
            "manuscript_status":"unreviewed_draft",
        }
        write_json(target/'replication_manifest.json',replication)
        state.update(status="prototype_complete",completed_utc=datetime.now(timezone.utc).isoformat(),
                     quality=quality,results_file=str(target/'results.json'))
        write_json(previous,state)
        return {"status":"prototype_complete","path":str(target),"analysis_rows":qc['analysis_rows'],
                "estimate":fit,"predictive_validation":heldout,"quality":quality,
                "written_files":[x.name for x in sorted(target.iterdir()) if x.is_file()]}
    except Exception as exc:
        state.update(status="failed_retryable",failure_type=type(exc).__name__,
                     failure_reason=str(exc)[:300])
        write_json(previous,state)
        raise


def make_demo(folder: Path) -> Path:
    """Seeded synthetic positive-treatment experiment; illustrative NOT evidence."""
    folder.mkdir(parents=True,exist_ok=True)
    data=folder/'SYNTHETIC_data.csv'
    rng=random.Random(104729)
    with data.open('w',newline='',encoding='utf-8') as fp:
        writer=csv.writer(fp)
        writer.writerow(['day','unit','treatment','baseline_risk','outcome'])
        from datetime import date,timedelta
        first=date(2024,1,1)
        for day in range(100):
            for unit in range(12):
                treat=int(rng.random()<0.45)
                baseline=0.2+0.15*rng.random()
                prob=1/(1+math.exp(-(-2.2+0.9*treat+2.0*baseline)))
                writer.writerow([(first+timedelta(days=day)).isoformat(),
                                 f'unit_{unit:02d}',treat,round(baseline,5),
                                 int(rng.random()<prob)])
    spec={
        "id":"factory-demo", "title":"Synthetic Crisis Escalation Demonstration",
        "research_question":"Does an entirely synthetic intervention correlate with binary crisis escalation?",
        "mechanism":"Illustrative: the simulated treatment shifts event risk; this is a constructed data-generating process, not IR evidence.",
        "hypotheses":[{"id":"H1","prediction":"Synthetic treatment raises simulated escalation risk", "sign":"positive"}],
        "data":{"csv_path":data.name,"redistribution_allowed":True,"synthetic":True},
        "design":{"method":"association","family":"binomial","outcome":"outcome",
                  "treatment":"treatment","time":"day","unit":"unit",
                  "controls":["baseline_risk"],"cluster":"unit","holdout_fraction":0.25},
        "literature":[],"novelty_review":{"status":"demo_only"},
    }
    name=folder/'factory_demo.json'
    write_json(name,spec)
    return name


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="General-purpose research-to-draft factory prototype; zero API charges")
    sub=parser.add_subparsers(dest="command",required=True)
    for cmd in ('plan','run'):
        sub.add_parser(cmd).add_argument('spec',type=Path)
    run_arg=sub.choices['run']
    run_arg.add_argument('--out',type=Path)
    run_arg.add_argument('--force',action='store_true')
    demo=sub.add_parser('demo')
    demo.add_argument('--out',type=Path,default=DEFAULT_RUNS/'factory_demo')
    status=sub.add_parser('status')
    status.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='plan':
            result=plan(args.spec.resolve())
        elif args.command=='run':
            result=run(args.spec,destination=args.out,force=args.force)
        elif args.command=='demo':
            generated=make_demo(args.out.expanduser().resolve())
            result=run(generated,destination=Path(args.out).expanduser().resolve()/'output')
            result['synthetic_demo_only']=True
        else:
            result=read_json(Path(args.out).expanduser().resolve()/'state.json')
        print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
        return 2 if result.get('status')=='blocked_before_analysis' else 0
    except (OSError,ValueError,TypeError,KeyError,ImportError,RuntimeError) as exc:
        print('Research Factory prototype stopped safely: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())

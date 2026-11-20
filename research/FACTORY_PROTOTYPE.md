# Predictioneering Research Factory — runnable prototype v0.1

This is a reusable, **research-only** end-to-end prototype. It is intentionally
separate from the production forecasting pipeline and from the existing Holy
Days modules. It **never** contacts Claude, ACLED, OpenAlex or any network API,
and it cannot publish or merge anything.

## One-command synthetic smoke test

In `~/predictioneering-research-test`, using the existing research Python venv:

```bash
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m pip install -r research/requirements.txt
"$P" -m unittest discover -s research/tests -q
"$P" -m research.factory.prototype demo
```

The `demo` command makes deterministic, explicitly synthetic example data and
runs the entire pipeline in the gitignored `research/projects/factory_runs/`
directory. It produces an **unreviewed** draft, not evidence about conflict.

## One-command research run (after supplying a specification and CSV)

```bash
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m research.factory.prototype plan /path/to/study.json
"$P" -m research.factory.prototype run /path/to/study.json
"$P" -m research.factory.prototype status --out research/projects/factory_runs/STUDY_ID
```

See `research/examples/factory_spec_template.json` for a complete starting
schema. Data CSV paths are resolved relative to the JSON spec file. No raw CSV
is copied into the research package, even if redistribution is permitted.

### Mandatory gating

A real research run must explicitly include:

- A **human** novelty review with `status: approved`, a reviewer name and
  substantive notes, or it halts before estimation and manuscript generation.
- An existing local data CSV and explicit redistribution and synthetic flags.
- A user-supplied, testable hypothesis and a fully specified analysis design.

`status: demo_only` is permitted *only* for synthetic example data. The
factory does not pretend metadata searches establish novelty. It does not
invent empirical data, bibliographic claims, formal proofs, or the theory.

### Supported analysis designs

| Design | Estimation | Predictive holdout |
| --- | --- | --- |
| Association | Gaussian, binomial, Poisson GLM; optional fixed effects, HC3 or clusters | Strict future-date split, proper metric versus train-only mean |
| Difference-in-differences | Binary treatment × post; unit and day FE, robust/clustered uncertainty | Explicitly not implemented (design-specific validation needed) |
| Regression discontinuity | Sharp cutoff, supplied bandwidth, local linear terms | Explicitly not implemented (design-specific validation needed) |

Rough causal assumptions are *not* verified by the estimator. DiD parallel
trends, RDD manipulation/continuity, actor classification, temporal leakage,
multiple testing, and independent scientific replication remain human gates.
Statistical estimates are marked **exploratory, not causal**.

### Outputs (private ignored research/projects)

- `theory_workbook.md` — mechanism and supplied hypotheses, proof obligations
- `design_workbook.md` — estimand/identification worksheet
- `results.json` — real sample statistics or explicit failure status
- `MANUSCRIPT_DRAFT.md` — unreviewed paper *scaffold* with actual numbers only
- `QC_REPORT.json`, `QC_REPORT.md` — formal pass/fail gates
- `replication_manifest.json` — source file hashes, environment and rerun command
- `state.json` — failed/retryable state, idempotent fingerprint and timestamps

### What's still missing for a fully autonomous weekly paper factory

- Automatic forecast-log ingestion from production with puzzle relevance
- Fully integrated literature retrieval, reading and human novelty adjudication
- Real game-theory solving and machine-verifiable proof checks
- Data acquisition/adapters beyond provided local CSV, and wider causal designs
- Advanced robustness, parallel trends, sensitivity, alternative specifications
- Automatic credible citations and narrative writing with source-level checking
- Weekly scheduling, manuscript submission and publication workflow

This prototype deliberately fills the central missing **one-command** bridge
from a reviewed puzzle/data specification to a transparently gated research
draft. The `Holy Days and Hard Bargains` test case remains unrun here.

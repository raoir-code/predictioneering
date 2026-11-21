# Research Factory v0.6 — Formal model → Python → Overleaf sprint

**Scope:** An independently gated **draft-production path** for a researcher-supplied formal game model, its comparative statics, an empirical study specification and a local dataset. No paid model calls, live web scraping, research novelty claims, production edits, submissions or licensed dataset uploads. Draft packages are private and gitignored. **This is not a scientifically complete paper or a model-solving agent.**

## One-command fast acceptance test

From your isolated research checkout:

```bash
cd ~/predictioneering-research-test
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m pip install -r research/requirements.txt
"$P" -m unittest discover -s research/tests -q
"$P" -m research.factory.paper_sprint demo
```

Demo is a **clearly synthetic**, complete-information ultimatum game in which the responder has a known outside option `u` and the proposer offers `x`. For the toy equilibrium `x*=u`, `dx*/du=1`. The demonstration simulates an observable noisy offer from this relation, estimates an exploratory Gaussian regression, calculates a strictly chronological holdout score, renders **two real PDF figures**, and packages a compilable `main.tex`, `references.bib`, results, provenance hashes, and **REVIEW_REQUIRED.md** in an Overleaf-importable ZIP. No theoretical novelty, verified equilibrium, real data or actual citations are claimed.

Example output under `research/projects/factory_runs/paper_sprint_synthetic_demo/package/`:

- `ultimatum-demo_OVERLEAF_DRAFT.zip` — upload as a new Overleaf project; no raw data included
- `overleaf/main.tex` — paper sections, mathematical comparative statics, analysis and limitations
- `overleaf/references.bib` — only source metadata actually supplied; never generated citations
- `overleaf/figures/estimate.pdf`, `overleaf/figures/holdout.pdf` — computed from analysis results
- `overleaf/PAPER_QC.json` — transparent, *failing* scientific review gates
- `overleaf/REVIEW_REQUIRED.md` — actual human approval checklist
- `overleaf/PACKAGE_MANIFEST.json` — input and output provenance hashes

## A real study: model first, then empirical hypothesis

Start from `research/examples/FORMAL_MODEL_TEMPLATE.json` and a reviewed `research/examples/factory_spec_template.json`. The formal JSON requires named players, information, timing, strategies, player payoffs, equilibrium argument, parameter assumptions, the asserted equilibrium expression, and a comparative-static mapping to each H1/H2 and observed dataset predictor/outcome.

```bash
# First: theory → hypothesis scaffold (no regression, no API)
"$P" -m research.factory.paper_sprint hypotheses /path/to/formal_model.json

# The output hypothesis text/sign must match study.json's prespecified H1/H2.
# Then run an existing local study spec with actual private CSV and human novelty approval:
"$P" -m research.factory.paper_sprint run /path/to/study.json \
  --formal-model /path/to/formal_model.json \
  --out research/projects/factory_runs/YOUR_STUDY/paper_sprint
```

The `run` command invokes the existing `prototype.run` in the requested private run folder (or checks the unchanged cached analysis, if `--analysis-dir` is explicitly supplied). It **refuses** a missing dataset, stale analysis fingerprint, mismatched hypotheses, incorrect variable mappings, or unsupported symbolic expression syntax. `sympy` performs the derivative algebra under explicitly supplied sign assumptions. **That does not prove the alleged equilibrium is actually optimal or that its parameters map credibly onto a real-world variable.** Those remain human checks.

The scientific writer does not invent descriptive statistics, tests, novelty, or source claims. It uses actual `results.json` only, and the generated text is visibly labeled an unreviewed shell. Prediction improvements are scored against the existing train-mean baseline where supported; they are not evidence of production improvement. `research.factory.prototype` currently evaluates temporal OOS only for the association design.

## Correct citation contract

Provide real author, year, title, and a valid DOI or HTTPS URL in `study.json`'s `literature` array. Missing or malformed records are explicitly omitted from the `.bib`; none are synthesized. Bibliographic entries alone do not support literature claims.

Optionally, a researcher can supply **page-linked claims** in `study.json`:

```json
"literature_claims": [
  {
    "source_key": "provided001",
    "page": 13,
    "claim": "Precise researcher-written paraphrase of the cited author's argument.",
    "verbatim_quote": "A short passage transcribed from the actual source.",
    "human_quote_checked": true
  }
]
```

The factory includes these only if the source key exists, the page is plausible and a reviewer attests that the quote was checked. It renders `\cite[p.~13]{provided001}` rather than an unattributed assertion. **The tool does not possess the original source pages and cannot independently verify that claim or quotation.** The final human must re-check every citation; the `claim_to_source_citations_independently_checked` gate stays FALSE.

## Hard stops and missing capabilities

- Real puzzle adjudication/verified Claude investigative diagnoses, original historical news and game theory source retrieval are still **unfinished**.
- There is **no autonomous formal game solver**; a researcher or Claude must first write the proposed equilibrium and proof. The machine verifies **derivative algebra only, conditional on the supplied equilibrium**.
- The package is a LaTeX *working-paper draft*, **not a completed journal submission**. Lit review and contribution still require actual PDF-based source checks; variables and causal identification need review; robustness, nonlinear structural estimation, multiple-testing control, full replication and final human manuscript signoff remain incomplete.
- Compilation is tested automatically only on machines with `pdflatex`; **Overleaf can compile without a local TeX installation**. The ZIP does not include raw research data, API keys or paid article contents.

**Next sprint:** complete one real research pilot end-to-end after a forecast case has passed factual and theoretical diagnosis. Then iterate on source-claim verification, formal proof checks, robust estimators, source-linked drafting, and independent replication. The synthetic fast path proves wiring, not scientific acceptance.

# Research Factory — Master MVP Checklist

**Updated:** November 23, 2026  
**Branch:** `research/puzzle-finder-phase1-20261119` (draft PR, separate from production)

**Goal:** Turn one real IR puzzle into a defensible formal model, testable hypotheses, reproducible estimates, and an Overleaf-ready paper with figures, tables, citations, and a replication bundle. **Ship one complete paper pipeline before expanding the factory.**

## Target workflow

**Puzzle → Literature + Novelty → Formal Model → Hypotheses → Research Design → Data → Analysis → Validation → Manuscript → Final QC**

- Fold **Diagnosis** into Puzzle; run forecast-miss forensics only for puzzles originating in forecasting errors.
- Fold **Novelty** into Literature; a standalone novelty gate adds little if the literature synthesis evaluates the contribution.
- Keep **Design** distinct from **Data**, but check data feasibility *while* designing.
- Require human decisions at meaningful scientific checkpoints, not paperwork for its own sake.
- Preserve Holy Days' existing approvals and audit history when simplifying the current 12-stage controller. **This checklist does not yet change the code.**

## Where we stand

- [x] Isolated research branch; versioned human approvals, revisions, and audit trail.
- [x] 259 tests passed on Mac (November 23); Holy Days puzzle, diagnosis, and **preliminary** literature screening approved.
- [~] Zotero/local-PDF passage index and seven targeted Holy Days literature leads; **full original-paper synthesis is not built**.
- [~] `paper_sprint.py` prototype: accepts a supplied game, checks some symbolic derivatives, runs prototype estimators/holdout, and generates figures and LaTeX. **Does not discover/solve a genuine model or produce a validated real paper.**
- [ ] Full real-data, end-to-end paper demonstrated.

## P0 — Ship the MVP (in order)

- [ ] **1. Literature + contribution.** Read closest original papers; audit claims/pages; synthesize rival explanations and contrary results; state a narrow, defensible gap. No irrelevant citations or novelty-by-absence.
- [ ] **2. Formal model.** Generate the simplest suitable bargaining/strategic game; specify timing, information, actions and payoffs; derive and check equilibrium conditions, not just derivatives.
- [ ] **3. Hypotheses.** Translate *proved* model predictions into falsifiable, measurable implications with explicit scope conditions.
- [ ] **4. Research design.** Choose outcomes, unit, estimand, controls, identification strategy and robustness tests. Use DiD/RDD only with a credible design; assess accessible data before locking the plan.
- [ ] **5. Data procurement.** Obtain an authorized real dataset; validate calendar/events, actor direction, coverage and missingness; record licenses, versions, source hashes and joins.
- [ ] **6. Analysis.** Run reproducible estimators, diagnostics, alternatives, nulls and uncertainty; export publication-ready tables and figures from actual results.
- [ ] **7. Validation.** Reproduce end-to-end and check leakage, identification assumptions and robustness. OOS forecasting only when scientifically relevant.
- [ ] **8. Manuscript.** Generate a compiling Overleaf-ready `.tex`, verified `.bib`, figures, tables, appendix, and replication instructions; no invented citations, proofs or findings.
- [ ] **9. End-to-end acceptance.** Run **Holy Days** from approved puzzle through a genuine empirical result and compiled draft, or switch to a more feasible real puzzle if data/theory block it. Human approves scientific substance; QC checks the artifact.

**Next coding task:** Connect the existing formal-model/estimation/LaTeX prototype into one resumable run with real inputs and explicit failure states. Close the literature/full-text gap before claiming a novel contribution.

## Later — Not MVP blockers

- [ ] Streamline the 12-stage approval implementation to the target workflow without destroying historical decisions; then build the CK2-style approve/revise UI.
- [ ] Ingest and scientifically profile the entire Zotero PDF library with incremental caching.
- [ ] Automate weekly puzzle discovery, forecast-miss dossiers, independent critiques, and paper-revision cycles.
- [ ] Expand data connectors and integrate validated results back into Predictioneering after separate authorization.

**Guardrails:** Source-grounded claims; honest nulls and uncertainty; no fabricated equilibria, causal identification or references; keep private PDFs/data off public GitHub; authorize paid API use explicitly; never alter production forecasting code during factory development.

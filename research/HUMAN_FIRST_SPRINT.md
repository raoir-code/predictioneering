# Next-build roadmap — human-first Holy Days pilot

The review controller was corrected so only the researcher can approve a stage. No AI critique required; AI review remains opt-in. The prior Holy Days `awaiting_critique` record is preserved and is now directly approvable. The current actionable next step is review of the existing puzzle proposal, then a separately gated theoretical/measurement diagnosis.

Remaining production sequence, each with a user report, explicit sign-off and ability to revise only affected work:

1. **Literature worker:** Search original PDFs and scholarly indexes; perform full-text argument, game-model, and evidence comparison; verify every citation and record missing papers. Do not infer novelty from metadata.
2. **Novelty worker:** Compare most similar existing models and let the researcher approve a specific gap or reject it.
3. **Formal model worker:** Construct games, solve equilibria and derive comparative statics with independent mathematical verification before sign-off.
4. **Hypotheses worker:** Derive operational, falsifiable predictions from the approved model, without post-hoc fitting.
5. **Data worker:** Search repositories and ACLED/Zotero/private sources, score coverage, measurement validity and rights, acquire approved inputs, and request a human decision on compromises.
6. **Design worker:** Lock the estimand, covariates, DAG, time splitting, and uncertainty/identification checks.
7. **Analysis and validation workers:** Reuse the working Python statistics, figures and temporal holdout infrastructure; add sensitivity, falsification and independent replication as needed.
8. **Manuscript and QC workers:** Reuse the working Overleaf package generator, then substantively check every claim, equation, figure and original-source citation.
9. **Revision agent:** With an explicitly authorized model call, use the frozen previous artifact plus your natural-language change request, produce a real new version and show a change log. Never claim a work order alone fixes the science. Never autoapprove.

All adapters must call `review_workflow.require_ready` before executing and `submit` after producing work. This roadmap is **not** a claim that autonomous research workers for all these tasks are complete.

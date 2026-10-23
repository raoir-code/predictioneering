# Theory test 5 (pre-registered Oct 23, 2026): do rivalries change phase? (recent vs long-run restart record)

H6 (strategic-rivalry escalation phases: Colaresi, Rasler & Thompson 2007; Diehl & Goertz 2000): a directed pair's RECENT record of
starting episodes predicts resuming strikes beyond its long-run record (rivalry intensity is persistent but time-varying, so a
constant-rate model averages regime shifts away; e.g. Israel <-> Iran: ~0.5/yr over 2015-2026 vs ~1.8/yr since 2024).
Data, episodes, spells and model: exactly theory test 4 (docs/theory_test4_prereg.md), including the G + 1 clock, with two added
covariates measured at each spell-week, using only episodes that STARTED BEFORE that week:
  recent = log(1 + episode starts in the preceding 730 days)
  older  = log(1 + episode starts per year from the pair's first observed strike to 730 days before that week; 0 if none)
Decision rule: H6 supported iff the `recent` coefficient is > 0 with p < 0.05 under ALL THREE G (14, 30, 60), with `older` in the
model. Reported in full either way, including whether `older` remains significant once `recent` is included.
If supported: production use (restart rates estimated with recent years weighted more) gets its own pre-registered held-out replay.

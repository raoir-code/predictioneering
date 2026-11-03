# Pre-registration: what does the engine lose if the local tables go stale or go away? (Nov 3, 2026)

Written before any run on real data. Script: `analysis/degradation_replay.py` (synthetic checks pass; the arms were smoke-tested
with repo priors and a fabricated anchor table). Report only: it writes one result file and never touches the engine's own files.

## Why

- After the local data ends, the unified engine's priors, hardening and last-strike anchors can at best be kept frozen, and at
  worst must be deleted (production then falls back to repo priors, no hardening, no anchors).
- Which of these actually carries forecast skill decides what matters in the licensing question and in the final refresh
  (Nov 19–20). Scored on resolved contracts, the answer key we keep (`docs/answer_key_agreement_result.md`).

## Replay (fixed now)

The replay of `docs/contract_def_refit_prereg.md`, unchanged: `analysis/refit_compare.score_rows`, every resolved strike contract
first forecast on or after 2026-07-01, priced at production's first-forecast time with the news cache as it stood then; ceasefire
"holds" contracts and the old engine are out of scope. Arms:

| Arm | Priors | Hardening | Last-strike anchors |
|---|---|---|---|
| **FULL** (baseline) | held-out world fit (data ≤ 2026-06-30) | production β, K | full table, ≥ 7 days before the forecast |
| **STALE** | as FULL | as FULL | table cut at 2026-06-30: the data ends as the replay starts |
| **NOHARDEN** | as FULL | off | as FULL |
| **REPO** | repo priors | off | none (production with `pilot/local/` deleted) |

Only contracts priced in every arm are scored.

## Rule (fixed now)

- For each arm: ΔBrier = Brier(arm) − Brier(FULL), 95% interval by bootstrap over pairs (2,000 draws).
- **LOAD-BEARING** if the lower bound > 0: losing that component costs forecast skill. It gets priority in the final refresh and in
  the licensing question.
- **NOT LOAD-BEARING** otherwise: losing it costs nothing we can detect.
- Reported, not deciding: YES and NO separately; ΔBrier by month of first forecast (STALE should grow with time since the cut); by
  pair; the market at the same moment.

## Known before registration

- FULL is the contract-definition replay's "broad" arm (Brier 0.1439, n = 119 on Nov 3); hardening's own held-out replay gave
  Brier(with) − Brier(without) = −0.0045 [−0.0210, +0.0044] (`docs/hardening_result.md`); the held-out refit replay (`docs/refit_result.md`). None of these
  ran the STALE or REPO arms.

## Known limits

- **The held-out priors are already frozen at June 30**, so the cost of priors ageing is measured only through REPO (older, coarser).
- **STALE ages anchors by up to ~3.5 months**, about what the end of the local data means by March 2027; longer gaps are extrapolation.
- **The replay's news cache is the live stream as it was** (starved for several pairs until Nov 2), so STALE's news refresh is
  weaker than it will be with the full-recall feed.

# Pre-registration: strike rates on the contract definition, fighting state on the broad one (Nov 4, 2026)

Written before any run on real data. Script: `analysis/q_contract.py` (synthetic checks pass; the build path was smoke-tested on
fabricated rows). Roadmap step 1.

## Why

- `docs/no_day_diagnosis_prereg.md` (`0021ddf`): 81.5% of our excess Brier over the market on NO outcomes comes from **fighting
  days without a qualifying strike** (class A). By the rule, the lever is the strike rate q, not the state. Israel→Syria carries
  70% of class A, Saudi Arabia→Yemen 28%.
- The engine's prior centres for q and q0 are the world fit's `p_rec_F` and `p_rec_N`. Those are rates at which the event data
  records **broad** activity (air/drone plus all shelling) on fighting and quiet days (`analysis/pair_fits.py`: "an observation
  process, never the contract strike rate"). Where a pair mostly shells (Israel→Syria), the prior expects qualifying strikes on
  almost every fighting day, and a pair with few resolved contracts never moves far from it.
- The contract-definition refit (`docs/contract_def_refit_result.md`, not adopted) redefined everything, including what counts
  as fighting; that shortened Lebanon's fighting episodes and cost it. **This specification is different and narrower:**
  fighting stays broad (shelling is fighting), and only the rate of contract-qualifying strikes during fighting and quiet changes.
  It is a second specification, motivated by the diagnosis; we say so here rather than hide it.

## Method (fixed now)

- For each world pair, keep the fitted state model (h, μ and the broad emission) exactly as it is.
- Forward-backward on the broad daily series gives P(fighting) for every day.
- **q_contract** = Σ P(fighting)·[contract-qualifying strike that day] / Σ P(fighting); **q0_contract** the same with P(quiet).
  Days where either series is only imprecisely dated are skipped. "Contract-qualifying" = `contract_def_refit.qualifies`
  (air/drone strikes; shelling/missile events only where the attacker's home state shares no land border with the target).
- These two numbers replace `p_rec_F` and `p_rec_N` in a copy of `world_fits.json` (originals kept as `p_rec_F_broad`,
  `p_rec_N_broad`). Nothing else changes: h, μ, `priors_world.json`, hardening, anchors, the engine code. Coalition pairs (q prior
  0.5 in the engine, e.g. Saudi Arabia→Yemen) are unaffected.

## Arms and replay

- **FULL:** held-out world fit (`pilot/local/heldout/`, data ≤ 2026-06-30), production hardening, current anchors.
- **QC:** the same with `pilot/local/heldout_qc/world_fits.json` (contract emissions computed on the same held-out window).
- Replay: `analysis/refit_compare.score_rows` via `contract_def_refit.arm`, unchanged (resolved strike contracts first forecast on or
  after 2026-07-01, priced at production's first-forecast time).

## Adoption rule (fixed now; the same as the contract-definition refit)

Adopt if **both**: (1) Brier(QC) ≤ Brier(FULL); (2) no pair with ≥ 3 replayed contracts worse by more than 0.05.
If adopted: `pilot/local/candidate_qc/world_fits.json` (contract emissions on the production fit's own window) replaces
`pilot/local/world_fits.json`; the previous file is kept in a dated backup folder. One engine change, its own run, a patch note.
Reported, not deciding: the cluster-bootstrap interval by pair, YES/NO split, every pair; `--describe` (broad vs contract
emissions for the traded pairs, no outcomes).

## Known before registration

- The NO diagnosis above; the contract-definition refit's per-pair results (Israel→Syria 0.450 → 0.391; Lebanon 0.060 → 0.078);
  T3's FULL Brier 0.1439 on 119 contracts.

## Known limits

- **Geography stands in for missile vs artillery** (the local data has no notes text): cross-border missiles between neighbours are
  missed, expeditionary artillery is counted.
- **Pairs with many resolved contracts barely move** (their own windows dominate the q posterior); the change matters for pairs
  priced mostly from the prior.
- **Data-bound:** needs the local data; must run before Nov 23.

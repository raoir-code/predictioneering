# Result: local strike days vs resolved strike contracts: BREAK (Nov 3, 2026)

Pre-registration: `docs/answer_key_agreement_prereg.md` (`8f7bbd6`, before the join). Script: `analysis/answer_key_agreement.py --measure`.
Local data through 2026-10-09. 110 resolved strike contracts (64 YES, 46 NO); 15 unmapped (sub-territories, European collectives,
Iran→Egypt/Ukraine, Saudi Arabia→Iran, Pakistan→Yemen).

## Verdict: BREAK

| | Estimate | 95% | Gate (lower ≥ 0.9) |
|---|---|---|---|
| P(local yes \| contract YES) | 0.859 | (0.703, 0.983) | fail |
| P(local no \| contract NO) | **0.652** | (0.500, 0.795) | fail |

Agreement 0.773, kappa 0.52. Sensitivity (any date precision, ±1 day): 0.922 (0.784, 1.0) and 0.565 (0.389, 0.75): BREAK.
By kind: dailies 0.974 / 0.579; by-date windows 0.692 / 0.704.

**By the rule:** results scored on the local data and results scored on resolved contracts are never pooled. Past detection and
calibration results remain statements about the local definition.

## Where the definitions diverge (25 disagreements)

**The local data says "strike" when the contract resolved NO (16 of 46 NO contracts):**
- **Israel→Syria** (3 by-date NOs; local strike days throughout): artillery, as found in `docs/contract_def_refit_result.md`.
- **Saudi Arabia→Yemen** (3 dailies, 1 by-date): local strike days on every NO date. Most likely border shelling, which the dailies
  (Saudi armed forces, air/missile only) do not count.
- **Iran→Oman** (3 by-date), **Iran→Iraq** (1), **Iran→Gulf/Arab country** (4 dailies): local events the contracts did not count
  (likely strikes on vessels or Kurdish groups in Iraq, or interceptions coded as attacks).
- **Israel→Lebanon** (1 daily, Sep 18).

**The contract resolved YES with no local strike (9 of 64 YES):**
- **Iran→UAE, Iran→Jordan, Iran→Bahrain** ("Will Iran target X by …", 8 contracts): no local strike days at all in the window. The
  "target" template likely counts launches at the territory, intercepted or not; the local data codes impacts.
- Iran→Arab country, Aug 31 (1 daily).

## Reading

- **The local definition is broader on fighting pairs and narrower on "target" ladders.** On NO days it sees strikes the contracts
  do not count, so an engine fit on it carries a hazard that is too high for those pairs. That matches where we lose: the NO
  outcomes (Brier 0.448 in the refit replay) and Israel→Syria.
- **Dailies agree on YES (0.97) but not on NO (0.58).** The daily disagreements are concentrated in Saudi→Yemen and the Iran
  dailies: definition, not timing.
- **Resolved contracts are the right answer key going forward.** They are the estimand we are scored on.
- **The engine is unchanged.** The earlier contract-definition refit (air/drone plus geography-based missiles) was not adopted. A
  per-pair definition after seeing these results would be a forking path. A pair-specific correction is a candidate for its own
  pre-registration, scored on resolved contracts only.

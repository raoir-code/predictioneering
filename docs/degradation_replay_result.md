# Result: degradation replay: all three components LOAD-BEARING (Nov 3, 2026)

Pre-registration: `docs/degradation_replay_prereg.md` (`60df9bc`, before the run). Script: `analysis/degradation_replay.py --measure`.
119 resolved strike contracts first forecast on or after 2026-07-01, priced in every arm. FULL reproduces the contract-definition
replay's broad arm exactly (0.1439).

| Arm | Brier | ΔBrier vs FULL | 95% (pairs) | YES / NO | Grade |
|---|---|---|---|---|---|
| FULL | 0.1439 | – | – | – | – |
| STALE (anchors cut at Jun 30) | 0.1472 | +0.0033 | [+0.0002, +0.0165] | +0.004 / 0.000 | LOAD-BEARING (barely) |
| NOHARDEN | 0.1598 | +0.0158 | [+0.0026, +0.0380] | +0.024 / −0.033 | LOAD-BEARING |
| REPO (everything local deleted) | 0.1650 | +0.0210 | [+0.0048, +0.0696] | +0.029 / −0.024 | LOAD-BEARING |
| Market | 0.1293 | | | | |

## Reading

- **Deleting everything costs about 0.021 Brier**, more than our whole gap to the market (0.015). It would take us from 0.144 to
  0.165 against a market at 0.129.
- **Hardening carries most of it** (+0.016). It helps YES days and hurts NO days, as in its own replay (`docs/hardening_result.md`:
  YES better, NO worse). That replay's overall interval included zero (−0.0045 [−0.0210, +0.0044], other priors, holds included);
  on this set it is clearly load-bearing.
- **Stale anchors cost little and not where expected.** The cost does not grow month by month (Aug +0.027, Sep and Oct +0.001),
  because resolved contracts and news sightings refresh the anchor for busy pairs (Israel→Lebanon +0.000). It falls on pairs with
  few resolutions and a starved news stream: **Israel→Syria +0.050**.
- **REPO's damage is concentrated:** Iran→Iraq +0.155, Iran→Bahrain +0.151, Iran→UAE +0.073, Israel→Syria +0.041, Saudi→Yemen
  +0.019. Its gains (Iran→Jordan −0.040, Iran→Arab country −0.013) are on 3–8 contracts.

## What follows

- **Priority for what to keep after the data ends (licensing question):** (1) hardening β and K: two numbers, the largest share;
  (2) the world priors; (3) the last-strike anchors, the smallest.
- **If derived tables cannot be kept, the fallback costs ≈ 0.02 Brier.** The contingency is an open-data refit (priors and
  hardening on UCDP GED, REFIT-GRADE directions per `docs/open_events_agreement_result.md`), scored on this replay against FULL and
  REPO. It must run before the local data ends, while FULL can still be computed.
- **The final anchor refresh (Nov 19–20) is worth doing** but matters mainly for Israel→Syria-type pairs.
- Nothing changes in production.

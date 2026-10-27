# Pre-registration: does the unified engine respond correctly to *true* quiet? (Oct 27, 2026)

Quiet-days plan, Part 5. Written before any real-data run. Script: `analysis/quiet_calibration.py`. Harness checks pass
(`--synthetic`, including the production pricer run on synthetic contracts), and the real-data path was smoke-tested on
fabricated rows. Report only. Nothing here changes production.

## Why

Two questions are tangled together in "overshoot on hot dyads":

1. Does the engine *see* quiet? It does not. `docs/detection_result.md` and `docs/gdelt_detection_result.md` both fail.
2. Given quiet it could see, does the engine *respond* correctly?

This test answers the second question on its own. It hands the engine the true strike record, as if every day were known,
so any remaining miscalibration belongs to the model's response (restart rate, hardening, war length), not to observation.

## Design

- **Pricer:** the production one (`pilot/unified_price.price_group`), unchanged.
- **Inputs, held out to June 30:**
  - the world fit in `pilot/local/heldout/` (data ≤ 2026-06-30)
  - held-out hardening (`pilot/local/hardening_heldout.json`)
  - news reports off; rivalry phase off (not adopted)
  - the last-strike table built from the true record. The engine reads only strikes at least 7 days before the forecast day.
- **Truth:** the same definition as the world fit: state X's forces, an air/drone strike or a shelling/artillery/missile
  attack, located in Y.
- **Universe:** world-fit directions with at least 5 true strike days in Apr 1 to Jun 30, 2026 (decided before the test
  window).
- **Forecast origins t:** every 3rd day from Jul 1, while t + 29 ≤ the event data's last complete day. A direction enters
  at t only if it has at least one true strike in the previous 60 days (a hot direction).
- **Each forecast:**
  - Evidence: 60 daily contracts for days t−60 … t−1, each carrying its true outcome.
  - Priced: two by-date contracts, "at least one strike in [t, t+W−1]", for W = 7 and W = 30.
- **Grouping:** by k, the days since the last true strike before t, in bins 1–2, 3–6, 7–13, 14–29 and 30–60.

## Measure

For each (W, k bin): mean forecast − observed rate, with a 95% bootstrap interval over directions (2,000 draws).

## Decision rule (fixed now)

- **Which cells count:** k ≥ 3, with at least 5 directions and at least 30 forecasts. Smaller cells are reported only.
- **A cell fails** if |mean forecast − observed| > 0.05 and its 95% interval excludes 0.

| Verdict | What follows |
|---|---|
| **PASS** (no deciding cell fails) | No change. The engine's response to quiet is calibrated. The overshoot risk is purely about seeing quiet (plan Parts 2–4). |
| **FAIL-OVERSHOOT** (every failing cell over) | Pre-register a refit of the quiet response (restart rate and hardening) on quiet-conditional data, with its own held-out test. No change from this test. |
| **FAIL-UNDERSHOOT** (every failing cell under) | The same, in the other direction. |
| **FAIL-MIXED** | Report, and diagnose by W and k before any refit is pre-registered. |
| **INCONCLUSIVE** (no deciding cell) | No change. |

## Known limits

- **Production never has perfect daily evidence.** It has market resolutions and positive news reports. This test
  isolates the model's response to quiet; it does not measure production accuracy.
- **Consecutive origins overlap** (a 30-day window, every 3 days). The bootstrap resamples whole directions for that
  reason.
- **The truth is compiled from news reports,** so quiet days may include unrecorded strikes. That would make the
  engine's forecasts look too high in long-quiet cells.

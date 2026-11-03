# Pre-registration: can our strike feed and GDELT together make silence count as quiet? (Nov 3, 2026)

Written before the two sensors are joined on any real data. Script: `analysis/feed_gdelt_combined.py` (synthetic checks pass).
Report only; nothing here changes production.

## Why

- Neither sensor alone clears its bar. The new strike feed: pooled d 0.526 (0.365, 0.675), alpha 0.052 (upper 0.101)
  (`docs/strike_feed_detection_result.md`). GDELT with per-direction offsets: d 0.79, alpha 0.094 on unseen 2025, narrowly
  (`docs/gdelt_baseline_result.md`).
- The feed misses routine, near-daily strikes that English wires stop reporting; GDELT codes events from a much wider source
  base. If their misses are independent, joint silence is far more informative than either alone. Earlier, the old stream's
  and raw GDELT's misses were nearly independent (0.54 vs 0.57, `docs/gdelt_detection_result.md`).
- The detection rule (`docs/detection_prereg.md`, point 2) sends a failing single stream to a second, independent source and
  asks that independence be checked, not assumed. Here the combined rate is **measured directly**, so the result does not
  depend on independence; independence is reported.

## Data

- **Sensor 1:** the backfilled strike feed and its labels, exactly as scored in `docs/strike_feed_detection_result.md`.
- **Sensor 2:** GDELT with per-direction offsets, the primary rule of `analysis/gdelt_baseline.py`: code set and thresholds
  learned on 2026-01-01..06-30 (where a direction has ≥ 5 strike and ≥ 5 quiet days; else the pooled threshold), on the same
  coverage filter, then frozen. Articles of strike-coded events dated [f−2, f] and published by 13:00 UTC on f. GDELT outage days
  are unobserved.
- **Test window:** 2026-07-01 to the event data's last complete day (the July–October confirmatory holdout). Only days observed
  by both sensors count.
- **Reference:** `detection_rate.PRIMARY`, truth window [f−2, f], as in every detection test so far.
- Pooled over directions that strike contracts have priced.

## Estimand and gates (fixed now)

What quiet-day evidence needs is not a hit rate but the **joint-silence likelihood ratio**:
LR = P(neither sensor hits | a strike in [f−2, f]) / P(neither hits | none), Jeffreys-smoothed. A day of joint silence
multiplies the odds of a strike by LR.

**PASS** if both hold:

1. the pooled LR's upper 95% bound is below **0.5** (one joint-silent day at least halves the odds); and
2. the macro LR (mean over pooled directions with at least 5 strike days) has an upper 95% bound below **0.5**, so that one
   steady war cannot carry it.

Intervals: bootstrap over (direction, ISO week) blocks, 2,000 draws.

| Verdict | What follows |
|---|---|
| **PASS** | Pre-register Part 4 (quiet days into the unified engine) with **two sensors**, each with its own per-direction d and alpha shrunk toward its pooled values, misses modeled as clustered where the data show it, adopted only by a paired-Brier replay on the Jul–Oct holdout (Gate 2). A live GDELT feed in the daily run needs Adi's licensing call first. |
| **FAIL** | No quiet-day evidence from news-based sensors before Nov 23. Both sensors stay as strike sightings only. The Lebanon-lull blind spot stays until a better source (official statements, a different provider) is found. |
| **INCONCLUSIVE** | Report only. |

## Also reported (not gating)

- The either-stream hit rate (d, alpha) with the original three gates, for comparison with the single-stream tests.
- Independence on strike days: P(GDELT miss) vs P(GDELT miss | feed miss).
- Per direction: d, alpha, LR, independence.

## Known limits

- **GDELT's July–October 2026 data has been looked at before** (the raw GDELT test, Oct 27) under a different rule. The offsets
  rule's thresholds come only from January–June and are fixed, so the test is out-of-sample for this rule, not unseen data.
- **The feed side is a historical reconstruction** (GNews's index, not the live feed), as before.
- **The reference is compiled from news**; when all three miss the same strike, the LR looks better than it is.
- **The reference counts artillery**, which neither sensor reports as an air strike (Israel→Syria, Iran→Iraq). This makes LR
  look worse there than for the contracts' own definition.
- **Per-day LR assumes nothing about runs of silence.** If joint misses cluster, several silent days are worth less than the
  product; Part 4 must model that.

# Result: the new strike feed, backfilled Jul 1 – Oct 9, 2026: FAIL (Nov 3, 2026)

Pre-registration: `docs/strike_feed_detection_prereg.md` (`6abaa4e`, before any backfill). Script:
`analysis/strike_feed_detection.py`. Backfill: 1,818 files (18 pairs × 101 file days), 2,192 GNews calls, no errors; every
headline labeled with the production labeler (prompt v2). Event data through 2026-10-09. Pooled over 20 contract directions.

**Procedural note:** a first `--measure` was run while labeling was still in progress (7 pairs unlabeled, so their headlines
counted as misses): pooled d 0.494 (0.331, 0.65), verdict FAIL. The registered result below is the run on complete labels.

## Gates

| Gate | Rule | Result |
|---|---|---|
| Pooled d, lower 95% | ≥ 0.50 | **0.526** (0.365, 0.675): fail |
| Pooled alpha, upper 95% | < 0.10 | **0.052** (0.014, **0.101**): fail by 0.001 |
| Macro-average d, lower 95% | ≥ 0.50 | **0.617** (0.437, 0.690): fail |

**Verdict: FAIL.** No quiet-day evidence from this feed alone. It stays in production for strike sightings.

## By direction (strike days ≥ 5)

| Direction | Strike days | d | 95% | alpha | Old stream d (same days) | P(miss \| missed the day before) vs P(miss) |
|---|---|---|---|---|---|---|
| Israel→Lebanon | 31 | 0.27 | (0.11, 0.42) | 0.000 | 0.41 | 0.91 vs 0.77 |
| Israel→Syria | 20 | 0.07 | (0.00, 0.18) | 0.045 | 0.10 | 1.0 vs 1.0 |
| Iran→Iraq | 20 | 0.21 | (0.04, 0.39) | 0.045 | 0.03 | 0.85 vs 0.77 |
| Iran→Kuwait | 20 | 0.98 | (0.91, 1.00) | 0.136 | 0.05 | – |
| Iran→Jordan | 16 | 0.91 | (0.78, 1.00) | 0.607 | 0.75 | – |
| Iran→Oman | 14 | 0.37 | (0.12, 0.61) | 0.029 | 0.02 | 1.0 vs 0.73 |
| Iran→Bahrain | 13 | 0.96 | (0.87, 1.00) | 0.361 | – | – |
| Iran→Qatar | 9 | 0.95 | (0.82, 1.00) | 0.023 | – | – |
| Saudi Arabia→Yemen | 8 | 0.72 | (0.43, 1.00) | 0.094 | 0.18 | – |

## Sensitivity (not gating): reference narrowed to air/drone strikes

Pooled d 0.572 (0.404, 0.737), alpha 0.075 (0.03, 0.127), macro d 0.646 (0.471, 0.765). Still fails. The artillery mismatch
(see `docs/contract_def_refit_prereg.md`) explains only a small part of the shortfall.

## Reading

- **A real improvement on the old stream** (pooled d 0.20 on Oct 27), but not enough for silence to count as quiet.
- **Coverage, not labeling, is the limit.** The feed sees rare, newsworthy strikes (Iran→Gulf, 0.91–0.98) and misses routine,
  near-daily ones (Israel→Lebanon 0.27, Iran→Iraq 0.21, Israel→Syria 0.07) that English wire coverage stops reporting one by
  one. Misses cluster where coverage is thin.
- **False alarms concentrate in Iran→Jordan (0.61) and Iran→Bahrain (0.36):** likely interceptions or strikes on foreign bases
  labeled as hits, or events the reference does not code there.
- **Israel→Lebanon scored below the old stream on the same days (0.27 vs 0.41).** The backfill is GNews's historical index,
  not what the live feed saw (the pre-registered limit). That limit cuts both ways.
- Pakistan→Afghanistan shows 0 strike days while Afghanistan→Pakistan shows 5: check the reference's actor naming.

## What follows (by the rule)

A second, independent source. GDELT with per-direction offsets passed narrowly on its own (`docs/gdelt_baseline_result.md`:
d 0.79, alpha 0.094). If the two streams' misses are independent, the combined rate is 1 − (1 − d₁)(1 − d₂). Independence is
tested, not assumed, under its own pre-registration (before Nov 23).

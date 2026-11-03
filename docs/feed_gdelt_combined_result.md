# Result: strike feed + GDELT offsets, joint silence as evidence of quiet: FAIL (Nov 3, 2026)

Pre-registration: `docs/feed_gdelt_combined_prereg.md` (`cd76319`, before the sensors were joined on real data). Script:
`analysis/feed_gdelt_combined.py --real`. Test 2026-07-01 .. 2026-10-09; GDELT code set `plus_generic_force` (chosen on Jan–Jun),
15 directions with their own threshold; 18 contract directions observed by both sensors.

## Gates

| Gate | Rule | Result |
|---|---|---|
| Pooled joint-silence LR, upper 95% | < 0.5 | **0.278** (0.132, **0.475**): pass |
| Macro LR (directions with ≥ 5 strike days), upper 95% | < 0.5 | **0.286** (0.204, **0.572**): fail |

**Verdict: FAIL.** No quiet-day evidence from news-based sensors. Both stay in production as strike sightings only.

Reported: either-sensor hit rate d 0.810 (0.686, 0.917), alpha 0.316 (0.234, 0.404). Misses are **not** independent:
P(GDELT miss) 0.208 vs P(GDELT miss | feed miss) 0.397.

## By direction (registered reference)

| Direction | Strike days | Either-sensor d | alpha | Joint-silence LR | P(GDELT miss) | P(GDELT miss \| feed miss) |
|---|---|---|---|---|---|---|
| Israel→Lebanon | 31 | 0.92 | – (no quiet days) | – | 0.065 | 0.087 |
| Iran→Iraq | 20 | 0.69 | 0.409 | 0.52 | 0.40 | 0.375 |
| Iran→Kuwait | 20 | 0.98 | 0.409 | 0.04 | 0.0 | – |
| Israel→Syria | 20 | 0.12 | 0.045 | 0.92 | 0.90 | 0.947 |
| Iran→Jordan | 16 | 0.97 | 0.750 | 0.12 | 0.0 | 0.0 |
| Iran→Oman | 14 | 0.77 | 0.206 | 0.29 | 0.286 | 0.333 |
| Iran→Bahrain | 13 | 0.96 | 0.528 | 0.08 | 0.0 | – |
| Iran→Qatar | 9 | 0.95 | 0.205 | 0.06 | 0.0 | – |
| Saudi Arabia→Yemen | 8 | 0.94 | 0.781 | 0.25 | 0.0 | 0.0 |
| Iran→Saudi Arabia | 3 | 0.88 | 0.411 | 0.21 | 0.0 | 0.0 |

## Sensitivity (not gating): reference narrowed to air/drone strikes

Pooled LR 0.202 (0.082, 0.370); macro 0.246 (0.150, **0.555**): would also FAIL. Israel→Syria drops to 3 strike days (out of
the macro); the macro now fails on Iran→Iraq (LR 0.52) and Iran→Oman (0.54). The artillery reference (a limit named in the
pre-registration) explains Israel→Syria, but not the whole failure.

## Reading

- **Joint silence is real evidence on average** (it cuts the odds of a strike about 3.5-fold, pooled), but **not reliably across
  directions**, which is what the macro gate exists to catch.
- **The two sensors share a blind spot:** when the feed misses a strike, GDELT misses it about twice as often. Both are news;
  strikes nobody reports are invisible to both.
- **Israel→Lebanon is seen well (0.92)**, but the window has no quiet days, so how informative its silence is cannot be measured
  here. The Oct 28–30 lull lies after the event data ends.
- **The quiet-days track stops here for now.** The engine keeps "no report = no information". The remaining risk (lulls in hot
  rivalries) is a source limit. A future source (official military statements, a non-news feed) would need its own
  pre-registration.

# Pre-registration: is GDELT's bias consistent per direction? (Oct 27, 2026)

Written before any 2025 GDELT data is looked at. Script: `analysis/gdelt_baseline.py`. Synthetic checks pass (`--synthetic`), and the
real-data path was smoke-tested on fabricated rows. Report only. Nothing here changes production.

## Why

`docs/gdelt_detection_result.md` failed on false alarms. In loud rivalries GDELT codes talk about strikes as strikes nearly every day:
alpha was 0.98 for United States→Iran. A source with a *consistent* bias can still be read, the way a clock that is always an hour
fast can. If each direction's level of strike-coded coverage on ordinary days (its "offset") is stable over time, a threshold
learned per direction should separate strike days from talk in a period it has never seen.

This idea came from looking at the July–October 2026 GDELT results. So it is tested on **2025**, a year whose GDELT data has not been
pulled or looked at before today.

## Data and signal

- **GDELT 2.0 event files** for 2025 and 2026 (`analysis/gdelt_pull.py`): CAMEO root 19, cross-border, our country set.
- **The signal v_f** for direction X→Y on day f is the total article count (NumArticles) of qualifying events with:
  - an event date in [f−2, f], and
  - publication by GDELT by 13:00 UTC on f (the time of the 9am ET run).
- **Reference:** the local offline event data, with the true-strike definition of `docs/detection_prereg.md`.

## Primary rule: a per-direction threshold ("offset")

- **On 2026-01-01 to 06-30 only:**
  - Each contract direction with at least 5 true-strike days and at least 5 quiet days there gets the threshold τ that maximizes
    its own Youden index (d − alpha). Candidates: 1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 75, 100, 150, 200, 300, 500, 750, 1000 and 1500
    articles.
  - Every other direction gets the pooled τ that maximizes Youden over all of them.
  - The code set (air/artillery: 194 and 195; or plus generic force: 190, 194 and 195) is the one with the higher pooled Youden.
- **On 2025, once, with every threshold frozen:** a hit is v_f ≥ τ for that direction. The estimands are d and alpha as before,
  pooled over contract directions whose target the reference covers in 2025, with block-bootstrap intervals over (direction, ISO week).

## Decision rule (fixed now; the same thresholds as the earlier detection tests)

- **PASS:** the pooled d's lower 95% bound is at least 0.50, and the pooled alpha is at most 0.10. GDELT, read with per-direction
  offsets, may then carry quiet-day evidence in a pre-registered model stage (quiet-days plan, Part 4), which has its own test and
  adoption rule.
- **FAIL:** the offsets are not stable enough across years to read GDELT as a calibrated clock. Quiet-day evidence stays off.

## Also reported, with no verdict

- The no-hit likelihood ratio, (1 − d) / (1 − alpha): what one quiet GDELT day is worth.
- d and alpha for the directions with their own threshold, separately from those on the pooled one.
- **A spike rule** (a hit when v_f is at least r times the direction's own median over days f−32 to f−3), with r and the minimum
  article count chosen on the same 2026 window. It fails by construction in steady wars, where strikes become the baseline, which
  is why it is not the primary rule.

## Known limits

- **The test year comes before the selection window.** This tests whether offsets are stable over time, not walk-forward production
  use. A production stage would learn offsets on past data only.
- **The reference is compiled from news,** like GDELT. When both miss the same strike, d is overstated.
- **Offsets can shift:** a new war, or a change in coverage, moves a pair's level of talk. A production stage would need to monitor
  each direction's false-alarm rate on resolved contracts.

## Amendment 1 (Oct 27, after the 2025 download, before any comparison with the reference)

The 2025 download found 1,681 of 35,040 files missing upstream, and no GDELT rows at all from June 15 to July 1, 2025, during the
Israel–Iran war. (Only daily row counts were looked at.)

- **The change:** a day with zero GDELT rows across all directions is an outage. Day f is unobserved, and skipped, if any day in
  [f−2, f] is an outage. This is the same rule as for missing news files: unobserved, never quiet.
- **For the spike rule:** outage days are left out of the baseline, which needs at least half of its 30 days observed.
- **Unchanged:** the decision rule.
- **Synthetic checks:** outage days found exactly, and those days plus the two after skipped.

# Result: GDELT with per-direction offsets (Oct 27, 2026)

Pre-registration: `docs/gdelt_baseline_prereg.md` plus amendment 1. Script: `analysis/gdelt_baseline.py --real`. The event data runs
through Oct 9, 2026. 17 GDELT outage days (2025-06-15 to 07-01) were treated as unobserved.

## Selection (2026 Jan to Jun)

The generic-force code set (CAMEO 190, 194, 195). 15 directions got their own threshold; the rest got the pooled threshold of 20
articles over 3 days.

## Test (2025, unseen): PASSES the pre-registered rule, narrowly

| | d | alpha | Rule |
|---|---|---|---|
| Pooled (1,114 strike days, 7,536 quiet days) | **0.788** (95%: 0.742–0.828) | **0.094** (0.082–0.108) | d's lower bound ≥ 0.50: passes. alpha ≤ 0.10: passes (its upper bound is 0.108) |
| Directions with their own threshold only | 0.42 | 0.083 | (reported only) |
| Spike rule (secondary) | 0.33 | 0.104 | (reported only) |

A no-hit day multiplies the odds of a strike by 0.23.

## Reading: the pass is real under the rule, but it is not mainly an offset effect

- **Two steady wars carry most of the pooled d.** Israel→Lebanon (d 0.94, alpha 0.00) and Russia→Ukraine (1.00, 0.00) account for
  692 of the 1,114 strike days. Both use the pooled threshold.
- **Most quiet days come from directions with no strikes at all,** where false alarms are rare.
- **The idea being tested held for some directions but not most of them.**
  - **Held** (but each direction has few strike days): Israel→Iran (d 0.83, alpha 0.001), Iran→Iraq (alpha 0.013) and the United
    States→Venezuela.
  - **Shifted between 2025 and 2026:** Israel→Syria (alpha 0.17), Saudi Arabia→Yemen (threshold 1, alpha 0.33) and
    Pakistan→Afghanistan (alpha 0.23). Their 2026 offsets did not carry to 2025.
- **The case that matters most** for overshoot, a quiet day inside a hot rivalry, is a small share of this pool.

## What follows

- **By the rule, GDELT read with per-direction offsets may enter a quiet-days Part 4 pre-registration.** Passing changes nothing in
  production by itself. Part 4 has its own held-out test on real contracts and its own adoption rule.
- **What Part 4 should account for** (to be fixed in its pre-registration, not decided here):
  - alpha differs a lot by direction, so the evidence a no-hit day carries should come from each direction's own d and alpha, not
    the pooled ones;
  - directions whose offset shifted between years should be excluded, or their false-alarm rate monitored on resolved contracts;
  - July to October 2026 has not yet been scored under this rule, so it can serve as a held-out check.

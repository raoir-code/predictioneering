# Result: the unified engine's response to true quiet is calibrated (Oct 27, 2026)

Pre-registration: `docs/quiet_calibration_prereg.md`. Script: `analysis/quiet_calibration.py --real`. The event data runs
through Oct 9, 2026. The universe is 20 directions; there were 387 hot forecast origins and 774 forecasts.

## Verdict: PASS

No deciding cell (k ≥ 3, at least 5 directions, at least 30 forecasts) misses by more than 0.05 with an interval that
excludes 0. **No change.**

| W | k (quiet days) | n | Directions | Forecast | Observed | Diff | 95% CI |
|---|---|---|---|---|---|---|---|
| 7 | 1–2 | 172 | 14 | 0.906 | 0.895 | +0.011 | [−0.013, +0.050] |
| 7 | 3–6 | 53 | 12 | 0.558 | 0.641 | −0.083 | [−0.195, +0.071] |
| 7 | 7–13 | 49 | 12 | 0.356 | 0.429 | −0.073 | [−0.247, +0.095] |
| 7 | 14–29 | 59 | 11 | 0.158 | 0.186 | −0.028 | [−0.169, +0.104] |
| 7 | 30–60 | 54 | 9 | 0.081 | 0.093 | −0.012 | [−0.156, +0.070] |
| 30 | 1–2 | 172 | 14 | 0.967 | 0.971 | −0.004 | [−0.019, +0.015] |
| 30 | 3–6 | 53 | 12 | 0.797 | 0.811 | −0.014 | [−0.075, +0.079] |
| 30 | 7–13 | 49 | 12 | 0.655 | 0.735 | −0.079 | [−0.203, +0.074] |
| 30 | 14–29 | 59 | 11 | 0.428 | 0.542 | −0.114 | [−0.359, +0.160] |
| 30 | 30–60 | 54 | 9 | 0.258 | 0.333 | −0.076 | [−0.366, +0.152] |

## Reading

- **Given the true record, the engine cools at about the right rate.** Its forecasts fall from about 0.9 (struck in the
  last two days) to about 0.1 (a month or more of quiet) over 7 days, tracking what happened.
- **So the overshoot risk on hot dyads is about *seeing* quiet, not responding to it.** That part is unsolved: the news
  stream and GDELT both fail (`docs/detection_result.md`, `docs/gdelt_detection_result.md`). The remaining work is quiet-days
  plan Parts 2 to 4.
- **Not a finding, but worth watching:** 9 of the 10 point estimates are slightly *below* what happened. Given true quiet,
  the engine may cool slightly too fast, the opposite of overshoot. The intervals are wide (9 to 14 directions) and every
  one includes 0, so the rule's verdict stands.

## Limits

These are the pre-registered ones:
- **The evidence here is perfect.** Production has only market resolutions and positive news reports, so this test does
  not measure production accuracy.
- **Origins overlap.** The bootstrap resamples whole directions for that reason.
- **The truth is compiled from news.**

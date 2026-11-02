# Pre-registration: how much Brier could perfect eyes buy? (Nov 2, 2026)

Quiet-days plan, the "oracle-observation replay" adopted on Oct 27 as the first step before any more work on seeing quiet.
Written before any real-data run. Script: `analysis/oracle_replay.py`. Harness checks pass (`--synthetic`, including the
production pricer run on synthetic contracts). Report only. Nothing here changes production.

## Why

On Nov 2 we found that the strike-news stream for Israel→Lebanon had recorded no strike since Sep 17 (the engine's GNews
query missed the usual "Israeli airstrikes" phrasing). Israel→Syria (latest Aug 22) and Israel→Iran (none) look the same. A
full-recall strike feed shipped the same day (`95ef80c`). Before spending more on eyes (re-measuring the detection rate,
backfilling history, putting quiet days into the engine), we need the ceiling: if the engine saw every day perfectly, how
much better would its forecasts be than with the lagged evidence it actually runs on?

## Design

- **Pricer, inputs, universe, origins:** exactly as in `docs/quiet_calibration_prereg.md` (Part 5). The production pricer,
  unchanged; the held-out world fit and hardening (data ≤ 2026-06-30); news reports and rivalry phase off; directions with at
  least 5 true strike days in Apr 1 to Jun 30, 2026; origins every 3rd day from Jul 1; a direction enters at t only if it
  has at least one true strike in the previous 60 days.
- **Two evidence arms, priced on the same origin:**
  - **ORACLE:** every day t−60 … t−1 is a resolved daily window carrying its true outcome, strike or quiet.
  - **BLIND:** only days t−60 … t−LAG−1 are known; the last LAG days are unobserved. **Primary LAG = 7** (the engine's own
    last-strike horizon, and roughly what a starved news stream plus lagging resolutions leaves). LAG = 3 is a secondary arm,
    reported only.
- **Priced:** "at least one strike in [t, t+W−1]" for **W = 1 (primary: our dailies)**, 7 and 30.

## Measure

dBrier = Brier(BLIND) − Brier(ORACLE), paired by origin, with a 95% bootstrap interval over directions (2,000 draws).
Reported for every (W, LAG) cell, and for the primary cell by k, the days since the last true strike.

## Decision rule (fixed now)

The primary cell is W = 1, LAG = 7. It decides only with at least 5 directions and at least 30 forecasts.

| Verdict | Condition | What follows |
|---|---|---|
| **EYES-MATTER** | dBrier ≥ 0.02 and its 95% interval's lower end > 0 | Seeing is a bottleneck. Proceed: re-measure the detection rate on the new strike feed (backfilled if the GNews quota allows, before Nov 23), then Part 4 (quiet days into the engine) if d clears its pre-registered bar. |
| **EYES-DONT-MATTER** | the interval's upper end < 0.02 | Even perfect eyes cannot move the dailies by 0.02. Keep the strike feed (cheap), stop further eyes work, and look at the model instead. |
| **INCONCLUSIVE** | anything else, or too few directions/forecasts | No new eyes work is pre-registered on the strength of this test; report and decide with Adi. |

## Known limits

- **This is a ceiling, by construction.** The oracle is scored against the same record it sees. Real eyes will recover only
  part of dBrier.
- **BLIND is a stylised floor, not production.** It still sees days t−60 … t−LAG−1 perfectly, as if every one had resolved.
  Production sees only the days that have their own resolved contracts, plus positive news reports. For directions with no
  daily markets, production is worse than BLIND, so dBrier understates the value of eyes there.
- **The truth is compiled from news reports,** so "quiet" days may hide unrecorded strikes (same caveat as Part 5).
- **Consecutive origins overlap** (a 30-day window every 3 days); the bootstrap resamples whole directions for that reason.

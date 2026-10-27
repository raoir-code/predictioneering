# Result: detection rate of our live news stream (Oct 27, 2026)

Pre-registration: `docs/detection_prereg.md` plus amendments 1 and 2. Script: `analysis/detection_rate.py --real`.
The event data runs through Oct 9, 2026. The pooled numbers cover the 20 contract directions.

## Decision rule: FAILS

| | Result | Rule |
|---|---|---|
| Pooled d (detection rate) | **0.20** (95%: 0.10–0.30; 176 strike days) | lower bound ≥ 0.50: **fails** |
| Pooled α (false-alarm rate) | 0.012 (95%: 0.00–0.03; 384 quiet days) | ≤ 0.10: passes |
| Air/drone strikes only (sensitivity) | d 0.24, α 0.020 | same conclusion |

- **The rule's outcome:** the news stream alone may not carry quiet-day evidence. The next stage waits for a second,
  independent live source.
- **What a no-hit day is worth at these rates:** a prior of 0.5 moves only to 0.45.

## Misses are clustered (amendment 1)

- P(miss) = 0.78. P(miss | missed the day before) = 0.89.
- So a run of no-hit days is worth less than the product of the single days.
- The unified engine's current rule, treating no-report days as no information, is therefore correct and stays.

## Crowding is not the main cause (amendment 2)

- **Israel→Lebanon:** d is higher on days at the 20-article cap (0.60, n=25) than under it (0.29, n=38). Busy news days
  are also the days strikes get covered.
- **Israel→Syria:** the opposite (0.07 at the cap vs 0.25 under it), but only 8 strike days fall under the cap.
- **Mixed, so not the explanation.**

## By direction (at least 5 strike days)

| Direction | Coverage | Strike days | d | Never reported within 7 days |
|---|---|---|---|---|
| Israel→Lebanon | 0.82 | 63 | 0.41 | 24 |
| Israel→Syria | 0.34 | 35 | 0.12 | 45 |
| Iran→Oman | 0.74 | 27 | 0.02 | 20 |
| Saudi Arabia→Yemen | 0.40 | 24 | 0.18 | 27 |
| Yemen→Saudi Arabia | 0.40 | 19 | 0.57 | 4 |
| Iran→Iraq | 0.60 | 14 | 0.03 | 9 |
| Iran→Kuwait | 0.20 | 10 | 0.05 | 5 |

Coverage is the share of calendar days with a non-empty headline file.

The likely causes are news-gathering, not modeling:
- **Low coverage** on several directions: no headline file on most days.
- **Strikes never reported** in our headlines at all.
- **Targets not named:** headlines about Iranian strikes that say "Gulf states" rather than a specific country, which
  the labeler correctly does not count.

## Caveats

- **d is an upper bound.** The reference data is itself compiled from news.
- **The peaceful control dyads were never labeled** (unlabeled share 1.00), so their α of about 0 carries no information.
- **Check the reference's coverage before using these rows.** Pakistan↔Afghanistan (α 0.25) and Ethiopia/Eritrea
  (α 0.07) show no true strike days. The reference may not cover those countries.

## What follows (from the quiet-days plan)

- **A second source:** measure GDELT's d and α against the same local data, pre-registered, while that data is
  available.
- **News-gathering fixes:** daily coverage for every tracked direction, and strike-specific queries for hot directions.
  Each is re-measured on resolved daily contracts.
- **Watch, no change:** a positive report is weighed with Israel→Lebanon's catch rate (0.36). For the Iran→Gulf
  directions the true rate is far lower, so a positive report there is weaker evidence than the engine assumes.

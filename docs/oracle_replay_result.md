# Result: how much Brier could perfect eyes buy? EYES-MATTER, narrowly (Nov 2, 2026)

Pre-registration: `docs/oracle_replay_prereg.md` (`36a1fbe`, pushed 16:01, before the run at 16:09). Script:
`analysis/oracle_replay.py --real`. Event data through 2026-10-09; 20 pairs in the universe, 18 priced; 387 hot origins;
2,322 paired forecasts.

## Numbers

| Cell | n | Directions | Brier, oracle | Brier, blind | dBrier | 95% CI |
|---|---|---|---|---|---|---|
| **W=1, lag 7 (primary)** | 387 | 18 | 0.0823 | 0.1036 | **+0.0213** | [0.0043, 0.0453] |
| W=1, lag 3 | 387 | 18 | 0.0823 | 0.0950 | +0.0127 | [0.0031, 0.0236] |
| W=7, lag 7 | 387 | 18 | 0.1183 | 0.1459 | +0.0276 | [0.0097, 0.0486] |
| W=7, lag 3 | 387 | 18 | 0.1183 | 0.1253 | +0.0070 | [−0.0015, 0.0168] |
| W=30, lag 7 | 387 | 18 | 0.1256 | 0.1417 | +0.0160 | [0.0030, 0.0303] |
| W=30, lag 3 | 387 | 18 | 0.1256 | 0.1316 | +0.0060 | [0.0003, 0.0121] |

Primary cell by k, the days since the last true strike (500 draws):

| k | n | dBrier | 95% CI |
|---|---|---|---|
| 1–2 | 172 | +0.0320 | [−0.0044, 0.0850] |
| 3–6 | 53 | +0.0359 | [−0.0044, 0.0908] |
| 7–13 | 49 | +0.0154 | [−0.0059, 0.0414] |
| 14–29 | 59 | +0.0015 | [0.0004, 0.0030] |
| 30–60 | 54 | −0.0000 | [−0.0007, 0.0002] |

## Verdict: EYES-MATTER (narrowly)

The primary cell has dBrier +0.0213 ≥ 0.02, and the interval's lower end (0.0043) is above 0. So it passes the rule as
written. But the point estimate only just clears the bar, and the interval runs from about a fifth of the bar to twice it.

## Reading

- **Ceiling for the dailies:** perfect eyes would cut next-day Brier by about a fifth (0.104 → 0.082).
- **Recency carries most of the value.** Seeing the last 3 days (blind at lag 3) recovers 60% of the gap (0.0127 of
  0.0213). A feed that reports within a day or two captures most of what is on offer.
- **It is concentrated in active fighting.** The gain is about +0.03 when the last strike was 1–6 days ago, and about 0
  after 14 or more quiet days, because the engine already cools by itself (consistent with the Part 5 PASS). That is the
  Lebanon and Saudi→Yemen daily book.
- **Weekly contracts gain too** (+0.028 at W=7, lag 7).

## What follows (by the rule)

Re-measure the detection rate on the new strike feed (`95ef80c`), backfilled through GNews's historical search for
Jul–Oct (analysis only, before Nov 23). Then Part 4 (quiet days into the engine), if d clears its pre-registered gates.

## Limits (as pre-registered)

- A ceiling: the oracle is scored against the record it sees.
- BLIND is a stylised floor that still sees older days perfectly. Production without daily markets is worse than BLIND.
- The truth is compiled from news reports; quiet days may hide unrecorded strikes.

# Result: GDELT as a second live source for seeing strikes (Oct 27, 2026)

Pre-registration: `docs/gdelt_detection_prereg.md`. Script: `analysis/gdelt_detection.py --real`. The event data runs
through Oct 9, 2026. Pooled over 27 contract directions whose targets the reference covers. Seven were excluded as not
covered: China→Taiwan, Ethiopia→Eritrea, Iran→Egypt, and the United States→Colombia, Cuba, Denmark and Mexico.

## Evidence rule chosen on Jan to Jun 2026

The generic-force code set (CAMEO 190, 194, 195) with at least 10 articles: Youden 0.544. The runners-up were the same
codes with at least 5 articles (0.528) and air/artillery with at least 2 (0.527).

## Test (Jul 1 to Oct 9): FAILS on false alarms

| | d | alpha | Rule |
|---|---|---|---|
| GDELT alone | 0.63 (95%: 0.56–0.70; 621 strike days) | **0.23** (0.20–0.27) | d passes; **alpha > 0.10 fails** |
| News or GDELT (days with a news file) | 0.54 (0.42–0.67) | **0.37** (0.28–0.46) | **fails** |

- **Misses are close to independent:** P(GDELT miss) = 0.54, and P(GDELT miss | news missed) = 0.57. The two sources
  fail on different days.
- **The problem is false alarms.** In heavily discussed directions, GDELT codes talk about strikes as strikes:
  - United States→Iran: alpha 0.98
  - Iran→Saudi Arabia: 0.61
  - Pakistan→Afghanistan: 0.45
  - Iran→Oman: 0.35

## By direction (test window, at least 3 strike days)

| Direction | Strike days | d | alpha |
|---|---|---|---|
| Israel→Lebanon | 101 | 0.39 | 0.000 |
| Russia→Ukraine | 101 | 1.00 | 0.000 |
| Israel→Syria | 85 | 0.24 | 0.029 |
| Saudi Arabia→Yemen | 69 | 0.72 | 0.167 |
| Iran→Oman | 66 | 0.41 | 0.347 |
| Iran→Iraq | 61 | 0.49 | 0.159 |
| United States→Iran | 43 | 0.99 | 0.975 |
| Iran→Kuwait | 30 | 0.69 | 0.076 |
| Iran→Jordan | 21 | 0.98 | 0.204 |
| Iran→Bahrain | 13 | 0.89 | 0.174 |
| Pakistan→Afghanistan | 12 | 0.96 | 0.450 |
| Iran→Qatar | 9 | 0.85 | 0.124 |
| Iran→United Arab Emirates | 4 | 0.50 | 0.209 |
| Iran→Saudi Arabia | 3 | 0.88 | 0.611 |
| Iran→Syria | 3 | 0.88 | 0.035 |

## What follows

- **By the pre-registered rule, quiet-day evidence stays off.** The unified engine keeps treating no-report days as no
  information. Nothing changes in production.
- **Not concluded here:** alpha varies widely by direction. It is near 0 for Israel→Lebanon, Israel→Syria and Iran→Syria,
  and above 0.3 for the most discussed pairs. A direction-specific rule might pass for a subset. That is a new hypothesis,
  chosen after seeing these numbers, so it would need its own pre-registration and a held-out test. It is not a reading
  of this result.
- **The next candidate source** (for example, official military or coalition statements) gets its own pre-registration
  under the same thresholds.

# NNA detection test: result (Nov 11, 2026)

Prereg `8b72238` + amendments 1–2; labels `nna-v2` (blind hand check by ChatGPT: 30 of 30; `nna-v1` had failed at 26 of 30).
NNA English, Jul 1 – Nov 10, 2026: 3,532 articles, every day observed (5 article fetches failed; negligible).

## Verdict: FAIL (no retry on this data)

| Key | Strike days caught (d) | False alarms (α) | LR(no hit) |
|---|---|---|---|
| 1. Local event data, Jul 1 – Oct 9 (hit = QUALIFYING or BORDERLINE) | **74 / 99 = 0.745** [0.67, 0.81] | 1 / 2 = 0.50 [0.17, 0.88] | 0.51 [0.31, 1.70] |
| 2. Resolved dailies (hit = QUALIFYING) | 0.75 (n = 49 YES days) | 0 / 4 → 0.10 | 0.28 |
| 2, borderline counts | 0.83 | 1 / 4 → 0.30 | 0.24 |

- Rule 1 (d lower ≥ 0.50): **pass**. Rule 2 (LR upper < 0.5): **fail**. Key-2 "conflict": an artifact of key 1's two quiet days.
- **Why it failed:** Israel struck Lebanon on 99 of the 101 days of key 1, leaving two quiet days, so α (and the value of a silent
  day) could not be measured. The rule was written without first counting the quiet days in the answer key: a design miss.
- Misses are independent: P(miss | missed the previous strike day) 0.21 vs P(miss) 0.25 (n = 24).
- Key 2's four NO days (Sep 18, Oct 29, Oct 30, Nov 6): no qualifying strike reported on any. **Nov 6 resolved NO with only a
  drone-dropped sound bomb reported**: the resolvers do not count drone-dropped small munitions (QUALIFYING-only is the right
  contract reading).
- English NNA misses about 1 qualifying strike day in 4; the Arabic service is fuller and may close part of that gap.

## What it means

- Silence stays worthless in production (standing decision unchanged). NNA is not wired into anything.
- **Forward test allowed:** resolved Israel→Lebanon dailies from Nov 11 on are new data. A new pre-registration on them alone,
  never pooled with key 1 or with the four NO days above, once about 15 NO days have accumulated. Arabic NNA is a candidate
  addition at that point.
- The fetcher and labeler stay in the repo (`pilot/nna_fetch.py`, `pilot/nna_label.py`, `analysis/nna_detection.py`); the cache
  stays local.

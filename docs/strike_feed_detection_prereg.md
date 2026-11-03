# Pre-registration: does the new strike feed see strikes well enough for silence to mean quiet? (Nov 3, 2026)

Written before any backfill or real data. Script: `analysis/strike_feed_detection.py` (synthetic checks pass: `--synthetic`).
Analysis only: backfilled files and labels live in `pilot/local/` (gitignored). The production cache, the production labels,
the engine's evidence and every published price are untouched.

## Why

- The oracle replay (`docs/oracle_replay_result.md`) found EYES-MATTER, narrowly: perfect eyes would cut next-day Brier by
  about a fifth, almost all of it in active fighting, and most of it from the last 3 days.
- The old stream's detection result (`docs/detection_result.md`, d 0.20) was measured on a starved stream: its queries
  missed the usual strike phrasing, and Israel→Lebanon recorded no strike after Sep 17.
- The new full-recall feed (`95ef80c`) has run only since Nov 2. Waiting for it to build a record would push the measurement
  past the event data's expiry (Nov 23). GNews's historical search lets us reconstruct what the feed would have seen.

## Data

- **Stream (backfilled):** for each of the 18 pairs in `pilot/news_strikes.DYADS` and each file day f from Jul 1 to the event
  data's last complete day:
  - the production query, `pilot/strike_news_fetch.query(A, B)`;
  - the production window: 48 hours ending at 13:00 UTC on f (the 9am ET run), paged as in production (25 per page, up to 4);
  - a day with a fetch error, or with no articles, is unobserved, never quiet.
- **Labels:** the production labeler, `pilot/news_strikes.classify`, prompt v2, unchanged. Written to a separate local file.
- **Hit on file day f:** a headline labeled X→Y, published in [f−2, f]. The same definition as `docs/detection_prereg.md`.
- **Reference:** the local event data, with the primary definition from `docs/detection_prereg.md` (air/drone strike or
  shelling/artillery/missile attack located in Y, X's state forces acting; not maritime). Truth window [f−2, f].

## Estimands

The same as `docs/detection_prereg.md`: d = P(hit | true strike in the window), alpha = P(hit | none), Jeffreys points;
pooled intervals from a bootstrap over (direction, ISO week) blocks. Pooled over directions that strike contracts have priced.

## Gates (fixed now)

The new feed may carry quiet-day evidence into the next stage only if **all three** hold:

1. the pooled d's lower 95% bound is at least **0.50**;
2. the pooled alpha's upper 95% bound is below **0.10** (stricter than the Oct 27 rule's point estimate);
3. the per-direction (macro) average d, over pooled directions with at least 5 strike days, has a lower 95% bound of at least
   **0.50**, so that no single steady war can carry the result.

| Verdict | What follows |
|---|---|
| **PASS** | Pre-register Part 4 (quiet days into the engine) using this feed, each direction's own d and alpha shrunk toward the pooled values, with Gate 2 (paired Brier improvement on the Jul–Oct 2026 holdout) deciding adoption. |
| **FAIL** | No quiet-day evidence from this feed. It stays in production for strike sightings (cheap; adds positives only). Next source: GDELT with per-direction offsets, or official military statements, each under its own pre-registration. |
| **INCONCLUSIVE** (no strike days or no intervals) | Report only. |

## Also reported (not gating)

- Per direction: d, its interval, alpha, and the **old stream's d on the same days** (how much the new feed improved).
- Whether misses cluster: P(miss | missed the day before) vs P(miss).

## Known limits

- **The historical index is not what existed that morning.** Articles indexed late can appear in a backfilled window, and
  removed articles cannot. This makes the backfilled d an optimistic estimate of the live feed's.
- **The reference is compiled from news.** When both miss the same strike, d is overstated.
- **GNews's English coverage is thin for some pairs** (Israel–Lebanon: ~27 articles a week even with the full-recall query).
  That is a property of the source the feed can't fix; the test measures it.
- **Labels are made after the fact,** but each headline is judged on its own text, as in production.

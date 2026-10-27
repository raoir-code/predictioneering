# Pre-registration: how well does our live news stream see strikes? (Oct 27, 2026)

Written before any real data is touched. Script: `analysis/detection_rate.py` (synthetic checks pass: `--synthetic`).
Report only. Nothing in this study changes production.

## Why

The system cannot tell "nothing happened" from "something happened and we missed it". A day with no strike headline
is evidence of quiet only through two numbers: how often the stream reports a strike that happened (d), and how
often it reports one that didn't (alpha). With them,

P(strike in the window | no hit) = pi (1 - d) / (pi (1 - d) + (1 - pi)(1 - alpha)),   pi = the prior.

Without them, silence is uninterpretable. This study measures d and alpha. A later, separately pre-registered stage
uses them.

## Data

- **Stream:** the pipeline's own daily headline files (`cache/gnews/<Dyad>_<YYYYMMDD>.json`) and their strike labels
  (`pilot/news_strike_labels.jsonl`, prompt v2), exactly as `pilot/news_strikes.py` reads them.
  - A hit on file day f: a headline labeled X -> Y, published in [f-2, f].
  - An empty or missing file is unobserved, never quiet.
- **Reference:** the local offline event data.
  - A true strike day for X -> Y: an event of type air/drone strike or shelling/artillery/missile attack, located in Y
    (not maritime), with X's state forces as the acting side.
  - The same definitions as the strike-without-war fit.
- **Period:** each direction's first headline file through the event data's last complete day (latest event minus 7 days).

## Estimands

For each direction X -> Y and each observed file day f, let S = any true strike in [f-2, f] and O = a hit on f:

- **d = P(O | S)**, the detection rate.
- **alpha = P(O | not S)**, the false-alarm rate.
- **Estimation:** Jeffreys point estimates, (k + 0.5) / (n + 1).
- **Intervals:**
  - Per direction: approximate 95% intervals.
  - Pooled: bootstrap over (direction, ISO week) blocks, because consecutive days overlap.

The truth window equals the news window. A synthetic check showed that adding a day of slack to the truth side counts
strikes the stream could not yet report as misses (a perfect stream scored d = 0.87).

Also reported:
- **Coverage:** observed days as a share of calendar days.
- **Lag:** from a true strike day to the first hit headline.
  - Same day, within 2 days, or never within 7.
  - A headline from the day before counts, for time zones.
- **Unlabeled share** of headlines.
- **Sensitivity:** air/drone strikes only.
- **Peaceful control dyads,** where any hit is a false alarm.

## Pooling

- The pooled d and alpha use only directions that strike contracts have priced.
- Reverse directions (e.g. Lebanon -> Israel) are reported but not pooled. The reference counts state forces only, while
  the news labels also count armed groups operating from that territory.

## Decision rule for the next stage (fixed now)

1. **The news stream alone may carry quiet-day evidence** if both hold:
   - the pooled d's lower 95% bound is at least 0.50, and
   - the pooled alpha is at most 0.10.
2. **Otherwise,** the next stage waits for a second, independent live source. It will use the combined rate
   d = 1 - (1 - d1)(1 - d2) if the misses are independent; that independence is to be checked, not assumed.
3. **Direction-level carry-over:** per-direction d with at least 5 strike days is carried into the next stage, shrunk
   toward the pooled d. The next stage's pre-registration sets the shrinkage.

## Known limits

- **The reference is itself compiled from news.** When both miss the same strike, d is overstated. It is an upper bound
  on what the stream sees.
- **The labels were made after the fact, but each file holds only what existed that morning.** The labeler judges each
  headline on its own text.
- **Overlap with the event data ends at its last complete day.** Recent weeks are not in the test.

## Amendment 1 (Oct 27, before any real data)

Added a check of whether misses come in clusters. Among consecutive observed days that both had a true strike, it
compares P(miss today | missed yesterday) with P(miss).

- **Why:** the unified engine treats no-report days as no information, because it assumes coverage gaps come in
  clusters. This measures that assumption.
- **What follows:** if misses are independent, k no-hit days are worth roughly the product of k single-day likelihood
  ratios. If they are clustered, they are worth less, and the next stage must model the clustering.
- **Status:** report only. The decision rule above is unchanged.
- **Synthetic checks:** independent misses recovered (0.29 vs 0.25), and 4-day blackouts detected (0.75 vs 0.41).

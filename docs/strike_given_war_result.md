# Empirical P(strike | war) for strike contracts — result (docs/strike_given_war_prereg.md + amendments)

| gate | empirical | engine (LLM P(B|A)) | |
|---|---|---|---|
| (1) out-of-time wars: fit on wars starting <= 2022, scored on wars 2023 .. 2026-06 (Brier) | 0.3061 | 0.2403 (typical value 0.435) | FAIL |
| (2) contract replay, 10 resolved contracts from 2026-07-01, all YES (Brier) | 0.5676 | 0.5585 (market 0.0377) | FAIL |

Cluster bootstrap on (2), by dyad: Brier(empirical) - Brier(logged) = +0.0091, 95% [+0.0017, +0.0311].
ADOPTION RULE -> NOT adopted (no local parameter file; the engine keeps its own P(B|A)).

Reading: the pooled rate is below the engine's typical P(B|A), not above it, so the Ethiopia -> Eritrea gap to the market is not a
base-rate error in P(B|A). The rate is not stationary: air/drone strikes on the other side's territory are far more common in
interstate wars since 2023 than before (drone proliferation), so a rate fitted on the earlier era under-predicts the later one, and
the engine's value is closer to the recent era. Any revisit should model the era (or the initiator's demonstrated air/drone use),
pre-registered, not pool across it.

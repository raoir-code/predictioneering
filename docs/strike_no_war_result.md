# Empirical P(strike | no war) for strike contracts — result (docs/strike_no_war_prereg.md + amendment 1)

| gate | empirical | engine (LLM P(B|not A)) | |
|---|---|---|---|
| (1) out-of-time: L chosen on 2019-2022 (730 days); scored on origins 2023-01 .. 2026-05, W in {7, 30, 60}, 23 directions, 2,753 pair-windows (Brier) | 0.0575 | 0.0602 (with the production cap: 0.0592) | PASS |
| (2) contract replay: 2 resolved contracts, both YES | 0.5363 | 0.9598 (market 0.0046) | not informative (< 10 contracts, one outcome) |

Gate 1: log loss 0.2075 vs 0.2445; cluster bootstrap by pair, Brier(empirical) - Brier(LLM) 95% [-0.0073, +0.0008]. Reported: B including
shelling/missile attacks, 0.0620 vs 0.0679. First run, before amendment 1 (two groups of directions wrongly dropped): 0.0645 vs 0.0684.
ADOPTION RULE -> ADOPTED (local frozen table; directions whose markets are all daily contracts, and sub-state targets, keep the LLM value).

Reading: the gain is small and mixed by pair (better on Israel -> Syria and most Iran -> Gulf directions, worse on Iran -> Iraq, Iran ->
Syria, Pakistan -> Afghanistan). The table is frozen at its data end and goes stale; replacing it needs a live view of quiet days (the
main open problem). Where the during-war or unified component prices a contract, its price is still the one published.

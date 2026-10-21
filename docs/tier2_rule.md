# Tier 2 validation rule (pre-registered Oct 21, 2026)

Purpose: decide when we may claim an edge over Polymarket, pitch it, or bet real money.

1. Scope (claimed product): contracts priced by the unified engine, first published on or after
   Oct 21, 2026. Every other published forecast is reported alongside and never dropped.
2. Score: our FIRST published forecast vs the outcome (Brier). Comparator: the market price at that
   same moment. Statistic: D = mean of [Brier(ours) - Brier(market)], paired per contract.
3. Looks: tested at exactly 30, 60 and 100 resolved contracts, no peeking in between.
   Each look uses a 98.3% bound (95% split across 3 looks).
4. Edge claim at a look iff:
   (a) cluster bootstrap by dyad-week (10,000 draws) puts the upper bound of D below 0, AND
   (b) the stalled-contract check (5) does not flip the sign.
5. Stalled contracts: published, date passed 14+ days ago, never settled.
   - Every report shows resolved and stalled counts, by family.
   - Check: score each stalled contract as if it resolved at the market's last price (expected
     Brier; conservative). D over resolved + stalled must stay below 0.
   - A stalled contract that later settles enters with its real outcome.
6. Voided / 50-50 resolutions: excluded from Brier, counted and reported.
7. No retroactive edits: model changes never touch past forecasts; nothing leaves the record.

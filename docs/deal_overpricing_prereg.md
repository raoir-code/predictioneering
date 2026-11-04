# Pre-registration: do markets overprice deals? (Nov 4, 2026)

Written before any price history is fetched. Script: `analysis/deal_overpricing.py` (synthetic checks pass). Report only.

## Why

- Of the resolved deal and ceasefire-agreement contracts we store, 72 of 94 resolved NO (deals: 34 of 40).
- Hypothesis (domestic politics, `claude/Mechanism Cards` in the project notes; two-level games): markets price leaders' signals of
  progress and underprice what blocks a deal, so "deal / ceasefire agreement by date X" is priced too high. The literature does not
  identify this mechanism well enough to build it; this tests the market directly, without needing the mechanism.
- If true, it is an edge on a whole contract family, independent of our strike engine.

## Sample (fixed now)

- `pilot/ceasefire_markets.json`, classified by `pilot/ceasefire_bc.classify_all`: family AGREEMENT, type **DEAL** or
  **CEASEFIRE** (agreement reached / signed / announced). Excluded: extensions, breakdowns, races, conjunctions, processes, and
  contracts that are not Yes/No.
- Resolved (closed, outcome 0 or 1), with a listing time, a close time and a YES token. **94 contracts, 11 actor clusters**
  (US–Iran 33, Israel–Hamas 17, Russia–Ukraine 13 + 3, Israel–Hezbollah 11, Israel–Iran 5, others ≤ 3).

## Measures (fixed now)

- **Price:** the YES price at a fixed time; last trade point at or before it, else the first within 24 hours after.
  - **Primary:** listing + 24 hours.
  - **Secondary (reported):** the midpoint of the scheduled life (listing .. end date).
  - A contract already resolved at that time is excluded and counted (by outcome).
- **Bias** = mean price − share resolved YES. **Market Brier.** **Return on $1 bet on NO** at that price, averaged per contract
  (fees, spread and price impact ignored: an indication, not a trading result).
- 95% intervals by bootstrap over actor clusters (one negotiation = one cluster; ladders are nested), 2,000 draws.

## Rule (fixed now)

- **OVERPRICED** if the primary bias's 95% lower bound > 0. Otherwise **NOT ESTABLISHED**.
- If OVERPRICED, what follows (each its own pre-registration): (1) compare our agreement model's prices with the market on the same
  contracts (the watch list says it is already behind the market on deal timing); (2) a NO-side correction to the agreement model,
  scored forward. Nothing changes in production from this test alone.
- Reported, not deciding: the secondary arm; by type; by cluster; the NO return and its interval.

## Known before registration

- Outcome counts and clusters above. No price was fetched or seen.

## Known limits

- **11 clusters, one of them a third of the sample** (US–Iran): the interval is wide and one negotiation can drive the result.
- **Selection:** contracts are listed when a deal is in the news, which is part of what is being tested, not a bias in the test.
- **Thin markets:** a 24-hour-old price can be a stale opening quote; the midpoint arm is the check.

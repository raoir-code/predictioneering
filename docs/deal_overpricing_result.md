# Result: do markets overprice deals? NOT ESTABLISHED (Nov 4, 2026)

Pre-registration: `docs/deal_overpricing_prereg.md` (`a5413c5`, before any price was fetched). Script: `analysis/deal_overpricing.py --measure`.

| Arm | n (clusters) | Mean price | Share YES | Bias (95%, by cluster) | Market Brier | $1 on NO (95%) |
|---|---|---|---|---|---|---|
| **Primary: listing + 24h** | 83 (11) | 0.274 | 0.193 | **+0.081 [−0.012, +0.219]** | 0.129 | +0.115 [−0.097, +0.420] |
| Secondary: midpoint of life | 76 (11) | 0.142 | 0.118 | +0.023 [−0.047, +0.112] | 0.091 | +0.034 [−0.073, +0.171] |

Excluded (primary): 7 without a price, 4 resolved before the price time (2 YES, 2 NO). Midpoint arm: 12 YES and 4 NO already resolved.

**Verdict: NOT ESTABLISHED** (the primary bias's lower bound is below 0). Nothing follows by the rule.

## Reading

- **The point estimate is the hypothesized direction and not small:** a day after listing, deals were priced at 27% and happened 19% of
  the time; NO at that price returned ~11% on average. Deals (+0.106) more than ceasefire agreements (+0.064).
- **By negotiation (descriptive, not tested):** positive in 9 of 11 clusters (Israel–Hamas +0.24, Sudan +0.35, Israel–Syria +0.30,
  Russia +0.25); negative in US–Iran (−0.07, n = 29, a third of the sample) and Israel–Hezbollah (−0.02).
- **The overpricing shrinks as contracts age** (midpoint bias +0.02): markets correct; any edge is early in a contract's life.
- **Power is the limit:** 11 negotiations, one of them a third of the sample. A single re-test is worth pre-registering for when the
  sample has ≥ 20 negotiations (new resolutions only; no repeated peeking).

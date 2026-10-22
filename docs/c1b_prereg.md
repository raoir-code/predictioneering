# Family C v1b — listed-market reference class (pre-registered Oct 22, 2026, before any C1b replay)

Motivation (from the C1 comparison, 416d066): 25% of listed agreement contracts resolved YES; mean C1 forecast 0.027, market 0.317.
We forecast conditional on a market being listed, so the reference class is listed agreement markets, not conflict-years.

Prior for actor set A, type k, priced at time t:
- Pool: every OTHER actor set's resolved agreement contracts of type k with close time < t. Per actor set j: exposure_j = days
  covered by the union of its resolved windows; events_j = number of disjoint clusters of overlapping YES windows.
  If fewer than 3 actor sets have exposure for type k, pool across all types; if still fewer than 3, use C1's PA-X prior.
- m = sum(events) / sum(exposure) per year. V = max(0, exposure-weighted between-set variance of rates - m / mean exposure).
  sigma^2 = log(1 + V / m^2) (floor 0.05, numerical only); log_mu = log(m) - sigma^2 / 2 (prior mean equals m).
Likelihood: A's own resolved windows, exact (as C1). Close-time guard throughout.
Comparison: C1b vs C1 vs C0 vs market on the same resolved contracts (24h after listing): Brier, log loss, YES/NO, by actor set;
cluster bootstrap by actor set (2,000) of Brier(C1b) - Brier(C1).
Switch: C1b replaces C1 in production iff Brier(C1b) < Brier(C1). Publication unaffected.
Caveat: development data; pools very different conflicts; listing selection is now modeled explicitly, not removed.

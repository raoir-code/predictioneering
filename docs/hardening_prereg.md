# Peace hardening in the unified engine (production use of theory test 4) — pre-registered Oct 23, 2026, before any replay

Change: when projecting forward from the forecast date, a quiet pair's restart rate is h x m(t) instead of h, with
  m(t) = t^beta / K,  t = weeks since the pair's last episode ended = max(1, (days since the last known strike - 30) / 7)
  (the G = 30 clock of theory test 4), beta = test 4's ROBUST G = 30 coefficient (pair heterogeneity is already in each pair's h),
  K = exposure-weighted mean of t^beta over all quiet spell-weeks in the data (so m averages to 1 and h keeps its long-run meaning).
Last known strike = latest day with positive evidence for the pair in our own records (resolved YES windows, positive news days);
none -> m = 1 (no change). Two-direction holds (v1): evidence of either direction. The posterior over (mu, q, q0) is fitted as now
(constant h); only the forward projection changes. Daily steps; exact per day.
Leakage guard: a HELD-OUT beta and K are estimated on data through 2026-06-30 only. Replay: every resolved unified contract (strike
groups and holds) whose first forecast is on/after 2026-07-01, priced at that moment with vs without hardening (held-out beta, K),
vs the market. Brier, log loss, YES/NO, by pair; cluster bootstrap by pair (2,000).
Adoption rule: hardening (with the full-data beta and K) goes live iff Brier(with) <= Brier(without) on that replay; otherwise not.
Parameters derived from the local data stay in gitignored local files; the public repo records only this rule and the verdict.

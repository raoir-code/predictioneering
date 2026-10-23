# Refit of the unified world priors — result (docs/refit_prereg.md)

Held-out replay, contracts first forecast on/after 2026-07-01 (held-out priors fit on data before that date only):

| priors | Brier | log loss |
|---|---|---|
| current (repo) | 0.1455 | 0.458 |
| held-out refit | 0.1353 | 0.434 |
| market (same moment) | 0.1233 | 0.398 |

n = 79 (YES 66, NO 13). YES: current 0.092, refit 0.084, market 0.122. NO: current 0.418, refit 0.397, market 0.128.
Cluster bootstrap by pair (2,000): Brier(refit) - Brier(current) = -0.0102, 95% [-0.0467, +0.0085].
By pair: Iran -> Gulf states and Iraq improved; Israel -> Lebanon improved (0.038 vs market 0.060); Israel -> Syria not improved
(0.514 vs market 0.214; still excluded from the unified engine by its publish rule).

Adoption rule (Brier(refit) <= Brier(current)): ADOPTED. The production fit is used through the engine's local override.
The improvement is modest and not statistically distinguishable from zero at this sample size; the NO-outcome gap is unchanged in kind.

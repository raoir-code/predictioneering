# Peace hardening in the unified engine — result (docs/hardening_prereg.md + amendment)

Theory test 4 (docs/theory_test4_prereg.md, analysis/theory_test4_results.json): peace hardens; the hazard of resuming strikes falls
with time since the last episode (robust G = 30 coefficient about -0.66). Production use: a quiet pair's restart rate in the forward
projection is h x t^beta / K (t = weeks since the episode ended), with the multiplier averaging 1 over all quiet time.

Held-out replay (beta, K estimated on data before 2026-07-01; contracts from 2026-07-01, 116 incl. 37 holds):

| | Brier | log loss |
|---|---|---|
| without hardening | 0.0928 | 0.315 |
| with hardening (held-out) | 0.0883 | 0.324 |
| market (same moment) | 0.0990 | 0.334 |

YES n=103: 0.054 -> 0.044 (market 0.095). NO n=13: 0.401 -> 0.438 (market 0.128).
Improved: Iran -> Iraq (0.180 -> 0.123), Israel -> Syria (0.518 -> 0.454), Israel -> Lebanon, Saudi Arabia -> Yemen.
Worse: holds (all 37 held; hardening raised their break probability).
Cluster bootstrap by pair (2,000): Brier(with) - Brier(without) = -0.0045, 95% [-0.0210, +0.0044].
Adoption rule (Brier(with) <= Brier(without)): ADOPTED, with the full-data beta and K (local parameter files).

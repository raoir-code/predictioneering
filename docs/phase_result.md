# Rivalry phase in the unified engine — result (docs/phase_prereg.md + amendment)

Held-out cross-validation (data through 2026-06-30; 108 origins, 9,315 pair-origins at risk, 1,044 episode starts; hardening on):

| weighting | log likelihood | Brier |
|---|---|---|
| none (phi = 1) | -2551.04 | 0.08015 |
| best recency weighting (H = 365 d, kappa = 260 wk) | -2552.04 | 0.08014 |
| other half-lives (182 .. 1826 d, kappa = 260 wk) | -2552.3 .. -2557.0 | 0.0801-0.0802 |

CHOICE: none. By the pre-registered rule there is no replay and rivalry phase is NOT adopted (no local parameter file; the engine
is unchanged). For the record, the same CV on the full data chose H = 365 d with a log-likelihood gain of +0.42 over 112 origins
(Brier 0.08038 -> 0.08032): negligible, and not the held-out choice.

Reading: theory test 5's association (recent episode starts predict restarts) does not add out-of-sample predictive value once each
pair's own long-run rate and peace hardening are in the model. Hardening already makes a recently active pair restart faster (its
clock is short), which is most of what a hot rivalry phase looks like in this data.

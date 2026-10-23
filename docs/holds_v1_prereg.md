# Family A v1 — shared fighting state for two-direction holds (pre-registered Oct 23, 2026, before any v1 replay)

Scope: holds contracts counting strikes in BOTH directions (today: Israel x Iran). Single-direction holds unchanged (v0).
Model (ChatGPT review, Oct 22): one two-state chain for the confrontation (shared N/F state, rates h, mu); the qualifying event is a
strike in EITHER direction, daily probability q_u = 1 - (1 - q_1)(1 - q_2) in F and q0_u likewise in N (= D_union = D_1 + D_2).
P(holds through D) = P(no union strike in [created, D] | evidence). Exact, unified machinery unchanged.
Prior: h and mu = geometric means of the two directions' world-prior means; log-sd of mu = the larger of the two; q_c and q0_c of the
union from the two directions' centres by the formula above.
Evidence (close-time guard throughout): held holds contracts = union NO windows; broken holds contracts = union YES windows (now
usable for two-direction contracts); YES windows of either direction's strike groups with the same structural definition = union YES;
union NO only where both directions have NO windows on the same days; positive news days of either direction.
Replay: the same resolved two-direction holds contracts as the v0 replay (priced 24h after listing), v1 vs v0 vs market; Brier, log loss.
Adoption rule: v1 replaces v0 unless Brier(v1) > Brier(v0) + 0.01. Stated in advance: every replayed contract held, so this replay
cannot discriminate (it favours whichever model says "holds" more, and v1 does by construction); adoption rests on theory (independence
is known to understate "holds" when strikes are correlated) with the replay as a harm check only.

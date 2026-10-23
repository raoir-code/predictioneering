# Rivalry phase in the unified engine (production use of theory test 5) — pre-registered Oct 23, 2026, before any replay

Theory test 5 (docs/theory_test5_prereg.md + amendment, analysis/theory_test5_results.json): a pair's record of starting episodes in
the 730 days before its current episode predicts resuming strikes; the long-run record adds nothing once that is known.

Change: when projecting forward, a pair's restart rate is h x m(t) x phi instead of h x m(t) (m = peace hardening, unchanged), with
  phi = exp(gamma x (recent_now - rbar_pair))
  recent_now = log(1 + episode starts in the 730 days before the start of the pair's CURRENT episode, excluding it) — test 5's
               covariate, G = 30 episodes, fixed through the spell (so phi is constant over the forecast horizon);
  rbar_pair  = the pair's own exposure-weighted mean of `recent` over its quiet spell-weeks in the fit data, so phi averages 1
               within each pair and h keeps its meaning as the pair's long-run rate (phi moves a pair only relative to its own past);
  gamma      = the WITHIN-pair coefficient: test 5's G = 30 model with `recent` split into (recent - rbar_pair) and rbar_pair
               (Mundlak / correlated random effects). gamma is the coefficient on (recent - rbar_pair). The between-pair part is
               not used: between-pair differences are already in each pair's h. log(weeks since) stays in the model, so gamma is net
               of hardening (no double counting).
Episodes for recent_now: the frozen strike-date table (strikes dated >= 7 days before the forecast; hardening amendment rule) plus
our own positive evidence days before the forecast date. Pair not in the fit (no rbar) or no strikes -> phi = 1.
Two-direction holds (v1): the union's h is the geometric mean of the two directions' h, so phi_union = geometric mean of the two
phis (each direction's table days plus the union's positive evidence days). No clipping.

Leakage guard: HELD-OUT gamma and rbar from data through 2026-06-30 only. Replay: exactly the hardening replay
(analysis/hardening_compare.py set: resolved unified strike contracts at production's first-forecast time, holds 24h after listing,
first forecast on/after 2026-07-01), current production (local priors + hardening) without vs with phi (held-out), vs the market.
Brier, log loss, YES/NO, by pair; cluster bootstrap by pair (2,000).
Adoption rule: phi (full-data gamma and rbar) goes live iff Brier(with) <= Brier(without) on that replay; otherwise not.
Parameters derived from the local data stay in gitignored local files; the public repo records only this rule and the verdict.

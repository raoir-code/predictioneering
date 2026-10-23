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

## Amendment (Oct 23, before any real data): the multiplier is a recency-weighted rate chosen by out-of-sample prediction
Synthetic checks (pairs with heterogeneous long-run rates, hardening, with and without regime shifts) showed that a regression
coefficient is not a safe basis for phi. The within-pair (Mundlak) gamma above is NEGATIVELY biased under no shifts (-0.17 to -0.37,
p < .05: `recent` is a lag of the outcome, so demeaning by the pair's own mean builds in regression to the mean; Nickell bias), and
stays negative when shifts are present. The pooled test-5 coefficient is POSITIVELY biased under no shifts in sparser data (+0.11 to
+0.25; pair heterogeneity leaks through the noisy `older` control). Replaced, before any real data, by the literal follow-up named in
test 5's pre-registration ("restart rates estimated with recent years weighted more"):
  phi = [(S_H + kappa x rho) / (E_H + kappa)] / rho
  S = the pair's episode starts (a strike more than G = 30 days after its previous strike), E = its at-risk exposure in weeks
  weighted by the hardening multiplier m(t) (so phi does not re-count hardening), rho = (S + 1) / (E + 1 / rho_class) its long-run
  rate (rho_class pooled over all pairs), S_H and E_H the same sums discounted with half-life H days. phi > 1 when recent starts
  run above the pair's own long-run rate; kappa (pseudo-exposure, weeks) shrinks phi to 1 when recent exposure is thin.
(H, kappa) are chosen by prequential cross-validation (analysis/phase_fit.py): origins every 28 days from 2018-01-01; every pair at
risk at the origin is scored on whether a new episode starts within 90 days, using only strikes before the origin,
P = 1 - exp(-rho x phi x hardening exposure over the 90 days); grid H in {182, 365, 730, 1095, 1826} days x kappa in {26, 52, 104,
260} weeks, plus "none" (phi = 1); choice = the highest total log likelihood. Synthetic re-check: no shifts -> "none" chosen in 3 of 3
seeds (no bias); shifts in half the pairs -> H = 182 chosen in 2 of 3. Production phi (pilot/unified_price.py) equals the CV's phi to
machine precision.
Held-out: CV on data through 2026-06-30 with the held-out hardening parameters. If it chooses "none", phi stays off and there is no
replay (reported). Otherwise the replay, the comparison (current production, local priors + hardening, without vs with phi) and the
adoption rule are as above; the production (H, kappa, rho_class) come from the CV on the full data. Two-direction holds: geometric
mean of the two directions' phi (unchanged). Everything else above is unchanged.

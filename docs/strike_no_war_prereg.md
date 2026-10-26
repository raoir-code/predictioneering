# Empirical P(strike | no war) for the onset engine's strike contracts — pre-registered Oct 26, 2026, before any fit or replay

Problem: for strike contracts ("Will X strike Y by D?", Polymarket's definition: an air strike or surface-to-surface missile strike,
initiated by X's armed forces, that impacts Y's territory; artillery, ground incursions and interceptions do not count), the engine
prices P = P(A) P(B|A) + (1 - P(A)) P(B|not A). P(B|not A), the chance that X strikes Y's territory in the contract window WITHOUT
serious clashes or war between them, is an LLM judgment: a rate over a reference period (usually 30 days), converted to the window
by 1 - (1 - p)^(min(d, ref) / ref). It never extrapolates beyond the reference period (a 66-day contract gets the 30-day value).
Where P(A) is small this term is the price. Example (Oct 26): Israel -> Syria by Nov 30, LLM rate 0.92 per 30 days, P(A) 0.02,
published 0.91 vs market 0.315. This changes only P(B|not A). It does not address the long-dated P(A) misses (Saudi -> Iran,
Pakistan -> Yemen by Dec 31), which come from the ICB boost and are a separate question (forward test, to be pre-registered).

Change: P(B|not A) for qualifying contracts is replaced by an empirical window hit rate for the contract's direction.
- A (war episode): as in docs/strike_given_war_prereg.md: days with a Battles event between the two states' militaries, merged when
  gaps are <= 30 days, kept if >= 25 fatalities. War days = each episode's first day to 30 days after its last day.
- B: an Air/drone strike by X's state forces located in Y's country (maritime locations excluded). If the contract names several
  initiators ("France, UK, or Germany"), B is a strike by any of them.
- Estimator, at a forecast date t, horizon W = the contract's days remaining (at least 1), lookback L days: among all W-day windows
  lying inside (t - L, t] and containing no war day for the pair, the share with at least one B day. The windows overlap, so the
  effective number of independent windows is n = (non-war days in the lookback) / W, and
  P(B|not A) = (share x n + 0.5) / (n + 1)   (Jeffreys posterior mean on n effective windows).
  No estimate (the LLM value stays) when the lookback has fewer than W non-war days. Window hit rates handle bursty strikes
  directly: they do not assume independent days, unlike converting a daily rate.
- L is chosen from {90, 180, 365, 730} days by Brier on SELECTION origins (monthly, 2019-01-01 .. 2022-12-01, windows ending
  <= 2022-12-31, data through 2022-12-31), pooled over W in {7, 30, 60}. Recent lookbacks are candidates because base rates move
  (the strike share in interstate wars tripled after 2022; Israel -> Syria changed with the Syrian regime).
- Reported, not used: B including Shelling/artillery/missile attacks (an upper bound: missiles qualify but artillery does not, and
  ACLED codes them together, so the primary B undercounts missile-only initiators); the daily-rate conversion 1 - (1 - h)^W.

Pairs: every direction (initiator set -> target state) of a qualifying strike contract in predictions/log.jsonl, chosen from the
contract universe, not from the event data (no selection on outcomes). Names are mapped to the event data's country names; unmatched
names are reported and excluded. Markets whose LLM reference period is under 7 days (daily contracts) are not in the universe: a
1-day rate is not a by-date belief, and those dyads' dailies are priced by the unified engine; a direction with only daily markets
is excluded (reported).

Applies to: unresolved contracts meeting the conditions of docs/strike_given_war_prereg.md (translated action type airstrike or
missile_strike, initiator and target state, parent-event relation not "equivalent" or "conflict_bound", conflict polarity, CORE,
no contract family), whose target is a whole state (sub-state targets such as "Greater Beirut" keep the LLM value; sub-territory
targets are parked). P(A) and P(B|A) are unchanged; the price is recomputed with the two-term formula, after restoring the model's
own P(B|not A) from the previous run. Where the during-war or unified component prices a contract, its price is still the one
published. Blended price and Kelly fields are logged only and are not recomputed.

Production table: rates computed at the last complete day of the local pull and frozen (no live inputs from the pull). The table
goes stale; its data-end date is recorded, and the main open problem (seeing quiet days live) is what would replace it.

Gate 1 (primary), out-of-time: TEST origins monthly 2023-01-01 .. 2026-05-01 (data through 2026-06-30; windows must end by then),
W in {7, 30, 60}, every pair not in a war episode at the origin. Empirical estimate (the selected L, data up to the origin only) vs
the LLM reference for the same pair and W: per pair, the mean daily hazard h implied by its first logged engine forecast per market
(raw rate and reference days), as 1 - (1 - h)^W WITHOUT the production cap (the LLM's implied belief at W; the capped production
value is reported). Daily contracts carry 1-day reference rates, so the cap would hand the LLM a 1-day value at W = 30; scoring the
uncapped belief is the reading most favourable to the LLM. Outcome windows containing a war day are skipped (the estimand
conditions on no war). War days are defined from data through 2026-06-30 (an episode's 25-fatality floor can be crossed after the
origin); strike days used by an estimate are only those up to the origin. Pairs without a logged LLM value are scored for the
report but not in the gate. Brier and log loss, pooled; cluster bootstrap by pair (2,000). The LLM reference was formed with
knowledge of 2023-2026, which favours it; the test is conservative for the empirical rate.
Gate 2, contract replay: every resolved qualifying contract in the Brier log whose first engine-published forecast has the logged
fields, logged price (without) vs the same P(A) and P(B|A) with the held-out P(B|not A) (data through the day before that forecast)
(with). It gates only if it has >= 10 contracts and both outcomes; otherwise it is reported only (an all-YES or all-NO set is not
a test: lesson of Oct 23).
Adoption rule: the frozen table goes live iff Brier(empirical) <= Brier(LLM reference) on gate 1 AND (gate 2 is not informative,
or Brier(with) <= Brier(without) on gate 2). Both reported in full either way.

Before any real data: a synthetic check of the estimator (zero-rate pair near 0; known Bernoulli rate recovered; bursty strikes:
window hit rate unbiased where the daily-rate conversion is not; a rate drop tracked by the short lookback; strikes inside war
episodes not counted). Any flaw found there is fixed by a dated amendment before the real fit.
Parameters derived from the local data stay in gitignored local files; the public repo records only this rule and the verdict.

# Empirical P(strike | war) for the onset engine's strike contracts — pre-registered Oct 23, 2026, before any fit or replay

Problem: for strike contracts ("Will X strike Y by D?", Polymarket's definition: an air strike or surface-to-surface missile strike
that impacts Y's territory), the engine prices P = P(A) P(B|A) + (1 - P(A)) P(B|not A). P(B|A), the chance that X strikes Y's
territory GIVEN serious clashes or war between them (A, ~ICB VIOL >= 3), is an LLM judgment blended with a deterministic position
inside an anchor range (and the action bridge). Example: Ethiopia -> Eritrea, P(B|A) 0.44-0.47 (Oct 21-23).

Change: P(B|A) for these contracts is replaced by an empirical rate from interstate wars.
- A (war episode): days with a Battles event between two states' militaries (actor1/assoc on one side, actor2/assoc on the other,
  "Military Forces of ..."), per unordered pair of states, merged into episodes when gaps are <= 30 days, kept if the episode has
  >= 25 reported fatalities (UCDP's armed-conflict threshold). Battles only, so A does not contain B by construction; wars fought
  only by strikes (no ground clashes) are not in the reference class, which makes the estimate conservative for them.
- B, for each direction X -> Y of each episode: an Air/drone strike by X's state forces located in Y's country, from the episode's
  first day to its last.
- P(B|A) = (directions with B + 0.5) / (directions + 1) (Jeffreys posterior mean), pooled over all episodes and directions.
  Reported, not used: B including shelling/artillery/missile attacks (an upper bound: artillery is not a strike under Polymarket's
  definition), B within the episode's first 30 days, episodes with >= 100 fatalities.
Applies to: the engine's price for unresolved contracts (conflict polarity; where the during-war or unified component prices a
contract, its price is still the one published) whose translated action type is airstrike or missile_strike, with both an initiator and a target state, and whose parent-event relation is not "equivalent" or
"conflict_bound" (those have P(B|A) = 1 by construction). P(A) and P(B|not A) (horizon-scaled) are unchanged; the price is recomputed
with the two-term formula. Applied as the last step before the during-war pass, after restoring the model's own P(B|A) from the
previous run, so a cached translation never compounds it. Blended price and Kelly fields are logged only and are not recomputed.

Leakage guard: HELD-OUT rate from episodes starting on or before 2026-06-30, data through 2026-06-30 only.
Replay: every resolved contract in the Brier log with a logged engine forecast on/after 2026-07-01 meeting the conditions above,
at its FIRST such logged forecast whose published price was the engine's: logged price (without) vs the same P(A) and P(B|not A) with the held-out P(B|A) (with), vs the
market at that moment. Brier, log loss, YES/NO, by dyad; cluster bootstrap by dyad (2,000).
Adoption rule: the full-data rate goes live iff Brier(with) <= Brier(without) on that replay; otherwise not.
Parameters derived from the local data stay in gitignored local files; the public repo records only this rule and the verdict.

## Amendment (Oct 23, before any fit on real data)
Synthetic check: an episode's last Battles day can be followed by strikes within the 30-day merge gap (the same episode by the
episode rule), which the "first to last day" window missed. B's window is now the episode's first day to 30 days after its last
day (the same for the shelling/missile upper bound). Everything else unchanged.

## Amendment 2 (Oct 23, before any fit on real data): the primary gate is an out-of-time test on wars
The contract replay can barely discriminate: a smoke run with a placeholder rate (no real data) found only 10 qualifying resolved
contracts (the horizon-scaled P(B|not A) and days remaining are logged only since mid-October), all resolved YES, nearly all with
P(A) < 0.1. On an all-YES set any higher P(B|A) lowers Brier, so as a gate it would pass anything above the logged values.
Added, as the primary test of the quantity itself: P(B|A) fitted on episodes starting on or before 2022-12-31 (data through then),
scored by Brier on the war directions of episodes starting 2023-01-01 .. 2026-06-30 (data through 2026-06-30), against the engine's
typical LLM P(B|A) on strike contracts (the mean over qualifying logged engine forecasts, first per market).
Adoption rule: the full-data rate goes live iff (1) Brier(empirical) <= Brier(LLM reference) on the out-of-time wars AND (2) Brier(with)
<= Brier(without) on the contract replay. Both reported in full either way.

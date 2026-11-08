# Directional P(B|A) for strike contracts — pre-registered Nov 8, 2026, before any fit or replay

Nothing below had been computed when this was committed. The MID data was inspected for structure and codes only.

## Problem
Strike contracts ("Will X strike Y by D?") are priced P = P(A) P(B|A) + (1 - P(A)) P(B|not A). P(B|A), the chance that X strikes Y
given a crisis or war between them, takes no account of X's role in the episode. Swapping in one pooled empirical rate made it worse
(Nov 6: Saudi -> Iran price 0.60 vs market 0.13). The Oct 23 pooled empirical rate failed both gates
(`docs/strike_given_war_result.md`): its level is not stationary (strikes far more common since 2023), and that result says any
revisit should model the era or the initiator, not pool across them.

## Change
Keep the engine's own P(B|A) as the level (it reflects the current era and beat the pooled empirical rate out of time), and tilt it
by X's role in the current episode with a role odds ratio estimated from MID:

    logit P'(B|A) = logit P_engine(B|A) + 0.5 * ln(OR)   if X is the target
    logit P'(B|A) = logit P_engine(B|A) - 0.5 * ln(OR)   if X is the initiator
    P'(B|A) = P_engine(B|A)                               if X's role is unclear

OR = odds(target uses force) / odds(initiator uses force), from MID. P(A) and P(B|not A) unchanged; the price is recomputed with the
two-term formula. Applied with restore-then-apply, like `pilot/strike_given_war.py`, so a cached translation never compounds it.
Same qualifying contracts as `strike_given_war.qualifies()`.

## MID estimate of OR (open data; can live in the public repo)
- Data: dyadic MID 3.1 (Maoz et al.), directed dyad rows, collapsed to directed dispute-dyads (disno, statea, stateb). Rows with
  invalid codes are dropped.
- X's level toward Y: the max of `hihosta` over that directed dispute-dyad's rows.
- Role: `rolea` = 1 (primary initiator) or 3 (primary target). Joiners (2, 4) are excluded from the primary estimate.
- A: the dyad reached use of force, i.e. max(level X->Y, level Y->X) >= 4.
- B: X's own level toward Y >= 4.
- Primary sample: disputes starting 1946-2010. Rates are Jeffreys posterior means, and OR is computed from them. 95% CI from a
  cluster bootstrap by dispute (2,000 draws).
- Known bias: MID codes a clash for both sides, which inflates the target's force rate. That pulls OR toward 1, so the tilt is
  conservative.

## Role label for live and replayed contracts
- Tracked file `pipeline/episode_roles.json`, one entry per directed pair X->Y that has in-scope strike contracts.
- Label (Adi, Nov 8: "first move", matching MID's originator coding): "initiator" if X (or its side) made the first militarized move
  of the current episode (a threat, a display, or a use of force against Y); "target" if Y did; "unclear" otherwise. Each entry gets
  a date and a one-line basis.
- Episode: the run of militarized actions between the pair (either direction, including proxies on X's or Y's side) up to the label
  date; a gap of 6 months or more with no militarized action by either side starts a new episode.
- Replay labels needed first: 17 directed pairs, all first forecast Oct 17-28, 2026. Live labels (about 28 pairs) only if both gates pass.
- ChatGPT researches the labels; Adi hand-checks them. Labels are fixed BEFORE the replay is run.
- For the replay, the label is the role in the episode that was current at the contract's first logged forecast. It uses only
  information from before that date.

## Gates
1. MID out of time: OR and rates fitted on disputes starting 1946-1989. Brier on the directions of disputes starting 1990-2010:
   role-split rates vs the pooled rate. Pass iff Brier(role) < Brier(pooled).
2. Contract replay: every resolved contract in the Brier log whose first logged forecast on or after 2026-07-01 was engine-priced
   and meets `qualifies()`. Currently 54 contracts (37 YES, 17 NO; Israel-Lebanon 16, Saudi Arabia-Yemen 16, Iran-Saudi Arabia 5,
   Iran-Iraq 4, 13 others). With = the tilted P'(B|A); without = the logged price. Brier and log loss, by dyad; cluster bootstrap by
   dyad (2,000). Pass iff Brier(with) <= Brier(without).
   Gate 2 also catches double counting: if the LLM's P(B|A) already prices the role, the tilt hurts Brier.

Adoption rule: OR goes live iff gates 1 AND 2 pass. Both are reported in full either way. If it fails, no retry on the same data.

## Reported, not gating
OR on all years and on 1990-2010 only; joiners included; the market at the same moment; Saudi -> Iran explicitly; an ACLED version
(recent-era pooled level tilted by role), run locally if the licence allows, with no parameters in the repo.

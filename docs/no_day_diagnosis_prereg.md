# Pre-registration: where does the engine lose on NO outcomes? (Nov 4, 2026)

Written before the join. Script: `analysis/no_day_diagnosis.py` (synthetic checks pass). It joins two result files already on disk
(`pilot/local/degradation_replay.json` from T3, `pilot/local/answer_key_agreement.json` from T2); no new pricing. Report only.

## Why

- Roadmap step 1 was "recalibrate q". But q (P(qualifying strike | fighting day)) is a posterior per pair: a weak prior from the
  world fit, updated by the pair's own resolved contracts, which already use the contract definition. For Israel→Lebanon, q ≈ 0.97
  comes from ~48 YES dailies out of 51. So "q is overconfident" is not established.
- NO outcomes are where we lose (fair record: 0.328 vs market 0.223; T3 replay NO Brier 0.448). Two different causes predict two
  different fixes:
  - **A. Fighting, no qualifying strike:** the pair kept fighting (shelling, ground action), but nothing the contract counts. The fix
    is on the strike side: a definition-consistent q.
  - **B. True quiet:** nothing happened; the engine still believed the pair was fighting (a lull it could not see). The fix is on
    the state side: regime persistence and exit (μ), quiet-day information. Not q.
- The local data separates them: T2 recorded, for every contract in its window, whether the local data (broad definition) has a
  strike day.

## Measure and rule (fixed now)

- Sample: NO contracts in the T3 replay (FULL arm, 119 contracts) that also appear in T2 (windows inside the local data, to Oct 9).
- Class A: T2 local strike day in the window. Class B: none.
- Excess Brier over the market, summed per class: Σ (ours² − market²) over the class's NO contracts (market at the same moment).
- **Rule:** if class A carries ≥ 50% of the total excess → **lever = q** (next: pre-register a definition-consistent q).
  Otherwise → **lever = state** (next: pre-register a change to regime persistence / exit). If total excess ≤ 0 → no NO-side fix.
- Reported, not deciding: counts and excess by pair; calibration of FULL prices by decile (all 119 contracts).

## Known before registration

- T2's per-class counts across all 46 NO contracts (16 with local strike days, 30 without) and the pairs involved; T3's NO-side
  Brier. Not known: the joined subset or how the excess splits.

## Known limits

- **Small n:** the joined NO set is a few dozen contracts from a handful of pairs; the rule picks a direction to work on, not a
  parameter value. The fix itself gets its own pre-registration and replay.
- **The local data is the broad definition and lags by a week:** class B may include contracts with strikes the local data missed.
- Holds contracts are not in the T3 replay; the US×Iran ladder losses are outside this diagnosis.

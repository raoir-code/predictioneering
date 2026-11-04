# Pre-registration: the DAG sets the onset rate for quiet strike pairs (roadmap step 3, Nov 4, 2026)

Written before any run on real data. Script: `analysis/dag_onset_replay.py` (synthetic checks pass). Engine code: `pilot/unified_price.price_group`
accepts `P["h_dag"]`; inert unless a caller sets it (only this replay, and production only after adoption).

## Why

- One engine: SSPE/God's DAG explains whether a fighting episode starts (onset rate h); the hazard model explains what happens once
  it has (q, μ). Today they are two disconnected formulas. Strike contracts on pairs with no fitted history and no sign of fighting
  are declined by the hazard model ("engine decides onset") and priced by the standalone DAG path: P(A) × an LLM's P(B|A).
- That path's misses on such pairs: Pakistan→Yemen 0.40 vs market 0.05, Saudi→Iran 0.39 vs 0.12, Israel→Iraq 0.02 vs 0.32.
- Step 3 routes these contracts through the one equation, with the DAG supplying h. The LLM's P(B|A) disappears for them: the strike
  rate given fighting is the hazard model's q.

## Scope (fixed now)

- Strike-template contracts ("X military action against / X target Y on / by date") in groups the unified engine declines today:
  class prior only, no resolved YES window, no news sighting.
- Excluded: sub-national targets (Greater Beirut, Moscow, Kyiv, Mecca: out of scope by event class), ceasefire families, pairs the
  hazard model already prices.

## Method (fixed now)

1. **DAG onset rate.** From the standalone engine's P(A) for the same contract and run (as logged, including its ICB crisis boost:
   when a crisis is known, its base rate is part of the DAG's answer), over d days to the contract date (logged `days_remaining`;
   older rows lack it, so deadline − forecast date, as the engine computes it): h_DAG = −ln(1 − P(A)) / d.
2. **Attenuate by log-linear pooling with the class prior:** log h = (1 − w)·log h_class + w·log h_DAG, **w = 0.5** (the base
   attenuation of the back-of-the-envelope rule; 0.25 and 0.75 reported only). The class prior is the held-out world fit
   (data ≤ 2026-06-30), as in the other replays.
3. **Everything else from the hazard model unchanged:** class μ, q, q0, production hardening and anchors. Start state: the
   reverse direction's fighting probability where it has resolved windows (as today), otherwise the model's own start.
4. **Price:** P(at least one qualifying strike in the contract's window) from the unified forward pass.

## Replay and adoption (fixed now)

- **Sample:** every resolved contract in scope, priced at its first forecast time, with P(A) and d as logged at that time.
- **Arms:** STANDALONE = the published price logged at that time; DAG-H = the method above. Market at the same moment, reported.
- **Adopt if both:** (1) Brier(DAG-H) ≤ Brier(STANDALONE); (2) no pair with ≥ 3 contracts worse by more than 0.05.
- If adopted: the unified engine prices these groups in production, with the day's P(A) from the engine pass (the wiring is a
  separate commit; one engine change, its own run, patch note). The standalone path stops pricing them. No shadow period: adopted
  means live.
- Reported, not deciding: the pair-cluster bootstrap; YES/NO split; w = 0.25 / 0.75.

## Known before registration

- A smoke run of the script in a sandbox with the **repo** priors (not the held-out local fit, so a different scope and different
  prices) printed numbers: 55 contracts, mostly Iran ladders, standalone 0.248 vs DAG-H 0.202, harm-guard failures on Iran→Qatar and
  Iran→Saudi Arabia. Those numbers are not the result and decide nothing; the scope under the held-out fit differs (pairs with a
  world fit are out of scope).

## Known limits

- **Small, NO-heavy sample:** the rule mostly guards against harm; forward resolutions are the real test.
- **P(A) is undirected** (a dyad's onset); the contract's direction comes from its initiator.
- **P(A) includes the ICB "live boost"** (acute crisis signals); the back-conversion to a daily rate treats it as constant over
  the horizon.
- Not data-bound to the raw local tables (uses the frozen class priors and logged prices), but depends on keeping the derived
  tables after Nov 23 (licensing call).

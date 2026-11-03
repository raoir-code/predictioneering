# Pre-registration: fit the strike priors on the contracts' own definition of a strike (Nov 3, 2026)

Written before any fit or replay on this definition. Script: `analysis/contract_def_refit.py` (synthetic checks pass).
Outputs are local and gitignored; production changes only if the rule below adopts.

## Why

- Polymarket's strike contracts count **air strikes (incl. one-way attack drones) and surface-to-surface missiles**. They
  exclude artillery, mortars, rocket artillery (MLRS), ground incursions, small arms, ATGMs and minor drones.
- Our unified world priors and last-strike anchors count every "Air/drone strike" and every "Shelling/artillery/missile attack".
- Where a side mostly shells, the two diverge. Israel→Syria in 2026: Jul 13 / Aug 13 / Sep 19 / Oct (to the 9th) 7 strike days
  on our definition, against 1 / 3 / 0 / 1 air/drone days. The current series resolved **NO three times** (Aug 31, Sep 15,
  Sep 30); the unified engine priced those at 0.61–0.76.
- For Israel→Lebanon (air almost every day) and Saudi→Yemen the two definitions nearly coincide, so the change should mostly
  move pairs where shelling dominates.

## The contract definition (fixed now)

- Every "Air/drone strike" event.
- Plus every "Shelling/artillery/missile attack" event whose notes name a missile (`ballistic`, `cruise`,
  `surface-to-surface`, `missile(s)`), **minus** anti-tank guided missiles (`anti-tank`, `ATGM`, `Kornet`).
- Everything else unchanged: actors, territory, maritime exclusion, the world-fit model and its pooling (`analysis/world_fits.py`),
  hardening β and K.

## Arms

- **Broad (current method):** the held-out world fit already on disk (`pilot/local/heldout/`, data ≤ 2026-06-30) and the current
  anchors (`pilot/local/last_strike.json`).
- **Contract:** the same held-out fit on the contract definition (`pilot/local/heldout_contract/`) and anchors on the contract
  definition. The engine reads anchors only ≥ 7 days before the forecast, as in production.
- **Replay:** `analysis/refit_compare.score_rows`, unchanged: every resolved contract first forecast on or after 2026-07-01,
  priced at production's first-forecast time; market at the same moment, reported only.

## Adoption rule (fixed now)

Adopt the contract definition if **both** hold:

1. Brier(contract) ≤ Brier(broad) on the replay; and
2. no pair with at least 3 replayed contracts is worse by more than 0.05 (the unified publish rule's harm guard).

If adopted: the production fit on the contract definition (`pilot/local/candidate_contract/`, data through the last complete
day) and the contract anchors replace `pilot/local/priors_world.json`, `world_fits.json` and `last_strike.json`. The previous files
are kept in a dated backup folder. One engine change, on its own run, with a patch note.

Reported, not deciding: the cluster-bootstrap interval by pair, YES/NO split, every pair.

## Known limits

- **The notes classifier is a keyword rule.** It cannot separate FPV or loitering munitions from other drone strikes (both are
  "Air/drone strike"), and it may count a reported but intercepted missile. Both make the contract definition slightly too broad.
- **Older contract series may have used broader wording.** The rule scores them all against this definition anyway.
- **The replay is small** (about a hundred contracts, mostly YES days in two wars); a pass is weak evidence, a pair-level harm
  is the stronger signal.
- **Data-bound:** the refit needs the local event data, so it must run before Nov 23.

## Amendment 1 (Nov 3, before any completed fit and before any replay)

- **What happened:** `--describe` (monthly strike counts only, no outcomes) showed Iran→Israel collapsing from 31 strike days in
  March 2026 to 3. A look at the rows showed why: **the local tables carry no notes text** (fields: date, type, sub-type, actors,
  country, province, fatalities). The missile keyword rule could therefore never fire. A `--fit` had been started and was
  stopped before it finished; no replay was run.
- **New contract definition:** every "Air/drone strike" event, plus "Shelling/artillery/missile attack" events **only where the
  attacker's home state shares no land border with the target**. Such strikes are beyond artillery range, so they are missiles.
  - Bordering pairs (Israel→Syria, Israel→Lebanon, Saudi Arabia→Yemen, Pakistan→Afghanistan, Iran→Iraq) and forces fighting in
    their own country keep air/drone events only.
  - Home state: a faction maps to its territory (`Yemen [Houthi]` → Yemen); a named coalition to its lead state
    (`Operation Restoring Hope` → Saudi Arabia, `Global Coalition Against Daesh` → United States). A fixed land-border table
    covers the world fit's region; a pair outside it keeps air/drone events only, and `--describe` reports how many events that
    affects.
- **New known limits:**
  - Missiles fired across a land border are dropped (for example a cross-border ballistic missile).
  - Expeditionary forces' in-country artillery (e.g. foreign forces shelling inside Syria or Iraq) is counted as a missile strike
    when their home state does not border the target.
- Arms, replay and adoption rule are unchanged.

**Erratum to amendment 1 (Nov 3, before any completed fit and before any replay).** `--describe` listed the shelling/missile
events falling outside the border table: United States→Iran (26 events) and Iran→Bahrain (7) were among them, i.e. counted as
non-strikes. Causes: the United States was missing from the table, and a state with no land border (Bahrain) was never registered.
Fixed by registering every listed state and adding the United States, United Kingdom, France, China, the two Koreas, Myanmar,
Thailand, Cambodia, Greece, Venezuela and Colombia. The definition itself is unchanged. The second `--fit` was stopped before it
finished.

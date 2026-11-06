# Pre-registration: the open-data contingency for the local tables (Nov 6, 2026)

**Question.** If the local event tables can no longer be refreshed or kept after Nov 23, what should the unified engine use for its
world priors, hardening (β, K) and strike-date anchors? The candidates are the repo priors with hardening and anchors off (REPO, the
state before Oct 26), or the same model refit on open data, UCDP GED (OPEN).

**Why now.** The comparison needs the local reference (FULL), which can only be computed before the data ends. The degradation
replay (`docs/degradation_replay_prereg.md`, Nov 3) found all three local components load-bearing: deleting everything costs +0.021
Brier, hardening alone +0.016, stale anchors +0.003.

## Data (open, CC BY 4.0)

- UCDP GED 26.1 (1989–2025) and GED Candidate 26.01–26.09 (Jan–Sep 2026); sha256 as in `data/external/ucdp/MANIFEST.json`.
- Candidate rows inside GED's span are dropped (GED supersedes them).

## Strike series (`analysis/ucdp_refit.py`), fixed before any replay

- **Attacker and location:** T1's rule (`analysis/open_events_agreement.attackers`). If the location's government is a party, the
  other side's governments strike it. If it isn't, every government side strikes it. The government of Yemen acting abroad is
  `Yemen [Houthi]`.
- **Ambiguous events dropped:** governments on both sides and the location not a party (e.g. Iran vs Israel and the US in Kuwait).
  The attacker can't be told apart.
- **Events:** type_of_violence 1 (state-based) and 3 (one-sided), from 2015-01-01. Exact dates (date_prec 1) are observed; others
  are unobserved in the fits and count as strike dates in the hardening spells and anchors (as in the local fits).
- **Class:** `world_fits.klass`, with the target read from the event. Location's government a party → state; attacker a faction →
  de facto authority; else → non-state; one-sided → no named target.
- **Fits:** `analysis/world_fits.py` unchanged (two-state model, ≥ 10 exact active days, class shrinkage); the hardening estimator
  of `analysis/hardening_fit.py` (theory test 4's robust G = 30 coefficient, K over spell-weeks).
- **Known differences from the local data:** lethal events only; no air vs artillery split; ground fighting included; no Saudi
  Arabia → Yemen (UCDP codes Saudi Arabia as a secondary supporter) and no coalitions.

Computed before this document (inputs only; no contract outcome read): held-out priors (window to 2026-06-30), production
hardening β = −0.640 (p ≈ 1e−70, 36,319 spell-weeks, 513 restarts), anchors for 113 pairs.

## Replay (`analysis/degradation_replay.py --measure-open`)

Same replay as T3 (`refit_compare.score_rows`): every resolved strike contract first forecast on or after 2026-07-01, priced at
production's first-forecast time, scored on its resolution. Contracts priced in every arm only.

| Arm | Priors | Hardening | Anchors |
|---|---|---|---|
| FULL | local, held-out (≤ 2026-06-30) | local, production | local, full table (≥ 7 days before, as live) |
| REPO | repo | off | none |
| **OPEN** | UCDP, held-out (≤ 2026-06-30) | UCDP, production (≤ 2026-09-30) | UCDP, cut at 2026-06-30 |
| OPEN_NOHARDEN | UCDP, held-out | off | UCDP, cut at 2026-06-30 |

The OPEN anchors are cut at the replay's start, like T3's STALE arm, because UCDP Candidate data arrives with up to a month's
lag. After the cut, anchors come only from news sightings and resolved windows, as live.

## Decision rule

1. **The fallback after the local data ends** is the arm with the lowest Brier among OPEN, OPEN_NOHARDEN and REPO. **An open arm
   within 0.002 of the best wins**, the lower open arm first: it has an open licence and can be refreshed monthly.
2. Reported, not decisive: OPEN − FULL and REPO − FULL (what the loss costs), OPEN − REPO, OPEN − OPEN_NOHARDEN, each with a 95%
   bootstrap interval over pairs; Brier by pair.
3. **Adoption is a data-source change, not a model change.** If OPEN or OPEN_NOHARDEN is chosen, it replaces the local tables in
   production when they must be deleted (not before), in its own run, with a patch note. Its outputs then move from `pilot/local/`
   into the repo (open licence).
4. No re-tries on the same replay set. If REPO is chosen, the open refit is not re-tuned on these contracts.

Out of scope: the old path's P(B|¬A) table (`strike_no_war.json`). UCDP can't stand in for its low-casualty strike pairs (T1); if
the table can't be kept, the old path falls back to its own estimate, as before Oct 26.

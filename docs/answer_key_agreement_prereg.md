# Pre-registration: do the local strike days agree with how our strike contracts resolved? (Nov 3, 2026)

Written before any join with the local data. Script: `analysis/answer_key_agreement.py` (synthetic checks pass; the measuring code
was smoke-tested on fabricated strike days only). Outputs are local and gitignored; nothing here touches production.

## Why

- Every detection and calibration test so far used the local event data as the answer key. After its data ends, the answer key
  becomes **resolved Polymarket contracts**, which use the contracts' own strike definition.
- If the two agree, results before and after the switch are comparable. If not, they must never be pooled, and we learn where the
  definitions diverge (e.g. Israel→Syria artillery, `docs/contract_def_refit_result.md`).

## Sample (fixed now)

- Every resolved strike contract in `pilot/unified_data.load()` (the "X military action against Y on/by date" template), ceasefire
  "holds" contracts excluded, whose window lies inside the local data (first 2026 event date .. last complete day).
- Window days follow the engine (`unified_data.windows`): a YES uses every day it touched; a NO only fully covered days; days in the
  rules' time zone.
- Reference keys: the initiator's own state or faction plus coalitions it leads (`Operation Restoring Hope` for Saudi Arabia); a
  collective target ("an Arab country") is the union of its listed members. Contracts with no reference key (sub-territories such as
  Greater Beirut, collectives without members) are listed as unmapped and excluded.
- **Local YES** = at least one exact-date strike day of those keys in the window (the world-fit series: air/drone plus
  shelling/artillery/missile, maritime excluded).

## Measures and rule (fixed now)

- **P(local yes | contract YES)** and **P(local no | contract NO)**, with 95% intervals by bootstrap over (pair, ISO week of the
  window's end) clusters, 2,000 draws.
- **CONTINUOUS** if both lower bounds ≥ 0.9: future tests scored on resolved contracts may be compared and pooled with past results
  scored on the local data.
- **BREAK** otherwise: the two answer keys are never pooled; past results stay statements about the local definition; the pairs
  with disagreements are recorded as definition mismatches for any later refit.
- Reported, not deciding: agreement and kappa; daily vs by-date; by pair; the same with any date precision and ±1 day; every
  disagreement with the local strike days within 3 days of the window.

## Known before registration

- Every contract's outcome (public), the local strike-day totals of several directions from earlier results, and the Israel→Syria
  mismatch (three NO resolutions on days the local data had shelling). So a BREAK on Israel→Syria is expected; the informative pairs
  are Israel→Lebanon, Saudi Arabia→Yemen and the Iran ladders.

## Known limits

- **Contracts sit on hot pairs and recent months** (mostly Jul–Oct 2026), so this is agreement where markets exist, not in general.
- **Local coding lags:** strikes in the last week before the data end may be missing; the window stops at the last complete day.
- **Overlapping contracts** (a daily inside a by-date ladder) share days; the cluster bootstrap absorbs part of that dependence.

# Pre-registration: can NNA see Israel→Lebanon strike days, and quiet ones? (Nov 10, 2026)

Committed with the labeler (`pilot/nna_label.py`, prompt `nna-v1`) before any article is labeled for scoring and before any
answer key is joined. Report only; nothing here changes production. A later, separately pre-registered stage would turn a pass
into quiet-day evidence (quiet-days plan, Part 4).

## Why

Our news stream catches 1 strike day in 5 (d 0.20, Oct 27) and its misses cluster, so a day with no report says nothing.
GDELT failed on false alarms; news + GDELT failed jointly (Nov 3). The market saw Nov 6 and Nov 7 as quiet; we priced 0.93 and
0.92. Lebanon's state news agency (NNA) reports Israeli actions in Lebanon the same day and names the weapon, and the contract's
resolution sources include official Lebanese information.

## Source

- NNA **English** articles (`pilot/nna_fetch.py`): every article in the 13 English categories active in 2026, from the public
  daily sitemaps; title, description (NNA items are one or two sentences), publish time. No keyword filter.
  English chosen before labeling: its daily lists cover nearly every day Jul–Nov 2026 and its URLs describe the event; Arabic
  is not used.
- Day = Beirut calendar day of the event (`event_day` "previous" moves an item to the day before its publication).
- A day with no fetched article is **unobserved**, never quiet.

## Labels (prompt `nna-v1`, frozen by this commit)

Each article → one class, highest action wins:
- **QUALIFYING:** Israeli air strike (bombs, air-to-surface missiles, air-launched drone strikes) or surface-to-surface missile /
  one-way attack drone that hit Lebanese land.
- **BORDERLINE:** a drone dropping a small munition (grenade, sound bomb, stun bomb, incendiary, "explosive materials").
- **OTHER_ACTION:** artillery, tank shells, mortars, gunfire, demolitions, incursions, sweeps, bulldozing, arrests, overflights,
  flares, ATGM, FPV drones, short-range loitering munitions, intercepted munitions (all excluded by the contract's rules).
- **NONE:** everything else.

**Hand-check before scoring:** 30 items drawn by `--sample` (10 QUALIFYING, 10 OTHER_ACTION, 5 BORDERLINE, 5 NONE that mention
Israel / strikes; seed 1110). Adi records agree / disagree on the class. The labels are used only if at least 27 of 30 agree.
Otherwise the prompt is revised as a new version, everything is relabeled, and a fresh sample is drawn, all before scoring.

## Answer keys and the hit definition

1. **Local event data** (primary for the decision), Jul 1 – the last complete day (latest event minus 7 days). A true strike day:
   at least one "air/drone strike" event by Israeli state forces located in Lebanon. That category includes drone-dropped
   munitions, so on this key a **hit = a QUALIFYING or BORDERLINE item** that day. Artillery-only days are not strike days.
2. **Resolved Polymarket dailies** ("Israel military action against Lebanon on <date>"): the contract's own truth, every daily
   resolved by the time the analysis runs (51 now: 48 YES / 3 NO). On this key a **hit = a QUALIFYING item** (the contract's
   reading); BORDERLINE-counts reported as a sensitivity.

## Estimands

Per key: d = P(hit | strike day), α = P(hit | no strike day), Jeffreys estimates (k + 0.5) / (n + 1); LR(no hit) =
(1 − d) / (1 − α), the factor a silent day applies to the odds of a strike. 95% intervals: bootstrap over ISO-week blocks
(2,000). Also: clustering, P(miss | missed the previous strike day) vs P(miss); lag (same day / next day / later); coverage
(observed days / calendar days); class counts; the borderline-only days.

## Decision rule (fixed now)

NNA may carry quiet-day evidence for Israel→Lebanon if, on key 1, **both** hold:
1. d's lower 95% bound ≥ 0.50, and
2. LR(no hit)'s upper 95% bound < 0.5 (a silent day at least halves the odds of a strike).

Key 2 must not contradict: its point estimates of d and α fall inside key 1's 95% intervals, or the result is reported as
a conflict and nothing is adopted. Key 2 cannot pass or fail on its own (few NO days).

If the rule fails, NNA stays a sighting source at most, and silence stays worthless. No retry on the same data.

## Deadline

Key 1 is gone after Nov 23: fetch, label, hand-check and score by Nov 19.

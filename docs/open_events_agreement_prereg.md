# Pre-registration: can open event data replace the local event data as the source of strike days? (Nov 3, 2026)

Written before any join with the local data. Script: `analysis/open_events_agreement.py` (synthetic checks pass; `--describe`
reads the open data only). Outputs are local and gitignored; nothing here touches production.

## Why

- The world priors, hardening, last-strike anchors and the P(strike | no war) table are fit on the local event data. After its
  data end, the slow parts (base rates by pair class, hardening β) stay valid for years; the fast part (each pair's last strike
  date) goes stale and is refreshed only by our own news sightings.
- If an open dataset matches the local strike days closely enough, it can carry refits and anchors forward. It must be measured
  while both can still be compared.
- Candidate: **UCDP GED Candidate**, monthly releases with at most a month's lag, CC BY 4.0 (Hegre et al. 2020). File:
  `GEDEvent_v26_01_26_09.csv` (Jan 1 – Sep 30, 2026; sha256 `134da9b3df08b65266802c4b662e572f396c70c92ab62297319be657540bcede`).

## Series compared (fixed now)

- **Reference:** the world-fit strike series (`analysis/refit_local.py` rules): air/drone strikes plus shelling/artillery/missile
  attacks, maritime excluded, attacker = actor 1's state or de facto authority (coalitions → lead state), target = event country,
  exact dates only.
- **Open:** UCDP events of type 1 (state-based) or 3 (one-sided), exact dates only (`date_prec` = 1). Direction attacker → location:
  - the location's government on one side → every government on the other side;
  - the location's government not a party, one side without a government (e.g. Israel vs Hezbollah in Lebanon) → the government side;
  - governments on both sides, neither the location's (e.g. Iran vs Israel+US in Kuwait) → every government, flagged **ambiguous**;
  - UCDP's "Government of Yemen" acting outside Yemen → the reference's Houthi key.
- **Window:** Jan 1 – Sep 30, 2026, cut at the reference's last complete day.

## Measures

- Per direction with ≥ 5 reference strike days: **recall** = share of reference strike days with an open event within ±1 day;
  **precision** = share of open strike days with a reference strike within ±1 day. 95% intervals by bootstrap over ISO weeks
  (2,000 draws); pooled numbers over (direction, ISO week) blocks.

## Rules (fixed now)

- **REFIT-GRADE:** recall lower bound ≥ 0.6 **and** precision lower bound ≥ 0.8. Eligible as the strike-day source for refits.
- **ANCHOR-GRADE:** precision lower bound ≥ 0.8 only. Eligible as a source of last-strike dates (an open day is a real strike day),
  not of rates.
- **NONE:** otherwise.
- **Plan verdict:** if REFIT-GRADE directions carry ≥ 50% of the reference strike days among contract directions → **open-data
  refits** for those directions (the rest stay frozen). Otherwise → **no open-data refits; priors stay frozen.**
- Using an open source in production (refit or anchors) is a separate engine change with its own pre-registration. This test only
  qualifies a source.
- Reported, not deciding: the pooled intervals; open-only directions (≥ 5 open days, < 5 reference days: a naming check); the
  same grades with ambiguous events dropped.

## Known before registration

- `--describe` on the open data alone (no outcomes): strike days by direction and month. Israel→Lebanon 161, Israel+US→Iran 65
  (UCDP's Iran-war dyad joins them, so the two directions are identical), Pakistan→Afghanistan 39, Afghanistan→Pakistan 23,
  Iran→Iraq 18, Iran→Kuwait 8; Israel→Syria 2 (type 1/3, any precision); no Saudi→Yemen or Houthi direction.
- Reference strike-day totals for several directions in Jul 1 – Oct 9 from earlier results (`docs/strike_feed_detection_result.md`).
- So several grades are predictable (Israel→Syria, Saudi→Yemen and Houthi directions will be NONE). The informative directions are
  Israel→Lebanon, Israel/US→Iran, Iran→Iraq and Pakistan↔Afghanistan.

## Known limits

- **Lethal events only.** UCDP codes an event only with at least one death; non-lethal strikes are missed by design.
- **No event type.** Air strikes, shelling and ground clashes are not separated; a ground clash in south Lebanon counts as an
  Israel→Lebanon day.
- **Coalition dyads cannot be split.** US→Iran and Israel→Iran are one series; ambiguous third-country events count for every
  government.
- **Secondary supporters are not in the candidate data**, so the Saudi-led coalition's strikes in Yemen have no open series.
- **Candidate releases are revised** in the annual GED; this measures the candidate as released.

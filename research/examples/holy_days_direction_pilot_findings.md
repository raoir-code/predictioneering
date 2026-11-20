# Holy Days and Hard Bargains — preliminary ACLED direction-coding audit

**Status (2026-11-20):** Preliminary, **AI-assisted review only**; not independently verified, not a pre-registration and not a tested holiday effect. Raw licensed ACLED source notes and the reviewed worksheet remain private in a researcher's local files, not this public repo.

## Source and sampling

- Pilot: ACLED Lebanon, 2024-10-01 to 2024-10-31; 3,046 raw events, 3,038 on exact dates.
- 2,964 events eligible for the **provisional weapons-user proxy** (Actor1 as tentative side using weapons, **not necessarily initiator of hostilities**), limited to exact-date air/drone strikes and shelling/missile events, not battles or mine/IED cases.
- Eligible population counts by ACLED subtype and Actor2 availability: air/drone+Actor2 1,485; air/drone-no Actor2 1,034; shelling+Actor2 68; shelling-no Actor2 377.
- Deterministic stratified sample: 20 from each of the four strata (80 total). This **oversamples** shelling relative to population composition. Neither 80-case simple percentages nor independently judged accuracy can be generalized to other theaters, actors or years.
- On 2026-11-20, user provided a CSV annotated by Claude from ACLED notes, with every reviewer reason explicitly marked **AI-assisted annotation, not verified ground truth**. The local uploaded file was inspected; all 80 rows had unique IDs and all expected review columns.

## Observed provisional judgments (NOT independent validation)

| Subtype | Actor2 available? | Population | Reviewed | Actor1 weapons user yes | Actor1 unclear | Actor2 target yes | Actor2 unclear | Actor2 target no |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Air/drone strike | Yes | 1,485 | 20 | 20 | 0 | 1 | 19 | 0 |
| Air/drone strike | No | 1,034 | 20 | 20 | 0 | n/a | n/a | n/a |
| Shelling/artillery/missile | Yes | 68 | 20 | 19 | 1 | 13 | 6 | 1 |
| Shelling/artillery/missile | No | 377 | 20 | 19 | 1 | n/a | n/a | n/a |

**Totals:** provisional Actor1 weapons-user assignment judged yes in **78/80** (97.5% in the **stratified sample**, not population estimate), unclear in 2/80 and contradicted in 0/80. Of **40** reviewed events with an Actor2, only **14** judged confirmed Actor2 targeted (35%), **25** unclear (62.5%) and **1** contradicted (2.5%); 40 other rows have no Actor2. A high apparent Actor1 agreement rate does **not** establish independent, blinded reliability. Reasons were authored by the same annotating AI and must not be treated as independent ground truth. Eight case identifiers were separately highlighted for human attention in the accompanying AI report; most are uncertainties, not proven coding errors.

## Implications for paper hypotheses

1. **H1 own holy-day restraint** may be measurable using observed violence *by weapons-using actor* if the proxy survives independent local verification, the actor-specific holiday calendar is valid, and the wider panel supplies meaningful within-actor date variation. Do not treat calendar correlations as causal without robust weather/season/reporting checks.
2. **H2 opponent-holiday exploitation** is **not** testable by silently setting Actor2 equal to the target: even among events with Actor2 filled, 25/40 target judgments were unclear and one contradicted. Build source-validated dyadic target-side mappings, or narrow to cases where the adversary is identifiable; report what gets excluded.
3. **Actor1 -> event country is NOT a universal substitute for Actor1 -> adversary.** Events within Lebanon can involve Lebanese and outside military actors, civilians, peacekeepers and multiple armed sides; the country where force occurred is not by itself the target actor's affiliation or holy-day calendar. Any territory-level alternative must be defended as a different estimand.
4. **H3 shared-holiday truces** needs a separate ceasefire/agreement outcome dataset rather than inferring peace from absence of ACLED events.
5. **Learning and visibility mechanisms** require independent measurement and should not be assumed identified by event subtypes alone.

## Next scientific gate (in priority order)

1. Perform genuinely independent human/source verification of the eight flagged cases **plus a separate small random subsample of AI-affirmed cases**. Document adjudication and disagreements; avoid only inspecting the hardest cases.
2. Copy reviewed CSV to the locally gitignored ACLED directory (no overwrite required); run:
   `python -m research.factory.holiday_direction --evaluate --review-file research/inbox/acled/holy_days/DIRECTION_VALIDATION_PRIVATE_reviewed.csv`
   The output rates are *conditional on decisive review* and remain AI-assisted pending human verification.
3. Define and freeze actor/religious holiday calendars and target-side identification rules before expanding to multiple holiday seasons/theaters. Pull both sides of relevant borders; analyze day/pair exposure, including zeros.
4. Solve the repeated bargaining game before interpreting the shared-holiday prediction. Calendar dates are anticipated; deterrence, feints and preparation might reverse naive exploitation effects.

**Explicit non-result:** No causal estimates, no holiday-specific regressions, no proven model predictions, and no scientific novelty claim have been established by this audit.

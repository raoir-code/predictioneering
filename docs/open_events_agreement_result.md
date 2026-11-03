# Result: open event data vs the local strike days: OPEN-DATA REFITS for REFIT-GRADE directions (Nov 3, 2026)

Pre-registration: `docs/open_events_agreement_prereg.md` (`74df2d0`, before the join). Script: `analysis/open_events_agreement.py --measure`.
Window Jan 1 – Sep 30, 2026; UCDP GED Candidate 26.01.26.09; ±1 day.

## Verdict

Contract strike days in REFIT-GRADE directions: **0.559** (rule ≥ 0.5) → **open-data refits for REFIT-GRADE directions; every
other direction stays frozen.** Same verdict with ambiguous events dropped (0.559). Pooled recall 0.42–0.52, precision 0.92–0.97.

## Contract directions (* in the output)

| Direction | Ref days | Open days | Recall (95%) | Precision (95%) | Grade |
|---|---|---|---|---|---|
| Russia→Ukraine | 273 | 273 | 1.00 | 1.00 | REFIT |
| Israel→Lebanon | 270 | 160 | 0.82 (0.74, 0.89) | 1.00 | REFIT |
| United States→Iran | 77 | 65 | 0.86 (0.70, 0.96) | 0.94 (0.85, 0.99) | REFIT |
| Pakistan→Afghanistan | 56 | 33 | 0.79 (0.61, 0.91) | 0.94 (0.83, 1.00) | REFIT |
| Israel→Iran | 43 | 65 | 1.00 | 0.65 (0.36, 0.85) | NONE |
| Iran→Kuwait, Oman, UAE, Bahrain, Jordan, Saudi Arabia, Syria | 11–55 | 0–7 | 0.02–0.42 | 1.00 | ANCHOR |
| Israel→Syria | 100 | 2 | 0.02 | 0.5 | NONE |
| Iran→Iraq | 91 | 18 | 0.33 (0.14, 0.51) | 0.94 (0.78, 1.00) | NONE |
| Saudi Arabia→Yemen | 62 | 0 | 0 | – | NONE |
| Iran→Qatar | 16 | 0 | 0 | – | NONE |

## Reading

- **The open data covers the high-casualty wars** (Ukraine, Lebanon, the Iran war, Pakistan–Afghanistan) and **not the routine
  strike pairs** (Israel→Syria, Saudi→Yemen, Iran→Iraq, Iran→Gulf). The low-coverage pairs are the same ones our news feed misses.
- **REFIT-GRADE recall is 0.8–0.9, not 1.** A refit on the open data would undercount strike days by 10–20%; any refit must
  correct for that, under its own pre-registration.
- **Israel→Iran vs United States→Iran:** the open data joins them into one series. The reference splits them and also has a joint
  "United States and/or Israel" actor (42 days), so Israel→Iran's precision is low by construction.
- **Every ANCHOR grade depends on ambiguous events:** with them dropped, all Iran→Gulf directions fall to NONE (Israel→Syria rises
  to ANCHOR on 1–2 days). Treat them as NONE in practice.
- **Pakistan→Afghanistan has 56 reference strike days** in this series. The earlier "0 strike days" was from the detection test's
  Jul–Oct window and state-forces rule, not a naming error in the world-fit series.

## What follows

Nothing changes in production. After the local data ends, a refit or anchor feed from the open data for the four REFIT-GRADE
directions is a separate engine change with its own pre-registration (recall correction included). Every other direction keeps
its frozen priors, with anchors from news sightings and resolved contracts.

# Result: strike priors on the contracts' own strike definition: NOT ADOPTED (Nov 3, 2026)

Pre-registration: `docs/contract_def_refit_prereg.md`, with amendment 1 and its erratum (all before any completed fit or replay).
Script: `analysis/contract_def_refit.py --compare`. Replay: 119 resolved contracts first forecast on or after 2026-07-01.

| | Broad (current) | Contract definition | Market |
|---|---|---|---|
| **All (n=119)** | **0.1439** | **0.1452** | 0.1293 |
| YES (n=102) | 0.0932 | 0.1022 | 0.1253 |
| NO (n=17) | 0.4481 | 0.4035 | 0.1532 |

| Pair | n | YES | Broad | Contract | Market |
|---|---|---|---|---|---|
| Israel→Lebanon | 51 | 48 | 0.0597 | 0.0775 | 0.0748 |
| Saudi Arabia→Yemen | 37 | 33 | 0.2236 | 0.2147 | 0.1857 |
| Iran→Arab country | 8 | 8 | 0.0294 | 0.0152 | 0.1330 |
| Iran→Iraq | 8 | 8 | 0.1212 | 0.1293 | 0.1734 |
| Israel→Syria | 6 | 3 | 0.4501 | 0.3905 | 0.2137 |
| Iran→Jordan | 3 | 2 | 0.4545 | 0.4624 | 0.2638 |
| Iran→Kuwait | 2 | 0 | 0.1196 | 0.1025 | 0.0305 |
| Israel→Yemen | 2 | 0 | 0.0185 | 0.0200 | 0.0295 |
| Iran→Bahrain | 1 | 0 | 0.1660 | 0.1634 | 0.0240 |
| Iran→UAE | 1 | 0 | 0.0973 | 0.0899 | 0.0342 |

Cluster bootstrap by pair: contract − broad = +0.0013, 95% [−0.0218, +0.0137]. Pairs worse by > 0.05 (n ≥ 3): none.

## Verdict: NOT ADOPTED

Rule 1 fails (0.1452 > 0.1439); rule 2 passes. Production priors and anchors are unchanged.

## Reading

- **The fix works where it was aimed:** Israel→Syria (0.450 → 0.391) and the NO outcomes (0.448 → 0.404) improve.
- **It costs Israel→Lebanon** (0.060 → 0.078; 48 of 51 YES). The stricter count drops some Lebanon days, so Lebanon dailies are
  priced a little lower. With n = 51 that pair dominates the total.
- **Definition explains only part of the Israel→Syria gap:** even on the contract definition the engine (0.39) is far above the
  market (0.21).
- **No pair-specific definition follows from this.** Choosing a definition per pair after seeing these numbers is the kind of
  forking path the pre-registration exists to prevent. Israel→Syria stays excluded from the unified engine by the publish rule
  and priced by the old engine (strike-without-war table, also frozen at its data end).

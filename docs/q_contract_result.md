# Result: contract-definition strike rates on the broad fighting state: NOT ADOPTED (Nov 4, 2026)

Pre-registration: `docs/q_contract_prereg.md` (`eb3f91d`; erratum `767cdfe`, before any result). Script: `analysis/q_contract.py`.
Replay: 125 resolved strike contracts first forecast on or after 2026-07-01.

| | FULL | QC | Market |
|---|---|---|---|
| **All (n=125)** | **0.1467** | **0.1484** | 0.1317 |
| YES (n=102) | 0.0932 | 0.0965 | 0.1253 |
| NO (n=23) | 0.3838 | 0.3789 | 0.1597 |

Cluster bootstrap by pair: QC − FULL = +0.0018, 95% [−0.0007, +0.0050]. Pairs worse by > 0.05 (n ≥ 3): none.
**Rule 1 fails (0.1484 > 0.1467): NOT adopted.** Production `world_fits.json` unchanged.

## What moved (held-out window)

- Prior centre of q fell where the pair shells or uses short-range fire: Israel→Syria 0.405 → 0.263, Pakistan→Afghanistan
  0.539 → 0.201, Houthi→Saudi 0.527 → 0.090, Iran→Iraq 0.610 → 0.448, Israel→Lebanon 0.966 → 0.864. Iran→Gulf, Israel↔Iran,
  US→Iran barely changed.
- Prices barely moved: Israel→Syria 0.4501 → 0.4469; Israel→Lebanon 0.0597 → 0.0621 and Iran→Iraq 0.1212 → 0.1360 got worse
  (YES days priced lower).

## Reading

- **The NO-day loss is not in the per-day strike rate.** For a multi-week window, once the engine is sure the pair is fighting,
  even q = 0.26 per day makes at least one qualifying strike near-certain. Israel→Syria's NO windows were weeks of shelling with almost
  no air strikes (2026 air/drone strike days: Jul 1, Aug 3, Sep 0), far below its 2015–2026 average. That is a change in tempo
  (the pair's recent strike rate vs its history), not a definition problem the prior can fix.
- **Pairs with many contracts are hurt slightly:** their own windows already set q; lowering the prior centre only drags YES days.
- **No further specification for Israel→Syria now** (forking paths). It stays off the unified engine by the publish rule.

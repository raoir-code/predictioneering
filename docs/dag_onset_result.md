# Result: the DAG sets the onset rate for quiet strike pairs: NOT ADOPTED (Nov 4, 2026)

Pre-registration: `docs/dag_onset_prereg.md` (`8c4a357`, before the run). Script: `analysis/dag_onset_replay.py --measure`.
32 resolved contracts in scope (74 sub-national skipped; 8 already priced by the unified engine).

| | STANDALONE | DAG-H (w = 0.5) | Market |
|---|---|---|---|
| **All (n=32)** | **0.1189** | **0.1259** | 0.1096 |
| YES (n=4) | 0.9376 | 0.8030 | |
| NO (n=28) | 0.0019 | 0.0292 | |

Pair-cluster bootstrap: DAG-H − STANDALONE = +0.0070, 95% [−0.0157, +0.0545]. Pairs worse by > 0.05 (n ≥ 3): none.
Reported only: w = 0.25 → 0.1183; w = 0.75 → 0.1514.
**Rule 1 fails (0.1259 > 0.1189): NOT adopted.** The engine hook stays inert; the standalone path keeps pricing these contracts.

## Reading

- **On resolved quiet pairs the standalone path was nearly perfect on NOs** (0.0019 over 28): at first forecast it priced them near
  zero. The one-equation version adds a few percent on each (class μ and q make any onset produce a strike quickly), which costs more
  than it gains on the 4 YES (Iran ladders, where both are badly wrong).
- **The misses that motivated this step are open contracts priced after the context keeper inflated P(A)** (Pakistan→Yemen: P(A)
  0.04 in September, 0.78–0.90 in late October). That is fixed at its source (`5eaec87`); it was not an onset-formula problem.
- **No second weight:** w = 0.25 edges below the standalone path, but choosing it after seeing results is a forking path.
- The one-equation goal stands; quiet-pair onset is not where it pays first.

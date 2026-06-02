# Migration Notes — Day 1

## What changed in backtest_venezuela.py

Replace the hardcoded ALPHA block at the top:

```python
# OLD — delete this
ALPHA = {
    "Capabilities":          0.001,
    "Trade":                -0.2233,
    "TerritorialDispute":    1.5331,
    "CommitmentProblem":     0.2723,
    "PreferenceSimilarity": -1.0689,
    "LeaderHorizon":        -0.05,
    "Democracy":            -0.0350,
    "AudienceCosts":        0.35,
}
```

With:

```python
# NEW — reads from alpha/conflict_onset.json
import sys
sys.path.insert(0, ".")
from pipeline.load_alpha import load_alpha
ALPHA = load_alpha()
```

That's the only required edit. Everything else in backtest_venezuela.py stays identical.

## Workflow going forward

1. Edit `engine/derbies/conflict_onset.py` (add/remove studies, change DAG)
2. Run `python pipeline/run_derby.py`  →  writes to `alpha/conflict_onset.json`
3. Run `python pipeline/backtest_venezuela.py`  →  automatically picks up new alpha

## Expert priors

Edit `pipeline/load_alpha.py` → `EXPERT_PRIORS` dict.
Each entry needs: beta, se (wide = uncertain), source, note.

## Adding a new dyad (e.g. Iran)

1. Copy `pipeline/backtest_venezuela.py` → `pipeline/backtest_iran.py`
2. Change DYAD, DYAD_LABEL, DATA_FILE, NEWS_QUERY, slugs at top
3. Decide if Iran uses the same alpha (same DAG) or needs its own derby
   - Same DAG + different BASELINE values = probably fine to start
   - Fundamentally different mechanisms = new derby

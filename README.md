# Predictioneering

Geopolitical conflict forecasting via structural meta-analysis (God's DAG framework).

## Architecture

```
Two layers, one clean interface:

  [ESTIMATION LAYER]                    [FORECASTING LAYER]
  engine/derbies/conflict_onset.py      pipeline/backtest_venezuela.py
         ↓ python pipeline/run_derby.py        ↑ reads from
  alpha/conflict_onset.json  ──────────────────┘
```

## Workflow

```bash
# 1. Update the derby (add studies, change DAG)
#    edit engine/derbies/conflict_onset.py

# 2. Re-estimate alpha
python pipeline/run_derby.py

# 3. Run backtest
python pipeline/backtest_venezuela.py

# 4. Scrape fresh Polymarket data
python pipeline/polymarket_scraper.py
```

## Adding a new dyad

Copy `pipeline/backtest_venezuela.py` → `pipeline/backtest_NEWDYAD.py`.
Change DYAD, DYAD_LABEL, DATA_FILE, NEWS_QUERY at the top.
Usually reuse the same `alpha/conflict_onset.json` unless the dyad
needs a fundamentally different DAG.

## Expert priors (no published study)

Edit `pipeline/load_alpha.py` → `EXPERT_PRIORS`.
Required fields: beta, se (wide = uncertain), source, note.

## Files
- `engine/gods_dag_v2.py`         — estimation engine, don't touch
- `engine/derbies/conflict_onset.py` — filled-in derby (10 studies)
- `engine/derbies/_template.py`   — blank template for new derbies
- `library/hazard_library_v4.json`— scraped coefficient library
- `alpha/conflict_onset.json`     — estimated structural parameters
- `pipeline/run_derby.py`         — runs derby, writes to alpha/
- `pipeline/load_alpha.py`        — loads alpha into pipeline
- `pipeline/backtest_venezuela.py`— live/backtest pipeline
- `pipeline/polymarket_scraper.py`— Polymarket price history scraper
- `predictions/log.csv`           — timestamped prediction log (sacred)

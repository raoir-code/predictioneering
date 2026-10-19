#!/bin/bash
# Predictioneering daily pipeline orchestrator
# Usage: ./pipeline/run_pipeline.sh

set -e
# Keep the Mac awake for the whole run (the Oct 18 run slept ~25h mid-run). -w $$ ends it when this script exits.
/usr/bin/caffeinate -is -w $$ &

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d'=' -f2)
export GNEWS_API_KEY=$(grep GNEWS_API_KEY .env | cut -d'=' -f2)

PYTHON=/opt/homebrew/bin/python3.11
GIT=$(which git)
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/pipeline_$(date +%Y%m%d_%H%M%S).log"

echo "=== Predictioneering pipeline run: $(date) ===" | tee -a "$LOGFILE"

echo "Watchdog check..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.watchdog >> "$LOGFILE" 2>&1 || echo "  [watchdog] check itself failed to run (non-fatal)" | tee -a "$LOGFILE"

echo "[pilot] News collector, Israel->Lebanon (non-fatal, forward-only data)..." | tee -a "$LOGFILE"
$PYTHON -u pilot/strike_collector.py >> "$LOGFILE" 2>&1 || echo "  [pilot] collector failed (non-fatal)" | tee -a "$LOGFILE"

echo "[1/6] Scraping Polymarket..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.scrape_live >> "$LOGFILE" 2>&1
echo "Scrape done." | tee -a "$LOGFILE"

if [ -f pipeline/.last_weekly_run ]; then
    WEEKLY_AGE=$(( ($(date +%s) - $(stat -f %m pipeline/.last_weekly_run)) / 3600 ))
else
    WEEKLY_AGE=999999
fi
if [ "$WEEKLY_AGE" -gt 168 ]; then
    echo "[2/6] Disciplinarian (full re-run -- weekly marker is ${WEEKLY_AGE}h old)..." | tee -a "$LOGFILE"
    $PYTHON -u -m pipeline.disciplinarian >> "$LOGFILE" 2>&1
else
    echo "[2/6] Disciplinarian skipped (weekly marker is ${WEEKLY_AGE}h old, < 7 days)." | tee -a "$LOGFILE"
fi

echo "[3/6] Engine (predict.py)..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.predict >> "$LOGFILE" 2>&1
echo "Engine done." | tee -a "$LOGFILE"

echo "[4/6] Translator..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.translator >> "$LOGFILE" 2>&1
echo "[scope] Contract-scope refresh for new kinetic markets (non-fatal; G4)..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.backfill_contract_scopes >> "$LOGFILE" 2>&1 || echo "  [scope] refresh failed (non-fatal)" | tee -a "$LOGFILE"
echo "[meta] Listing metadata for new markets (non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.market_meta >> "$LOGFILE" 2>&1 || echo "  [meta] failed (non-fatal)" | tee -a "$LOGFILE"
echo "Translator done." | tee -a "$LOGFILE"

echo "[5/6] Resolver..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.resolver >> "$LOGFILE" 2>&1
echo "Resolver done." | tee -a "$LOGFILE"

echo "[pilot] Shadow pricer, Israel->Lebanon (logs only, non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u pilot/shadow_pricer.py >> "$LOGFILE" 2>&1 || echo "  [pilot] shadow pricer failed (non-fatal)" | tee -a "$LOGFILE"
echo "[pilot] Ceasefire classifier: label new articles (non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u pilot/ceasefire_news.py --classify >> "$LOGFILE" 2>&1 || echo "  [pilot] ceasefire classifier failed (non-fatal)" | tee -a "$LOGFILE"
echo "[pilot] Shadow v2b fighting-state filter (logs only, non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u pilot/fighting_state.py >> "$LOGFILE" 2>&1 || echo "  [pilot] shadow v2b failed (non-fatal)" | tee -a "$LOGFILE"

if [ "$WEEKLY_AGE" -gt 168 ]; then
    echo "[6/6] Context keeper weekly sweep (weekly marker is ${WEEKLY_AGE}h old)..." | tee -a "$LOGFILE"
    $PYTHON -u -m pipeline.context_keeper --sweep >> "$LOGFILE" 2>&1
    touch pipeline/.last_weekly_run
    echo "  [weekly marker] pipeline/.last_weekly_run updated." | tee -a "$LOGFILE"
else
    echo "[6/6] Context keeper sweep skipped (weekly marker is ${WEEKLY_AGE}h old, < 7 days)." | tee -a "$LOGFILE"
fi

echo "Syncing data files to docs/..." | tee -a "$LOGFILE"
cp pipeline/classified_feed.json docs/classified_feed.json
if [ -f "predictions/log.jsonl" ]; then cp predictions/log.jsonl docs/predictions_log.jsonl; fi
if [ -f "predictions/brier_log.jsonl" ]; then cp predictions/brier_log.jsonl docs/brier_log.jsonl; fi

echo "Pushing to GitHub..." | tee -a "$LOGFILE"
for f in pipeline/classified_feed.json predictions/log.jsonl pipeline/translator_cache.json predictions/brier_log.jsonl predictions/brier_summary.json pipeline/dyad_configs.json pipeline/context_changelog.jsonl pipeline/node_score_history.jsonl pipeline/.context_cooldown_state.json pipeline/node_memory_state.json pipeline/theater_state.json pipeline/contract_scopes.json pipeline/market_meta.json docs/classified_feed.json docs/predictions_log.jsonl docs/brier_log.jsonl docs/index.html; do
    if [ -f "$f" ]; then
        $GIT add "$f"
    else
        echo "  [skip] $f does not exist yet" | tee -a "$LOGFILE"
    fi
done
$GIT add pilot/shadow_log.jsonl >> "$LOGFILE" 2>&1 || echo "  [pilot] could not stage shadow log (non-fatal)" | tee -a "$LOGFILE"
$GIT add pilot/shadow_log_v2.jsonl >> "$LOGFILE" 2>&1 || echo "  [pilot] could not stage v2 log (non-fatal)" | tee -a "$LOGFILE"
$GIT add pilot/ceasefire_labels.jsonl >> "$LOGFILE" 2>&1 || echo "  [pilot] could not stage ceasefire labels (non-fatal)" | tee -a "$LOGFILE"
$GIT add -f cache/gnews_pilot >> "$LOGFILE" 2>&1 || echo "  [pilot] could not stage pilot news cache (non-fatal)" | tee -a "$LOGFILE"
$GIT commit -m "Daily predictions: $(date +%Y-%m-%d)" >> "$LOGFILE" 2>&1 || echo "Nothing to commit." | tee -a "$LOGFILE"
# Retry: after sleep/wake the network may not be back yet (Oct 19: "Could not resolve host").
for i in 1 2 3 4 5; do
    if $GIT push >> "$LOGFILE" 2>&1; then break; fi
    if [ "$i" -eq 5 ]; then echo "  [push] failed 5 times; commit stays local, next run pushes it" | tee -a "$LOGFILE"; exit 1; fi
    echo "  [push] attempt $i failed; retrying in 60s" | tee -a "$LOGFILE"; sleep 60
done

echo "=== Pipeline complete: $(date) ===" | tee -a "$LOGFILE"

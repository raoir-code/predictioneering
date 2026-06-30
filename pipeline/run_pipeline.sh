#!/bin/bash
# Predictioneering daily pipeline orchestrator
# Usage: ./pipeline/run_pipeline.sh

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d'=' -f2)
export GNEWS_API_KEY=$(grep GNEWS_API_KEY .env | cut -d'=' -f2)

PYTHON=/opt/homebrew/bin/python3.11
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/pipeline_$(date +%Y%m%d_%H%M%S).log"

echo "=== Predictioneering pipeline run: $(date) ===" | tee -a "$LOGFILE"

echo "[1/6] Scraping Polymarket..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.scrape_live >> "$LOGFILE" 2>&1
echo "Scrape done." | tee -a "$LOGFILE"

FEED_AGE=$(( ($(date +%s) - $(stat -f %m pipeline/classified_feed.json)) / 3600 ))
if [ "$FEED_AGE" -gt 168 ]; then
    echo "[2/6] Disciplinarian (full re-run -- feed is ${FEED_AGE}h old)..." | tee -a "$LOGFILE"
    $PYTHON -u -m pipeline.disciplinarian >> "$LOGFILE" 2>&1
else
    echo "[2/6] Disciplinarian skipped (feed is ${FEED_AGE}h old, < 7 days)." | tee -a "$LOGFILE"
fi

echo "[3/6] Engine (predict.py)..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.predict >> "$LOGFILE" 2>&1
echo "Engine done." | tee -a "$LOGFILE"

echo "[4/6] Translator..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.translator >> "$LOGFILE" 2>&1
echo "Translator done." | tee -a "$LOGFILE"

echo "[5/6] Resolver..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.resolver >> "$LOGFILE" 2>&1
echo "Resolver done." | tee -a "$LOGFILE"

if [ "$FEED_AGE" -gt 168 ]; then
    echo "[6/6] Context keeper weekly sweep (feed is ${FEED_AGE}h old)..." | tee -a "$LOGFILE"
    $PYTHON -u -m pipeline.context_keeper --sweep >> "$LOGFILE" 2>&1
else
    echo "[6/6] Context keeper sweep skipped (feed is ${FEED_AGE}h old, < 7 days)." | tee -a "$LOGFILE"
fi

echo "Pushing to GitHub..." | tee -a "$LOGFILE"
for f in pipeline/classified_feed.json predictions/log.jsonl pipeline/translator_cache.json predictions/brier_log.jsonl predictions/brier_summary.json pipeline/dyad_configs.json pipeline/context_changelog.jsonl pipeline/node_score_history.jsonl pipeline/.context_cooldown_state.json; do
    if [ -f "$f" ]; then
        git add "$f"
    else
        echo "  [skip] $f does not exist yet" | tee -a "$LOGFILE"
    fi
done
git commit -m "Daily predictions: $(date +%Y-%m-%d)" >> "$LOGFILE" 2>&1 || echo "Nothing to commit." | tee -a "$LOGFILE"
git push >> "$LOGFILE" 2>&1

echo "=== Pipeline complete: $(date) ===" | tee -a "$LOGFILE"

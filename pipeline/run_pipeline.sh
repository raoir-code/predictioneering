#!/bin/bash
# Predictioneering daily pipeline orchestrator
# Usage: ./pipeline/run_pipeline.sh

set -e  # Exit on any error

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Load environment variables
export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d'=' -f2)
export GNEWS_API_KEY=$(grep GNEWS_API_KEY .env | cut -d'=' -f2)

PYTHON=/opt/homebrew/bin/python3.11
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/pipeline_$(date +%Y%m%d_%H%M%S).log"

echo "=== Predictioneering pipeline run: $(date) ===" | tee -a "$LOGFILE"

# Step 1: Scrape
echo "[1/4] Scraping Polymarket..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.scrape_live >> "$LOGFILE" 2>&1
echo "Scrape done." | tee -a "$LOGFILE"

# Step 2: Disciplinarian (new markets only — check if classified_feed is fresh)
FEED_AGE=$(( ($(date +%s) - $(stat -f %m pipeline/classified_feed.json)) / 3600 ))
if [ "$FEED_AGE" -gt 168 ]; then  # Older than 7 days
    echo "[2/4] Disciplinarian (full re-run — feed is ${FEED_AGE}h old)..." | tee -a "$LOGFILE"
    $PYTHON -u -m pipeline.disciplinarian >> "$LOGFILE" 2>&1
else
    echo "[2/4] Disciplinarian skipped (feed is ${FEED_AGE}h old, < 7 days)." | tee -a "$LOGFILE"
fi

# Step 3: Engine
echo "[3/4] Engine (predict.py)..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.predict >> "$LOGFILE" 2>&1
echo "Engine done." | tee -a "$LOGFILE"

# Step 4: Translator + Logger
echo "[4/4] Translator..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.translator >> "$LOGFILE" 2>&1
echo "Translator done." | tee -a "$LOGFILE"

# Step 5: Resolver (check for resolved markets, update Brier score)
echo "[5/5] Resolver..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.resolver >> "$LOGFILE" 2>&1
echo "Resolver done." | tee -a "$LOGFILE"

# Git push
echo "Pushing to GitHub..." | tee -a "$LOGFILE"
git add pipeline/classified_feed.json predictions/log.jsonl pipeline/translator_cache.json predictions/brier_log.jsonl predictions/brier_summary.json
git commit -m "Daily predictions: $(date +%Y-%m-%d)" >> "$LOGFILE" 2>&1 || echo "Nothing to commit." | tee -a "$LOGFILE"
git push >> "$LOGFILE" 2>&1

echo "=== Pipeline complete: $(date) ===" | tee -a "$LOGFILE"

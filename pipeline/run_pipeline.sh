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

echo "[$(date +%H:%M:%S)] === Predictioneering pipeline run: $(date) ===" | tee -a "$LOGFILE"
RUN_DATE=$(date +%Y-%m-%d)
# Stale-run guard (Oct 26): the Oct 24 run slept with the lid closed and published Saturday's news on Monday, 51h later,
# while launchd swallowed the Sunday/Monday fires. If the date has rolled over before any prediction is written, stop:
# counted failure, nothing priced from an old information set. Once the translator starts, the run finishes and publishes.
fresh_or_abort() {
    if [ "$(date +%Y-%m-%d)" != "$RUN_DATE" ]; then
        echo "[$(date +%H:%M:%S)] STALE RUN: started $RUN_DATE, now $(date +%Y-%m-%d) at $1; aborted before pricing (counted failure)" | tee -a "$LOGFILE"
        exit 3
    fi
}

echo "[$(date +%H:%M:%S)] Watchdog check..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.watchdog >> "$LOGFILE" 2>&1 || echo "  [watchdog] check itself failed to run (non-fatal)" | tee -a "$LOGFILE"

echo "[$(date +%H:%M:%S)] [pilot] News collector, Israel->Lebanon (non-fatal, forward-only data)..." | tee -a "$LOGFILE"
$PYTHON -u pilot/strike_collector.py >> "$LOGFILE" 2>&1 || echo "  [pilot] collector failed (non-fatal)" | tee -a "$LOGFILE"

echo "[$(date +%H:%M:%S)] [1/6] Scraping Polymarket..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.scrape_live >> "$LOGFILE" 2>&1
echo "[$(date +%H:%M:%S)] Scrape done." | tee -a "$LOGFILE"

if [ -f pipeline/.last_weekly_run ]; then
    WEEKLY_AGE=$(( ($(date +%s) - $(stat -f %m pipeline/.last_weekly_run)) / 3600 ))
else
    WEEKLY_AGE=999999
fi
if [ "$WEEKLY_AGE" -gt 168 ]; then
    echo "[$(date +%H:%M:%S)] [2/6] Disciplinarian (full re-run -- weekly marker is ${WEEKLY_AGE}h old)..." | tee -a "$LOGFILE"
    $PYTHON -u -m pipeline.disciplinarian >> "$LOGFILE" 2>&1
else
    echo "[$(date +%H:%M:%S)] [2/6] Disciplinarian daily sync: today's prices + new listings only (weekly marker is ${WEEKLY_AGE}h old)..." | tee -a "$LOGFILE"
    $PYTHON -u -m pipeline.disciplinarian --daily-sync >> "$LOGFILE" 2>&1 || echo "  [sync] FAILED (non-fatal; prices and market list stay at the last sync)" | tee -a "$LOGFILE"
fi

fresh_or_abort "engine"
echo "[$(date +%H:%M:%S)] [3/6] Engine (predict.py)..." | tee -a "$LOGFILE"
echo "[$(date +%H:%M:%S)] [classify] Retry markets left in ERROR by an earlier outage (non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.disciplinarian --retry-errors >> "$LOGFILE" 2>&1 || echo "  [classify] retry failed (non-fatal)" | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.predict >> "$LOGFILE" 2>&1
echo "[$(date +%H:%M:%S)] Engine done." | tee -a "$LOGFILE"

echo "[$(date +%H:%M:%S)] [4/6] Translator..." | tee -a "$LOGFILE"
echo "[$(date +%H:%M:%S)] [rules] Rules text + listing dates for new contracts (non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.market_rules >> "$LOGFILE" 2>&1 || echo "  [rules] fetch failed (non-fatal)" | tee -a "$LOGFILE"
echo "[$(date +%H:%M:%S)] [ceasefire] Ceasefire contracts (families A/B/C): refresh + replays, reported only (non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u pilot/ceasefire_holds.py --refresh --replay >> "$LOGFILE" 2>&1 || echo "  [holds] refresh/replay failed (non-fatal; previous policy kept)" | tee -a "$LOGFILE"
$PYTHON -u pilot/ceasefire_bc.py --replay >> "$LOGFILE" 2>&1 || echo "  [ceasefire-bc] replay failed (non-fatal; report only)" | tee -a "$LOGFILE"
$PYTHON -u pilot/war_outcomes.py --refresh --replay >> "$LOGFILE" 2>&1 || echo "  [war-outcome] refresh/replay failed (non-fatal; report only)" | tee -a "$LOGFILE"
fresh_or_abort "translator"
$PYTHON -u -m pipeline.translator >> "$LOGFILE" 2>&1
echo "[$(date +%H:%M:%S)] [scope] Contract-scope refresh for new kinetic markets (non-fatal; G4)..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.backfill_contract_scopes >> "$LOGFILE" 2>&1 || echo "  [scope] refresh failed (non-fatal)" | tee -a "$LOGFILE"
echo "[$(date +%H:%M:%S)] [news] Label new headlines for tomorrow (non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u pilot/news_strikes.py --label >> "$LOGFILE" 2>&1 || echo "  [news] labeling failed (non-fatal)" | tee -a "$LOGFILE"
echo "[$(date +%H:%M:%S)] [meta] Listing metadata for new markets (non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.market_meta >> "$LOGFILE" 2>&1 || echo "  [meta] failed (non-fatal)" | tee -a "$LOGFILE"
echo "[$(date +%H:%M:%S)] Translator done." | tee -a "$LOGFILE"

echo "[$(date +%H:%M:%S)] [5/6] Resolver..." | tee -a "$LOGFILE"
$PYTHON -u -m pipeline.resolver >> "$LOGFILE" 2>&1
echo "[$(date +%H:%M:%S)] [unified] Recompute publish policy from the replay (non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u pilot/unified_price.py --policy >> "$LOGFILE" 2>&1 || echo "  [unified] policy refresh failed (non-fatal; previous policy kept)" | tee -a "$LOGFILE"
echo "[$(date +%H:%M:%S)] Resolver done." | tee -a "$LOGFILE"

echo "[$(date +%H:%M:%S)] [pilot] Shadow pricer, Israel->Lebanon (logs only, non-fatal)..." | tee -a "$LOGFILE"
# retired Oct 20 (production prices these markets): $PYTHON -u pilot/shadow_pricer.py >> "$LOGFILE" 2>&1 || echo "  [pilot] shadow pricer failed (non-fatal)" | tee -a "$LOGFILE"
echo "[$(date +%H:%M:%S)] [pilot] Ceasefire classifier: label new articles (non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u pilot/ceasefire_news.py --classify >> "$LOGFILE" 2>&1 || echo "  [pilot] ceasefire classifier failed (non-fatal)" | tee -a "$LOGFILE"
echo "[$(date +%H:%M:%S)] [talks] Negotiation-evidence collector, agreement actor sets (forward-only, logs only, non-fatal)..." | tee -a "$LOGFILE"
$PYTHON -u pilot/talks_collector.py >> "$LOGFILE" 2>&1 || echo "  [talks] collector failed (non-fatal)" | tee -a "$LOGFILE"
echo "[$(date +%H:%M:%S)] [pilot] Shadow v2b fighting-state filter (logs only, non-fatal)..." | tee -a "$LOGFILE"
# retired Oct 20 (production prices these markets): $PYTHON -u pilot/fighting_state.py >> "$LOGFILE" 2>&1 || echo "  [pilot] shadow v2b failed (non-fatal)" | tee -a "$LOGFILE"

if [ "$WEEKLY_AGE" -gt 168 ]; then
    echo "[$(date +%H:%M:%S)] [6/6] Context keeper weekly sweep (weekly marker is ${WEEKLY_AGE}h old)..." | tee -a "$LOGFILE"
    $PYTHON -u -m pipeline.context_keeper --sweep >> "$LOGFILE" 2>&1
    touch pipeline/.last_weekly_run
    echo "[$(date +%H:%M:%S)]   [weekly marker] pipeline/.last_weekly_run updated." | tee -a "$LOGFILE"
else
    echo "[$(date +%H:%M:%S)] [6/6] Context keeper sweep skipped (weekly marker is ${WEEKLY_AGE}h old, < 7 days)." | tee -a "$LOGFILE"
fi

echo "[$(date +%H:%M:%S)] Syncing data files to docs/..." | tee -a "$LOGFILE"
cp pipeline/classified_feed.json docs/classified_feed.json
if [ -f "predictions/log.jsonl" ]; then cp predictions/log.jsonl docs/predictions_log.jsonl; fi
if [ -f "predictions/brier_log.jsonl" ]; then cp predictions/brier_log.jsonl docs/brier_log.jsonl; fi

echo "[$(date +%H:%M:%S)] Pushing to GitHub..." | tee -a "$LOGFILE"
for f in pipeline/classified_feed.json predictions/log.jsonl pipeline/translator_cache.json predictions/brier_log.jsonl predictions/brier_summary.json pipeline/dyad_configs.json pipeline/context_changelog.jsonl pipeline/node_score_history.jsonl pipeline/.context_cooldown_state.json pipeline/node_memory_state.json pipeline/theater_state.json pipeline/contract_scopes.json pipeline/agglomeration_configs.json pipeline/disciplinarian_cache.json pipeline/market_meta.json pipeline/market_rules.json pilot/news_strike_labels.jsonl pilot/unified_publish.json pilot/ceasefire_markets.json pilot/holds_publish.json pilot/holds_price_cache.json pilot/bc_replay.json pilot/war_outcome_markets.json pilot/war_outcome_replay.json docs/classified_feed.json docs/predictions_log.jsonl docs/brier_log.jsonl docs/index.html; do
    if [ -f "$f" ]; then
        $GIT add "$f"
    else
        echo "[$(date +%H:%M:%S)]   [skip] $f does not exist yet" | tee -a "$LOGFILE"
    fi
done
$GIT add pilot/shadow_log.jsonl >> "$LOGFILE" 2>&1 || echo "  [pilot] could not stage shadow log (non-fatal)" | tee -a "$LOGFILE"
$GIT add pilot/shadow_log_v2.jsonl >> "$LOGFILE" 2>&1 || echo "  [pilot] could not stage v2 log (non-fatal)" | tee -a "$LOGFILE"
$GIT add pilot/ceasefire_labels.jsonl >> "$LOGFILE" 2>&1 || echo "  [pilot] could not stage ceasefire labels (non-fatal)" | tee -a "$LOGFILE"
$GIT add -f cache/gnews_pilot >> "$LOGFILE" 2>&1 || echo "  [pilot] could not stage pilot news cache (non-fatal)" | tee -a "$LOGFILE"
$GIT add pilot/talks_labels.jsonl >> "$LOGFILE" 2>&1 || echo "  [talks] could not stage talks labels (non-fatal)" | tee -a "$LOGFILE"
$GIT add -f cache/gnews_talks >> "$LOGFILE" 2>&1 || echo "  [talks] could not stage talks news cache (non-fatal)" | tee -a "$LOGFILE"
$GIT commit -m "Daily predictions: $(date +%Y-%m-%d)" >> "$LOGFILE" 2>&1 || echo "Nothing to commit." | tee -a "$LOGFILE"
# Retry: after sleep/wake the network may not be back yet (Oct 19: "Could not resolve host").
for i in 1 2 3 4 5; do
    if $GIT push >> "$LOGFILE" 2>&1; then break; fi
    if [ "$i" -eq 5 ]; then echo "  [push] failed 5 times; commit stays local, next run pushes it" | tee -a "$LOGFILE"; exit 1; fi
    echo "[$(date +%H:%M:%S)]   [push] attempt $i failed; retrying in 60s" | tee -a "$LOGFILE"; sleep 60
done

echo "[$(date +%H:%M:%S)] === Pipeline complete: $(date) ===" | tee -a "$LOGFILE"

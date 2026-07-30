#!/bin/bash
cd ~/predictioneering
echo "======================================================"
echo "[1] LAUNCHD — is the job even alive?"
echo "======================================================"
launchctl list | grep -i predict
echo "--- detailed status (last exit code, next run) ---"
launchctl print gui/$(id -u)/com.predictioneering.daily 2>&1 | grep -E "state|last exit|program|next"
echo "--- plist file integrity ---"
ls -la ~/Library/LaunchAgents/com.predictioneering*.plist
plutil -lint ~/Library/LaunchAgents/com.predictioneering.daily.plist

echo
echo "======================================================"
echo "[2] SYSTEM SLEEP/WAKE — was the Mac even open at 9am?"
echo "======================================================"
pmset -g log | grep -E "Wake|Sleep|DarkWake" | tail -40
echo "--- uptime / last reboot ---"
uptime
last reboot | head -5

echo
echo "======================================================"
echo "[3] LOCAL PIPELINE LOGS — did run_pipeline.sh even start?"
echo "======================================================"
ls -la logs/ | tail -15
echo "--- any log files from Jul 25-29? ---"
find logs/ -name "*2026072[5-9]*" -exec echo {} \; -exec tail -30 {} \; -exec echo "---" \;

echo
echo "======================================================"
echo "[4] GIT STATE — ran locally but didn't push?"
echo "======================================================"
git status
echo "--- unpushed commits ---"
git log origin/main..HEAD --oneline
echo "--- recent history ---"
git log --oneline -10
echo "--- remote sanity ---"
git remote -v
echo "--- does push even work? ---"
git push --dry-run 2>&1

echo
echo "======================================================"
echo "[5] PYTHON INTERPRETER — did the hardcoded path break?"
echo "======================================================"
/opt/homebrew/bin/python3.11 --version 2>&1
which python3.11
brew list --versions python@3.11 2>&1

echo
echo "======================================================"
echo "[6] API KEYS — present, non-empty, still valid?"
echo "======================================================"
grep -c "ANTHROPIC_API_KEY=" .env
grep -c "GNEWS_API_KEY=" .env
echo "--- Anthropic key liveness (should NOT be 401) ---"
curl -s -o /dev/null -w "HTTP %{http_code}\n" https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(grep ANTHROPIC_API_KEY .env | cut -d= -f2)" \
  -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}'
echo "--- GNews key liveness ---"
curl -s -o /dev/null -w "HTTP %{http_code}\n" "https://gnews.io/api/v4/search?q=test&max=1&apikey=$(grep GNEWS_API_KEY .env | cut -d= -f2)"

echo
echo "======================================================"
echo "[7] DISK SPACE — silently full?"
echo "======================================================"
df -h / | head -2

echo
echo "======================================================"
echo "[8] FILE TIMESTAMPS — precise last-write times"
echo "======================================================"
stat -f "%Sm  %N" pipeline/classified_feed.json docs/classified_feed.json predictions/log.jsonl pipeline/translator_cache.json .env

echo
echo "======================================================"
echo "[9] STUCK PROCESSES — anything hung since Jul 24?"
echo "======================================================"
ps aux | grep -i "python.*pipeline" | grep -v grep

echo
echo "======================================================"
echo "[10] SHELL HISTORY — reconstruct the Jul 24 debug session"
echo "======================================================"
history | grep -E "predict\.py|translator\.py|dry-run|dyad" | tail -30

echo
echo "======================================================"
echo "DONE. Scroll up to [1] and work down."
echo "======================================================"

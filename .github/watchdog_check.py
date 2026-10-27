"""Independent watchdog: runs on GitHub's servers, not the laptop, so it still fires when the Mac is asleep or off.

Fails (non-zero exit -> GitHub emails the repo owner) when today's daily run is missing or looks broken:
  1. no "Daily predictions: <today, US Eastern>" commit
  2. predictions/log.jsonl has no rows stamped today
  3. today's priced count is under half of the previous run's (a run that "succeeded" but priced almost nothing)
  4. any published conditional_p outside [0, 1] or not a number
The pipeline's own pipeline/watchdog.py only runs inside the pipeline and only writes to a local file,
so it cannot report a run that never started. Read-only: this script changes nothing in the repo.
"""
import json, math, subprocess, sys
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def day_et(ts):
    return datetime.fromisoformat(ts).astimezone(ET).date().isoformat()


def check(today, log_path="predictions/log.jsonl", commits=None):
    problems = []
    if commits is None:
        commits = subprocess.run(["git", "log", "--format=%s", "-60"], capture_output=True, text=True, check=True).stdout.splitlines()
    if f"Daily predictions: {today}" not in commits:
        problems.append(f"no 'Daily predictions: {today}' commit (laptop asleep/off, stale-run abort, or a crash before the push)")
    by_day = {}
    with open(log_path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            p = r.get("conditional_p")
            if p is None:
                continue
            d = day_et(r["timestamp"])
            by_day.setdefault(d, {}).setdefault(r["timestamp"], []).append(p)
    # Compare runs, not days: a day can hold two runs (Oct 26: the stale run and the fresh one). Use each day's last run.
    by_day = {d: runs[max(runs)] for d, runs in by_day.items()}
    todays = by_day.get(today, [])
    if not todays:
        problems.append(f"predictions/log.jsonl has no priced rows dated {today}")
    else:
        bad = [p for p in todays if not isinstance(p, (int, float)) or math.isnan(p) or not 0 <= p <= 1]
        if bad:
            problems.append(f"{len(bad)} published prices outside [0, 1] or not numbers")
        earlier = sorted(d for d in by_day if d < today)
        if earlier and len(todays) < 0.5 * len(by_day[earlier[-1]]):
            problems.append(f"only {len(todays)} contracts priced today vs {len(by_day[earlier[-1]])} on {earlier[-1]}")
    return problems, len(todays)


def _tests():
    import os, tempfile
    rows = [{"timestamp": "2026-10-26T15:00:00+00:00", "conditional_p": 0.5}] * 3 + [{"timestamp": "2026-10-26T17:00:00+00:00", "conditional_p": 0.5}] * 10
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        for r in rows + [{"timestamp": "2026-10-27T14:00:00+00:00", "conditional_p": 0.4}] * 9:
            f.write(json.dumps(r) + "\n")
    ok = ["Daily predictions: 2026-10-27"]
    assert check("2026-10-27", f.name, ok) == ([], 9)
    assert "no 'Daily predictions" in check("2026-10-27", f.name, ["ops: x"])[0][0]
    assert "no priced rows" in check("2026-10-28", f.name, ["Daily predictions: 2026-10-28"])[0][0]
    with open(f.name, "a") as g:
        g.write(json.dumps({"timestamp": "2026-10-28T14:00:00+00:00", "conditional_p": 1.4}) + "\n")
    probs = check("2026-10-28", f.name, ["Daily predictions: 2026-10-28"])[0]
    assert any("outside" in p for p in probs) and any("only 1" in p for p in probs)
    # 00:30 UTC on Oct 28 is still Oct 27 in Eastern time
    assert day_et("2026-10-28T00:30:00+00:00") == "2026-10-27"
    os.unlink(f.name)


if __name__ == "__main__":
    _tests()
    today = datetime.now(ET).date().isoformat()
    problems, n = check(today)
    if problems:
        print(f"WATCHDOG FAIL for {today}:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"WATCHDOG OK for {today}: daily commit present, {n} contracts priced")

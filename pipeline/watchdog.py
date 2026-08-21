"""
watchdog.py — bare-minimum staleness sensor.

Checks absolute staleness (not "did today's run succeed") so it's useful
regardless of where in the pipeline a run failed, or whether the machine
was even awake for prior runs. Never raises/exits non-zero on a detected
problem -- that's the whole point, it's a sensor, not an actor. Alerts get
appended to logs/ALERT.log (persistent trail) and also printed to stdout.

Run: python3.11 -m pipeline.watchdog
"""

import subprocess
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALERT_LOG = os.path.join(ROOT, "logs", "ALERT.log")

THRESHOLDS_HOURS = {
    "git_commit":       36,   # daily 9am cadence + slack
    "predictions_log":  36,   # predict.py should append daily
    "weekly_marker":    192,  # 7-day cadence (168h) + 1 day slack
}


def hours_since(timestamp: float) -> float:
    return (datetime.now(timezone.utc).timestamp() - timestamp) / 3600


def check_git_commit_age():
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=ROOT, capture_output=True, text=True, check=True
        )
        last_commit_ts = float(out.stdout.strip())
        age = hours_since(last_commit_ts)
        return age, THRESHOLDS_HOURS["git_commit"]
    except Exception as e:
        return None, f"[watchdog] could not check git commit age: {e}"


def check_file_age(relpath: str, threshold_key: str):
    path = os.path.join(ROOT, relpath)
    if not os.path.exists(path):
        return None, f"file not found: {relpath}"
    age = hours_since(os.path.getmtime(path))
    return age, THRESHOLDS_HOURS[threshold_key]


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    alerts = []
    status_lines = []

    checks = [
        ("git commit", check_git_commit_age, None),
        ("predictions/log.jsonl", lambda: check_file_age("predictions/log.jsonl", "predictions_log"), None),
        ("weekly disciplinarian marker", lambda: check_file_age("pipeline/.last_weekly_run", "weekly_marker"), None),
    ]

    for label, fn, _ in checks:
        result = fn()
        age, threshold = result
        if age is None:
            msg = f"[WATCHDOG WARN] {label}: {threshold}"
            alerts.append(msg)
            status_lines.append(msg)
            continue
        status_lines.append(f"[watchdog] {label}: {age:.1f}h old (threshold {threshold}h)")
        if age > threshold:
            msg = f"[WATCHDOG ALERT] {label} is {age:.1f}h old, exceeds {threshold}h threshold"
            alerts.append(msg)

    print(f"=== Watchdog check: {now_iso} ===")
    for line in status_lines:
        print(line)

    if alerts:
        os.makedirs(os.path.dirname(ALERT_LOG), exist_ok=True)
        with open(ALERT_LOG, "a") as f:
            f.write(f"\n--- {now_iso} ---\n")
            for a in alerts:
                f.write(a + "\n")
        print(f"\n{len(alerts)} alert(s) written to logs/ALERT.log:")
        for a in alerts:
            print("  " + a)
    else:
        print("\nAll checks OK, no alerts.")


if __name__ == "__main__":
    main()

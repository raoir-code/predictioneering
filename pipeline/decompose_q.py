#!/usr/bin/env python3.11
"""
decompose_q.py — post-hoc q-submodel attribution from backtest_results.json.
Pure arithmetic, no API calls, runs in <1s. Run after a backtest finishes.

Usage: python3.11 pipeline/decompose_q.py
"""
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).parent.parent
results_path = ROOT / "pipeline" / "backtest_results.json"

rows = json.loads(results_path.read_text())
resolved = [r for r in rows if r.get("resolution") is not None and "q_full" in r]

if not resolved:
    print("No resolved rows with q_components found — did the backtest run with Patch 4 applied?")
    raise SystemExit(1)

tp = [r for r in resolved if r["resolution"] == 1]  # resolved YES
tn = [r for r in resolved if r["resolution"] == 0]  # resolved NO


def summarize(label, group):
    if not group:
        print(f"\n{label}: no rows")
        return
    print(f"\n{label} (n={len(group)})")
    for key in ["q_full", "q_onset_only", "q_live_only"]:
        vals = [r[key] for r in group]
        print(f"  {key:<14} mean={mean(vals):.4f}  median={median(vals):.4f}  "
              f"min={min(vals):.4f}  max={max(vals):.4f}")


print("=" * 60)
print("Q-SUBMODEL DECOMPOSITION — resolved markets only")
print("=" * 60)
summarize("Resolved YES (true positives)", tp)
summarize("Resolved NO  (true negatives)", tn)

print("\n" + "-" * 60)
print("Mean per-component contribution: TP vs TN")
print("-" * 60)
if tp and tn:
    all_keys = list(tp[0]["q_components"].keys())
    print(f"  {'component':<32} {'TP mean':>10} {'TN mean':>10} {'gap':>10}")
    for k in all_keys:
        tp_mean = mean(r["q_components"][k] for r in tp)
        tn_mean = mean(r["q_components"][k] for r in tn)
        print(f"  {k:<32} {tp_mean:>10.4f} {tn_mean:>10.4f} {tp_mean - tn_mean:>10.4f}")
    print("\n  Largest TP-TN gaps are the components doing the discriminating work.")
    print("  Near-zero gaps across the board (with q_full itself flat) would point back")
    print("  to the T-7 base-rate ceiling rather than the q-submodel — i.e. evidence for")
    print("  Mach 3's crisis-regime layer rather than further q enrichment.")
else:
    print("  Need at least one resolved-YES and one resolved-NO market to compare.")

#!/usr/bin/env python3.11
"""
Patch 3 — wire run_leakage_check() over to the two-call structure (Call A
+ Call B) so the contamination check covers all 19 fields, not just the
original 11. Requires Patch 2 applied first (needs score_nodes_call_a/b
and Q_PARENTS_ONSET_LLM/Q_PARENTS_LIVE to exist).

Run from repo root: python3.11 patch_3_leakage_check.py
"""
from pathlib import Path

path = Path("pipeline/backtest.py")
content = path.read_text()

old = r'''
    articles_correct = fetch_gnews("US-Iran", snapshot)
    scores_correct   = score_nodes("US-Iran", articles_correct, snapshot)

    # B: wrong headlines (China-Taiwan, July 2024 — wrong dyad, wrong time)
    wrong_date       = date(2024, 7, 15)
    articles_wrong   = fetch_gnews("China-Taiwan", wrong_date)
    scores_wrong     = score_nodes("US-Iran", articles_wrong, snapshot)

    print(f"\n  Snapshot date: {snapshot}")
    print(f"  Correct headlines ({len(articles_correct)}): US-Iran Nov 2025")
    print(f"  Wrong headlines   ({len(articles_wrong)}): China-Taiwan Jul 2024\n")
    print(f"  {'Node':<22} {'Correct':>8} {'Wrong':>8} {'Delta':>8}")
    print("  " + "-"*48)

    max_delta = 0
    for node in NODES:
        c = scores_correct.get(node, 0)
        w = scores_wrong.get(node, 0)
        d = abs(c - w)
        max_delta = max(max_delta, d)
        flag = " ← MOVES" if d > 0.2 else ""
        print(f"  {node:<22} {c:>8.2f} {w:>8.2f} {d:>8.2f}{flag}")
'''

new = r'''
    articles_correct = fetch_gnews("US-Iran", snapshot)
    call_a_correct    = score_nodes_call_a("US-Iran", articles_correct, snapshot)
    trigger_violent_c = call_a_correct.get("TriggerType", 0.0) >= 0.60
    call_b_correct    = score_nodes_call_b("US-Iran", articles_correct, snapshot, trigger_violent_c)
    scores_correct    = {**call_a_correct, **call_b_correct}

    # B: wrong headlines (China-Taiwan, July 2024 — wrong dyad, wrong time)
    wrong_date        = date(2024, 7, 15)
    articles_wrong    = fetch_gnews("China-Taiwan", wrong_date)
    call_a_wrong       = score_nodes_call_a("US-Iran", articles_wrong, snapshot)
    trigger_violent_w  = call_a_wrong.get("TriggerType", 0.0) >= 0.60
    call_b_wrong       = score_nodes_call_b("US-Iran", articles_wrong, snapshot, trigger_violent_w)
    scores_wrong       = {**call_a_wrong, **call_b_wrong}

    all_scored_fields = NODES + Q_PARENTS_ONSET_LLM + Q_PARENTS_LIVE

    print(f"\n  Snapshot date: {snapshot}")
    print(f"  Correct headlines ({len(articles_correct)}): US-Iran Nov 2025")
    print(f"  Wrong headlines   ({len(articles_wrong)}): China-Taiwan Jul 2024\n")
    print(f"  {'Node':<32} {'Correct':>8} {'Wrong':>8} {'Delta':>8}")
    print("  " + "-"*58)

    max_delta = 0
    for node in all_scored_fields:
        c = scores_correct.get(node, 0)
        w = scores_wrong.get(node, 0)
        d = abs(c - w)
        max_delta = max(max_delta, d)
        flag = " ← MOVES" if d > 0.2 else ""
        print(f"  {node:<32} {c:>8.2f} {w:>8.2f} {d:>8.2f}{flag}")
'''

assert old in content, "OLD BLOCK NOT FOUND — aborting, no changes made. Run patches in order (1,2,3,4) and only once each."
assert content.count(old) == 1, "OLD BLOCK NOT UNIQUE — aborting, refusing to guess which occurrence to replace"

content = content.replace(old, new)
path.write_text(content)
print("Patch 3 applied — contamination check now scores all 19 fields via Call A + Call B.")

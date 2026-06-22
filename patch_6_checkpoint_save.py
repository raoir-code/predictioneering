#!/usr/bin/env python3.11
"""
Patch 6 — save backtest_results.json incrementally, after each market
finishes, instead of only once at the very end. This is the second half
of last night's fix: even with Patch 5's retry logic, there's always some
residual risk of an unhandled failure eventually crashing a long run.
Checkpointing after each market means a future crash only loses whatever
wasn't checkpointed yet, not the entire night's API spend.
Requires Patch 2 applied first (uses RESULTS_OUT, already defined at the
top of the file).

Run from repo root: python3.11 patch_6_checkpoint_save.py
"""
from pathlib import Path

path = Path("pipeline/backtest.py")
content = path.read_text()

old = r'''            print(f"  {beat} T-{offset:3d} ({snapshot_date}) | "
                  f"Engine: {engine_p:.1%} | Market: {mkt_price:.1%} | "
                  f"Res: {res_str} | Articles: {len(articles)}")

    return rows'''

new = r'''            print(f"  {beat} T-{offset:3d} ({snapshot_date}) | "
                  f"Engine: {engine_p:.1%} | Market: {mkt_price:.1%} | "
                  f"Res: {res_str} | Articles: {len(articles)}")

        # Checkpoint: save progress after each market finishes, so a crash
        # mid-run (e.g. a network timeout) doesn't lose everything back to
        # the start -- only loses whatever wasn't checkpointed yet.
        RESULTS_OUT.write_text(json.dumps(rows, indent=2))
        print(f"  [checkpoint] {len(rows)} rows saved → {RESULTS_OUT}")

    return rows'''

assert old in content, "OLD BLOCK NOT FOUND — aborting, no changes made. Run patches in order and only once each."
assert content.count(old) == 1, "OLD BLOCK NOT UNIQUE — aborting, refusing to guess which occurrence to replace"

content = content.replace(old, new)
path.write_text(content)
print("Patch 6 applied — results now checkpoint-save after every market, not just once at the very end.")

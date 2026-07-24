"""
One-time targeted backfill: regenerate baselines for the specific dyads that
failed during the July 24 full re-classification run due to max_tokens=400
truncating the JSON response mid-string ("Unterminated string" errors).
Fixed to max_tokens=900 in disciplinarian.py before running this.

Run: python3.11 pipeline/backfill_failed_baselines.py
     python3.11 pipeline/backfill_failed_baselines.py --dry-run
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(__file__))
from disciplinarian import generate_baseline, load_dyad_configs, save_dyad_configs

FAILED_DYADS = [
    "US-Yemen",
    "UK-Iran",
    "Netherlands-Iran",
    "Europe-Iran",
    "Iran-Gulf States",
    "US-Qatar",
    "US-Turkey",
    "Iran-UAE",
    "Greece-Iran",
    "Italy-Iran",
    "Israel-Egypt",
    "US-Ukraine",
    "US-Unknown",
    "Saudi Arabia-Yemen",
]


def main():
    dry_run = "--dry-run" in sys.argv
    configs = load_dyad_configs()

    already_present = [d for d in FAILED_DYADS if d in configs]
    if already_present:
        print(f"Already present in dyad_configs.json, skipping: {already_present}")

    targets = [d for d in FAILED_DYADS if d not in configs]
    print(f"Backfilling {len(targets)} dyads: {targets}\n")

    results = {}
    errors = []
    for i, dyad in enumerate(targets):
        try:
            new_config = generate_baseline(dyad)
            results[dyad] = new_config
            print(f"  {i+1}/{len(targets)}. {dyad:20} -> OK "
                  f"(action_type={new_config.get('action_type')})")
            if not dry_run:
                configs[dyad] = new_config
        except Exception as e:
            errors.append(f"{dyad}: {e}")
            print(f"  {i+1}/{len(targets)}. {dyad:20} -> ERROR: {e}")
        time.sleep(0.3)

    if not dry_run and results:
        save_dyad_configs(configs)
        print(f"\nWrote {len(results)} new dyad baselines to dyad_configs.json")
    elif dry_run:
        print(f"\n[DRY RUN] Would have written {len(results)} new baselines")

    if errors:
        print(f"\n{len(errors)} error(s), still need manual attention:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()

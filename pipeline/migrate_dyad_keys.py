"""
One-time migration: canonicalize dyad keys in predictions/log.jsonl and
pipeline/dyad_configs.json using pipeline/dyad_registry.py.

Backs up both files before writing. Safe to re-run (idempotent) -- rows already
on their canonical key are left untouched.
"""
import json
import shutil
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from dyad_registry import ALIASES, _ALIAS_TO_CANONICAL, NON_BILATERAL, CANONICAL_KEYS

LOG_PATH = "predictions/log.jsonl"
CONFIG_PATH = "pipeline/dyad_configs.json"

def backup(path):
    if not os.path.exists(path):
        print(f"  [skip backup, missing] {path}")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    bak_path = f"{path}.bak.{stamp}"
    shutil.copy2(path, bak_path)
    print(f"  backed up -> {bak_path}")

def migrate_log():
    print(f"\n=== Migrating {LOG_PATH} ===")
    if not os.path.exists(LOG_PATH):
        print("  [missing, skipping]")
        return
    backup(LOG_PATH)

    rewritten = 0
    total = 0
    out_lines = []
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            row = json.loads(line)
            dyad = row.get("dyad")
            if dyad in _ALIAS_TO_CANONICAL:
                row["dyad"] = _ALIAS_TO_CANONICAL[dyad]
                rewritten += 1
            out_lines.append(json.dumps(row))

    with open(LOG_PATH, "w") as f:
        f.write("\n".join(out_lines) + "\n")

    print(f"  {total} rows read, {rewritten} rows rekeyed to canonical dyad")

def migrate_config():
    print(f"\n=== Migrating {CONFIG_PATH} ===")
    if not os.path.exists(CONFIG_PATH):
        print("  [missing, skipping]")
        return
    backup(CONFIG_PATH)

    with open(CONFIG_PATH) as f:
        configs = json.load(f)

    removed = []
    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            if alias in configs:
                if canonical not in configs:
                    configs[canonical] = configs[alias]
                    print(f"  [promoted] '{alias}' config -> '{canonical}' (canonical was missing)")
                del configs[alias]
                removed.append(alias)

    with open(CONFIG_PATH, "w") as f:
        json.dump(configs, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"  removed {len(removed)} dead alias config entries: {removed}")
    print(f"  {len(configs)} canonical/non-bilateral keys remain")

def validate():
    print("\n=== Post-migration validation ===")
    with open(CONFIG_PATH) as f:
        configs = json.load(f)
    remaining_keys = set(configs.keys())

    problems = []
    for alias_set in ALIASES.values():
        for alias in alias_set:
            if alias in remaining_keys:
                problems.append(f"alias '{alias}' still present in dyad_configs.json")

    log_dyads = set()
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    log_dyads.add(json.loads(line).get("dyad"))

    for d in log_dyads:
        if d in _ALIAS_TO_CANONICAL:
            problems.append(f"log.jsonl still contains un-migrated alias dyad '{d}'")

    if problems:
        print("  FAILED:")
        for p in problems:
            print(f"    - {p}")
        sys.exit(1)
    else:
        print("  OK -- no aliases remain in config or log")

if __name__ == "__main__":
    migrate_log()
    migrate_config()
    validate()

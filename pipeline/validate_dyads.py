"""
Startup validation dump. Run before the daily pipeline (or manually, anytime)
to confirm every dyad in dyad_configs.json resolves to exactly one canonical
key and has a non-empty crisis_context. Exits non-zero on any failure so it
can gate run_pipeline.sh if desired.

Run: python3.11 pipeline/validate_dyads.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dyad_registry import ALIASES, NON_BILATERAL, CANONICAL_KEYS, _ALIAS_TO_CANONICAL, find_fuzzy_match

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "dyad_configs.json")


def main():
    with open(CONFIG_PATH) as f:
        configs = json.load(f)

    keys = list(configs.keys())
    failures = []
    warnings = []

    for k in keys:
        if k in _ALIAS_TO_CANONICAL:
            failures.append(
                f"'{k}' is a known dead alias for '{_ALIAS_TO_CANONICAL[k]}' but still "
                f"exists as its own dyad_configs.json entry -- re-run migrate_dyad_keys.py"
            )

    for k in keys:
        if k in NON_BILATERAL:
            continue
        entry = configs[k]
        ctx = entry.get("crisis_context")
        if not ctx or not str(ctx).strip():
            warnings.append(f"'{k}' has no crisis_context set")

    for i, k1 in enumerate(keys):
        for k2 in keys[i+1:]:
            if find_fuzzy_match(k1, [k2]):
                already_known = (
                    k1 in _ALIAS_TO_CANONICAL and _ALIAS_TO_CANONICAL[k1] == k2
                ) or (
                    k2 in _ALIAS_TO_CANONICAL and _ALIAS_TO_CANONICAL[k2] == k1
                )
                if not already_known:
                    failures.append(
                        f"UNREGISTERED COLLISION: '{k1}' and '{k2}' look like the same "
                        f"dyad but neither is in dyad_registry.py ALIASES -- add one"
                    )

    for canonical in CANONICAL_KEYS:
        if canonical not in configs and canonical not in NON_BILATERAL:
            warnings.append(
                f"registry canonical key '{canonical}' has no dyad_configs.json entry"
            )

    print(f"Checked {len(keys)} dyad_configs.json entries "
          f"({len(keys) - len([k for k in keys if k in NON_BILATERAL])} bilateral, "
          f"{len([k for k in keys if k in NON_BILATERAL])} non-bilateral)\n")

    if warnings:
        print(f"⚠️  {len(warnings)} warning(s):")
        for w in warnings:
            print(f"    - {w}")
        print()

    if failures:
        print(f"❌ {len(failures)} FAILURE(S):")
        for fail in failures:
            print(f"    - {fail}")
        sys.exit(1)
    else:
        print("✅ Validation passed -- no dead aliases, no unregistered collisions")
        sys.exit(0)


if __name__ == "__main__":
    main()

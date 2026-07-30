import json, re
from collections import Counter

def load_jsonl(path):
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        print(f"  [missing] {path}")
    return rows

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  [missing] {path}")
        return {}
    except json.JSONDecodeError:
        print(f"  [malformed json] {path}")
        return {}

def extract_dyad_keys(obj, keys_found, path_hint):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("dyad", "dyad_key", "dyad_name", "pair"):
                if isinstance(v, str):
                    keys_found[v] += 1
            if isinstance(v, (dict, list)):
                extract_dyad_keys(v, keys_found, path_hint)
    elif isinstance(obj, list):
        for item in obj:
            extract_dyad_keys(item, keys_found, path_hint)

print("=== dyad_configs.json ===")
configs = load_json("pipeline/dyad_configs.json")
config_keys = sorted(configs.keys()) if isinstance(configs, dict) else []
for k in config_keys:
    print(f"  {k}")
print(f"  --> {len(config_keys)} canonical-candidate keys from dyad_configs.json")

print("\n=== predictions/log.jsonl ===")
log_rows = load_jsonl("predictions/log.jsonl")
log_keys = Counter()
extract_dyad_keys(log_rows, log_keys, "log.jsonl")
for k, c in sorted(log_keys.items()):
    flag = "  <-- NOT IN dyad_configs.json" if k not in config_keys else ""
    print(f"  {k}  (n={c}){flag}")

print("\n=== translator_cache.json ===")
cache = load_json("pipeline/translator_cache.json")
cache_keys = Counter()
extract_dyad_keys(cache, cache_keys, "translator_cache.json")
for k, c in sorted(cache_keys.items()):
    flag = "  <-- NOT IN dyad_configs.json" if k not in config_keys else ""
    print(f"  {k}  (n={c}){flag}")

print("\n=== Fuzzy collision check (case/order/separator variants) ===")
def normalize(s):
    parts = re.split(r"[-_/]", s.lower().strip())
    return tuple(sorted(p.strip() for p in parts if p))

all_keys = set(config_keys) | set(log_keys) | set(cache_keys)
buckets = {}
for k in all_keys:
    buckets.setdefault(normalize(k), []).append(k)

collisions = {norm: variants for norm, variants in buckets.items() if len(variants) > 1}
if collisions:
    for norm, variants in collisions.items():
        print(f"  COLLISION: {variants}")
else:
    print("  none found (unexpected given known US-Iran/USA-Iran, NATO-Russia/Russia-NATO cases — check field extraction above)")

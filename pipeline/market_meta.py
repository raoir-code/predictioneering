"""
Static listing metadata per market (creation / start / end dates) from the Gamma API.
Why (Oct 19): by-date contracts resolve YES on a qualifying action 'between market creation and the specified
date', so each listing's window start is needed to turn resolutions into strike exposure (window-hazard model).
Static metadata only: no prices, no outcomes. Fetches only ids not yet stored; never rewrites a stored record.

  python -m pipeline.market_meta            fetch missing ids (CORE markets in the feed + every scored market)
  python -m pipeline.market_meta --limit N  at most N fetches
"""
import json, sys, time, datetime as dt, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
META = ROOT / "market_meta.json"
GAMMA = "https://gamma-api.polymarket.com/markets/"

def ids_wanted():
    ids = set()
    feed = json.loads((ROOT / "classified_feed.json").read_text())
    feed = feed if isinstance(feed, list) else feed.get("markets", feed.get("data", []))
    ids |= {str(m.get("market_id")) for m in feed if m.get("bucket") == "CORE"}
    for fn in (ROOT.parent / "predictions" / "brier_log.jsonl", ROOT.parent / "predictions" / "log.jsonl"):
        if fn.exists():
            for l in fn.read_text().splitlines():
                if l.strip():
                    ids.add(str(json.loads(l).get("market_id")))
    return {i for i in ids if i and i != "None"}

def fetch(mid):
    req = urllib.request.Request(GAMMA + mid, headers={"User-Agent": "predictioneering/market_meta"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    return d[0] if isinstance(d, list) else d

def save(meta):
    tmp = META.with_suffix(".json.tmp"); tmp.write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n"); tmp.replace(META)

def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    meta = json.loads(META.read_text()) if META.exists() else {}
    todo = sorted(ids_wanted() - set(meta))
    if limit is not None:
        todo = todo[:limit]
    new = failed = 0
    for i, mid in enumerate(todo, 1):
        try:
            d = fetch(mid)
            meta[mid] = {"question": d.get("question"), "createdAt": d.get("createdAt"), "startDate": d.get("startDate"),
                         "endDate": d.get("endDate"), "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat()}
            new += 1
        except Exception as ex:
            failed += 1
            print(f"  [meta] {mid}: {ex!r}")
        if i % 50 == 0:
            save(meta); print(f"  [meta] {i}/{len(todo)}")
        time.sleep(0.15)
    save(meta)
    print(f"[meta] stored {len(meta)} | fetched {new} new | failed {failed}")

if __name__ == "__main__":
    main()

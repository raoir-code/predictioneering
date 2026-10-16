"""
Pilot news collector, Israel -> Lebanon (During-War spec v0.4). Forward-only: news history
cannot be re-fetched, so every day this does not run is lost.

Design (Oct 16 diagnosis): GNews caps a request at 25 and holds only ~50 "Lebanon" articles
per 48h; a narrow boolean strike query returned 0. So collect EVERYTHING for broad queries,
page through all of it, and let pilot/lebanon_ledger.py's classifier find strikes/ceasefires.
Keeps url and source. One file per query per run: cache/gnews_pilot/<name>_<UTC stamp>.json.
fetched_at = first_seen_at. Never raises: always exits 0 so it cannot break the daily run.
"""
import json, os, time, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / "cache" / "gnews_pilot"
QUERIES = {"lebanon": "Lebanon", "hezbollah": "Hezbollah"}
PER_PAGE, MAX_PAGES, WINDOW_H = 25, 6, 48

def load_env():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def collect(requests, key, q):
    now = dt.datetime.now(dt.timezone.utc)
    base = {"q": q, "lang": "en", "max": PER_PAGE, "sortby": "publishedAt", "apikey": key,
            "from": (now - dt.timedelta(hours=WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    arts, total, errors, seen = [], None, None, set()
    for page in range(1, MAX_PAGES + 1):
        b = requests.get("https://gnews.io/api/v4/search", params={**base, "page": page}, timeout=30).json()
        if b.get("errors"):
            errors = b["errors"]; break
        total = b.get("totalArticles", total)
        batch = [a for a in b.get("articles", []) if a.get("url") not in seen]
        if not batch:
            break  # empty page, or pagination unsupported (repeat of page 1)
        for a in batch:
            seen.add(a.get("url")); arts.append(a)
        if total is not None and len(arts) >= total:
            break
        time.sleep(1)
    params = {k: v for k, v in base.items() if k != "apikey"}
    return arts, total, errors, params, page

def main():
    try:
        load_env()
        import requests
        key = os.environ.get("GNEWS_API_KEY")
        if not key:
            print("[pilot_collector] no GNEWS_API_KEY -- skipped"); return
        OUTDIR.mkdir(parents=True, exist_ok=True)
        for name, q in QUERIES.items():
            try:
                arts, total, errors, params, pages = collect(requests, key, q)
                stamp = dt.datetime.now(dt.timezone.utc)
                rec = {"fetched_at": stamp.isoformat(), "query_name": name, "params": params,
                       "total_reported": total, "pages_read": pages, "errors": errors, "n": len(arts),
                       "articles": [{"title": a.get("title"), "description": a.get("description"),
                                     "url": a.get("url"), "source": (a.get("source") or {}).get("name"),
                                     "publishedAt": a.get("publishedAt")} for a in arts]}
                (OUTDIR / f"{name}_{stamp.strftime('%Y%m%dT%H%MZ')}.json").write_text(json.dumps(rec))
                print(f"[pilot_collector] {name}: {len(arts)} of {total} reported, {pages} page(s)"
                      + (f" errors={errors}" if errors else ""))
            except Exception as ex:
                print(f"[pilot_collector] {name}: failed ({ex}) -- continuing")
    except Exception as ex:
        print(f"[pilot_collector] failed ({ex}) -- non-fatal")

if __name__ == "__main__":
    main()

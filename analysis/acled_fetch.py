"""
ACLED pull for priors (offline only; never used live). Credentials from .env: ACLED_USERNAME, ACLED_PASSWORD.
  python analysis/acled_fetch.py --test   small queries to check field and actor naming
  python analysis/acled_fetch.py --pull   full pull (next step)
"""
import os, re, sys, json
from collections import Counter
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
API = "https://acleddata.com/api/acled/read"

def env(k):
    if os.environ.get(k):
        return os.environ[k]
    for line in (ROOT / ".env").read_text().splitlines():
        m = re.match(rf"^\s*(?:export\s+)?{k}\s*=\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip('"').strip("'")
    raise SystemExit(f"{k} missing from .env")

def token():
    r = requests.post("https://acleddata.com/oauth/token", headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"username": env("ACLED_USERNAME"), "password": env("ACLED_PASSWORD"),
                            "grant_type": "password", "client_id": "acled"}, timeout=60)
    r.raise_for_status()
    return r.json()["access_token"]

def read(tok, **params):
    r = requests.get(API, params=params, headers={"Authorization": f"Bearer {tok}"}, timeout=180)
    r.raise_for_status()
    return r.json()

def test():
    tok = token()
    for country, dates in (("Yemen", "2018-01-01|2018-01-31"), ("Lebanon", "2024-09-15|2024-09-30"), ("Syria", "2025-01-01|2025-03-31")):
        j = read(tok, country=country, event_date=dates, event_date_where="BETWEEN", event_type="Explosions/Remote violence", limit=1000)
        d = j.get("data") or []
        print(f"--- {country} {dates}: count {j.get('count')} | {len(d)} rows returned")
        if not d:
            print("    response:", {k: v for k, v in j.items() if k != "data"}); continue
        print("    fields:", sorted(d[0]))
        print("    sub_event_type:", dict(Counter(x.get("sub_event_type") for x in d).most_common(6)))
        print("    actor1:", dict(Counter(x.get("actor1") for x in d).most_common(8)))
        print("    example:", {k: d[0].get(k) for k in ("event_date", "actor1", "actor2", "sub_event_type", "admin1", "fatalities")})


import hashlib, time, datetime as dt
OUT = ROOT / "data" / "external" / "acled"
COUNTRIES = ["Lebanon", "Syria", "Yemen", "Iraq", "Iran", "Israel", "Afghanistan", "Jordan",
             "United Arab Emirates", "Bahrain", "Kuwait", "Qatar", "Saudi Arabia", "Oman"]
YEARS = range(2015, 2026)   # priors use data through 2025-12-31 only: 2026 stays clean for replay
KEEP = ("event_id_cnty", "event_date", "year", "time_precision", "event_type", "sub_event_type", "actor1", "assoc_actor_1",
        "actor2", "country", "admin1", "location", "latitude", "longitude", "fatalities", "source", "timestamp")
PAGE = 5000

def pull():
    OUT.mkdir(parents=True, exist_ok=True)
    man_p = OUT / "MANIFEST.json"
    man = json.loads(man_p.read_text()) if man_p.exists() else {"_doc": "ACLED Explosions/Remote violence, pulled for offline priors only. Data through 2025-12-31. JSONL gitignored; sha256 + query recorded.", "files": {}}
    tok = token()
    for c in COUNTRIES:
        for y in YEARS:
            fn = f"{c.replace(' ', '_')}_{y}.jsonl"
            if fn in man["files"]:
                continue
            rows, page = [], 1
            while True:
                for attempt in range(4):
                    try:
                        j = read(tok, country=c, event_date=f"{y}-01-01|{y}-12-31", event_date_where="BETWEEN",
                                 event_type="Explosions/Remote violence", limit=PAGE, page=page)
                        break
                    except Exception as ex:
                        if attempt == 3:
                            raise
                        time.sleep(5 * (attempt + 1)); tok = token()
                d = j.get("data") or []
                rows += [{k: x.get(k) for k in KEEP} for x in d]
                if len(d) < PAGE:
                    break
                page += 1; time.sleep(0.5)
            f = OUT / fn
            f.write_text("".join(json.dumps(r) + "\n" for r in rows))
            man["files"][fn] = {"query": {"country": c, "year": y, "event_type": "Explosions/Remote violence"}, "rows": len(rows),
                                "pages": page, "pulled": dt.date.today().isoformat(), "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
            man_p.write_text(json.dumps(man, indent=2) + "\n")
            print(f"  {c} {y}: {len(rows)} events ({page} page{'s' if page > 1 else ''})", flush=True)

def actors():
    INIT = {"Israel": ["Israel"], "Saudi Arabia": ["Saudi", "Restoring Hope", "Decisive Storm"], "Iran": ["Military Forces of Iran", "Islamic Revolutionary Guard"],
            "Pakistan": ["Military Forces of Pakistan"], "United States": ["United States"], "Turkey": ["Military Forces of Turkey"]}
    tab = {}
    for f in sorted(OUT.glob("*.jsonl")):
        for l in f.read_text().splitlines():
            r = json.loads(l)
            for ini, keys in INIT.items():
                a = r.get("actor1") or ""
                if any(k in a for k in keys):
                    t = tab.setdefault((ini, r["country"]), {"names": Counter(), "days": set(), "sub": Counter()})
                    t["names"][a] += 1; t["days"].add(r["event_date"]); t["sub"][r["sub_event_type"]] += 1
    for (ini, c), t in sorted(tab.items(), key=lambda kv: -len(kv[1]["days"])):
        if len(t["days"]) < 3:
            continue
        print(f"--- {ini} -> {c}: {len(t['days'])} active days | {dict(t['sub'].most_common(3))}")
        print(f"    actor1 names: {dict(t['names'].most_common(4))}")

WORLD = ROOT / "data" / "external" / "acled_world"
CROSS_KEEP = ("event_id_cnty", "event_date", "year", "time_precision", "sub_event_type", "actor1", "inter1", "actor2", "inter2",
              "assoc_actor_2", "country", "admin1", "fatalities")
COALITION = re.compile(r"^(Operation |Global Coalition|NATO\b|Coalition)", re.I)

def home_of(actor1):
    m = re.match(r"^Military Forces of (?:the )?(.+?) \(", actor1 or "")
    return m.group(1) if m else None

def cross_border(r):
    a = r.get("actor1") or ""
    if COALITION.match(a):
        return True
    h = home_of(a)
    return bool(h) and h != r.get("country")

def pull_world():
    """All countries, Explosions/Remote violence, 2015-2025, month by month; keep only cross-border state / de facto / coalition strikes."""
    WORLD.mkdir(parents=True, exist_ok=True)
    man_p = WORLD / "MANIFEST.json"
    man = json.loads(man_p.read_text()) if man_p.exists() else {"_doc": "ACLED Explosions/Remote violence, ALL countries 2015-2025, filtered to cross-border strikes "
           "(actor1 = Military Forces of X striking outside X, or a coalition operation). For class priors only. JSONL gitignored.", "files": {}}
    tok = token()
    for y in YEARS:
        fn = f"world_{y}.jsonl"
        if fn in man["files"]:
            continue
        kept, seen = [], 0
        for mth in range(1, 13):
            last = (dt.date(y + (mth == 12), mth % 12 + 1, 1) - dt.timedelta(1)).day
            page = 1
            while True:
                for attempt in range(4):
                    try:
                        j = read(tok, event_date=f"{y}-{mth:02d}-01|{y}-{mth:02d}-{last}", event_date_where="BETWEEN",
                                 event_type="Explosions/Remote violence", limit=PAGE, page=page); break
                    except Exception:
                        if attempt == 3: raise
                        time.sleep(5 * (attempt + 1)); tok = token()
                d = j.get("data") or []; seen += len(d)
                kept += [{k: x.get(k) for k in CROSS_KEEP} for x in d if cross_border(x)]
                if len(d) < PAGE: break
                page += 1; time.sleep(0.5)
        f = WORLD / fn; f.write_text("".join(json.dumps(r) + "\n" for r in kept))
        man["files"][fn] = {"query": {"year": y, "event_type": "Explosions/Remote violence", "countries": "all", "filter": "cross-border"},
                            "rows_seen": seen, "rows_kept": len(kept), "pulled": dt.date.today().isoformat(),
                            "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
        man_p.write_text(json.dumps(man, indent=2) + "\n")
        print(f"  {y}: {seen} events scanned, {len(kept)} cross-border kept", flush=True)

def pull_live(start="2026-01-01"):
    """2026 to today, all countries, Explosions/Remote violence, cross-border only, WITH ACLED's timestamp (last-update time)
    for walk-forward use as a LIVE fighting signal. Overwrites live_2026.jsonl; the manifest records the pull time."""
    WORLD.mkdir(parents=True, exist_ok=True); tok = token(); kept, seen = [], 0
    s0, today = dt.date.fromisoformat(start), dt.date.today()
    m = dt.date(s0.year, s0.month, 1)
    while m <= today:
        nxt = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1); end = min(today, nxt - dt.timedelta(1)); page = 1
        while True:
            for attempt in range(4):
                try:
                    j = read(tok, event_date=f"{m}|{end}", event_date_where="BETWEEN", event_type="Explosions/Remote violence", limit=PAGE, page=page); break
                except Exception:
                    if attempt == 3: raise
                    time.sleep(5 * (attempt + 1)); tok = token()
            d = j.get("data") or []; seen += len(d)
            kept += [{**{k: x.get(k) for k in CROSS_KEEP}, "timestamp": x.get("timestamp")} for x in d if cross_border(x)]
            if len(d) < PAGE: break
            page += 1; time.sleep(0.5)
        print(f"  {m:%Y-%m}: cumulative {seen} scanned, {len(kept)} cross-border kept", flush=True); m = nxt
    f = WORLD / "live_2026.jsonl"; f.write_text("".join(json.dumps(r) + "\n" for r in kept))
    man_p = WORLD / "MANIFEST.json"; man = json.loads(man_p.read_text())
    man["files"]["live_2026.jsonl"] = {"query": {"from": start, "to": str(today), "event_type": "Explosions/Remote violence", "countries": "all", "filter": "cross-border"},
                                       "rows_seen": seen, "rows_kept": len(kept), "pulled_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                       "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "note": "LIVE signal; timestamp = ACLED last-update time (walk-forward safe, conservative)"}
    man_p.write_text(json.dumps(man, indent=2) + "\n")

if __name__ == "__main__":
    if "--test" in sys.argv: test()
    elif "--pull" in sys.argv: pull()
    elif "--actors" in sys.argv: actors()
    elif "--world" in sys.argv: pull_world()
    elif "--live" in sys.argv: pull_live()
    else: print("use --test | --pull | --actors")

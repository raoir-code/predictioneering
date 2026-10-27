"""
GDELT 2.0 event pull for the second-source detection test (docs/gdelt_detection_prereg.md). GDELT is open data.
Downloads the 15-minute event export files for a date range and keeps only "Fight" events (CAMEO root 19) whose acting
country and location country are both in our country set and differ (cross-border). Output (gitignored): data/external/gdelt/strikes_<start>_<end>.jsonl,
one row per kept event with the fields the test needs, including DATEADDED (when GDELT published it, UTC), which makes the
test walk-forward: an event counts on a day only if GDELT had published it by that morning's run.
  python analysis/gdelt_pull.py 2026-01-01 2026-10-16 [--workers 16]
"""
import sys, io, csv, json, zipfile, datetime as dt, concurrent.futures as cf, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://data.gdeltproject.org/gdeltv2/{}.export.CSV.zip"
# CAMEO actor country code -> FIPS 10-4 location code (GDELT uses CAMEO for actors and FIPS for places)
COUNTRIES = {
    "ISR": "IS", "LBN": "LE", "SYR": "SY", "IRN": "IR", "OMN": "MU", "SAU": "SA", "YEM": "YM", "IRQ": "IZ", "KWT": "KU",
    "ARE": "AE", "JOR": "JO", "BHR": "BA", "QAT": "QA", "EGY": "EG", "PAK": "PK", "AFG": "AF", "ERI": "ER", "ETH": "ET",
    "USA": "US", "GBR": "UK", "FRA": "FR", "DEU": "GM", "TUR": "TU", "CHN": "CH", "TWN": "TW", "JPN": "JA", "IND": "IN",
    "DNK": "DA", "PAN": "PM", "RUS": "RS", "UKR": "UP", "PHL": "RP", "PRK": "KN", "KOR": "KS", "CUB": "CU", "COL": "CO",
    "MEX": "MX", "VEN": "VE",
}
FIPS = set(COUNTRIES.values())
F = {"id": 0, "sqldate": 1, "a1code": 5, "a1country": 7, "a2country": 17, "root": 25, "code": 26, "base": 27, "rootcode": 28,
     "mentions": 31, "sources": 32, "articles": 33, "geo": 53, "added": 59, "url": 60}

def stamps(start, end):
    t = dt.datetime.combine(start, dt.time())
    while t.date() <= end:
        yield t.strftime("%Y%m%d%H%M%S"); t += dt.timedelta(minutes=15)

def keep(r):
    if len(r) < 61 or r[F["rootcode"]] != "19" or r[F["geo"]] not in FIPS:
        return False
    a = r[F["a1country"]] or (r[F["a1code"]] or "")[:3]
    return a in COUNTRIES and COUNTRIES[a] != r[F["geo"]]      # cross-border only: X's actor, located in another country Y

def row(r):
    a = r[F["a1country"]] or (r[F["a1code"]] or "")[:3]
    return {"id": r[F["id"]], "date": r[F["sqldate"]], "actor": a, "a1code": r[F["a1code"]], "a2country": r[F["a2country"]],
            "code": r[F["code"]], "base": r[F["base"]], "root_event": r[F["root"]] == "1", "mentions": int(r[F["mentions"]] or 0),
            "sources": int(r[F["sources"]] or 0), "articles": int(r[F["articles"]] or 0), "geo": r[F["geo"]],
            "added": r[F["added"]], "url": r[F["url"]]}

def fetch(stamp, session):
    for attempt in range(4):
        try:
            resp = session.get(BASE.format(stamp), timeout=60)
            if resp.status_code == 404:
                return stamp, [], "missing"
            resp.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(resp.content))
            rows = csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8", errors="replace"), delimiter="\t")
            return stamp, [row(r) for r in rows if keep(r)], "ok"
        except Exception as ex:
            err = repr(ex); time.sleep(2 * (attempt + 1))
    return stamp, [], f"failed: {err}"

def pull(start, end, workers=16, out=None):
    out = out or ROOT / "data" / "external" / "gdelt" / f"strikes_{start:%Y%m%d}_{end:%Y%m%d}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    S = list(stamps(start, end)); status = {"ok": 0, "missing": 0, "failed": []}; n = 0
    with requests.Session() as sess, open(out, "w") as fh, cf.ThreadPoolExecutor(workers) as ex:
        for i, (stamp, rows, st) in enumerate(ex.map(lambda s: fetch(s, sess), S)):
            if st == "ok": status["ok"] += 1
            elif st == "missing": status["missing"] += 1
            else: status["failed"].append((stamp, st))
            for r in rows: fh.write(json.dumps(r) + "\n"); n += 1
            if i % 2000 == 0: print(f"  {i}/{len(S)} files, {n} rows kept", flush=True)
    meta = {"start": str(start), "end": str(end), "files": len(S), **{k: (v if k != "failed" else len(v)) for k, v in status.items()},
            "rows": n, "failed_stamps": [s for s, _ in status["failed"]], "pulled_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1))
    print(f"[gdelt] {n} rows from {status['ok']} files ({status['missing']} missing upstream, {len(status['failed'])} failed) -> {out}")
    return out

if __name__ == "__main__":
    a, b = (dt.date.fromisoformat(x) for x in sys.argv[1:3])
    w = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 16
    pull(a, b, w)

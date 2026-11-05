"""
Strike-news fetch (Nov 2): a dedicated, full-recall headline feed for the tracked strike pairs (18; 20 from Nov 4 with US-Iran, US-Yemen).

Why: the engine's GNews queries (pipeline/dyad_configs.json "query") were written for node scoring, not for seeing strikes.
Several stack a third AND clause and use bare "Israel", so they miss the usual strike phrasing ("Israeli airstrikes ...",
"Israel shells towns in southern Lebanon"). Israel-Lebanon returned 5 articles in 7 days (vs 27 for the pair alone), and the
strike labeler got ~1 new Lebanon headline a day after Oct 20: the unified engine could see neither strikes nor quiet.

What: one uniform rule per pair, (A, demonym, capital, main armed actor) AND (same for B), no topic clause (the labeler in
pilot/news_strikes.py does the precision work). 48h window, paged to full recall (25 per page, up to MAX_PAGES).
Writes cache/gnews_strike/<Dyad>_<YYYYMMDD>.json, merged with an earlier same-day file. pilot/news_strikes.py reads it
alongside cache/gnews/. The engine's own queries and inputs are untouched. Never raises: always exits 0.
  python pilot/strike_news_fetch.py          fetch today
  python pilot/strike_news_fetch.py --test   offline checks (query lengths, merge)
"""
import json, os, sys, time, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / "cache" / "gnews_strike"
PER_PAGE, MAX_PAGES, WINDOW_H, QMAX = 25, 4, 48, 200     # GNews rejects q longer than ~200 chars (HTTP 400, Nov 2)

TERMS = {"Israel": ["Israel", "Israeli", "IDF"], "Lebanon": ["Lebanon", "Lebanese", "Hezbollah"],
         "Saudi Arabia": ['"Saudi Arabia"', "Saudi", "Riyadh"], "Yemen": ["Yemen", "Yemeni", "Houthi", "Houthis"],
         "Syria": ["Syria", "Syrian", "Damascus"], "Iran": ["Iran", "Iranian", "IRGC", "Tehran"], "Iraq": ["Iraq", "Iraqi", "Baghdad"],
         "United Arab Emirates": ["UAE", '"United Arab Emirates"', "Emirati", "Abu Dhabi"], "Bahrain": ["Bahrain", "Bahraini"],
         "Jordan": ["Jordan", "Jordanian", "Amman"], "Qatar": ["Qatar", "Qatari", "Doha"], "Kuwait": ["Kuwait", "Kuwaiti"],
         "Oman": ["Oman", "Omani", "Muscat"], "Egypt": ["Egypt", "Egyptian", "Cairo"], "Pakistan": ["Pakistan", "Pakistani", "Islamabad"],
         "Afghanistan": ["Afghanistan", "Afghan", "Taliban", "Kabul"], "Eritrea": ["Eritrea", "Eritrean", "Asmara"],
         "Ethiopia": ["Ethiopia", "Ethiopian", '"Addis Ababa"'],
         "United States": ['"United States"', "US", "American", "Pentagon", "CENTCOM"]}   # Nov 4: US directions had no strike feed (Qeshm, Nov 2-3)

def pairs():
    sys.path.insert(0, str(ROOT / "pilot"))
    import news_strikes as NS                       # single source for the tracked pairs
    return NS.DYADS

def query(A, B):
    q = "(" + " OR ".join(TERMS[A]) + ") AND (" + " OR ".join(TERMS[B]) + ")"
    assert len(q) <= QMAX, f"query too long ({len(q)}): {q}"
    return q

def load_env():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def collect(requests, key, q, now):
    base = {"q": q, "lang": "en", "max": PER_PAGE, "sortby": "publishedAt", "apikey": key,
            "from": (now - dt.timedelta(hours=WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ"), "to": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    arts, total, seen, page = [], None, set(), 0
    for page in range(1, MAX_PAGES + 1):
        b = None
        for attempt in (1, 2, 3):
            try:
                b = requests.get("https://gnews.io/api/v4/search", params={**base, "page": page}, timeout=30).json(); break
            except Exception:
                time.sleep(2 * attempt)
        if b is None or b.get("errors"):
            return arts, total, (b or {}).get("errors") or "request failed", page
        total = b.get("totalArticles", total)
        batch = [a for a in b.get("articles", []) if a.get("url") not in seen]
        if not batch: break
        for a in batch: seen.add(a.get("url")); arts.append(a)
        if total is not None and len(arts) >= total: break
        time.sleep(1)
    return arts, total, None, page

def merge(path, rec):
    """Union with an earlier same-day file (a re-run must not lose what the first run saw)."""
    if path.exists():
        try:
            old = json.loads(path.read_text())
            have = {a["url"] for a in rec["articles"]}
            rec["articles"] += [a for a in old.get("articles", []) if a.get("url") not in have]
        except Exception:
            pass
    rec["n"] = len(rec["articles"])
    return rec

def main():
    try:
        load_env()
        import requests
        key = os.environ.get("GNEWS_API_KEY")
        if not key: print("[strike-news] no GNEWS_API_KEY -- skipped"); return
        OUTDIR.mkdir(parents=True, exist_ok=True)
        now = dt.datetime.now(dt.timezone.utc); day = dt.datetime.now().strftime("%Y%m%d")   # local date, as cache/gnews
        tot_new = 0
        for dyad, (A, B) in pairs().items():
            try:
                q = query(A, B)
                arts, total, errors, pages = collect(requests, key, q, now)
                rec = {"fetched_at": now.isoformat(), "query": q, "window_h": WINDOW_H, "total_reported": total, "pages_read": pages,
                       "errors": errors, "articles": [{"title": a.get("title"), "description": a.get("description"), "url": a.get("url"),
                                                       "source": (a.get("source") or {}).get("name"), "publishedAt": a.get("publishedAt")}
                                                      for a in arts if a.get("title")]}
                path = OUTDIR / f"{dyad}_{day}.json"
                rec = merge(path, rec); path.write_text(json.dumps(rec)); tot_new += len(arts)
                print(f"  [strike-news] {dyad:22} {len(arts):3} of {total} reported, {pages} page(s)" + (f"  errors={errors}" if errors else ""))
            except Exception as ex:
                print(f"  [strike-news] {dyad}: failed ({ex!r}) -- continuing")
        print(f"[strike-news] {tot_new} headlines fetched for {len(pairs())} pairs -> {OUTDIR.relative_to(ROOT)}")
    except Exception as ex:
        print(f"[strike-news] failed ({ex!r}) -- non-fatal")

def _tests():
    for dyad, (A, B) in pairs().items():
        q = query(A, B)
        assert q.count(" AND ") == 1, q                                  # pair only, no topic clause
        assert "Israel" not in q or "Israeli" in q, q                    # demonyms included
    import tempfile
    p = Path(tempfile.mkdtemp()) / "X_20261102.json"
    p.write_text(json.dumps({"articles": [{"url": "u1", "title": "a"}, {"url": "u2", "title": "b"}]}))
    r = merge(p, {"articles": [{"url": "u2", "title": "b"}, {"url": "u3", "title": "c"}]})
    assert sorted(a["url"] for a in r["articles"]) == ["u1", "u2", "u3"] and r["n"] == 3, r
    print(f"strike_news_fetch tests: OK ({len(pairs())} pairs, longest query {max(len(query(*v)) for v in pairs().values())} chars)")

if __name__ == "__main__":
    _tests() if "--test" in sys.argv else main()

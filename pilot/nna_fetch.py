"""Nov 10: fetch NNA (Lebanon's National News Agency) English article metadata by day, for the NNA detection test
(docs/nna_detection_prereg.md). Source: the public daily sitemaps (/en/sitemap/n/<cat>?date=YYYY-MM-DD) and each article's
og:title, og:description (NNA items are one or two sentences) and published time. No keyword filter: every article in every
category active in 2026 is kept, so nothing is dropped before labeling.

Polite: one request every 1.5 s; robots.txt allows everything but /api/ and /admin/.
Cache: cache/nna/ (gitignored, and the daily run never stages it: NNA text is not republished). Resumable: re-running skips
days and articles already fetched.

  python3.11 pilot/nna_fetch.py 2026-11-07 2026-11-07     # smoke test, one day
  python3.11 pilot/nna_fetch.py 2026-07-01 2026-11-10     # full pull (~2.5 h)
"""
import re, sys, json, time, html, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "nna"
H = {"User-Agent": "Mozilla/5.0 (research; contact via site)"}
CATS = (1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 15, 18, 19)      # English categories with articles in Jul-Nov 2026 (probe, Nov 10)
BEIRUT = ZoneInfo("Asia/Beirut")
PAUSE = 1.5


def get(url, tries=3):
    for k in range(tries):
        try:
            r = requests.get(url, headers=H, timeout=30)
            time.sleep(PAUSE)
            if r.status_code == 200: return r.text
            if r.status_code == 404: return ""
        except requests.RequestException:
            pass
        time.sleep(5 * (k + 1))
    raise RuntimeError(f"fetch failed after {tries} tries: {url}")


def parse_day(xml):
    return re.findall(r"<loc>\s*(https?://[^<\s]+/en/news/\d+/[^<\s]*)\s*</loc>", xml)


def parse_article(url, page):
    def meta(k):
        m = re.findall(r'<meta[^>]+(?:property|name)="%s"[^>]+content="([^"]*)"' % re.escape(k), page)
        return m[0] if m else ""
    clean = lambda s: re.sub(r"\s+", " ", html.unescape(html.unescape(s))).replace("======", "").strip()
    pub = meta("article:published_time") or (re.findall(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z", page) or [""])[0]
    a = {"id": re.search(r"/news/(\d+)/", url).group(1), "url": url, "title": clean(meta("og:title")),
         "description": clean(meta("og:description")), "published_utc": pub, "beirut_day": None}
    if pub:
        a["beirut_day"] = dt.datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(BEIRUT).date().isoformat()
    return a


def day_urls(day):
    f = CACHE / "days" / f"{day}.json"
    if f.exists(): return json.loads(f.read_text())
    urls = {}
    for c in CATS:
        for u in parse_day(get(f"https://nna-leb.gov.lb/en/sitemap/n/{c}?date={day}")): urls.setdefault(u, c)
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(urls, indent=0))
    return urls


def article(url):
    aid = re.search(r"/news/(\d+)/", url).group(1)
    f = CACHE / "articles" / f"{aid}.json"
    if f.exists(): return json.loads(f.read_text()), False
    a = parse_article(url, get(url))
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(a, ensure_ascii=False))
    return a, True


def main(start, end):
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    days = [(d0 + dt.timedelta(n)).isoformat() for n in range((d1 - d0).days + 1)]
    n_art = n_new = n_fail = 0
    for i, day in enumerate(days, 1):
        try:
            urls = day_urls(day)
        except RuntimeError as e:
            print(f"[nna] {day}: sitemap FAILED ({e}); rerun to resume", flush=True); n_fail += 1; continue
        new = 0
        for u in urls:
            try:
                a, fresh = article(u); n_art += 1; new += fresh; n_new += fresh
            except RuntimeError as e:
                print(f"[nna] article FAILED {u} ({e})", flush=True); n_fail += 1
        print(f"[nna] {day} ({i}/{len(days)}): {len(urls)} articles, {new} new", flush=True)
    print(f"[nna] done: {len(days)} days, {n_art} articles ({n_new} fetched now), {n_fail} failures"
          + ("; rerun the same command to retry them" if n_fail else ""), flush=True)


def _tests():
    xml = ('<urlset><url><loc>https://nna-leb.gov.lb/en/news/226217/four-artillery-shells-land-in-beit-yahoun-2</loc>'
           '<lastmod>2026-11-07</lastmod></url><url><loc> https://nna-leb.gov.lb/en/news/226222/x </loc></url>'
           '<url><loc>https://nna-leb.gov.lb/en/sitemap/n/3?date=2026-11-07</loc></url></urlset>')
    assert parse_day(xml) == ["https://nna-leb.gov.lb/en/news/226217/four-artillery-shells-land-in-beit-yahoun-2",
                              "https://nna-leb.gov.lb/en/news/226222/x"], parse_day(xml)
    page = ('<meta property="og:title" content="Four artillery shells land in Beit Yahoun"/>'
            '<meta property="og:description" content="NNA - Nabatieh &amp;ndash; Four artillery shells, fired from Israeli positions, '
            'landed this afternoon.\n\n======"/><meta property="article:published_time" content="2026-11-07T22:42:12.000Z"/>')
    a = parse_article("https://nna-leb.gov.lb/en/news/226217/four-artillery-shells-land-in-beit-yahoun-2", page)
    assert a["title"] == "Four artillery shells land in Beit Yahoun" and a["id"] == "226217"
    assert a["description"].startswith("NNA - Nabatieh – Four artillery") and "=" not in a["description"], a["description"]
    assert a["beirut_day"] == "2026-11-08", a["beirut_day"]           # 22:42 UTC = 00:42 Beirut, next day
    b = parse_article("https://nna-leb.gov.lb/en/news/1/y", '<script>"2026-07-01T06:46:18.000Z"</script>')
    assert b["published_utc"] == "2026-07-01T06:46:18.000Z" and b["beirut_day"] == "2026-07-01" and b["title"] == ""
    print("nna_fetch tests: OK")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--test": _tests()
    elif len(sys.argv) == 3: main(sys.argv[1], sys.argv[2])
    else: print(__doc__)

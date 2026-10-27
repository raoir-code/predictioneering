"""
Forward-only negotiation-evidence collector for family C (C2 groundwork; docs/c1b_prereg.md, ChatGPT review Oct 22). LOGS ONLY:
nothing here prices a contract. News history cannot be re-fetched, so every day this does not run is lost.

Actor sets = those of the open agreement contracts we price (pilot/ceasefire_markets.json via pilot/ceasefire_bc.py).
Per actor set and run: one GNews query, last 48h, up to MAX_PAGES pages -> cache/gnews_talks/<actors>_<UTC stamp>.json.
Each article is labeled once, ever (pilot/talks_labels.jsonl), by the same model as the other labelers:
  TALKS_HELD     a negotiation meeting or round between the parties (direct or via a mediator in the room) actually took place
  TALKS_PLANNED  talks announced, scheduled or agreed to be held (not yet held)
  MEDIATION      a third party carried messages / shuttled between the parties (indirect channel), without a joint meeting
  TALKS_ENDED    talks suspended, collapsed, walked out of, or a side refused to attend
  AGREEMENT      an agreement / ceasefire / extension was announced (an OUTCOME: recorded, never used as a precursor signal)
  OTHER          anything else (calls for talks, commentary, fighting, unrelated)
Availability = fetch time (known), never publication time alone. Labels judged from the item text only. Never raises.

  python pilot/talks_collector.py            collect + label
  python pilot/talks_collector.py --test     offline tests
"""
import json, os, re, sys, time, hashlib, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot"))
OUTDIR = ROOT / "cache" / "gnews_talks"
LABELS = ROOT / "pilot" / "talks_labels.jsonl"
MODEL = "claude-sonnet-4-6"
PROMPT_VERSION = "talks-v1"
PER_PAGE, MAX_PAGES, WINDOW_H, BATCH = 25, 2, 48, 40
VALID = {"TALKS_HELD", "TALKS_PLANNED", "MEDIATION", "TALKS_ENDED", "AGREEMENT", "OTHER"}
NAMES = {"russia": "Russia", "ukraine": "Ukraine", "israel": "Israel", "hamas": "Hamas", "hezbollah": "Hezbollah", "lebanon": "Lebanon",
         "iran": "Iran", "us": "United States", "saudi": "Saudi Arabia", "houthi": "Houthi", "sudan": "Sudan", "syria": "Syria",
         "thailand": "Thailand", "cambodia": "Cambodia", "pakistan": "Pakistan", "afghanistan": "Afghanistan", "yemen": "Yemen",
         "venezuela": "Venezuela", "india": "India", "armenia": "Armenia", "azerbaijan": "Azerbaijan", "ethiopia": "Ethiopia",
         "eritrea": "Eritrea", "drc": "Congo", "rwanda": "Rwanda", "m23": "M23", "china": "China", "taiwan": "Taiwan"}
ALIASES = {"hamas": ["Hamas", "Gaza"], "houthi": ["Houthi", "Houthis"], "us": ["United States", "Washington"]}   # query aliases (lookup table)
TOPIC = "(ceasefire OR truce OR talks OR negotiations OR negotiators OR mediation OR \"peace deal\")"

PROMPT = """You are labeling news items for a conflict-forecasting system. Parties: {parties}.
For EACH item choose exactly one label, judging only from the item's text (no outside knowledge of later events):
TALKS_HELD: a negotiation meeting or round between these parties (directly, or with a mediator present) actually took place.
TALKS_PLANNED: talks between these parties were announced, scheduled, or agreed to be held, but have not yet taken place.
MEDIATION: a third party carried messages or shuttled between these parties (an indirect channel), with no joint meeting reported.
TALKS_ENDED: talks between these parties were suspended, collapsed, walked out of, or a party refused to attend.
AGREEMENT: an agreement, ceasefire, truce, extension or deal between these parties was announced as agreed or signed.
OTHER: anything else, including calls or demands for talks, proposals not yet discussed, commentary, fighting, or other parties.
Return JSON only, one entry per item: {{"labels": [{{"i": 0, "label": "OTHER"}}, ...]}}

Items:
{items}"""

def load_env():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); os.environ.setdefault(k.replace("export ", "").strip(), v.strip().strip('"').strip("'"))

def query(actors):
    parts = [("(" + " OR ".join(f'"{x}"' for x in ALIASES[a]) + ")") if a in ALIASES else f'"{NAMES[a]}"' for a in actors.split("|") if a in NAMES]
    return (" AND ".join(parts) + " AND " + TOPIC) if parts else None

def actor_sets():
    import ceasefire_bc as BC
    return sorted({c["actors"] for c in BC.agreement_contracts() if c["open"] and c["actors"]})

def akey(title):
    return hashlib.sha1(re.sub(r"\s+", " ", (title or "").strip().lower()).encode()).hexdigest()[:16]

def collect(requests, key, q):
    now = dt.datetime.now(dt.timezone.utc)
    base = {"q": q, "lang": "en", "max": PER_PAGE, "sortby": "publishedAt", "apikey": key,
            "from": (now - dt.timedelta(hours=WINDOW_H)).strftime("%Y-%m-%dT%H:%M:%SZ"), "to": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    arts, total, errors, seen = [], None, None, set()
    for page in range(1, MAX_PAGES + 1):
        b = requests.get("https://gnews.io/api/v4/search", params={**base, "page": page}, timeout=30).json()
        if b.get("errors"): errors = b["errors"]; break
        total = b.get("totalArticles", total)
        batch = [a for a in b.get("articles", []) if a.get("url") not in seen]
        if not batch: break
        for a in batch: seen.add(a.get("url")); arts.append(a)
        if total is not None and len(arts) >= total: break
        time.sleep(1)
    return arts, total, errors, {k: v for k, v in base.items() if k != "apikey"}

def label(requests, actors, arts, fetched_at):
    done = set()
    if LABELS.exists():
        for l in LABELS.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                if r["actors"] == actors and r["prompt_version"] == PROMPT_VERSION: done.add(r["key"])
    todo, seen = [], set()
    for a in arts:
        k = akey(a.get("title"))
        if a.get("title") and k not in done and k not in seen: seen.add(k); todo.append((k, a))
    if not todo: return 0
    import ceasefire_news as CN
    apik = CN.api_key(); n = 0
    parties = " and ".join(NAMES.get(a, a) for a in actors.split("|"))
    with open(LABELS, "a") as f:
        for b in range(0, len(todo), BATCH):
            chunk = todo[b:b + BATCH]
            items = "\n".join(f"[{j}] (published {str(a.get('publishedAt'))[:10]}) {a.get('title')} -- {(a.get('description') or '')[:300]}"
                              for j, (_, a) in enumerate(chunk))
            for attempt in (1, 2):
                try:
                    r = requests.post("https://api.anthropic.com/v1/messages",
                                      headers={"x-api-key": apik, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                                      json={"model": MODEL, "max_tokens": 4000, "temperature": 0,
                                            "messages": [{"role": "user", "content": PROMPT.format(parties=parties, items=items)}]}, timeout=180)
                    r.raise_for_status(); text = "".join(x.get("text", "") for x in r.json()["content"])
                    obj, _ = json.JSONDecoder().raw_decode(text[text.find("{"):])
                    out = {int(x["i"]): x["label"] for x in obj["labels"]}
                    assert set(out) == set(range(len(chunk))) and set(out.values()) <= VALID
                    break
                except Exception as ex:
                    if attempt == 2: raise
                    time.sleep(5)
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            for j, (k, a) in enumerate(chunk):
                f.write(json.dumps({"actors": actors, "key": k, "label": out[j], "model": MODEL, "prompt_version": PROMPT_VERSION,
                                    "labeled_at": now, "known": fetched_at, "published": a.get("publishedAt"), "title": a.get("title"),
                                    "url": a.get("url")}) + "\n")
                n += 1
    return n

def main():
    try:
        load_env(); import requests
        key = os.environ.get("GNEWS_API_KEY")
        if not key: print("[talks] no GNEWS_API_KEY -- skipped"); return
        OUTDIR.mkdir(parents=True, exist_ok=True)
        for actors in actor_sets():
            q = query(actors)
            if not q: print(f"[talks] {actors}: no query (unknown actor name) -- skipped"); continue
            try:
                arts, total, errors, params = collect(requests, key, q)
                stamp = dt.datetime.now(dt.timezone.utc)
                rec = {"fetched_at": stamp.isoformat(), "actors": actors, "params": params, "total_reported": total, "errors": errors,
                       "n": len(arts), "articles": [{"title": a.get("title"), "description": a.get("description"), "url": a.get("url"),
                                                     "source": (a.get("source") or {}).get("name"), "publishedAt": a.get("publishedAt")} for a in arts]}
                (OUTDIR / f"{actors.replace('|', '_')}_{stamp.strftime('%Y%m%dT%H%MZ')}.json").write_text(json.dumps(rec))
                nl = label(requests, actors, rec["articles"], rec["fetched_at"])
                print(f"[talks] {actors}: {len(arts)} of {total} articles, {nl} newly labeled" + (f" errors={errors}" if errors else ""))
            except Exception as ex:
                print(f"[talks] {actors}: failed ({ex!r}) -- continuing")
    except Exception as ex:
        print(f"[talks] failed ({ex!r}) -- non-fatal")

def _tests():
    assert query("russia|ukraine") == '"Russia" AND "Ukraine" AND ' + TOPIC
    assert query("sudan") == '"Sudan" AND ' + TOPIC
    assert query("hamas|israel") == '("Hamas" OR "Gaza") AND "Israel" AND ' + TOPIC
    assert query("zzz") is None
    assert akey("A  b") == akey("a b")
    print("talks_collector tests: OK")

if __name__ == "__main__":
    import importlib.util as _iu, pathlib as _pl   # token log, logs/api_usage_<date>.jsonl (report only)
    _sp = _iu.spec_from_file_location("pq_api_usage", _pl.Path(__file__).resolve().parents[1] / "pipeline" / "api_usage.py")
    _um = _iu.module_from_spec(_sp); _sp.loader.exec_module(_um); _um.enable()
    if "--test" in sys.argv: _tests()
    else: main()

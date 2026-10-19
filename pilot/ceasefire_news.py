"""
Ceasefire-announcement evidence for the fighting-state filter (during-war spec v0.4, v2b).
Theory: a ceasefire is an accepted offer (the mu event). Under a commitment problem (Powell 2006) a deal
that is not self-enforcing is announced without fighting stopping, so an announcement is weak evidence:
it multiplies the odds of fighting by 1/announcement_lr (theater default 2.0; 1 and 4 logged).
Only NEW_AGREEMENT carries weight. EXTENSION and OTHER are recorded, never used.
Availability = when our system first held the article (file fetch time; production files: end of file date,
conservative), never earlier. Labels are cached in pilot/ceasefire_labels.jsonl: one call per article, ever.

  python pilot/ceasefire_news.py --classify   label every cached article not yet labeled, then print the report
  python pilot/ceasefire_news.py --report     print counts, flagged articles and events only (no API calls)
"""
import json, os, re, glob, hashlib, time, sys, datetime as dt
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "pilot" / "during_war_config.json"
LABELS = ROOT / "pilot" / "ceasefire_labels.jsonl"
MODEL = "claude-sonnet-4-6"          # same model as pipeline/contract_scope.py
BATCH = 40
EVENT_WINDOW_DAYS = 3
VALID = {"NEW_AGREEMENT", "EXTENSION", "OTHER"}
PROMPT_VERSION = "v2"   # v1 flagged an implementation step (Jul 22 pilot-zone handover) as a ceasefire

PROMPT = """You are labeling news items for a conflict-forecasting system.
Pair: {initiator}, and the armed actors in {territory}: {combatants}.

For EACH item choose exactly one label:
NEW_AGREEMENT: the item reports that a NEW ceasefire, truce, or halt to hostilities between {initiator} and any of those actors was agreed, announced as agreed, or took effect within roughly the 48 hours before the item was published. The agreement itself must be a halt to the fighting.
EXTENSION: the item reports that an EXISTING ceasefire or truce between them was extended or renewed.
OTHER: anything else. This includes steps in implementing an existing agreement (troop withdrawals, handovers of territory or positions, deployments, security or disarmament arrangements); strikes or violations "despite the ceasefire"; talks, negotiations, proposals, demands or calls for a ceasefire; ceasefires involving other parties (for example Gaza or Iran); and analysis or commentary.

Judge only from the item's text. Do not use outside knowledge of later events.
Return JSON only, one entry per item: {{"labels": [{{"i": 0, "label": "OTHER"}}, ...]}}

Items:
{items}"""

def T(s):
    x = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)

def key(title):
    return hashlib.sha1(re.sub(r"\s+", " ", (title or "").strip().lower()).encode()).hexdigest()[:16]

def fetch_time(path, d):
    if isinstance(d, dict) and d.get("fetched_at"):
        return T(d["fetched_at"])
    m = re.search(r"_(\d{8})\.json$", path)
    if m:   # production cache: day granularity only -> end of that UTC day (conservative)
        return dt.datetime.strptime(m.group(1), "%Y%m%d").replace(hour=23, minute=59, tzinfo=dt.timezone.utc)
    return None

def load_articles(pair):
    arts = {}
    for g in pair["news_globs"]:
        for f in sorted(glob.glob(str(ROOT / g))):
            try:
                d = json.load(open(f))
            except Exception as ex:
                print(f"  [news] unreadable {f}: {ex!r}"); continue
            ft = fetch_time(f, d)
            if ft is None:
                print(f"  [news] no fetch time for {f}, skipped"); continue
            for a in (d.get("articles", []) if isinstance(d, dict) else d):
                if not isinstance(a, dict) or not a.get("title"):
                    continue
                pub = T(a["publishedAt"]) if a.get("publishedAt") else ft
                known = max(ft, pub)
                k = key(a["title"])
                if k not in arts or known < arts[k]["known"]:
                    arts[k] = {"key": k, "title": a["title"], "description": a.get("description") or "",
                               "published": pub, "known": known}
    return arts

def load_labels(pair_name):
    out = {}
    if LABELS.exists():
        for l in LABELS.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                if r["pair"] == pair_name and r.get("prompt_version") == PROMPT_VERSION:
                    out[r["key"]] = r
    return out

def api_key():
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r"^\s*(?:export\s+)?ANTHROPIC_API_KEY\s*=\s*(.+?)\s*$", line)
            if m:
                return m.group(1).strip('"').strip("'")
    raise SystemExit("ANTHROPIC_API_KEY not found in environment or .env")

def call(prompt, k):
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": k, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": MODEL, "max_tokens": 4000, "temperature": 0,
                            "messages": [{"role": "user", "content": prompt}]}, timeout=180)
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"])
    obj, _ = json.JSONDecoder().raw_decode(text[text.find("{"):])
    return obj["labels"]

def classify(pair_name, pair):
    done = load_labels(pair_name)
    arts = load_articles(pair)
    todo = sorted((a for a in arts.values() if a["key"] not in done), key=lambda a: a["known"])
    print(f"[ceasefire] {pair_name}: {len(arts)} unique articles, {len(todo)} to label")
    if not todo:
        return
    k = api_key(); nb = -(-len(todo) // BATCH)
    with open(LABELS, "a") as f:
        for b in range(nb):
            chunk = todo[b * BATCH:(b + 1) * BATCH]
            items = "\n".join(f"[{j}] (published {a['published'].date()}) {a['title']} -- {a['description'][:300]}"
                              for j, a in enumerate(chunk))
            prompt = PROMPT.format(initiator=pair["initiator"], territory=pair["territory"],
                                   combatants=", ".join(pair["combatants"]), items=items)
            for attempt in (1, 2):
                try:
                    out = {int(x["i"]): x["label"] for x in call(prompt, k)}
                    assert set(out) == set(range(len(chunk))), f"got {len(out)} labels for {len(chunk)} items"
                    assert set(out.values()) <= VALID, f"invalid labels {set(out.values()) - VALID}"
                    break
                except Exception as ex:
                    if attempt == 2:
                        raise
                    print(f"  retry batch {b + 1}: {ex!r}"); time.sleep(5)
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            for j, a in enumerate(chunk):
                f.write(json.dumps({"pair": pair_name, "key": a["key"], "label": out[j], "model": MODEL, "prompt_version": PROMPT_VERSION,
                                    "labeled_at": now, "known": a["known"].isoformat(), "title": a["title"]}) + "\n")
            f.flush()
            print(f"  batch {b + 1}/{nb} done")

def events(pair_name, pair, as_of=None):
    lab = load_labels(pair_name)
    flagged = sorted((a for a in load_articles(pair).values()
                      if lab.get(a["key"], {}).get("label") == "NEW_AGREEMENT"
                      and (as_of is None or a["known"] < as_of)), key=lambda a: a["known"])
    ev = []
    for a in flagged:
        if ev and (a["known"] - ev[-1]["first"]) < dt.timedelta(days=EVENT_WINDOW_DAYS):
            ev[-1]["articles"].append(a)
        else:
            ev.append({"first": a["known"], "articles": [a]})
    return ev

def report(pair_name, pair):
    lab = load_labels(pair_name); arts = load_articles(pair)
    counts = {}
    for a in arts.values():
        counts[lab.get(a["key"], {}).get("label", "UNLABELED")] = counts.get(lab.get(a["key"], {}).get("label", "UNLABELED"), 0) + 1
    print(f"[ceasefire] {pair_name}: {counts}")
    for want, cap in (("NEW_AGREEMENT", 200), ("EXTENSION", 30)):
        rows = sorted((a for a in arts.values() if lab.get(a["key"], {}).get("label") == want), key=lambda a: a["known"])
        print(f"--- {want} ({len(rows)}{', first ' + str(cap) + ' shown' if len(rows) > cap else ''})")
        for a in rows[:cap]:
            print(f"  known {a['known']:%Y-%m-%d %H:%M}Z | pub {a['published']:%Y-%m-%d} | {a['title'][:140]}")
    ev = events(pair_name, pair)
    print(f"--- events (NEW_AGREEMENT, {EVENT_WINDOW_DAYS}-day dedup): {len(ev)}")
    for e in ev:
        print(f"  {e['first']:%Y-%m-%d} ({len(e['articles'])} articles): {e['articles'][0]['title'][:120]}")

TESTS = [  # written by hand, modeled on 2026 events; all must pass before labeling
    ("Israel and Hezbollah agree to halt hostilities, truce to start at 4pm", "US, Qatari and Iranian mediators brokered the ceasefire, officials said on Friday.", "NEW_AGREEMENT"),
    ("Ceasefire between Israel and Lebanon takes effect after weeks of war", "The truce began at midnight; both governments confirmed they had accepted the terms.", "NEW_AGREEMENT"),
    ("Israel and Lebanon agree to renew their ceasefire for another 45 days", "The extension keeps the current truce in place while talks continue.", "EXTENSION"),
    ("Israeli strikes kill four in south Lebanon despite ceasefire", "The health ministry said the dead included two women.", "OTHER"),
    ("Lebanon's prime minister visits border village as deal with Israel begins", "Implementation began of a US-brokered agreement under which Israeli forces hand over villages to the Lebanese army after clearing Hezbollah positions.", "OTHER"),
    ("Lebanon urges Washington to press Israel for a halt to attacks", "Beirut asked the US envoy to secure an end to daily strikes.", "OTHER"),
    ("Gaza ceasefire takes effect as first hostages are released", "Israel and Hamas began a truce on Sunday morning.", "OTHER"),
    ("Israel and Iran agree to a ceasefire after twelve days of strikes", "The truce between the two countries took effect overnight.", "OTHER"),
]

def run_tests(pair):
    items = "\n".join(f"[{j}] (published 2026-01-01) {t} -- {d}" for j, (t, d, _) in enumerate(TESTS))
    prompt = PROMPT.format(initiator=pair["initiator"], territory=pair["territory"],
                           combatants=", ".join(pair["combatants"]), items=items)
    out = {int(x["i"]): x["label"] for x in call(prompt, api_key())}
    bad = 0
    for j, (t, d, want) in enumerate(TESTS):
        got = out.get(j); ok = got == want; bad += (not ok)
        print(f"  {'ok ' if ok else 'BAD'} want {want:13} got {got}: {t}")
    print(f"[ceasefire tests, prompt {PROMPT_VERSION}] {len(TESTS) - bad}/{len(TESTS)} correct")
    return bad == 0

if __name__ == "__main__":
    pairs = json.loads(CONFIG.read_text())["pairs"]
    if "--test" in sys.argv:
        sys.exit(0 if run_tests(pairs["Israel->Lebanon"]) else 1)
    for name, pair in pairs.items():
        if "--classify" in sys.argv:
            classify(name, pair)
        report(name, pair)

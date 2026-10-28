"""
Static rules text (Polymarket 'description') per market, from the Gamma API, plus a fingerprint of the
strike DEFINITION paragraph ('A qualifying military action refers to ...' up to the attribution/resolution clause).
Why (Oct 20): contracts may share evidence on one timeline only if they define a qualifying strike identically
(ChatGPT review). Static listing metadata only; fetches ids not yet stored; never changes a stored record.
  python -m pipeline.market_rules            fetch missing (every id in market_meta.json + open template contracts in the feed)
  python -m pipeline.market_rules --report   definition groups per initiator->target pair, daily vs by-date
"""
import json, re, sys, time, hashlib, urllib.request, datetime as dt
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RULES, META, FEED = ROOT / "market_rules.json", ROOT / "market_meta.json", ROOT / "classified_feed.json"
_M = "January|February|March|April|May|June|July|August|September|October|November|December"
TPL = re.compile(r"^(?:Will there be )?(.+?) military action (?:against|on) (.+?) (on|by) (?:" + _M + r") \d{1,2}(?:, \d{4})?\?\s*$", re.I)
ALIAS = {"saudiarabian": "saudiarabia"}

def norm(x):
    k = re.sub(r"[^a-z]", "", (x or "").lower()); return ALIAS.get(k, k)

def parse(q):
    m = TPL.match(q or "")
    return (f"{norm(m.group(1))}->{norm(m.group(2))}", "daily" if m.group(3).lower() == "on" else "bydate") if m else (None, None)

def definition(desc):
    d = re.sub(r"\s+", " ", desc or "")
    i = d.lower().find("qualifying military action refers to")
    if i < 0:
        return None
    j = min([k for k in (d.lower().find("the occurrence, attribution", i), d.lower().find("resolution source", i)) if k > 0] or [len(d)])
    return d[i:j].strip()

def fp(desc):
    x = definition(desc)
    return hashlib.sha1(x.lower().encode()).hexdigest()[:10] if x else None

def _target_tpl(q):
    """Oct 28: also fetch rules for every feed contract the unified engine's own template matches ("Will Iran target Iraq by
    ..."), the day it enters the feed. Before, those got rules only via market_meta.json, which runs after the translator,
    so a new "target" listing was engine-priced on its first day (Oct 28: the Iran->Iraq and Arab-country ladders)."""
    try:
        sys.path.insert(0, str(ROOT.parent / "pilot")); import unified_data as _UD
        return bool(_UD.TPL.match(q or ""))
    except Exception as ex:
        print(f"  [rules] unified template unavailable ({ex!r}); military-action template only"); return False

def fetch():
    rules = json.loads(RULES.read_text()) if RULES.exists() else {}
    ids = set(json.loads(META.read_text())) if META.exists() else set()
    feed = json.loads(FEED.read_text()); feed = feed if isinstance(feed, list) else feed.get("markets", feed.get("data", []))
    ids |= {str(m["market_id"]) for m in feed if parse(m.get("question"))[0] or _target_tpl(m.get("question"))}
    todo = sorted(i for i in ids if i not in rules or "createdAt" not in rules[i]); bad = 0
    for i, mid in enumerate(todo, 1):
        try:
            req = urllib.request.Request("https://gamma-api.polymarket.com/markets/" + mid, headers={"User-Agent": "predictioneering/market_rules"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read()); d = d[0] if isinstance(d, list) else d
            if mid in rules:   # add missing listing dates only; never change stored fields
                rules[mid].setdefault("createdAt", d.get("createdAt")); rules[mid].setdefault("endDate", d.get("endDate"))
            else:
                rules[mid] = {"question": d.get("question"), "description": d.get("description"), "definition_fp": fp(d.get("description")),
                              "createdAt": d.get("createdAt"), "endDate": d.get("endDate"), "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        except Exception as ex:
            bad += 1; print(f"  [rules] {mid}: {ex!r}")
        if i % 50 == 0:
            RULES.write_text(json.dumps(rules, indent=1, sort_keys=True) + "\n"); print(f"  [rules] {i}/{len(todo)}", flush=True)
        time.sleep(0.15)
    RULES.write_text(json.dumps(rules, indent=1, sort_keys=True) + "\n")
    print(f"[rules] stored {len(rules)} | fetched {len(todo) - bad} | failed {bad}")

def report():
    rules = json.loads(RULES.read_text()); g = defaultdict(lambda: defaultdict(list))
    for mid, r in rules.items():
        pr, kind = parse(r.get("question"))
        if pr: g[pr][(kind, r.get("definition_fp"))].append(r.get("question"))
    for pr in sorted(g, key=lambda p: -sum(len(v) for v in g[p].values())):
        print(f"--- {pr}")
        for (kind, f), qs in sorted(g[pr].items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
            print(f"    {kind:6} definition {f}: {len(qs):3} contracts  e.g. {qs[0][:70]}")
    seen = set()
    for pr in g:
        for (kind, f) in g[pr]:
            if f and f not in seen:
                seen.add(f)
                if pr in ("israel->syria", "saudiarabia->yemen", "israel->lebanon"):
                    ex = next(r for r in rules.values() if r.get("definition_fp") == f)
                    print(f"\n[{f}] {pr} {kind}: {definition(ex['description'])[:400]}")

if __name__ == "__main__":
    report() if "--report" in sys.argv else fetch()

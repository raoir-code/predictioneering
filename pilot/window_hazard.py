"""
Window-hazard pricer for by-date military-action contracts (Oct 19).
Contract (rules text): YES iff >= 1 qualifying action by A on B 'between market creation and the specified date'.
Each listing is interval-censored evidence on the pair's daily qualifying-strike rate lambda (same object as the
during-war strike rate; no new theory). Evidence is built on ONE day timeline per pair so overlapping listings
never double-count:
  quiet days   every day of a NO-resolved window; elapsed days of a still-open listing older than LAG_DAYS
               (rules: conflicting sources keep a market open up to 3 full calendar days)
  YES windows  a YES-resolved window minus quiet days must hold >= 1 strike day; nested windows keep the inner one
Likelihood: exp(-lambda * #quiet) * prod_YES (1 - exp(-lambda * len)). Prior: Jeffreys (lambda^-1/2), nothing tuned.
Price: P(>= 1 strike in the remaining days) = 1 - E_post[exp(-lambda * R)]. No evidence -> None (engine keeps its price).
Walk-forward: a forecast at time t uses only resolutions known before t and elapsed days up to t - LAG_DAYS.

  python pilot/window_hazard.py --replay   walk-forward replay on resolved listings vs production and market
  python pilot/window_hazard.py --dry      prices for open listings, print only
"""
import json, math, re, sys, datetime as dt
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
META, FEED, BRIER = ROOT / "pipeline" / "market_meta.json", ROOT / "pipeline" / "classified_feed.json", ROOT / "predictions" / "brier_log.jsonl"
VERSION, LAG_DAYS, ET = "window-hazard-v1", 3, ZoneInfo("America/New_York")
_M = "January|February|March|April|May|June|July|August|September|October|November|December"
BYD = re.compile(r"^(?:Will there be )?(.+?) military action (?:against|on) (.+?) by (?:" + _M + r") \d{1,2}(?:, \d{4})?\?\s*$", re.I)
ALIAS = {"saudiarabian": "saudiarabia"}
GRID = [math.exp(math.log(1e-4) + i * (math.log(3.0) - math.log(1e-4)) / 399) for i in range(400)]

def T(s):
    x = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)

def norm(x):
    k = re.sub(r"[^a-z]", "", (x or "").lower()); return ALIAS.get(k, k)

def pair_of(text):
    m = BYD.match(text or ""); return f"{norm(m.group(1))}->{norm(m.group(2))}" if m else None

def load_listings():
    meta = json.loads(META.read_text())
    res = defaultdict(list)
    for l in BRIER.read_text().splitlines():
        if l.strip():
            r = json.loads(l); res[str(r["market_id"])].append(r)
    feed = json.loads(FEED.read_text()); feed = feed if isinstance(feed, list) else feed.get("markets", feed.get("data", []))
    out, seen = [], set()
    def add(mid, text, extra):
        pr, md = pair_of(text), meta.get(mid)
        if not pr or not md or not md.get("createdAt") or not md.get("endDate") or mid in seen:
            return
        seen.add(mid)
        out.append({"market_id": mid, "pair": pr, "text": text,
                    "start": T(md["createdAt"]).astimezone(ET).date(), "end": T(md["endDate"]).astimezone(ET).date(), **extra})
    for mid, rs in res.items():
        r = rs[-1]; ts = [T(x["resolved_at"]) for x in rs if x.get("resolved_at")]
        fp = [T(x["first_prediction_ts"]) for x in rs if x.get("first_prediction_ts")]
        add(mid, r.get("market_label") or "", {"outcome": int(r["outcome"]), "known": min(ts) if ts else None,
            "first_ts": min(fp) if fp else None, "prod_first": r.get("first_p"),
            "mkt_first": r.get("market_p_true_first") if r.get("market_p_true_first") is not None else r.get("market_p_at_first")})
    for m in feed:
        mid = str(m.get("market_id"))
        if mid not in res and not m.get("resolved"):
            add(mid, m.get("question") or "", {"outcome": None, "known": None, "first_ts": None,
                "prod_now": m.get("conditional_p"), "mkt_now": m.get("market_price")})
    return out

def evidence(listings, pair, as_of):
    day = as_of.astimezone(ET).date(); quiet, yes = set(), []
    for x in listings:
        if x["pair"] != pair or x["start"] >= day:
            continue
        span = lambda a, b: {a + dt.timedelta(d) for d in range((b - a).days + 1)}
        if x["known"] is not None and x["known"] < as_of:
            (quiet.update(span(x["start"], x["end"])) if x["outcome"] == 0 else yes.append(span(x["start"], x["end"])))
        else:
            last = min(x["end"], day - dt.timedelta(LAG_DAYS))
            if last >= x["start"]:
                quiet |= span(x["start"], last)
    yes = [w - quiet for w in yes]
    yes = [w for w in yes if not any(o < w for o in yes)]
    uniq = []
    for w in yes:
        if w and w not in uniq:
            uniq.append(w)
    return len(quiet), [len(w) for w in uniq], any(not w for w in yes)

def price(nq, ys, R):
    if nq == 0 and not ys:
        return None
    lw = []
    for lam in GRID:
        ll = -lam * nq + sum(math.log(max(1e-300, 1 - math.exp(-lam * L))) for L in ys) + 0.5 * math.log(lam)
        lw.append(ll)
    mx = max(lw); w = [math.exp(v - mx) for v in lw]; Z = sum(w)
    return round(1 - sum(wi * math.exp(-lam * max(0, R)) for wi, lam in zip(w, GRID)) / Z, 4)

def replay():
    L = load_listings(); rows = []
    for x in L:
        if x["outcome"] is None or x["first_ts"] is None:
            continue
        nq, ys, contra = evidence(L, x["pair"], x["first_ts"])
        R = (x["end"] - x["first_ts"].astimezone(ET).date()).days + 1
        p = price(nq, ys, R)
        rows.append((x, nq, ys, contra, R, p))
    print(f"{'pair':28}{'window':24}{'y':>2}{'quiet':>6}{'yesW':>10}{'R':>4}{'wh':>7}{'prod':>7}{'mkt':>7}")
    for x, nq, ys, contra, R, p in sorted(rows, key=lambda r: (r[0]["pair"], r[0]["start"])):
        f = lambda v: f"{v:7.3f}" if isinstance(v, (int, float)) else f"{'-':>7}"
        print(f"{x['pair'][:27]:28}{str(x['start'])+'->'+str(x['end']):24}{x['outcome']:>2}{nq:>6}{str(ys)[:9]:>10}{R:>4}{f(p)}{f(x['prod_first'])}{f(x['mkt_first'])}{'  CONTRADICTION' if contra else ''}")
    sc = [(x, p) for x, nq, ys, c, R, p in rows if p is not None and x["prod_first"] is not None and x["mkt_first"] is not None]
    B = lambda k: sum((k(x, p) - x["outcome"]) ** 2 for x, p in sc) / len(sc)
    print(f"scored (all three present): n={len(sc)} of {len(rows)} | Brier window-hazard {B(lambda x, p: p):.4f} | production {B(lambda x, p: x['prod_first']):.4f} | market {B(lambda x, p: x['mkt_first']):.4f}")

def dry():
    L = load_listings(); now = dt.datetime.now(dt.timezone.utc)
    for x in sorted((x for x in L if x["outcome"] is None), key=lambda x: (x["pair"], x["end"])):
        nq, ys, contra = evidence(L, x["pair"], now)
        R = (x["end"] - now.astimezone(ET).date()).days + 1
        if R <= 0:
            continue
        p = price(nq, ys, R)
        print(f"  {x['pair'][:26]:27}| {x['text'][:58]:58} | wh {p if p is not None else '-'} | prod {x.get('prod_now')} | mkt {x.get('mkt_now')} | quiet {nq} yes {ys}")

if __name__ == "__main__":
    replay() if "--replay" in sys.argv else dry()

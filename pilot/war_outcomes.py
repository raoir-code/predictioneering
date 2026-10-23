"""
Family F, war outcomes ("war-outcome-v0") — docs/war_outcomes_prereg.md (pre-registered Oct 22, 2026).

One-shot events with a ladder of deadlines: CAPTURE (an armed actor captures / recaptures / retakes / takes control of a place),
ENTRY (armed forces enter a place), WITHDRAWAL (a state withdraws forces from a place). Event = series (question minus deadline).
Constant hazard per series. Prior: pooled over OTHER series of the same type closed before the forecast (events = series that
resolved YES, exposure = union of resolved windows), log-normal by the C1b moment formula (mean-matched); < 3 series -> all types;
still < 3 -> median 1/yr, log-sd 2.0. Own evidence: the series' earlier resolved deadlines (exact likelihood, as C1).

  python pilot/war_outcomes.py --refresh     fetch/refresh contracts (Gamma) -> pilot/war_outcome_markets.json
  python pilot/war_outcomes.py --replay      walk-forward replay vs market (REPORT ONLY) -> pilot/war_outcome_replay.json
  python pilot/war_outcomes.py --dry         today's prices vs market
  python pilot/war_outcomes.py --test        offline tests
"""
import json, re, sys, math, datetime as dt, urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot"))
import unified_data as UD, ceasefire_holds as CH, ceasefire_bc as BC

STORE = ROOT / "pilot" / "war_outcome_markets.json"
REPLAY = ROOT / "pilot" / "war_outcome_replay.json"
UTC = dt.timezone.utc
COMPONENT = "withdrawal-v0"
SEARCH = ["Russia capture", "capture by", "recapture", "take control", "troops enter", "forces enter", "enter by", "Houthis enter",
          "withdraw from", "withdraws from", "forces withdraw"]
FALLBACK = (0.0, 2.0)          # log-median 1/yr, log-sd 2.0 (pre-registered)
LAM = BC.LAMX

_EXCL = re.compile(r"\bNATO\b|\bNPT\b|treaty|fall to|\bprice\b|crude|Pahlavi|\bleader\b|election|\bEU\b|agreement|accord|"
                   r"footage|video|released|\bagrees? to\b", re.I)          # Oct 22, before replay: person/footage and pledge contracts
_CAP = re.compile(r"\b(capture|captures|recapture|retake|retakes|take control of|takes control of)\b", re.I)
_ENT = re.compile(r"\b(forces|troops|army|military|soldiers|houthis?|marines)\b.{0,40}\benters?\b", re.I)
_WDR = re.compile(r"\bwithdraws?\b.{0,60}\bfrom\b", re.I)
_DEADLINE = re.compile(r"\s+(?:by|before|in|on)\s*(?:(?:the )?end of\s+)?(?:" + UD._M + r"|\d{4}|eoy|\.\.\.|…).*$", re.I)

def classify_wo(q, desc):
    t, d = q or "", re.sub(r"\s+", " ", desc or "")
    if not t or _EXCL.search(t): return None
    dl = d.lower()
    # Oct 23 scope amendment (docs/war_outcomes_prereg.md): state decisions only. Captures of places and entries into
    # sub-national places are battlefield progress (operational), not bargaining: out of scope.
    # Entering another country is onset: left to the engine / classifier (never overridden here).
    if _CAP.search(t) or _ENT.search(t): return None
    if _WDR.search(t) and re.search(r"ground forces|troops|forces", dl): typ = "WITHDRAWAL"
    else: return None
    return {"family": "WAR_OUTCOME", "type": typ, "series": series_key(t)}

def series_key(q):
    s = re.sub(r"^will\s+", "", (q or "").strip().rstrip("?").strip(), flags=re.I)
    s = _DEADLINE.sub("", s)
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def store():
    return json.loads(STORE.read_text()) if STORE.exists() else {}

def contracts(S=None):
    out = []
    for mid, r in (S or store()).items():
        info = classify_wo(r.get("question"), r.get("description"))
        if not info: continue
        created = CH._ts(r.get("createdAt"))
        if not created: continue
        known = CH._ts(r.get("closedTime")) if r.get("closed") else None
        d = BC.due_date(r.get("question"), r.get("description"), created, r.get("endDate")) or (known.date() if known else None)
        if not d: continue
        tok = json.loads(r.get("clobTokenIds") or "[]")
        out.append({"id": str(mid), "series": info["series"], "type": info["type"], "start": created.date(), "created": created, "end": d,
                    "y": CH.holds_outcome(r), "known": known, "open": not r.get("closed"), "q": r.get("question"), "tok": tok[0] if tok else None})
    return out

def _win(x, as_of):
    if x["y"] is None or not (x["known"] and x["known"] < as_of): return None
    return (x["start"], min(x["end"], x["known"].date()) if x["y"] == 1 else x["end"], x["y"])

def prior(c, allc, as_of):
    for label, types in ((c["type"], {c["type"]}), ("all types", {"WITHDRAWAL"})):
        per = defaultdict(list)
        for x in allc:
            if x["series"] == c["series"] or x["type"] not in types: continue
            w = _win(x, as_of)
            if w and w[1] >= w[0]: per[x["series"]].append(w)
        g = []
        for s, ws in per.items():
            expo = len(set().union(*[BC._days(a, b) for a, b, _ in ws])) / 365.25
            if expo > 0: g.append((1 if any(y == 1 for _, _, y in ws) else 0, expo))
        if len(g) < 3: continue
        E, X = sum(e for e, _ in g), sum(x for _, x in g)
        if E == 0: continue
        m = E / X; r = [e / x for e, x in g]
        var = sum(x * (ri - m) ** 2 for (e, x), ri in zip(g, r)) / X
        V = max(0.0, var - m / (X / len(g)))
        sg = max(0.05, math.sqrt(math.log(1 + V / m ** 2)))
        return math.log(m) - sg ** 2 / 2, sg, f"listed {label} pool ({len(g)} other series): mean {m:.2f}/yr, log-sd {sg:.2f}"
    return FALLBACK[0], FALLBACK[1], "fallback prior: median 1/yr, log-sd 2.0"

def price(c, allc, as_of):
    own = [_win(x, as_of) for x in allc if x["series"] == c["series"] and x["id"] != c["id"]]
    own = [w for w in own if w and w[1] >= w[0]]
    if any(y == 1 for _, _, y in own): return 0.99, {"note": "event already resolved YES in an earlier deadline of this series"}
    days = (c["end"] - as_of.date()).days + 1
    if days <= 0: return None, None
    lmu, lsd, why = prior(c, allc, as_of)
    ll, nno, _ = BC.loglik_exact(own, LAM)
    lp = -0.5 * ((np.log(LAM) - lmu) / lsd) ** 2
    w = np.exp(ll + lp - (ll + lp).max()); w /= w.sum()
    p = float(1 - np.dot(w, np.exp(-LAM * days / 365.25)))
    return round(p, 4), {"prior": why, "own_no_days": nno}

def price_all(PP, now):
    allc = contracts(); n = 0
    for c in allc:
        if not c["open"]: continue
        p, d = price(c, allc, now)
        if p is None: continue
        PP[c["id"]] = {"p": p, "group": f"war-outcome:{c['type']}:{c['series']}", "source": json.dumps(d), "q": None, "pi": None, "component": COMPONENT}; n += 1
    print(f"[war-outcome] priced {n} contracts")

def tag(m):
    """Translator hook: returns the family name if this feed market is in family F."""
    return "WAR_OUTCOME" if classify_wo(m.get("question"), m.get("description")) else None

def refresh():
    S = store(); found = {}
    for q in SEARCH:
        try: d = CH._get(f"{CH.GAMMA}/public-search?q={urllib.parse.quote(q)}&events_status=all&limit_per_type=50&keep_closed_markets=1")
        except Exception as ex: print(f"  [war-outcome] search {q!r}: {ex!r}"); continue
        for e in d.get("events") or []:
            for m in e.get("markets") or []:
                if classify_wo(m.get("question"), m.get("description")): found[str(m["id"])] = m
    feed = json.loads((ROOT / "pipeline" / "classified_feed.json").read_text()); feed = feed if isinstance(feed, list) else feed.get("markets", [])
    for m in feed:
        mid = str(m.get("market_id"))
        if classify_wo(m.get("question"), m.get("description")) and mid not in found and mid not in S:
            try: found[mid] = CH._get(f"{CH.GAMMA}/markets/{mid}")
            except Exception as ex: print(f"  [war-outcome] {mid}: {ex!r}")
    for mid, r in list(S.items()):
        if not r.get("closed") and mid not in found:
            try: found[mid] = CH._get(f"{CH.GAMMA}/markets/{mid}")
            except Exception as ex: print(f"  [war-outcome] {mid}: {ex!r}")
    now = dt.datetime.now(UTC).isoformat()
    for mid, m in found.items(): S[mid] = {k: m.get(k) for k in CH.KEEP} | {"fetched_at": now}
    STORE.write_text(json.dumps(S, indent=1, sort_keys=True) + "\n")
    c = Counter((classify_wo(r["question"], r["description"]) or {}).get("type") for r in S.values())
    print(f"[war-outcome] store {len(S)} contracts {dict(c)} | open {sum(1 for r in S.values() if not r.get('closed'))}")

def replay():
    allc = contracts(); cache = json.loads(CH.PRICES.read_text()) if CH.PRICES.exists() else {}
    rows, skip = [], Counter()
    for c in allc:
        if c["y"] is None: continue
        as_of = c["created"] + dt.timedelta(hours=24)
        if not c["known"] or c["known"] <= as_of: skip["resolved before first run"] += 1; continue
        if c["end"] < as_of.date(): skip["past date"] += 1; continue
        p, d = price(c, allc, as_of)
        if p is None: skip["unpriced"] += 1; continue
        mk = CH.market_price(c["tok"], as_of, cache) if c["tok"] else None
        if mk is None: skip["no market price"] += 1; continue
        rows.append({"id": c["id"], "type": c["type"], "series": c["series"], "y": c["y"], "u": p, "m": mk, "q": c["q"]})
    CH.PRICES.write_text(json.dumps(cache) + "\n")
    cl = lambda p: min(0.999, max(0.001, p))
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs)
    LL = lambda xs, k: -sum(math.log(cl(x[k]) if x["y"] else 1 - cl(x[k])) for x in xs) / len(xs)
    res = {}
    print(f"\n=== WAR OUTCOMES REPLAY (report only): n={len(rows)} | skipped {dict(skip)}")
    if rows:
        print(f"  overall  model Brier {B(rows, 'u'):.4f} logloss {LL(rows, 'u'):.3f} | market Brier {B(rows, 'm'):.4f} logloss {LL(rows, 'm'):.3f}")
        for y in (1, 0):
            s = [x for x in rows if x["y"] == y]
            if s: print(f"  {'YES' if y else 'NO '} n={len(s):3} model {B(s, 'u'):.4f} market {B(s, 'm'):.4f}")
        for t in sorted({x["type"] for x in rows}):
            s = [x for x in rows if x["type"] == t]
            print(f"  {t:11} n={len(s):3} YES {sum(x['y'] for x in s):3} model {B(s, 'u'):.4f} market {B(s, 'm'):.4f}")
            res[t] = {"n": len(s), "yes": sum(x["y"] for x in s), "brier_model": round(B(s, "u"), 4), "brier_market": round(B(s, "m"), 4)}
        ser = sorted({x["series"] for x in rows}); rng = np.random.default_rng(20261022); diffs = []
        for _ in range(2000):
            pick = rng.choice(ser, len(ser)); xs = [x for s in pick for x in rows if x["series"] == s]
            diffs.append(B(xs, "u") - B(xs, "m"))
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        print(f"  cluster bootstrap by series (2,000): Brier(model) - Brier(market) = {B(rows, 'u') - B(rows, 'm'):+.4f}  95% [{lo:+.4f}, {hi:+.4f}]")
        res["overall"] = {"n": len(rows), "brier_model": round(B(rows, "u"), 4), "brier_market": round(B(rows, "m"), 4),
                          "logloss_model": round(LL(rows, "u"), 4), "logloss_market": round(LL(rows, "m"), 4), "bootstrap_model_minus_market": [round(float(lo), 4), round(float(hi), 4)]}
    REPLAY.write_text(json.dumps({"results": res, "skipped": dict(skip), "rows": rows, "computed_at": dt.datetime.now(UTC).isoformat()}, indent=1) + "\n")

def dry():
    PP = {}; price_all(PP, dt.datetime.now(UTC)); S = store()
    for k, v in sorted(PP.items(), key=lambda kv: str((S.get(kv[0]) or {}).get("question"))):
        r = S.get(k, {})
        try: mk = round(float(json.loads(r.get("outcomePrices") or "[]")[0]), 3)
        except Exception: mk = None
        print(f"  ours {v['p']:.3f} mkt {mk} | {(r.get('question') or k)[:80]}")

def _tests():
    cap = "This market will resolve to Yes if, according to the ISW map, Russia captures Sloviansk; territory shaded as Russian control."
    ent = "This market will resolve to Yes if Saudi ground forces enter Marib Governorate."
    wdr = "This market will resolve to Yes if Israel announces it has withdrawn all ground forces from Lebanon."
    assert classify_wo("Will Russia capture Sloviansk by December 31, 2026?", cap) is None                 # operational: out
    assert classify_wo("Saudi troops enter Marib Governorate by December 31?", ent) is None                 # sub-national: out
    assert classify_wo("Israeli forces enter Beirut by November 30?", ent) is None
    assert classify_wo("US forces enter Iran by December 31?", ent) is None                                # onset: engine
    assert classify_wo("Turkish troops enter Yemen by December 31, 2026?", ent) is None
    assert classify_wo("Israel withdraws from Lebanon by December 31, 2026?", wdr)["type"] == "WITHDRAWAL"
    assert classify_wo("Will US withdraw from NATO before 2027?", "formally initiates a withdrawal from NATO") is None
    assert classify_wo("Will Iran withdraw from the NPT before 2027?", "withdraw from the Nuclear Non-Proliferation Treaty") is None
    assert classify_wo("Will Reza Pahlavi enter Iran by December 31?", "physically enters Iran") is None
    assert classify_wo("Will US crude oil reserves fall to 400M by October 30?", "x") is None
    assert classify_wo("Body cam footage of Maduro capture released by Jan 31?", "footage of the capture of Maduro") is None
    assert classify_wo("Trump agree to withdraw troops from the Iranian region by December 31?", "US ground forces withdraw") is None
    assert series_key("Will Russia capture all of Kupiansk by October 31?") == series_key("Will Russia capture all of Kupiansk by December 31, 2026?")
    assert series_key("Israeli forces enter Beirut by...?") == series_key("Israeli forces enter Beirut by November 30?")
    # pricing: an earlier YES of the same series means the event already happened
    t0 = dt.datetime(2026, 9, 1, tzinfo=UTC)
    a = {"id": "1", "series": "s", "type": "WITHDRAWAL", "start": dt.date(2026, 8, 1), "created": t0, "end": dt.date(2026, 8, 31), "y": 1, "known": dt.datetime(2026, 8, 20, tzinfo=UTC), "open": False}
    b = {"id": "2", "series": "s", "type": "WITHDRAWAL", "start": dt.date(2026, 8, 1), "created": t0, "end": dt.date(2026, 12, 31), "y": None, "known": None, "open": True}
    assert price(b, [a, b], t0)[0] == 0.99
    print("war_outcomes tests: OK")

if __name__ == "__main__":
    if "--test" in sys.argv: _tests()
    if "--refresh" in sys.argv: refresh()
    if "--replay" in sys.argv: replay()
    if "--dry" in sys.argv: dry()

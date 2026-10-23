"""
Family A, "ceasefire holds" contracts (docs/ceasefire_scope_rule.md, docs/holds_replay_prereg.md). Oct 22, 2026.

"X ceasefire continues through D?" resolves NO iff a qualifying military action (Polymarket's strike definition) occurs between
market creation and D. That is a by-date strike window [created, D] with the polarity flipped:
  holds YES -> no-strike window (y=0) for every counted direction
  holds NO  -> strike window (y=1) for a single-direction contract; a two-direction NO cannot be attributed: not used, counted
Published price = P(contract YES) = product over counted directions of (1 - P(strike in window)).
  Independence across directions is v0.1; known bias: retaliation correlates strikes, so this understates "holds".
Holds contracts form their own unified groups (structural fingerprint prefixed "H"), so they never change an existing strike
group's price. Rules text + outcomes come from Polymarket (Gamma); an outcome is usable only after its close time (leakage guard).

  python pilot/ceasefire_holds.py --refresh            fetch/refresh holds contracts -> pilot/ceasefire_markets.json
  python pilot/ceasefire_holds.py --replay             pre-registered replay vs market -> pilot/holds_publish.json
  python pilot/ceasefire_holds.py --test               offline tests (classification, polarity, date parsing)
"""
import json, re, sys, math, time, datetime as dt
import urllib.request, urllib.parse
import numpy as np
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot"))
import unified_data as UD

STORE = ROOT / "pilot" / "ceasefire_markets.json"
PUB = ROOT / "pilot" / "holds_publish.json"
PRICES = ROOT / "pilot" / "holds_price_cache.json"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
UTC = dt.timezone.utc
SEARCH = ["ceasefire continues", "ceasefire continue", "ceasefire", "effective ceasefire", "ceasefire agreement", "peace deal",
          "ceasefire extension", "ceasefire cancelled", "truce", "peace agreement", "normalize relations"]
RULE = ("Amended Oct 22 (docs/ceasefire_publish_amendment.md): every family-A contract is priced and published. The pre-registered "
        "replay (docs/holds_replay_prereg.md) is recomputed daily and reported; it no longer gates publication.")
MIN_N, MARGIN, MIN_OWN_WINDOWS = 5, 0.03, 10

# ---------------------------------------------------------------- classification (deterministic, resolution text only)
_DIR = re.compile(r"initiated by (?:the )?(.+?)(?: or (?:the )?(.+?))?,? that directly impacts (?:the )?(.+?)\.", re.I)

def classify(question, desc):
    """-> {"family": "HOLDS", "dirs": [(initiator, target), ...] or None} | {"family": "GAP"} | None"""
    d = re.sub(r"\s+", " ", desc or ""); dl = d.lower(); ql = (question or "").lower()
    if "continuous" in dl and "-day period" in dl:
        return {"family": "GAP"}
    if "continu" in ql and "qualifying military action refers to" in dl and re.search(r"resolve to .{0,3}no.{0,3} if|no longer be in effect\b.{0,80}?\bif\b", dl):
        m = _DIR.search(d)
        if not m:
            return {"family": "HOLDS", "dirs": None}
        a, b, t = m.group(1).strip(), (m.group(2) or "").strip(), m.group(3).strip()
        if b and t.lower() in ("other country", "other", "each other", "other party"):
            return {"family": "HOLDS", "dirs": [(a, b), (b, a)]}
        if not b:
            return {"family": "HOLDS", "dirs": [(a, t)]}
        return {"family": "HOLDS", "dirs": None}          # "A or B ... impacts C": not handled in v0.1
    return None

_THRU = re.compile(r"through (" + UD._M + r") (\d{1,2})\b", re.I)

def contract_date(question, created, desc=None):
    m = _THRU.search(question or "")
    if not m and created:
        m2 = re.search(r"\bby (" + UD._M + r") (\d{1,2}), (\d{4})", desc or "")
        if m2: return dt.date(int(m2.group(3)), UD.MON[m2.group(1).lower()], int(m2.group(2)))
    if not m or not created:
        return None
    mon, day = UD.MON[m.group(1).lower()], int(m.group(2))
    d = dt.date(created.year, mon, day)
    return d if d >= created.date() - dt.timedelta(1) else dt.date(created.year + 1, mon, day)

def holds_outcome(r):
    """1 = ceasefire held (YES), 0 = broke (NO), None = open / void / unparseable."""
    if not r.get("closed"):
        return None
    try:
        outs, ps = json.loads(r.get("outcomes") or "[]"), [float(x) for x in json.loads(r.get("outcomePrices") or "[]")]
    except Exception:
        return None
    if len(ps) != 2 or not outs or outs[0].lower() != "yes":
        return None
    return 1 if ps[0] > 0.99 else (0 if ps[0] < 0.01 else None)

def _ts(s):
    if not s: return None
    s = s.strip().replace(" ", "T", 1)
    if s.endswith("+00"): s += ":00"
    return UD.T(s)

def contracts():
    """Unified-loader contracts, one per (holds market, counted direction). Ids are "<market_id>@<pair>"."""
    store = json.loads(STORE.read_text()) if STORE.exists() else {}
    out, skip = [], Counter()
    for mid, r in store.items():
        info = classify(r.get("question"), r.get("description"))
        if not info or info["family"] != "HOLDS": continue
        if not info["dirs"]: skip["holds: directions not parseable"] += 1; continue
        created = _ts(r.get("createdAt")); d = contract_date(r.get("question"), created, r.get("description")); tz = UD.tz_of(r.get("description"))
        if not created: skip["holds: no creation time"] += 1; continue
        if not d: skip["holds: no date in question"] += 1; continue
        if not tz: skip["holds: no time zone"] += 1; continue
        e0 = dt.datetime.combine(d, dt.time(23, 59, 59), ZoneInfo(tz)).astimezone(UTC)
        ho, known, n = holds_outcome(r), (_ts(r.get("closedTime")) if r.get("closed") else None), len(info["dirs"])
        for ini, ter in info["dirs"]:
            pair = f"{UD.norm(ini)}->{UD.norm(ter)}"
            if ho is None: so = None
            elif ho == 1: so = 0
            elif n == 1: so = 1
            else: so = None; skip["holds: two-direction NO (not attributable)"] += 1
            e = max(created, known) if (so == 1 and known and known < e0) else e0
            out.append({"id": f"{mid}@{pair}", "holds_of": str(mid), "ndirs": n, "pair": pair, "kind": "bydate", "fp": "H", "tz": tz,
                        "start": created, "end": e, "date": d, "outcome": so, "known": known if so is not None else None,
                        "open": not r.get("closed"), "question": r.get("question"),
                        "sfp": "H" + (UD.struct_fp(r.get("description"), ini, ter) or "nodef"), "members": None})
    return out, skip

def tag_feed(feed):
    """Translator hook: family-A contracts with parseable directions become CORE (deterministic, scope rule)."""
    import ceasefire_bc as BC
    n = Counter()
    for m in feed:
        if not isinstance(m, dict) or m.get("resolved"): continue
        info = BC.classify_all(m.get("question"), m.get("description"))
        fam = (info or {}).get("family")
        if fam not in ("HOLDS", "GAP", "AGREEMENT"):
            try:
                import war_outcomes as WO; fam = WO.tag(m)                  # Oct 22: family F (docs/war_outcomes_prereg.md)
            except Exception: fam = None
        if fam in ("HOLDS", "GAP", "AGREEMENT", "WAR_OUTCOME"):
            m["bucket"], m["contract_family"] = "CORE", fam
            m["bucket_reason"] = (f"Deterministic (docs/ceasefire_scope_rule.md as amended, family {fam}): priced only by its ceasefire component "
                                  "(HOLDS: unified-v1, GAP: unified-gap-v0, AGREEMENT: production C model, WAR_OUTCOME: war-outcome-v0); never by the onset engine.")
            n[fam] += 1
    print(f"[ceasefire] tagged CORE: {dict(n)}")
    return sum(n.values())

# ---------------------------------------------------------------- pricing hook (called from unified_price.production_prices)
def combine(PP, G=None, now=None):
    """Replace per-direction entries "<mid>@<pair>" by one entry per holds market, if every direction is priced and the
    series passed the pre-registered rule. Virtual entries are always removed."""
    virt = {k: v for k, v in PP.items() if "@" in k}
    for k in virt: PP.pop(k)
    store = json.loads(STORE.read_text()) if STORE.exists() else {}
    pol = json.loads(PUB.read_text()) if PUB.exists() else {"allowed": []}
    by = defaultdict(dict)
    for k, v in virt.items():
        mid, pair = k.split("@", 1); by[mid][pair] = v
    n = 0
    for mid, d in by.items():
        info = classify((store.get(mid) or {}).get("question"), (store.get(mid) or {}).get("description"))
        if not info or not info.get("dirs"): continue
        pairs = sorted(f"{UD.norm(a)}->{UD.norm(b)}" for a, b in info["dirs"])
        if set(pairs) != set(d): continue
        series = "+".join(pairs)
        if len(pairs) == 2 and G is not None and now is not None and two_dir_model() == "v1":
            try:
                pu, du = price_union([mid], G, now)
                if mid in pu:
                    PP[mid] = {"p": pu[mid], "group": "holds-v1:" + series, "source": du["source"], "q": round(du["q"], 3), "pi": round(du["pi"], 3)}
                    n += 1; continue
            except Exception as ex:
                print(f"[holds] v1 FAILED for {mid} ({ex!r}); v0 price used")
        p = 1.0
        for pr in pairs: p *= (1 - d[pr]["p"])
        PP[mid] = {"p": round(p, 4), "group": "holds:" + series, "source": "holds; " + " | ".join(f"{pr}: P(strike) {d[pr]['p']:.3f}, {d[pr]['source']}" for pr in pairs),
                   "q": d[pairs[0]]["q"], "pi": max(d[pr]["pi"] for pr in pairs)}
        n += 1
    print(f"[holds] {n} holds contracts priced (all series published; replay reported only)")
    return n

# ---------------------------------------------------------------- v1: shared fighting state for two-direction holds
def _two_dir(r):
    info = classify(r.get("question"), r.get("description"))
    return info if info and info.get("dirs") and len(info["dirs"]) == 2 else None

def _runs(days):
    out, cur = [], None
    for d in sorted(days):
        if cur and d == cur[1] + dt.timedelta(1): cur = (cur[0], d)
        else:
            if cur: out.append(cur)
            cur = (d, d)
    if cur: out.append(cur)
    return out

def union_params(pairs):
    import unified_price as UP
    Ps = [UP.params(p) for p in pairs]
    if any(p is None for p in Ps): return None
    cl = lambda x, lo, hi: min(hi, max(lo, x))
    return {"world_pair": "+".join(p["world_pair"] or "class" for p in Ps), "via": "union", "class": Ps[0]["class"],
            "h": math.exp(sum(math.log(p["h"]) for p in Ps) / len(Ps)), "mu": math.exp(sum(p["mu_lm"] for p in Ps) / len(Ps)),
            "mu_lm": sum(p["mu_lm"] for p in Ps) / len(Ps), "mu_ls": max(p["mu_ls"] for p in Ps),
            "q_c": cl(1 - math.prod(1 - p["q_c"] for p in Ps), 0.02, 0.98), "q0_c": cl(1 - math.prod(1 - p["q0_c"] for p in Ps), 0.001, 0.3)}

def price_union(mids, G, as_of, S=None):
    """docs/holds_v1_prereg.md. P(holds) for two-direction holds contracts `mids` (same direction set), as of `as_of`."""
    import unified_price as UP, unified as U
    from zoneinfo import ZoneInfo
    S = S or json.loads(STORE.read_text())
    r0 = S[mids[0]]; info = _two_dir(r0)
    if not info: return {}, {"unpriced": "not a two-direction holds contract"}
    pairs = sorted(f"{UD.norm(a)}->{UD.norm(b)}" for a, b in info["dirs"]); P = union_params(pairs)
    if not P: return {}, {"unpriced": "no parameters for a direction"}
    tz = UD.tz_of(r0.get("description")) or "UTC"; z = ZoneInfo(tz); today = as_of.astimezone(z).date(); last = today - dt.timedelta(1)
    ev = []
    for mid, r in S.items():                                     # resolved holds of the same direction set
        i2 = _two_dir(r)
        if not i2 or sorted(f"{UD.norm(a)}->{UD.norm(b)}" for a, b in i2["dirs"]) != pairs: continue
        ho, known, created = holds_outcome(r), (_ts(r.get("closedTime")) if r.get("closed") else None), _ts(r.get("createdAt"))
        d = contract_date(r.get("question"), created, r.get("description")) if created else None
        if ho is None or not known or not (known < as_of) or not d: continue
        a = created.astimezone(z).date()
        if ho == 1:                                              # held: no union strike after the creation day through D
            a2, b2 = (a if created.astimezone(z).time() == dt.time(0) else a + dt.timedelta(1)), min(d, last)
            if b2 >= a2: ev.append((a2, b2, 0))
        else:                                                    # broken: >= 1 union strike in [created, close]
            b2 = min(d, known.astimezone(z).date(), last)
            if b2 >= a: ev.append((a, b2, 1))
    base = {UD.struct_fp(r0.get("description"), a, b) for a, b in info["dirs"]}
    nos = []
    for p in pairs:                                              # direction strike groups, same structural definition
        dn = set()
        for (p2, f2), g2 in G.items():
            if p2 != p or str(f2).startswith("H") or g2[0].get("sfp") not in base: continue
            d0, T2, w2 = UD.windows(g2, as_of)
            for a2, b2, y in w2:
                A, B = d0 + dt.timedelta(a2), d0 + dt.timedelta(b2)
                if y == 1: ev.append((A, B, 1))
                else: dn |= {A + dt.timedelta(k) for k in range((B - A).days + 1)}
        nos.append(dn)
    ev += [(a, b, 0) for a, b in _runs(set.intersection(*nos))] if nos else []
    nd = set().union(*[UP.news_dates(p, as_of, z) for p in pairs])
    opens = []
    for mid in mids:
        r = S[mid]; created = _ts(r.get("createdAt")); d = contract_date(r.get("question"), created, r.get("description"))
        if created and d and d >= today: opens.append((mid, created.astimezone(z).date(), d))
    if not opens: return {}, None
    d0n = min([today] + [a for _, a, _ in opens] + [a for a, _, _ in ev] + ([today - dt.timedelta(60)] if nd else []))
    wins = [((a - d0n).days, (b - d0n).days, y) for a, b, y in ev]; Tn = (today - d0n).days
    nds = {(x - d0n).days for x in nd if x >= d0n}
    w, rows = UP.grid(P, Tn, wins, nds=nds)
    if not len(rows): return {}, {"unpriced": "contradictory evidence"}
    out = {}
    for mid, a, b in opens:
        A, B = (a - d0n).days, (b - d0n).days; ps = []
        for _, q, q0, st, mu in rows:
            stk = st if A >= Tn else U.forward_joint(Tn, wins, P["h"], mu, q, q0, keep_from=A, news_days=nds, news_ratio=UP.NEWS_FALSE / UP.NEWS_CATCH)[1]
            ps.append(U.price_open(stk, P["h"], mu, q, q0, Tn, A, B))
        out[mid] = round(1 - float(np.dot(w, ps)), 4)
    return out, {"source": f"holds v1 union {'+'.join(pairs)}: {len(wins)} windows, {len(nds)} news days",
                 "q": float(np.dot(w, [r[1] for r in rows])), "pi": float(np.dot(w, [sum(v for (s, _), v in r[3].items() if s == 1) for r in rows]))}

def two_dir_model():
    try: return json.loads(PUB.read_text()).get("two_direction_model", "v0")
    except Exception: return "v0"

def replay_v1(write=True):
    """docs/holds_v1_prereg.md: v1 vs v0 vs market on resolved two-direction holds (24h after listing); adoption rule."""
    import unified_price as UP
    cs, _ = UD.load(); G = UD.groups(cs); S = json.loads(STORE.read_text())
    cache = json.loads(PRICES.read_text()) if PRICES.exists() else {}
    vc = defaultdict(list)
    for c in cs:
        if c.get("holds_of"): vc[c["holds_of"]].append(c)
    rows, skip = [], Counter()
    for mid, r in S.items():
        if not _two_dir(r): continue
        ho = holds_outcome(r)
        if ho is None: skip["open or void"] += 1; continue
        created, known = _ts(r["createdAt"]), _ts(r["closedTime"]); as_of = created + dt.timedelta(hours=24)
        if known <= as_of: skip["resolved before first run"] += 1; continue
        pu, _ = price_union([mid], G, as_of, S)
        if mid not in pu: skip["v1 unpriced"] += 1; continue
        p0 = 1.0
        for c in vc.get(mid, []):
            pr, d = UP.price_group(G[(c["pair"], c["sfp"])], as_of, UP.params(c["pair"]), [dict(c, open=True)], G, c["pair"])
            if c["id"] not in pr: p0 = None; break
            p0 *= (1 - pr[c["id"]])
        if p0 is None: skip["v0 unpriced"] += 1; continue
        tok = json.loads(r.get("clobTokenIds") or "[]"); mk = market_price(tok[0], as_of, cache) if tok else None
        if mk is None: skip["no market price"] += 1; continue
        rows.append({"id": mid, "y": ho, "v1": pu[mid], "v0": round(p0, 4), "m": mk, "q": r["question"]})
    PRICES.write_text(json.dumps(cache) + "\n")
    cl = lambda p: min(0.999, max(0.001, p))
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs)
    LL = lambda xs, k: -sum(math.log(cl(x[k]) if x["y"] else 1 - cl(x[k])) for x in xs) / len(xs)
    print(f"\n=== HOLDS v1 REPLAY (docs/holds_v1_prereg.md): n={len(rows)} | skipped {dict(skip)}")
    if not rows: return rows
    for k in ("v1", "v0", "m"): print(f"  {k:3} Brier {B(rows, k):.4f} logloss {LL(rows, k):.3f}")
    for x in sorted(rows, key=lambda x: x["q"]): print(f"    y={x['y']} v1 {x['v1']:.3f} v0 {x['v0']:.3f} mkt {x['m']:.3f} | {x['q'][:60]}")
    pick = "v0" if B(rows, "v1") > B(rows, "v0") + 0.01 else "v1"
    print(f"  ADOPTION RULE -> two-direction model: {pick}  (caveat: all outcomes YES here; harm check only)")
    if write:
        pol = json.loads(PUB.read_text()) if PUB.exists() else {}
        pol["two_direction_model"] = pick
        pol["two_direction_replay"] = {"n": len(rows), "brier": {k: round(B(rows, k), 4) for k in ("v1", "v0", "m")}, "rule": "docs/holds_v1_prereg.md"}
        PUB.write_text(json.dumps(pol, indent=2) + "\n")
    return rows

# ---------------------------------------------------------------- data
def _get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "predictioneering"}), timeout=30) as f:
                return json.loads(f.read().decode())
        except Exception as ex:
            if i == tries - 1: raise
            time.sleep(2 * (i + 1))

def _in_scope(q, desc):
    import ceasefire_bc as BC
    return (BC.classify_all(q, desc) or {}).get("family") in ("HOLDS", "GAP", "AGREEMENT")

KEEP = ("question", "description", "createdAt", "closedTime", "closed", "outcomes", "outcomePrices", "clobTokenIds", "endDate", "slug")

def refresh():
    store = json.loads(STORE.read_text()) if STORE.exists() else {}
    found = {}
    for q in SEARCH:
        d = _get(f"{GAMMA}/public-search?q={urllib.parse.quote(q)}&events_status=all&limit_per_type=50&keep_closed_markets=1")
        for e in d.get("events") or []:
            for m in e.get("markets") or []:
                if _in_scope(m.get("question"), m.get("description")): found[str(m["id"])] = m
    feed = json.loads((ROOT / "pipeline" / "classified_feed.json").read_text())
    feed = feed if isinstance(feed, list) else feed.get("markets", feed.get("data", []))
    for m in feed:                                    # contracts in our feed that the search missed
        if _in_scope(m.get("question"), m.get("description")) and str(m["market_id"]) not in found and str(m["market_id"]) not in store:
            try: found[str(m["market_id"])] = _get(f"{GAMMA}/markets/{m['market_id']}")
            except Exception as ex: print(f"  [holds] {m['market_id']}: {ex!r}")
    for mid, r in list(store.items()):                # open ones: re-fetch for status/outcome
        if not r.get("closed") and mid not in found:
            try: found[mid] = _get(f"{GAMMA}/markets/{mid}")
            except Exception as ex: print(f"  [holds] {mid}: {ex!r}")
    now = dt.datetime.now(UTC).isoformat()
    for mid, m in found.items():
        store[mid] = {k: m.get(k) for k in KEEP} | {"fetched_at": now}
    STORE.write_text(json.dumps(store, indent=1, sort_keys=True) + "\n")
    import ceasefire_bc as BC
    fam = Counter((BC.classify_all(r["question"], r["description"]) or {}).get("family") for r in store.values())
    print(f"[holds] store {len(store)} contracts {dict(fam)} | open {sum(1 for r in store.values() if not r.get('closed'))}")

def market_price(token, as_of, cache):
    """YES price: last point at or before as_of, else first point within 24h after. Closed markets need fidelity >= 720."""
    if token not in cache:
        s, e = int((as_of - dt.timedelta(days=4)).timestamp()), int((as_of + dt.timedelta(days=2)).timestamp())
        try:
            h = _get(f"{CLOB}/prices-history?market={token}&startTs={s}&endTs={e}&fidelity=720").get("history") or []
            if not h:
                h = _get(f"{CLOB}/prices-history?market={token}&interval=max&fidelity=720").get("history") or []
        except Exception:
            h = []
        cache[token] = h
    t = as_of.timestamp(); h = cache[token]
    before = [x for x in h if x["t"] <= t]
    if before: return float(before[-1]["p"])
    after = [x for x in h if t < x["t"] <= t + 86400]
    return float(after[0]["p"]) if after else None

# ---------------------------------------------------------------- pre-registered replay (docs/holds_replay_prereg.md)
def replay(write=True):
    import unified_price as UP
    cs, _ = UD.load(); G = UD.groups(cs); store = json.loads(STORE.read_text())
    cache = json.loads(PRICES.read_text()) if PRICES.exists() else {}
    bym = defaultdict(list)
    for c in cs:
        if c.get("holds_of"): bym[c["holds_of"]].append(c)
    rows, skip = [], Counter()
    for mid, vcs in bym.items():
        r = store[mid]; ho = holds_outcome(r)
        if ho is None: skip["open or void"] += 1; continue
        if ho == 0 and len(vcs) > 1: skip["two-direction NO (not attributable)"] += 1
        created, known = _ts(r["createdAt"]), _ts(r["closedTime"]); as_of = created + dt.timedelta(hours=24)
        z = ZoneInfo(vcs[0]["tz"])
        if known <= as_of: skip["resolved before first run"] += 1; continue
        if vcs[0]["date"] < as_of.astimezone(z).date(): skip["past its date at first run"] += 1; continue
        ps = []
        for c in vcs:
            P = UP.params(c["pair"]); grp = G[(c["pair"], c["sfp"])]
            pr, d = UP.price_group(grp, as_of, P, [dict(c, open=True)], G, c["pair"])
            if c["id"] not in pr: ps = None; skip["unpriced at first run: " + ((d or {}).get("unpriced") or "no span")[:60]] += 1; break
            ps.append(pr[c["id"]])
        if ps is None: continue
        u = 1.0
        for p in ps: u *= (1 - p)
        tok = json.loads(r.get("clobTokenIds") or "[]")
        mk = market_price(tok[0], as_of, cache) if tok else None
        series = "+".join(sorted(c["pair"] for c in vcs))
        rows.append({"id": mid, "series": series, "y": ho, "u": round(u, 4), "m": mk, "as_of": as_of.isoformat(), "date": str(vcs[0]["date"]), "q": r["question"]})
    PRICES.write_text(json.dumps(cache) + "\n")
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs)
    res, allowed = {}, []
    print(f"\n=== HOLDS REPLAY (pre-registered): {len(rows)} contracts | skipped {dict(skip)}")
    for s in sorted({x["series"] for x in rows}):
        xs = [x for x in rows if x["series"] == s and x["m"] is not None]; nm = sum(1 for x in rows if x["series"] == s and x["m"] is None)
        if not xs: res[s] = {"n": 0, "no_market_price": nm}; continue
        bu, bm = B(xs, "u"), B(xs, "m"); ok = len(xs) >= MIN_N and bu <= bm + MARGIN
        res[s] = {"n": len(xs), "yes": sum(x["y"] for x in xs), "no": sum(1 - x["y"] for x in xs), "brier_unified": round(bu, 4),
                  "brier_market": round(bm, 4), "no_market_price": nm, "passes_prereg_rule": ok}
        if ok: allowed.append(s)
        print(f"  {s:34} n={len(xs):3} (YES {res[s]['yes']}, NO {res[s]['no']}) unified {bu:.4f} market {bm:.4f} | pre-reg rule {'PASS' if ok else 'FAIL'} (reported only; published regardless)"
              + (f" | {nm} without market price" if nm else ""))
        for x in sorted(xs, key=lambda x: x["date"]):
            print(f"      {x['date']} y={x['y']} unified {x['u']:.3f} market {x['m']:.3f} | {x['q'][:60]}")
    print("  caveat: each series is one or two episodes (a quiet spell, a break); effective sample << n.")
    if write:
        pol = json.loads(PUB.read_text()) if PUB.exists() else {}          # merge: keep keys other steps own (two_direction_model)
        pol.update({"rule": RULE, "allowed": allowed, "results": res, "skipped": dict(skip), "computed_at": dt.datetime.now(UTC).isoformat()})
        PUB.write_text(json.dumps(pol, indent=2) + "\n")
    return rows

# ---------------------------------------------------------------- tests
def _tests():
    us = ("This market will resolve to “No” if the United States takes a qualifying military action against Iran by the specified date, "
          "11:59 PM Iran Standard Time. Otherwise this market will resolve to “Yes.” A qualifying military action refers to an air strike "
          "or a surface-to-surface missile strike, initiated by the United States, that directly impacts Iran.")
    il = ("This market will resolve to \"Yes\" if a state of ceasefire remains in effect between Israel and Iran through the listed date, "
          "11:59 PM Iran Standard Time (IRST). A state of ceasefire will be considered to no longer be in effect between Israel and Iran if "
          "either Israel or Iran takes a qualifying military action against the other country. A qualifying military action refers to an "
          "air strike or a surface-to-surface missile strike, initiated by Israel or Iran, that directly impacts the other country.")
    gap = "This market will resolve to “Yes” if there is a continuous 14-day period during which Israel does not take a qualifying military action"
    agr = "This market will resolve to “Yes” if there is a ceasefire agreement between Russia and Ukraine by the specified date."
    assert classify("US x Iran ceasefire continues through October 31?", us) == {"family": "HOLDS", "dirs": [("United States", "Iran")]}
    assert classify("Israel x Iran ceasefire continues through October 31?", il) == {"family": "HOLDS", "dirs": [("Israel", "Iran"), ("Iran", "Israel")]}
    assert classify("Israel x Lebanon Effective Ceasefire by October 31?", gap) == {"family": "GAP"}
    assert classify("Russia x Ukraine ceasefire agreement by October 31?", agr) is None
    assert classify("US x Iran ceasefire continues through October 31?", agr) is None          # title alone never decides
    c0 = dt.datetime(2026, 9, 17, 15, tzinfo=UTC)
    assert contract_date("US x Iran ceasefire continues through October 22?", c0) == dt.date(2026, 10, 22)
    assert contract_date("Will the Iran ceasefire continue through May 20?", dt.datetime(2026, 5, 20, 1, tzinfo=UTC)) == dt.date(2026, 5, 20)
    assert contract_date("Israel x Iran ceasefire continues through January 15?", dt.datetime(2026, 12, 20, tzinfo=UTC)) == dt.date(2027, 1, 15)
    assert contract_date("US-Iran ceasefire continues through the midterms?", c0) is None
    assert holds_outcome({"closed": True, "outcomes": '["Yes", "No"]', "outcomePrices": '["1", "0"]'}) == 1
    assert holds_outcome({"closed": True, "outcomes": '["Yes", "No"]', "outcomePrices": '["0", "1"]'}) == 0
    assert holds_outcome({"closed": True, "outcomes": '["Yes", "No"]', "outcomePrices": '["0.5", "0.5"]'}) is None
    assert holds_outcome({"closed": False, "outcomes": '["Yes", "No"]', "outcomePrices": '["0.9", "0.1"]'}) is None
    assert UD.tz_of(us) == "Asia/Tehran"
    # polarity: holds YES -> no-strike window; single-direction NO -> strike window; combine = product of (1 - P(strike))
    global STORE, PUB
    import tempfile; tmp = Path(tempfile.mkdtemp()); S0, P0 = STORE, PUB; STORE, PUB = tmp / "s.json", tmp / "p.json"
    try:
        STORE.write_text(json.dumps({
            "1": {"question": "US x Iran ceasefire continues through October 22?", "description": us, "createdAt": "2026-09-17T15:00:00Z", "closed": True,
                  "closedTime": "2026-10-23 08:00:00+00", "outcomes": '["Yes", "No"]', "outcomePrices": '["1", "0"]'},
            "2": {"question": "US x Iran ceasefire continues through October 28?", "description": us, "createdAt": "2026-09-17T15:00:00Z", "closed": True,
                  "closedTime": "2026-10-02 08:00:00+00", "outcomes": '["Yes", "No"]', "outcomePrices": '["0", "1"]'},
            "3": {"question": "Israel x Iran ceasefire continues through October 31?", "description": il, "createdAt": "2026-09-01T00:00:00Z", "closed": False,
                  "outcomes": '["Yes", "No"]', "outcomePrices": '["0.8", "0.2"]'}}))
        cs, sk = contracts(); byid = {c["id"]: c for c in cs}
        assert byid["1@unitedstates->iran"]["outcome"] == 0 and byid["2@unitedstates->iran"]["outcome"] == 1
        assert byid["2@unitedstates->iran"]["end"] == _ts("2026-10-02 08:00:00+00")                  # strike window trimmed to close time
        assert byid["3@israel->iran"]["open"] and byid["3@iran->israel"]["open"] and byid["3@israel->iran"]["outcome"] is None
        assert byid["1@unitedstates->iran"]["sfp"].startswith("H")
        PUB.write_text(json.dumps({"allowed": ["iran->israel+israel->iran"]}))
        PP = {"3@israel->iran": {"p": 0.2, "source": "s", "q": 0.5, "pi": 0.1}, "3@iran->israel": {"p": 0.1, "source": "s", "q": 0.5, "pi": 0.3},
              "9@unitedstates->iran": {"p": 0.5, "source": "s", "q": 0.5, "pi": 0.1}, "777": {"p": 0.3}}
        combine(PP)
        assert set(PP) == {"3", "777"} and abs(PP["3"]["p"] - 0.72) < 1e-9, PP          # (1-.2)(1-.1); unknown/virtual dropped; others untouched
        PUB.write_text(json.dumps({"allowed": []})); PP = {"3@israel->iran": {"p": 0.2, "source": "s", "q": 0.5, "pi": 0.1}, "3@iran->israel": {"p": 0.1, "source": "s", "q": 0.5, "pi": 0.3}}
        combine(PP); assert set(PP) == {"3"}                                                # amended Oct 22: published regardless of replay
        assert contract_date("US-Iran ceasefire continues through the midterms?", c0, "by November 3, 2026, 11:59 PM ET") == dt.date(2026, 11, 3)
    finally:
        STORE, PUB = S0, P0
    print("ceasefire_holds tests: OK")

if __name__ == "__main__":
    if "--test" in sys.argv: _tests()
    if "--refresh" in sys.argv: refresh()
    if "--replay" in sys.argv: replay()
    if "--replay-v1" in sys.argv: replay_v1()

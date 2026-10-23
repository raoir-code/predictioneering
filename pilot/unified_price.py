"""
Unified engine, pieces C + D (Oct 20). Generic rules, no per-pair code.
SCOPE (v1): a group is priced if its (initiator, territory) maps to a worldwide ACLED pair (pilot/priors_world.json): direct;
via a faction alias (houthi -> Yemen [Houthi]); or via a coalition the initiator leads (Saudi Arabia -> Operation Restoring Hope).
A group with NO resolved windows of its own is priced only if the REVERSE direction of the same war has evidence: fighting is a
property of the dyad (bargaining while fighting), so its P(fighting) seeds this group (approximation: seed applied from the
earliest open window start). Otherwise unpriced (production). Sub-territories, collective targets, never-fought pairs: production.
h, mu: pooled worldwide posterior means (frozen). q, q0: Bayesian grid, prior Beta(weight 2) centred on the pair's ACLED
recorded-day rates ONLY if the ACLED actor IS the initiator (direct / faction); via a coalition the q prior is neutral (0.5)
and q0 is the class median (ACLED coalition activity is not Saudi-forces-only attribution). Likelihood = the group's resolved
windows (exact, pieces A+B). Price = posterior average; open by-date windows priced exactly (already happened since listing,
or happens by the end).
  python pilot/unified_price.py            dry run on today's open contracts
  python pilot/unified_price.py --replay   piece D: walk-forward replay vs production and market, pre-registered gate
GATE (written before the replay was run, Oct 20): ship only if (a) unified Brier <= production Brier - 0.02 on the scored set
and (b) no pair with >= 3 scored contracts is worse than production by > 0.05. Market Brier is reported, never used.
"""
import json, math, sys, re, datetime as dt
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import unified as U, unified_data as UD, news_strikes as NS

ROOT = Path(__file__).resolve().parent.parent
W = json.loads((ROOT / "pilot" / "priors_world.json").read_text())
F = json.loads((ROOT / "analysis" / "world_fits.json").read_text())
FACTION = {"houthi": "yemenhouthi"}; FACTION_HOME = {"houthi": "yemen"}             # lookup tables, not per-pair logic
LEADS = {"saudiarabia": ["operationrestoringhope", "operationdecisivestorm"], "turkey": ["operationpeacespring"]}
NEWS_CATCH = 0.36        # measured: P(report | strike in last 3 days), Israel->Lebanon Jul 25-Oct 19 (v2 labels)
NEWS_FALSE = 3 / 2200    # conservative: upper 95% bound, 0 false alarms in ~2,200 peaceful direction-days
NEWS_DIR = {}            # contract pair -> (cache dyad, direction), built generically from news_strikes.DYADS
for _dy, (_a, _b) in NS.DYADS.items():
    _ka, _kb = re.sub(r"[^a-z]", "", _a.lower()), re.sub(r"[^a-z]", "", _b.lower())
    NEWS_DIR[f"{_ka}->{_kb}"] = (_dy, "A_STRIKES_B"); NEWS_DIR[f"{_kb}->{_ka}"] = (_dy, "B_STRIKES_A")
_NEWS = {}

def news_dates(pair, as_of, tz):
    ini, ter = pair.split("->"); src = NEWS_DIR.get(pair) or NEWS_DIR.get(f"{FACTION_HOME.get(ini, ini)}->{ter}")
    if not src: return set()
    if src not in _NEWS: _NEWS[src] = NS.day_obs(*src)
    today = as_of.astimezone(tz).date()
    return {d for d, v in _NEWS[src].items() if v and d < today}

def evidence(grp, pair, as_of, G):
    """Dated windows: the group's own + YES windows of MEMBER groups with the same structural definition (a strike on any
    member is a strike on the collective). News pairs: the pair itself + initiator->member pairs."""
    d0, T, w = UD.windows(grp, as_of); ev = [(d0 + dt.timedelta(a), d0 + dt.timedelta(b), y) for a, b, y in w]
    mem = next((c["members"] for c in grp if c.get("members")), None); sfp = grp[0].get("sfp"); ini = pair.split("->")[0]; linked = []
    for m in mem or []:
        for (p2, f2), g2 in G.items():
            if p2 == f"{ini}->{m}" and g2[0].get("sfp") == sfp:
                d2, T2, w2 = UD.windows(g2, as_of)
                ev += [(d2 + dt.timedelta(a), d2 + dt.timedelta(b), 1) for a, b, y in w2 if y == 1]; linked.append(p2)
    # Oct 21: downward link. A collective NO window ("Iran targeted no Arab country on day t") is a NO window for every
    # member with the same structural definition. Env UNIFIED_DOWNLINK=0/1 (replay A/B); default on.
    import os
    if os.environ.get("UNIFIED_DOWNLINK", "1") == "1":
        ter = pair.split("->")[1]
        for (p2, f2), g2 in G.items():
            if p2 != pair and p2.split("->")[0] == ini and g2[0].get("sfp") == sfp and any(ter in (c.get("members") or []) for c in g2):
                d2, T2, w2 = UD.windows(g2, as_of)
                nos = [(d2 + dt.timedelta(a), d2 + dt.timedelta(b), 0) for a, b, y in w2 if y == 0]
                if nos: ev += nos; linked.append(p2 + " (NO)")
    return ev, [pair] + [f"{ini}->{m}" for m in (mem or [])], linked

def news_days(pair, as_of, d0n, tz):
    """Day indices (relative to d0n) of positive reports, from files written strictly before as_of's day (walk-forward)."""
    ini, ter = pair.split("->"); src = NEWS_DIR.get(pair) or NEWS_DIR.get(f"{FACTION_HOME.get(ini, ini)}->{ter}")
    if not src: return set()
    if src not in _NEWS: _NEWS[src] = NS.day_obs(*src)
    today = as_of.astimezone(tz).date()
    return {(d - d0n).days for d, v in _NEWS[src].items() if v and d < today and d >= d0n}

QG = np.linspace(0.02, 0.98, 25); Q0G = np.exp(np.linspace(math.log(0.001), math.log(0.3), 15))
key = lambda s: re.sub(r"[^a-z]", "", s.lower())
WK = {(key(k.split("->")[0]), key(k.split("->")[1])): k for k in W["pairs"]}
CLS = defaultdict(list)
for n, r in F.items(): CLS[r["class"]].append(r["p_rec_N"])
cmed = lambda c: sorted(CLS[c])[len(CLS[c]) // 2] if CLS[c] else 0.01
clip = lambda x, lo, hi: min(hi, max(lo, x))

def world_pair(pair):
    ini, ter = pair.split("->")
    if (FACTION.get(ini, ini), ter) in WK:
        return WK[(FACTION.get(ini, ini), ter)], ("faction" if ini in FACTION else "direct")
    for c in LEADS.get(ini, []):
        if (c, ter) in WK:
            return WK[(c, ter)], "coalition"
    return None, None

def params(pair):
    """World pair if fitted; otherwise the CLASS prior (rule 4: faction initiator -> defacto_authority, else state_vs_state).
    Class-prior groups are priced only with positive evidence of fighting (enforced in price_group)."""
    wk, via = world_pair(pair)
    if not wk:
        ini = pair.split("->")[0]; cls = "defacto_authority" if ini in FACTION else "state_vs_state"; C = W["classes"][cls]
        return {"world_pair": None, "via": "class_prior", "class": cls, "h": math.exp(C["log_h"]["mean"]), "mu": math.exp(C["log_mu"]["mean"]),
                "mu_lm": C["log_mu"]["mean"], "mu_ls": C["log_mu"]["tau"],
                "q_c": 0.5, "q0_c": clip(cmed(cls), 0.001, 0.3)}
    p, f = W["pairs"][wk], F[wk]
    qc, q0c = (f["p_rec_F"], f["p_rec_N"]) if via in ("direct", "faction") else (0.5, cmed(p["class"]))
    return {"world_pair": wk, "via": via, "class": p["class"], "h": math.exp(p["log_h"]["mean"]), "mu": math.exp(p["log_mu"]["mean"]),
            "mu_lm": p["log_mu"]["mean"], "mu_ls": p["log_mu"]["sd"],
            "q_c": clip(qc, 0.02, 0.98), "q0_c": clip(q0c, 0.001, 0.3)}

def lbeta(x, c, w=2.0):
    return (w * c - 1) * math.log(x) + (w * (1 - c) - 1) * math.log(1 - x)

GH = [(-2.856970, 0.011257), (-1.355626, 0.222076), (0.0, 0.533333), (1.355626, 0.222076), (2.856970, 0.011257)]   # 5-pt Gauss-Hermite, N(0,1)

def grid(P, Tn, wins, p_start=None, nds=()):
    """Posterior over (mu, q, q0). mu is NOT a point value: log mu ~ N(prior mean, prior sd) from the worldwide fit (pair posterior,
    or class spread tau), integrated by 5-point Gauss-Hermite (Oct 20: one average war length treated every retaliatory exchange as a
    campaign). The group's own evidence reweights the mu nodes, so a pair can learn that its episodes are short or long."""
    rows = []
    for zk, wk in GH:
        mu = math.exp(P["mu_lm"] + P["mu_ls"] * zk)
        for q in QG:
            for q0 in Q0G:
                if q0 >= q: continue
                ll, st = U.forward_joint(Tn, wins, P["h"], mu, q, q0, p_start=p_start, news_days=nds, news_ratio=NEWS_FALSE / NEWS_CATCH)
                if ll != -math.inf:
                    rows.append((ll + lbeta(q, P["q_c"]) + lbeta(q0, P["q0_c"]) + math.log(wk), q, q0, st, mu))
    if not rows:
        return np.array([]), []
    lw = np.array([r[0] for r in rows]); w = np.exp(lw - lw.max()); w /= w.sum()
    return w, rows

def pi_now(grp, as_of, P):
    d0, T, wins = UD.windows(grp, as_of)
    if not wins:
        return None
    w, rows = grid(P, T, wins)
    return float(sum(wi * sum(v for (s, _), v in r[3].items() if s == 1) for wi, r in zip(w, rows)))

def reverse_seed(pair, G, as_of):
    ini, ter = pair.split("->"); rev = f"{ter}->{FACTION_HOME.get(ini, ini)}"
    best = None
    for (p, fp), g in G.items():
        if p != rev: continue
        n = len(UD.windows(g, as_of)[2])
        if n and (best is None or n > best[0]): best = (n, g)
    if not best:
        return None
    Pr = params(rev)
    return pi_now(best[1], as_of, Pr) if Pr else None

def price_group(grp, as_of, P, opens, G, pair):
    z = ZoneInfo(UD.group_tz(grp)); today = as_of.astimezone(z).date()
    spans = {c["id"]: ((c["date"] if c["kind"] == "daily" else c["start"].astimezone(z).date()), c["date"]) for c in opens if c["date"] >= today}
    if not spans:
        return {}, None
    ev, npairs, linked = evidence(grp, pair, as_of, G)
    nd = set().union(*[news_dates(p, as_of, z) for p in npairs])
    seed = None
    own_ok = str(grp[0].get("sfp") or "").startswith("H") and len(ev) >= 10     # Oct 22 pre-reg: holds groups with >= 10 settled windows of their own
    if P["via"] == "class_prior" and not any(y == 1 for _, _, y in ev) and not nd and not own_ok:
        return {}, {"unpriced": "no fitted history and no positive evidence of fighting (engine decides onset)"}
    src = ("own windows" if ev else "news only") + (f" + {len(linked)} member groups" if linked else "")
    if not ev and not nd:
        pi = reverse_seed(pair, G, as_of)
        if pi is None:
            return {}, {"unpriced": "no evidence of its own, none in the reverse direction"}
        seed, src = np.array([1 - pi, pi]), f"seeded by reverse direction, P(fighting) {pi:.2f}"
    d0n = min([today] + [a for a, _ in spans.values()] + [a for a, _, _ in ev] + ([today - dt.timedelta(60)] if nd else []))
    wins = [((a - d0n).days, (b - d0n).days, y) for a, b, y in ev]; Tn = (today - d0n).days
    nds = {(d - d0n).days for d in nd if d >= d0n}
    idx = {k: ((a - d0n).days, (b - d0n).days) for k, (a, b) in spans.items()}
    w, rows = grid(P, Tn, wins, p_start=seed, nds=nds)
    if not len(rows):
        return {}, {"unpriced": "contradictory evidence"}
    out = {}
    for k, (a, b) in idx.items():
        ps = []
        for _, q, q0, st, mu in rows:
            stk = st if a >= Tn else U.forward_joint(Tn, wins, P["h"], mu, q, q0, p_start=seed, keep_from=a, news_days=nds, news_ratio=NEWS_FALSE / NEWS_CATCH)[1]
            ps.append(U.price_open(stk, P["h"], mu, q, q0, Tn, a, b))
        out[k] = round(float(np.dot(w, ps)), 4)
    pis = [sum(v for (s, _), v in r[3].items() if s == 1) for r in rows]
    return out, {"source": src + f", {len(nds)} news days", "windows": len(wins), "days": Tn, "q": float(np.dot(w, [r[1] for r in rows])),
                 "q0": float(np.dot(w, [r[2] for r in rows])), "pi": float(np.dot(w, pis)),
                 "war_half_life_post": float(np.dot(w, [math.log(2) / r[4] for r in rows]))}

def feed_index():
    f = json.loads((ROOT / "pipeline" / "classified_feed.json").read_text()); f = f if isinstance(f, list) else f.get("markets", f.get("data", []))
    return {str(m["market_id"]): m for m in f}

def dry():
    cs, _ = UD.load(); G = UD.groups(cs); now = dt.datetime.now(dt.timezone.utc); fd = feed_index()
    for (pair, fp), grp in sorted(G.items(), key=lambda kv: -len(kv[1])):
        P = params(pair); opens = [c for c in grp if c["open"]]
        if not P:
            print(f"--- {pair:26} out of scope v1 | {len(opens)} open stay on production"); continue
        pr, d = price_group(grp, now, P, opens, G, pair)
        if not d:
            print(f"--- {pair:26} [{P['via']}] no open contracts"); continue
        if "unpriced" in d:
            print(f"--- {pair:26} [{P['via']}] UNPRICED: {d['unpriced']}"); continue
        print(f"--- {pair:26} -> {P['world_pair']} [{P['class']}, via {P['via']}] | {d['source']} | q {d['q']:.2f} q0 {d['q0']:.3f} | P(fighting) {d['pi']:.2f}")
        for c in sorted((c for c in grp if c["id"] in pr), key=lambda c: c["date"])[:4]:
            m = fd.get(c["id"], {}); print(f"      {c['question'][:60]:60} | unified {pr[c['id']]:.3f} | prod {m.get('conditional_p')} | mkt {m.get('market_price')}")

def replay():
    cs, _ = UD.load(); G = UD.groups(cs)
    br = defaultdict(list)
    for l in (ROOT / "predictions" / "brier_log.jsonl").read_text().splitlines():
        if l.strip(): r = json.loads(l); br[str(r["market_id"])].append(r)
    rows = []
    for (pair, fp), grp in G.items():
        P = params(pair)
        if not P: continue
        for c in grp:
            rs = br.get(c["id"])
            if c["outcome"] is None or not rs: continue
            last = rs[-1]; fts = [UD.T(x["first_prediction_ts"]) for x in rs if x.get("first_prediction_ts")]
            if not fts or last.get("first_p") is None: continue
            as_of = min(fts)
            if c["known"] and c["known"] <= as_of: continue
            if c["kind"] == "bydate" and c["start"] > as_of: continue
            pr, d = price_group(grp, as_of, P, [c], G, pair)
            if c["id"] not in pr: continue
            mk = last.get("market_p_true_first") if last.get("market_p_true_first") is not None else last.get("market_p_at_first")
            rows.append({"id": c["id"], "gkey": f"{pair}|{fp}", "pair": pair, "kind": c["kind"], "y": c["outcome"], "u": pr[c["id"]], "p": float(last["first_p"]), "m": mk, "src": d["source"]})
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs)
    n = len(rows); bu, bp = B(rows, "u"), B(rows, "p"); mrows = [x for x in rows if x["m"] is not None]
    print(f"\n=== REPLAY: {n} contracts scored at production's first-forecast time ===")
    print(f"  Brier unified {bu:.4f} | production {bp:.4f} | market {B(mrows, 'm'):.4f} (n={len(mrows)}) | paired diff (unified - prod) {bu - bp:+.4f}")
    for y in (1, 0):
        s = [x for x in rows if x["y"] == y]
        if s: print(f"  outcome {'YES' if y else 'NO '}: n={len(s):3} unified {B(s, 'u'):.4f} production {B(s, 'p'):.4f}")
    worst = []
    print("  by pair:")
    for pair in sorted({x["pair"] for x in rows}):
        s = [x for x in rows if x["pair"] == pair]; d = B(s, "u") - B(s, "p")
        print(f"    {pair:26} n={len(s):3} unified {B(s, 'u'):.4f} production {B(s, 'p'):.4f} diff {d:+.4f} | kinds {sorted({x['kind'] for x in s})}")
        if len(s) >= 3 and d > 0.05: worst.append(pair)
    print("  leave-one-pair-out (unified - production):", {p: round(B([x for x in rows if x["pair"] != p], "u") - B([x for x in rows if x["pair"] != p], "p"), 4)
                                                       for p in sorted({x["pair"] for x in rows})})
    a, b = bu <= bp - 0.02, not worst
    print(f"  GATE (a) unified <= production - 0.02: {'PASS' if a else 'FAIL'} | (b) no pair (n>=3) worse by >0.05: {'PASS' if b else 'FAIL ' + str(worst)}")
    print(f"  => {'SHIP' if a and b else 'DO NOT SHIP'}")
    return rows

PUB = ROOT / "pilot" / "unified_publish.json"
RULE = ("A group is priced by the unified engine if in scope, UNLESS the walk-forward replay shows harm: >= 3 replayed contracts "
        "and unified Brier worse than production by > 0.05. Groups with < 3 replayed contracts are published (no evidence of harm). "
        "Lebanon / Saudi->Yemen dailies are priced by unified since Oct 20. Exclusions are computed, never hand-picked.")

def policy():
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        rows = replay()
    by = defaultdict(list)
    for x in rows: by[x["gkey"]].append(x)
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs)
    excl = {g: f"replay n={len(xs)}: unified {B(xs, 'u'):.3f} vs production {B(xs, 'p'):.3f}" for g, xs in by.items() if len(xs) >= 3 and B(xs, "u") - B(xs, "p") > 0.05}
    old = json.loads(PUB.read_text()) if PUB.exists() else {"enabled": True}
    PUB.write_text(json.dumps({"enabled": old.get("enabled", True), "rule": RULE, "excluded": excl, "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                               "replayed_groups": {g: len(xs) for g, xs in by.items()}}, indent=2) + "\n")
    print("excluded by rule:", excl or "none")

_PP = None
def production_prices():
    """{market_id: {...}} for open contracts in in-scope, non-excluded groups, as of now. Cached per process."""
    global _PP
    if _PP is not None: return _PP
    _PP = {}
    pol = json.loads(PUB.read_text()) if PUB.exists() else {"enabled": False}
    if not pol.get("enabled"):
        print("[unified] publishing disabled (pilot/unified_publish.json)"); return _PP
    cs, _ = UD.load(); G = UD.groups(cs); now = dt.datetime.now(dt.timezone.utc)
    for (pair, fp), grp in G.items():
        gk = f"{pair}|{fp}"; P = params(pair)
        if gk in pol.get("excluded", {}) or not P: continue
        try:
            pr, d = price_group(grp, now, P, [c for c in grp if c["open"]], G, pair)
        except Exception as ex:
            print(f"[unified] ERROR {gk}: {ex!r} -- engine price kept"); continue
        if not d or "unpriced" in d: continue
        for mid, p in pr.items():
            _PP[mid] = {"p": p, "group": gk, "source": d["source"], "q": round(d["q"], 3), "pi": round(d["pi"], 3)}
    try:
        import ceasefire_holds as _CH; _CH.combine(_PP)
    except Exception as ex:
        print(f"[holds] combine FAILED ({ex!r}); holds contracts unpriced")
        for k in [k for k in _PP if "@" in k]: _PP.pop(k)
    try:                                   # Oct 22: families B (unified-gap-v0) and C (agreement-v0), pilot/ceasefire_bc.py
        import ceasefire_bc as _BC; _BC.price_all(_PP, G, now)
    except Exception as ex:
        print(f"[ceasefire-bc] FAILED ({ex!r}); effective-ceasefire and agreement contracts unpriced")
    try:                                   # Oct 22: family F, war outcomes (pilot/war_outcomes.py)
        import war_outcomes as _WO; _WO.price_all(_PP, now)
    except Exception as ex:
        print(f"[war-outcome] FAILED ({ex!r}); war-outcome contracts unpriced")
    print(f"[unified] {len(_PP)} open contracts priced in {len({v['group'] for v in _PP.values()})} groups"); return _PP

if __name__ == "__main__":
    if "--replay" in sys.argv: replay()
    elif "--policy" in sys.argv: policy()
    else: dry()

"""docs/deal_overpricing_prereg.md: do Polymarket prices overstate the chance that a ceasefire or peace deal is reached by a date?
Sample: resolved family-C AGREEMENT contracts of type DEAL or CEASEFIRE (pilot/ceasefire_markets.json, classified by
pilot/ceasefire_bc.classify_all). Price = the YES price at a fixed time:
  primary    listing + 24h
  secondary  the midpoint of the scheduled life (listing .. end date)
A contract already resolved by that time is excluded (counted). Measures, clustered by actor pair (one negotiation = one cluster):
  bias = mean(price) - mean(outcome); market Brier; the average return of $1 on NO at that price (fees and spread ignored).
  python analysis/deal_overpricing.py --synthetic
  python analysis/deal_overpricing.py --measure     fetches price histories (cached: pilot/local/deal_prices.json)
Report only.
"""
import sys, json, random, datetime as dt
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot"))
LOCAL = ROOT / "pilot" / "local"; CACHE = LOCAL / "deal_prices.json"; OUT = LOCAL / "deal_overpricing.json"
TYPES = ("DEAL", "CEASEFIRE")
UTC = dt.timezone.utc

def T(s): return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(UTC)

# ── pure pieces (synthetic-checked) ──────────────────────────────────────────────────────────────────────────────────
def price_at(hist, t):
    """YES price: last point at or before t, else the first point within 24h after; None if neither."""
    ts = t.timestamp(); before = [x for x in hist if x["t"] <= ts]
    if before: return float(before[-1]["p"])
    after = [x for x in hist if ts < x["t"] <= ts + 86400]
    return float(after[0]["p"]) if after else None

def stats(rows):
    n = len(rows); mp = sum(r["p"] for r in rows) / n; my = sum(r["y"] for r in rows) / n
    ret = [((1 - r["y"]) / (1 - r["p"]) - 1) for r in rows if r["p"] < 0.99]
    return {"n": n, "mean_price": round(mp, 4), "freq_yes": round(my, 4), "bias": round(mp - my, 4),
            "brier_market": round(sum((r["p"] - r["y"]) ** 2 for r in rows) / n, 4),
            "buy_no_return": round(sum(ret) / len(ret), 4) if ret else None}

def boot(rows, key, B=2000, seed=20261104):
    cl = defaultdict(list)
    for r in rows: cl[r["cluster"]].append(r)
    ks = list(cl); rnd = random.Random(seed); v = []
    for _ in range(B):
        s = [r for k in (rnd.choice(ks) for _ in ks) for r in cl[k]]
        x = stats(s)[key]
        if x is not None: v.append(x)
    v.sort(); return round(v[int(0.025 * len(v))], 4), round(v[int(0.975 * len(v)) - 1], 4)

def verdict(ci): return "OVERPRICED" if ci[0] > 0 else "NOT ESTABLISHED"

# ── data ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def sample():
    import ceasefire_bc as BC
    store = json.loads((ROOT / "pilot" / "ceasefire_markets.json").read_text()); out = []
    for mid, m in store.items():
        info = BC.classify_all(m.get("question"), m.get("description"))
        if not info or info.get("family") != "AGREEMENT" or info.get("type") not in TYPES: continue
        if not m.get("closed") or not m.get("outcomePrices") or not m.get("clobTokenIds") or not m.get("createdAt") or not m.get("closedTime"): continue
        outs, prices, toks = json.loads(m["outcomes"]), json.loads(m["outcomePrices"]), json.loads(m["clobTokenIds"])
        if "yes" not in [o.lower() for o in outs]: continue            # not a Yes/No contract (e.g. "X or Y first?")
        iy = [o.lower() for o in outs].index("yes")
        if prices[iy] not in ("0", "1"): continue
        out.append({"id": mid, "q": m["question"], "type": info["type"], "cluster": info.get("actors") or "unknown", "token": toks[iy],
                    "y": int(prices[iy] == "1"), "created": T(m["createdAt"]), "end": T(m.get("endDate") or m["closedTime"]), "closed": T(m["closedTime"])})
    return out

def history(token, cache):
    if token not in cache:
        import ceasefire_holds as CH
        try: cache[token] = CH._get(f"{CH.CLOB}/prices-history?market={token}&interval=max&fidelity=720").get("history") or []
        except Exception: cache[token] = []
    return cache[token]

def measure():
    LOCAL.mkdir(parents=True, exist_ok=True); cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    S = sample(); res = {"sample": len(S)}
    arms = {"primary_listing_plus_24h": lambda c: c["created"] + dt.timedelta(hours=24),
            "secondary_midpoint": lambda c: c["created"] + (c["end"] - c["created"]) / 2}
    for arm, when in arms.items():
        rows, drop = [], defaultdict(int)
        for c in S:
            t = when(c)
            if c["closed"] <= t: drop[f"resolved before the price time ({'YES' if c['y'] else 'NO'})"] += 1; continue
            p = price_at(history(c["token"], cache), t)
            if p is None: drop["no price"] += 1; continue
            rows.append({**{k: c[k] for k in ("id", "q", "type", "cluster", "y")}, "p": p, "t": t.isoformat()})
        CACHE.write_text(json.dumps(cache))
        if not rows: res[arm] = {"dropped": dict(drop)}; continue
        st = stats(rows); ci = boot(rows, "bias"); rci = boot(rows, "buy_no_return")
        res[arm] = {**st, "bias_ci": ci, "buy_no_return_ci": rci, "clusters": len({r["cluster"] for r in rows}), "dropped": dict(drop),
                    "verdict": verdict(ci) if arm.startswith("primary") else "reported only",
                    "by_type": {ty: stats(s) for ty in TYPES if (s := [r for r in rows if r["type"] == ty])},
                    "by_cluster": {k: stats(s) for k in sorted({r["cluster"] for r in rows}) if (s := [r for r in rows if r["cluster"] == k])},
                    "rows": rows}
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(f"=== DEAL OVERPRICING (docs/deal_overpricing_prereg.md): {len(S)} resolved deal / ceasefire-agreement contracts")
    for arm in arms:
        r = res[arm]
        if "n" not in r: print(f"  {arm}: no rows {r['dropped']}"); continue
        print(f"  {arm}: n={r['n']} in {r['clusters']} clusters | mean price {r['mean_price']:.3f} vs YES rate {r['freq_yes']:.3f} | "
              f"bias {r['bias']:+.4f} 95% {list(r['bias_ci'])} | market Brier {r['brier_market']:.4f} | "
              f"$1 on NO returns {r['buy_no_return']:+.3f} 95% {list(r['buy_no_return_ci'])} | dropped {r['dropped']}")
        for ty, s in r["by_type"].items(): print(f"      {ty:9} n={s['n']:3} price {s['mean_price']:.3f} YES {s['freq_yes']:.3f} bias {s['bias']:+.3f}")
        if arm.startswith("primary"):
            for k, s in r["by_cluster"].items(): print(f"      {k:22} n={s['n']:3} price {s['mean_price']:.3f} YES {s['freq_yes']:.3f} bias {s['bias']:+.3f}")
    print(f"  VERDICT (primary, bias lower bound > 0): {res['primary_listing_plus_24h'].get('verdict')}")

def synthetic():
    h = [{"t": 100, "p": 0.3}, {"t": 200, "p": 0.5}]
    at = lambda s: dt.datetime.fromtimestamp(s, UTC)
    assert price_at(h, at(150)) == 0.3 and price_at(h, at(250)) == 0.5 and price_at(h, at(50)) == 0.3 and price_at(h, at(-90000)) is None
    rows = [{"cluster": f"c{i % 6}", "y": int(i % 5 == 0), "p": 0.45} for i in range(60)]          # YES rate 0.2, price 0.45
    s = stats(rows); assert s["bias"] == 0.25 and abs(s["buy_no_return"] - (0.8 / 0.55 - 1)) < 1e-3, s
    ci = boot(rows, "bias"); assert ci[0] > 0 and verdict(ci) == "OVERPRICED", ci
    fair = [{"cluster": f"c{i % 6}", "y": int(i % 2 == 0), "p": 0.5} for i in range(60)]
    assert verdict(boot(fair, "bias")) == "NOT ESTABLISHED"
    print("synthetic: all checks pass")

if __name__ == "__main__":
    a = sys.argv[1:] or ["--synthetic"]
    {"--synthetic": synthetic, "--measure": measure}[a[0]]()

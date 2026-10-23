"""Replay for docs/pastday_prereg.md (REPORT ONLY): resolved unified-group dailies still open 12h after their day ended, priced at
that moment by the unified engine (outcomes usable only after their close time), vs the market at the same moment.

  python analysis/pastday_replay.py
"""
import sys, json, math, datetime as dt
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot"))
import unified_data as UD, unified_price as UP, ceasefire_holds as CH

TOK = ROOT / "pilot" / "token_cache.json"

def token(mid, cache):
    if mid not in cache:
        try: cache[mid] = (json.loads(CH._get(f"{CH.GAMMA}/markets/{mid}").get("clobTokenIds") or "[]") or [None])[0]
        except Exception: cache[mid] = None
    return cache[mid]

def main():
    cs, _ = UD.load(); G = UD.groups(cs)
    toks = json.loads(TOK.read_text()) if TOK.exists() else {}; prices = json.loads(CH.PRICES.read_text()) if CH.PRICES.exists() else {}
    rows, skip = [], Counter()
    for (pair, fp), grp in G.items():
        P = UP.params(pair)
        if not P or str(fp).startswith("H"): continue
        for c in grp:
            if c["kind"] != "daily" or c["outcome"] is None or not c["known"]: continue
            z = ZoneInfo(c["tz"]); as_of = dt.datetime.combine(c["date"], dt.time(23, 59, 59), z).astimezone(dt.timezone.utc) + dt.timedelta(hours=12)
            if c["known"] <= as_of: skip["settled within 12h of the day's end"] += 1; continue
            pr, d = UP.price_group(grp, as_of, P, [dict(c, open=True)], G, pair)
            if c["id"] not in pr: skip["unpriced: " + str((d or {}).get("unpriced", "no span"))[:50]] += 1; continue
            tk = token(c["id"], toks); mk = CH.market_price(tk, as_of, prices) if tk else None
            if mk is None: skip["no market price"] += 1; continue
            rows.append({"id": c["id"], "pair": pair, "y": c["outcome"], "u": pr[c["id"]], "m": mk, "q": c["question"]})
    TOK.write_text(json.dumps(toks) + "\n"); CH.PRICES.write_text(json.dumps(prices) + "\n")
    cl = lambda p: min(0.999, max(0.001, p))
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs)
    LL = lambda xs, k: -sum(math.log(cl(x[k]) if x["y"] else 1 - cl(x[k])) for x in xs) / len(xs)
    print(f"=== PAST-DAY REPLAY (report only, docs/pastday_prereg.md): n={len(rows)} | skipped {dict(skip)}")
    res = {}
    if rows:
        print(f"  overall  unified Brier {B(rows, 'u'):.4f} logloss {LL(rows, 'u'):.3f} | market Brier {B(rows, 'm'):.4f} logloss {LL(rows, 'm'):.3f}")
        for y in (1, 0):
            s = [x for x in rows if x["y"] == y]
            if s: print(f"  {'YES' if y else 'NO '} n={len(s):3} unified {B(s, 'u'):.4f} market {B(s, 'm'):.4f}")
        for p in sorted({x["pair"] for x in rows}):
            s = [x for x in rows if x["pair"] == p]
            print(f"    {p:28} n={len(s):3} YES {sum(x['y'] for x in s):3} unified {B(s, 'u'):.4f} market {B(s, 'm'):.4f}")
            res[p] = {"n": len(s), "yes": sum(x["y"] for x in s), "brier_unified": round(B(s, "u"), 4), "brier_market": round(B(s, "m"), 4)}
        res["overall"] = {"n": len(rows), "brier_unified": round(B(rows, "u"), 4), "brier_market": round(B(rows, "m"), 4),
                          "logloss_unified": round(LL(rows, "u"), 4), "logloss_market": round(LL(rows, "m"), 4)}
    (ROOT / "analysis" / "pastday_replay_results.json").write_text(json.dumps({"results": res, "skipped": dict(skip), "rows": rows}, indent=1) + "\n")

if __name__ == "__main__":
    main()

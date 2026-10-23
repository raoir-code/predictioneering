"""
docs/refit_prereg.md: unified replay on contracts first forecast on/after 2026-07-01, under (a) the current repo priors and
(b) the held-out priors (pilot/local/heldout/); market at the same moment. Applies the adoption rule:
  Brier(b) <= Brier(a)  ->  pilot/local/candidate/ (production fit) is copied to pilot/local/ (the engine's override)
  else                  ->  no override (pilot/local/priors_world.json removed if present)

  python analysis/refit_compare.py
"""
import sys, json, math, shutil, datetime as dt
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot"))
import unified_price as UP, unified_data as UD

CUT = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
LOCAL = ROOT / "pilot" / "local"

def use_priors(wpath, fpath):
    UP.W = json.loads(Path(wpath).read_text()); UP.F = json.loads(Path(fpath).read_text())
    UP.WK = {(UP.key(k.split("->")[0]), UP.key(k.split("->")[1])): k for k in UP.W["pairs"]}
    UP.CLS = defaultdict(list)
    for n, r in UP.F.items(): UP.CLS[r["class"]].append(r["p_rec_N"])

def score_rows():
    cs, _ = UD.load(); G = UD.groups(cs)
    br = defaultdict(list)
    for l in (ROOT / "predictions" / "brier_log.jsonl").read_text().splitlines():
        if l.strip(): r = json.loads(l); br[str(r["market_id"])].append(r)
    out = {}
    for (pair, fp), grp in G.items():
        if str(fp).startswith("H"): continue
        P = UP.params(pair)
        if not P: continue
        for c in grp:
            rs = br.get(c["id"])
            if c["outcome"] is None or not rs: continue
            fts = [UD.T(x["first_prediction_ts"]) for x in rs if x.get("first_prediction_ts")]
            if not fts: continue
            as_of = min(fts)
            if as_of < CUT or (c["known"] and c["known"] <= as_of) or (c["kind"] == "bydate" and c["start"] > as_of): continue
            pr, d = UP.price_group(grp, as_of, P, [c], G, pair)
            if c["id"] not in pr: continue
            last = rs[-1]; mk = last.get("market_p_true_first") if last.get("market_p_true_first") is not None else last.get("market_p_at_first")
            out[c["id"]] = {"pair": pair, "y": c["outcome"], "u": pr[c["id"]], "m": mk}
    return out

def main():
    use_priors(ROOT / "pilot" / "priors_world.json", ROOT / "analysis" / "world_fits.json"); A = score_rows()
    use_priors(LOCAL / "heldout" / "priors_world.json", LOCAL / "heldout" / "world_fits.json"); Bh = score_rows()
    ids = sorted(set(A) & set(Bh)); rows = [{"pair": A[i]["pair"], "y": A[i]["y"], "a": A[i]["u"], "b": Bh[i]["u"], "m": A[i]["m"]} for i in ids]
    cl = lambda p: min(0.999, max(0.001, p))
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs if x[k] is not None) / max(1, sum(1 for x in xs if x[k] is not None))
    LL = lambda xs, k: -sum(math.log(cl(x[k]) if x["y"] else 1 - cl(x[k])) for x in xs if x[k] is not None) / max(1, sum(1 for x in xs if x[k] is not None))
    print(f"=== REFIT HELD-OUT REPLAY (docs/refit_prereg.md): {len(rows)} contracts first forecast >= {CUT.date()} "
          f"(only-in-a {len(set(A) - set(Bh))}, only-in-b {len(set(Bh) - set(A))})")
    for k, lab in (("a", "current priors"), ("b", "held-out refit"), ("m", "market")):
        print(f"  {lab:15} Brier {B(rows, k):.4f} logloss {LL(rows, k):.3f}")
    for y in (1, 0):
        s = [x for x in rows if x["y"] == y]
        if s: print(f"  {'YES' if y else 'NO '} n={len(s):3} current {B(s, 'a'):.4f} refit {B(s, 'b'):.4f} market {B(s, 'm'):.4f}")
    for p in sorted({x["pair"] for x in rows}):
        s = [x for x in rows if x["pair"] == p]
        print(f"    {p:28} n={len(s):3} YES {sum(x['y'] for x in s):3} current {B(s, 'a'):.4f} refit {B(s, 'b'):.4f} market {B(s, 'm'):.4f}")
    pairs = sorted({x["pair"] for x in rows}); rng = np.random.default_rng(20261023); diffs = []
    for _ in range(2000):
        xs = [x for p in rng.choice(pairs, len(pairs)) for x in rows if x["pair"] == p]
        diffs.append(B(xs, "b") - B(xs, "a"))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    print(f"  cluster bootstrap by pair (2,000): Brier(refit) - Brier(current) = {B(rows, 'b') - B(rows, 'a'):+.4f}  95% [{lo:+.4f}, {hi:+.4f}]")
    adopt = B(rows, "b") <= B(rows, "a")
    if adopt:
        for f in ("priors_world.json", "world_fits.json"): shutil.copy(LOCAL / "candidate" / f, LOCAL / f)
        print("  ADOPTION RULE -> refit ADOPTED: production fit copied to pilot/local/ (engine override, local only)")
    else:
        for f in ("priors_world.json", "world_fits.json"): (LOCAL / f).unlink(missing_ok=True)
        print("  ADOPTION RULE -> refit NOT adopted: current priors stay (no local override)")
    (LOCAL / "refit_compare_result.json").write_text(json.dumps({"n": len(rows), "brier": {k: round(B(rows, k), 4) for k in "abm"},
        "bootstrap_b_minus_a": [round(float(lo), 4), round(float(hi), 4)], "adopted": adopt, "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2) + "\n")

if __name__ == "__main__":
    main()

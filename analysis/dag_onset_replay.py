"""docs/dag_onset_prereg.md: the DAG sets the onset rate h for quiet strike pairs (roadmap step 3).
Scope: resolved strike-template contracts in groups the unified engine declines at the contract's first forecast ("no fitted history
and no positive evidence of fighting"), sub-national targets excluded. Arms, at the first forecast time:
  STANDALONE  the published price logged then (the standalone DAG path: P(A) x the LLM's P(B|A))
  DAG-H       the unified engine with log h = (1 - w) log h_class + w log h_DAG,  h_DAG = -ln(1 - P(A)) / d,  w = 0.5
              (P(A) and d = days remaining, both as logged at that time); everything else from the hazard model unchanged
Held-out priors (data <= 2026-06-30), production hardening and anchors, as in the other replays.
  python analysis/dag_onset_replay.py --synthetic
  python analysis/dag_onset_replay.py --measure     -> pilot/local/dag_onset_replay.json
Report only: nothing here touches production.
"""
import sys, json, math, datetime as dt
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
LOCAL = ROOT / "pilot" / "local"; OUT = LOCAL / "dag_onset_replay.json"
W, W_SENS = 0.5, (0.25, 0.75)
SUBNATIONAL = {"greaterbeirut", "beirut", "moscow", "kyiv", "mecca", "tehran", "telaviv", "jerusalem", "riyadh", "sanaa"}
EPS = 1e-6

# ── pure pieces (synthetic-checked) ──────────────────────────────────────────────────────────────────────────────────
def h_dag(p_a, d):
    """Daily onset rate implied by an onset probability p_a over d days."""
    p = min(max(float(p_a), EPS), 1 - EPS); return -math.log(1 - p) / max(1, int(d))

def pooled(h_class, hd, w):
    return math.exp((1 - w) * math.log(h_class) + w * math.log(hd))

def brier(xs, k): return sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs)

def rule(rows, k="dag", base="standalone"):
    worse = [p for p in sorted({x["pair"] for x in rows}) if len(s := [x for x in rows if x["pair"] == p]) >= 3
             and brier(s, k) - brier(s, base) > 0.05]
    return brier(rows, k) <= brier(rows, base) and not worse, worse

def boot(rows, k="dag", base="standalone", B=2000, seed=20261104):
    pairs = sorted({x["pair"] for x in rows}); rng = np.random.default_rng(seed); ds = []
    for _ in range(B):
        xs = [x for p in rng.choice(pairs, len(pairs)) for x in rows if x["pair"] == p]; ds.append(brier(xs, k) - brier(xs, base))
    lo, hi = np.percentile(ds, [2.5, 97.5]); return round(float(lo), 4), round(float(hi), 4)

# ── replay ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def first_log_rows():
    """market_id -> the predictions-log row of its first forecast (timestamp == brier_log's first_prediction_ts, else the earliest)."""
    br = {}
    for l in (ROOT / "predictions" / "brier_log.jsonl").read_text().splitlines():
        if l.strip(): r = json.loads(l); br[str(r["market_id"])] = r
    logs = defaultdict(list)
    for l in (ROOT / "predictions" / "log.jsonl").read_text().splitlines():
        if l.strip(): r = json.loads(l); logs[str(r["market_id"])].append(r)
    out = {}
    for mid, b in br.items():
        L = sorted(logs.get(mid, []), key=lambda r: r["timestamp"])
        if not L: continue
        ft = b.get("first_prediction_ts"); hit = [r for r in L if ft and r["timestamp"][:19] == ft[:19]]
        out[mid] = (hit or L)[0]
    return out

def measure():
    import refit_compare as RC, unified_price as UP, unified_data as UD
    RC.use_priors(LOCAL / "heldout" / "priors_world.json", LOCAL / "heldout" / "world_fits.json")
    UP.PHASE = None
    cs, _ = UD.load(); G = UD.groups(cs); first = first_log_rows(); rows, skipped = [], defaultdict(int)
    for (pair, fp), grp in G.items():
        if str(fp).startswith("H"): continue
        if pair.split("->")[1] in SUBNATIONAL: skipped["sub-national target"] += len(grp); continue
        P = UP.params(pair)
        if not P or P["via"] != "class_prior": continue
        for c in grp:
            r = first.get(c["id"])
            if c["outcome"] is None or r is None: continue
            as_of = UD.T(r["timestamp"])
            if (c["known"] and c["known"] <= as_of) or (c["kind"] == "bydate" and c["start"] > as_of): skipped["post-event or pre-listing"] += 1; continue
            base_pr, base_d = UP.price_group(grp, as_of, P, [c], G, pair)
            if c["id"] in base_pr: skipped["unified already prices it"] += 1; continue              # out of scope: not declined
            pa, pub, mk = r.get("engine_p"), r.get("conditional_p"), r.get("market_p")
            d = r.get("days_remaining") or max(1, (c["date"] - as_of.date()).days)   # older rows lack days_remaining: deadline - today, as the engine computes it
            if pa is None or pub is None or d is None: skipped["no logged P(A), days or price"] += 1; continue
            row = {"id": c["id"], "pair": pair, "y": c["outcome"], "standalone": float(pub), "m": mk, "p_a": pa, "days": d,
                   "h_class": P["h"], "h_dag": h_dag(pa, d), "q": c["question"]}
            for w, key in ((W, "dag"),) + tuple((ws, f"dag_w{ws}") for ws in W_SENS):
                Pw = dict(P, h=pooled(P["h"], row["h_dag"], w), h_dag=row["h_dag"])
                pr, _ = UP.price_group(grp, as_of, Pw, [c], G, pair); row[key] = pr.get(c["id"])
            if row["dag"] is None: skipped["DAG-H unpriced"] += 1; continue
            rows.append(row)
    if not rows:
        print("no contracts in scope", dict(skipped)); return
    adopt, worse = rule(rows); ci = boot(rows)
    mk = [x for x in rows if x["m"] is not None]
    res = {"n": len(rows), "skipped": dict(skipped), "brier": {"standalone": round(brier(rows, "standalone"), 4), "dag": round(brier(rows, "dag"), 4),
           "market": round(brier(mk, "m"), 4) if mk else None, **{f"dag_w{ws}": round(brier([x for x in rows if x[f'dag_w{ws}'] is not None], f'dag_w{ws}'), 4) for ws in W_SENS}},
           "ci_dag_minus_standalone": ci, "worse_pairs": worse, "adopted": adopt, "rows": rows}
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print(f"=== DAG ONSET (docs/dag_onset_prereg.md): {len(rows)} resolved contracts in scope (skipped {dict(skipped)})")
    print(f"  STANDALONE {res['brier']['standalone']:.4f} | DAG-H (w={W}) {res['brier']['dag']:.4f} | market {res['brier']['market']}"
          f" | w=0.25 {res['brier']['dag_w0.25']:.4f}, w=0.75 {res['brier']['dag_w0.75']:.4f}")
    for y in (1, 0):
        s = [x for x in rows if x["y"] == y]
        if s: print(f"  {'YES' if y else 'NO '} n={len(s):3} STANDALONE {brier(s, 'standalone'):.4f} DAG-H {brier(s, 'dag'):.4f}")
    for p in sorted({x["pair"] for x in rows}):
        s = [x for x in rows if x["pair"] == p]
        print(f"    {p:28} n={len(s):3} YES {sum(x['y'] for x in s):2} STANDALONE {brier(s, 'standalone'):.4f} DAG-H {brier(s, 'dag'):.4f}")
    print(f"  bootstrap by pair: DAG-H - STANDALONE = {res['brier']['dag'] - res['brier']['standalone']:+.4f} 95% {list(ci)} | pairs worse by > 0.05 (n >= 3): {worse or 'none'}")
    print(f"  ADOPTION RULE -> {'ADOPTED (production wiring is the next, separate commit)' if adopt else 'NOT adopted'}")

def synthetic():
    assert abs(h_dag(0.5, 30) - math.log(2) / 30) < 1e-12 and h_dag(1.0, 10) < 1.4 and h_dag(0.0, 10) > 0
    assert math.isclose(pooled(1e-4, 1e-2, 0.5), 1e-3) and math.isclose(pooled(1e-4, 1e-2, 0), 1e-4)
    rows = [{"pair": "a", "y": 0, "standalone": 0.4, "dag": 0.1}, {"pair": "a", "y": 0, "standalone": 0.3, "dag": 0.1},
            {"pair": "a", "y": 1, "standalone": 0.2, "dag": 0.15}, {"pair": "b", "y": 0, "standalone": 0.05, "dag": 0.2}]
    adopt, worse = rule(rows); assert adopt and worse == [], (adopt, worse)
    rows2 = rows + [{"pair": "b", "y": 0, "standalone": 0.05, "dag": 0.6}, {"pair": "b", "y": 0, "standalone": 0.05, "dag": 0.6}]
    adopt, worse = rule(rows2); assert not adopt and worse == ["b"], (adopt, worse)
    print("synthetic: all checks pass")

if __name__ == "__main__":
    a = sys.argv[1:] or ["--synthetic"]
    {"--synthetic": synthetic, "--measure": measure}[a[0]]()

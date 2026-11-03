"""docs/degradation_replay_prereg.md: what does the unified engine lose if the local tables can no longer be refreshed or kept?
Same replay as docs/contract_def_refit_prereg.md (analysis/refit_compare.score_rows: every resolved strike contract first forecast
on or after 2026-07-01, priced at production's first-forecast time, scored on the contract's resolution), four arms:
  FULL      held-out priors (data <= 2026-06-30), production hardening, anchors from the full table (>= 7 days before, as live)
  STALE     FULL, but anchors cut at 2026-06-30: the data ends at the start of the replay; news and resolved windows only after
  NOHARDEN  FULL with hardening off
  REPO      the complete fallback: repo priors, hardening off, no anchors (production with pilot/local/ deleted)
  python analysis/degradation_replay.py --synthetic   rule and anchor-cut checks only
  python analysis/degradation_replay.py --measure     -> pilot/local/degradation_replay.json
Report only: reads pilot/local/, writes one result file there, never touches the engine's own files.
"""
import sys, json, datetime as dt
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
LOCAL = ROOT / "pilot" / "local"; OUT = LOCAL / "degradation_replay.json"
HELDOUT = LOCAL / "heldout"; ANCHORS = LOCAL / "last_strike.json"
REPO_W, REPO_F = ROOT / "pilot" / "priors_world.json", ROOT / "analysis" / "world_fits.json"
CUT_ANCHORS = dt.date(2026, 6, 30)
ARMS = ("STALE", "NOHARDEN", "REPO")

def cut(table, end):
    """Anchor table as if the data had ended on `end`."""
    return {k: sorted(d for d in v if d <= end.isoformat()) for k, v in table.items()}

def brier(xs, k): return sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs) if xs else None

def boot(rows, k, seed=20261103, B=2000):
    """Brier(arm) - Brier(FULL), bootstrap over pairs."""
    pairs = sorted({x["pair"] for x in rows}); rng = np.random.default_rng(seed); ds = []
    for _ in range(B):
        xs = [x for p in rng.choice(pairs, len(pairs)) for x in rows if x["pair"] == p]; ds.append(brier(xs, k) - brier(xs, "full"))
    lo, hi = np.percentile(ds, [2.5, 97.5]); return round(float(lo), 4), round(float(hi), 4)

def grade(ci):
    return "LOAD-BEARING" if ci[0] > 0 else "NOT LOAD-BEARING"

def run_arm(world, fits, harden, anchors):
    import refit_compare as RC, unified_price as UP, unified as U
    RC.use_priors(world, fits); UP.HARDEN = harden; UP._LAST = anchors; UP.PHASE = None
    if hasattr(U, "_mats_c"): U._mats_c.cache_clear()
    return RC.score_rows()

def measure():
    import unified_price as UP
    harden = UP.HARDEN; full_tab = {k: sorted(v) for k, v in json.loads(ANCHORS.read_text()).items()}
    hw, hf = HELDOUT / "priors_world.json", HELDOUT / "world_fits.json"
    R = {"full": run_arm(hw, hf, harden, full_tab), "STALE": run_arm(hw, hf, harden, cut(full_tab, CUT_ANCHORS)),
         "NOHARDEN": run_arm(hw, hf, None, full_tab), "REPO": run_arm(REPO_W, REPO_F, None, {})}
    ids = sorted(set.intersection(*[set(v) for v in R.values()]))
    rows = [{"id": i, "pair": R["full"][i]["pair"], "y": R["full"][i]["y"], "m": R["full"][i]["m"], "full": R["full"][i]["u"],
             **{a: R[a][i]["u"] for a in ARMS}} for i in ids]
    br = __import__("collections").defaultdict(list)
    for l in (ROOT / "predictions" / "brier_log.jsonl").read_text().splitlines():
        if l.strip(): r = json.loads(l); br[str(r["market_id"])].append(r)
    month = {x["id"]: min(r["first_prediction_ts"] for r in br[x["id"]] if r.get("first_prediction_ts"))[:7] for x in rows}
    res = {"n": len(rows), "dropped": {k: len(set(v) - set(ids)) for k, v in R.items()}, "harden": bool(harden),
           "brier": {k: round(brier(rows, k), 4) for k in ("full",) + ARMS}, "market": round(brier([x for x in rows if x["m"] is not None], "m"), 4),
           "arms": {}, "by_month": {}, "by_pair": {}}
    for a in ARMS:
        ci = boot(rows, a); res["arms"][a] = {"d_brier": round(brier(rows, a) - brier(rows, "full"), 4), "ci": ci, "grade": grade(ci),
                                              "yes": round(brier([x for x in rows if x["y"]], a) - brier([x for x in rows if x["y"]], "full"), 4) if any(x["y"] for x in rows) else None,
                                              "no": round(brier([x for x in rows if not x["y"]], a) - brier([x for x in rows if not x["y"]], "full"), 4) if any(not x["y"] for x in rows) else None}
    for m in sorted(set(month.values())):
        s = [x for x in rows if month[x["id"]] == m]; res["by_month"][m] = {"n": len(s), **{a: round(brier(s, a) - brier(s, "full"), 4) for a in ARMS}}
    for p in sorted({x["pair"] for x in rows}):
        s = [x for x in rows if x["pair"] == p]; res["by_pair"][p] = {"n": len(s), "full": round(brier(s, "full"), 4), **{a: round(brier(s, a) - brier(s, "full"), 4) for a in ARMS}}
    res["rows"] = rows; OUT.write_text(json.dumps(res, indent=1))
    print(f"=== DEGRADATION REPLAY: {res['n']} resolved strike contracts first forecast >= 2026-07-01 (dropped per arm {res['dropped']})")
    print(f"  Brier: FULL {res['brier']['full']}  STALE {res['brier']['STALE']}  NOHARDEN {res['brier']['NOHARDEN']}  REPO {res['brier']['REPO']}  | market {res['market']}")
    for a, v in res["arms"].items(): print(f"  {a:9} dBrier {v['d_brier']:+.4f}  95% {list(v['ci'])}  (YES {v['yes']:+}, NO {v['no']:+})  -> {v['grade']}")
    print("  by month of first forecast (dBrier vs FULL):")
    for m, v in res["by_month"].items(): print(f"    {m} n {v['n']:3}  " + "  ".join(f"{a} {v[a]:+.4f}" for a in ARMS))
    print("  by pair:")
    for p, v in sorted(res["by_pair"].items(), key=lambda kv: -kv[1]["n"]): print(f"    {p:28} n {v['n']:3} FULL {v['full']:.4f}  " + "  ".join(f"{a} {v[a]:+.4f}" for a in ARMS))

def synthetic():
    t = {"Israel->Lebanon": ["2026-06-29", "2026-06-30", "2026-07-02"], "X->Y": ["2026-08-01"]}
    assert cut(t, CUT_ANCHORS) == {"Israel->Lebanon": ["2026-06-29", "2026-06-30"], "X->Y": []}
    rows = [{"pair": f"p{i % 6}", "y": i % 2, "full": 0.5 if i % 2 else 0.1, "STALE": 0.3 if i % 2 else 0.4, "NOHARDEN": 0.5 if i % 2 else 0.1}
            for i in range(60)]
    ci = boot(rows, "STALE"); assert ci[0] > 0 and grade(ci) == "LOAD-BEARING", ci
    ci = boot(rows, "NOHARDEN"); assert ci == (0.0, 0.0) and grade(ci) == "NOT LOAD-BEARING", ci
    print("synthetic: all checks pass")

if __name__ == "__main__":
    a = sys.argv[1:] or ["--synthetic"]
    {"--synthetic": synthetic, "--measure": measure}[a[0]]()

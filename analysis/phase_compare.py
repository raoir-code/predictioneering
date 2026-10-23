"""docs/phase_prereg.md: the hardening replay set (analysis/hardening_compare.py), current production (local priors + hardening)
without vs with the rivalry-phase multiplier (HELD-OUT H, kappa from analysis/phase_fit.py --heldout), vs market; then the adoption rule (copies
pilot/local/phase_candidate.json -> pilot/local/phase.json, or removes it).
  python analysis/phase_compare.py
"""
import sys, json, math, shutil
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot")); sys.path.insert(0, str(ROOT / "analysis"))
import unified_price as UP, unified as U
import refit_compare as RC, hardening_compare as HC

LOCAL = ROOT / "pilot" / "local"; CUT = RC.CUT

def run(phase):
    UP.PHASE = phase; U._mats_c.cache_clear()
    rows = RC.score_rows(); rows.update(HC.holds_rows()); return rows

def main():
    if (LOCAL / "priors_world.json").exists(): RC.use_priors(LOCAL / "priors_world.json", LOCAL / "world_fits.json")
    UP.HARDEN = json.loads((LOCAL / "hardening.json").read_text()) if (LOCAL / "hardening.json").exists() else None
    ho = json.loads((LOCAL / "phase_heldout.json").read_text())
    if ho.get("none"):                                       # amendment: held-out CV chose no recency weighting -> no replay, off
        (LOCAL / "phase.json").unlink(missing_ok=True)
        print("=== RIVALRY PHASE: held-out CV chose 'none' (phi = 1) -> no replay; rivalry phase NOT adopted"); return
    A = run(None); Bh = run(ho)
    ids = sorted(set(A) & set(Bh)); rows = [{"pair": A[i]["pair"], "y": A[i]["y"], "a": A[i]["u"], "b": Bh[i]["u"], "m": A[i]["m"]} for i in ids]
    cl = lambda p: min(0.999, max(0.001, p))
    sel = lambda xs, k: [x for x in xs if x[k] is not None]
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in sel(xs, k)) / max(1, len(sel(xs, k)))
    LL = lambda xs, k: -sum(math.log(cl(x[k]) if x["y"] else 1 - cl(x[k])) for x in sel(xs, k)) / max(1, len(sel(xs, k)))
    print(f"=== RIVALRY-PHASE HELD-OUT REPLAY (docs/phase_prereg.md): {len(rows)} contracts from {CUT.date()} "
          f"({sum(1 for i in ids if i.startswith('H'))} holds) | priors: {'local' if (LOCAL / 'priors_world.json').exists() else 'repo'} | "
          f"hardening: {'on' if UP.HARDEN else 'off'} (both arms)")
    for k, lab in (("a", "without phase"), ("b", "with (held-out)"), ("m", "market")): print(f"  {lab:16} Brier {B(rows, k):.4f} logloss {LL(rows, k):.3f}")
    for y in (1, 0):
        s = [x for x in rows if x["y"] == y]
        if s: print(f"  {'YES' if y else 'NO '} n={len(s):3} without {B(s, 'a'):.4f} with {B(s, 'b'):.4f} market {B(s, 'm'):.4f}")
    for p in sorted({x["pair"] for x in rows}):
        s = [x for x in rows if x["pair"] == p]
        print(f"    {p:40} n={len(s):3} YES {sum(x['y'] for x in s):3} without {B(s, 'a'):.4f} with {B(s, 'b'):.4f} market {B(s, 'm'):.4f}")
    pairs = sorted({x["pair"] for x in rows}); rng = np.random.default_rng(20261023); diffs = []
    for _ in range(2000):
        xs = [x for p in rng.choice(pairs, len(pairs)) for x in rows if x["pair"] == p]; diffs.append(B(xs, "b") - B(xs, "a"))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    print(f"  cluster bootstrap by pair (2,000): Brier(with) - Brier(without) = {B(rows, 'b') - B(rows, 'a'):+.4f}  95% [{lo:+.4f}, {hi:+.4f}]")
    adopt = B(rows, "b") <= B(rows, "a")
    if adopt: shutil.copy(LOCAL / "phase_candidate.json", LOCAL / "phase.json"); print("  ADOPTION RULE -> rivalry phase ADOPTED (local override)")
    else: (LOCAL / "phase.json").unlink(missing_ok=True); print("  ADOPTION RULE -> rivalry phase NOT adopted")
    (LOCAL / "phase_compare_result.json").write_text(json.dumps({"n": len(rows), "brier": {k: round(B(rows, k), 4) for k in "abm"},
        "bootstrap": [round(float(lo), 4), round(float(hi), 4)], "adopted": adopt}, indent=2) + "\n")

if __name__ == "__main__":
    main()

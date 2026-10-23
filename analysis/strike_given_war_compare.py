"""docs/strike_given_war_prereg.md + amendments: out-of-time war test (primary) and replay on resolved strike contracts at their first logged engine forecast on/after
2026-07-01 (published price = the engine's): logged price vs the same P(A), P(B|not A) with the HELD-OUT P(B|A), vs the market at that
moment; then the adoption rule (copies pilot/local/strike_given_war_candidate.json -> pilot/local/strike_given_war.json, or removes it).
  python analysis/strike_given_war_compare.py
"""
import sys, json, math, shutil
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot"))
from strike_given_war import qualifies
LOCAL = ROOT / "pilot" / "local"; CUT = "2026-07-01"

def rows(p_emp):
    out = {}; outc = {}
    for l in (ROOT / "predictions" / "brier_log.jsonl").read_text().splitlines():
        if l.strip(): b = json.loads(l); outc[str(b["market_id"])] = b.get("outcome")
    for l in (ROOT / "predictions" / "log.jsonl").read_text().splitlines():
        if not l.strip(): continue
        r = json.loads(l); mid = str(r.get("market_id"))
        if mid in out or outc.get(mid) not in (0, 1) or r.get("timestamp", "") < CUT: continue
        if r.get("pricing_component") not in (None, "engine") or not qualifies(r): continue
        a, c = r["engine_p"], r["p_b_given_not_a_scaled"]
        was = r.get("conditional_p_pre_empirical") or r.get("conditional_p")
        if was is None: continue
        out[mid] = {"pair": r.get("dyad"), "y": outc[mid], "a": was, "b": round(a * p_emp + (1 - a) * c, 4), "m": r.get("market_p"),
                    "pba_was": r.get("p_b_given_a_pre_empirical") or r.get("p_b_given_a"), "pa": a, "q": (r.get("market_label") or "")[:60]}
    return list(out.values())

def main():
    ho = json.loads((LOCAL / "strike_given_war_heldout.json").read_text()); xs = rows(ho["p"])
    cl = lambda p: min(0.999, max(0.001, p))
    sel = lambda xs, k: [x for x in xs if x[k] is not None]
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in sel(xs, k)) / max(1, len(sel(xs, k)))
    LL = lambda xs, k: -sum(math.log(cl(x[k]) if x["y"] else 1 - cl(x[k])) for x in sel(xs, k)) / max(1, len(sel(xs, k)))
    print(f"=== P(STRIKE | WAR) HELD-OUT REPLAY (docs/strike_given_war_prereg.md): {len(xs)} resolved contracts first forecast >= {CUT} | "
          f"held-out P(B|A) {ho['p']:.3f} ({ho['k']}/{ho['n']}) | logged P(B|A) mean {np.mean([x['pba_was'] for x in xs]) if xs else float('nan'):.3f}")
    if not xs: print("  no qualifying contracts: nothing to replay; NOT adopted"); (LOCAL / "strike_given_war.json").unlink(missing_ok=True); return
    for k, lab in (("a", "logged (LLM P(B|A))"), ("b", "empirical (held-out)"), ("m", "market")): print(f"  {lab:21} Brier {B(xs, k):.4f} logloss {LL(xs, k):.3f}")
    for y in (1, 0):
        s = [x for x in xs if x["y"] == y]
        if s: print(f"  {'YES' if y else 'NO '} n={len(s):3} logged {B(s, 'a'):.4f} empirical {B(s, 'b'):.4f} market {B(s, 'm'):.4f}")
    for p in sorted({x["pair"] for x in xs}):
        s = [x for x in xs if x["pair"] == p]
        print(f"    {str(p):28} n={len(s):3} YES {sum(x['y'] for x in s):3} logged {B(s, 'a'):.4f} empirical {B(s, 'b'):.4f} market {B(s, 'm'):.4f} | mean P(A) {np.mean([x['pa'] for x in s]):.3f}")
    moved = sorted(xs, key=lambda x: -abs(x["b"] - x["a"]))[:8]
    for x in moved: print(f"      {x['q']:60} y={x['y']} logged {x['a']:.3f} -> {x['b']:.3f} (market {x['m']})")
    pairs = sorted({x["pair"] for x in xs}); rng = np.random.default_rng(20261023); diffs = []
    for _ in range(2000):
        ss = [x for p in rng.choice(pairs, len(pairs)) for x in xs if x["pair"] == p]; diffs.append(B(ss, "b") - B(ss, "a"))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    print(f"  cluster bootstrap by dyad (2,000): Brier(empirical) - Brier(logged) = {B(xs, 'b') - B(xs, 'a'):+.4f}  95% [{lo:+.4f}, {hi:+.4f}]")
    sys.path.insert(0, str(ROOT / "analysis")); import strike_given_war_fit as SG
    v = SG.validate()
    adopt = bool(v["pass"]) and B(xs, "b") <= B(xs, "a")
    print(f"  rule (amendment 2): out-of-time war test {'PASS' if v['pass'] else 'FAIL'} AND contract replay not worse "
          f"{'PASS' if B(xs, 'b') <= B(xs, 'a') else 'FAIL'}")
    if adopt: shutil.copy(LOCAL / "strike_given_war_candidate.json", LOCAL / "strike_given_war.json"); print("  ADOPTION RULE -> empirical P(strike | war) ADOPTED (local override)")
    else: (LOCAL / "strike_given_war.json").unlink(missing_ok=True); print("  ADOPTION RULE -> NOT adopted")
    (LOCAL / "strike_given_war_compare_result.json").write_text(json.dumps({"n": len(xs), "brier": {k: round(B(xs, k), 4) for k in "abm"},
        "bootstrap": [round(float(lo), 4), round(float(hi), 4)], "validation": v, "adopted": adopt}, indent=2) + "\n")

if __name__ == "__main__":
    main()

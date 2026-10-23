"""docs/hardening_prereg.md: replay on contracts first forecast on/after 2026-07-01, without vs with hardening (HELD-OUT beta, K),
vs market; then the adoption rule (copies pilot/local/hardening_candidate.json -> pilot/local/hardening.json, or removes it).
  Part 1: resolved unified strike contracts at production's first-forecast time (as analysis/refit_compare.py).
  Part 2: resolved holds contracts (single- and two-direction) listed on/after 2026-07-01, priced 24h after listing.
  python analysis/hardening_compare.py
"""
import sys, json, math, shutil, datetime as dt
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot")); sys.path.insert(0, str(ROOT / "analysis"))
import unified_price as UP, unified_data as UD, ceasefire_holds as CH, unified as U
import refit_compare as RC

LOCAL = ROOT / "pilot" / "local"; CUT = RC.CUT

def holds_rows():
    cs, _ = UD.load(); G = UD.groups(cs); S = json.loads(CH.STORE.read_text())
    cache = json.loads(CH.PRICES.read_text()) if CH.PRICES.exists() else {}
    vc = defaultdict(list)
    for c in cs:
        if c.get("holds_of"): vc[c["holds_of"]].append(c)
    out = {}
    for mid, r in S.items():
        info = CH.classify(r.get("question"), r.get("description")); ho = CH.holds_outcome(r)
        if not info or not info.get("dirs") or ho is None: continue
        created, known = CH._ts(r["createdAt"]), CH._ts(r["closedTime"]); as_of = created + dt.timedelta(hours=24)
        if created < CUT or known <= as_of: continue
        if len(info["dirs"]) == 2:
            pu, _ = CH.price_union([mid], G, as_of, S); p = pu.get(mid)
        else:
            p = 1.0
            for c in vc.get(mid, []):
                pr, _ = UP.price_group(G[(c["pair"], c["sfp"])], as_of, UP.params(c["pair"]), [dict(c, open=True)], G, c["pair"])
                if c["id"] not in pr: p = None; break
                p *= (1 - pr[c["id"]])
        if p is None: continue
        tok = json.loads(r.get("clobTokenIds") or "[]"); mk = CH.market_price(tok[0], as_of, cache) if tok else None
        out["H" + mid] = {"pair": "holds:" + "+".join(sorted(f"{UD.norm(a)}->{UD.norm(b)}" for a, b in info["dirs"])), "y": ho, "u": round(p, 4), "m": mk}
    return out

def run(harden):
    UP.HARDEN = harden; U._mats_c.cache_clear()
    rows = RC.score_rows(); rows.update(holds_rows()); return rows

def main():
    RC.use_priors(LOCAL / "priors_world.json", LOCAL / "world_fits.json") if (LOCAL / "priors_world.json").exists() else None
    A = run(None); Bh = run(json.loads((LOCAL / "hardening_heldout.json").read_text()))
    ids = sorted(set(A) & set(Bh)); rows = [{"pair": A[i]["pair"], "y": A[i]["y"], "a": A[i]["u"], "b": Bh[i]["u"], "m": A[i]["m"]} for i in ids]
    cl = lambda p: min(0.999, max(0.001, p))
    sel = lambda xs, k: [x for x in xs if x[k] is not None]
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in sel(xs, k)) / max(1, len(sel(xs, k)))
    LL = lambda xs, k: -sum(math.log(cl(x[k]) if x["y"] else 1 - cl(x[k])) for x in sel(xs, k)) / max(1, len(sel(xs, k)))
    print(f"=== HARDENING HELD-OUT REPLAY (docs/hardening_prereg.md): {len(rows)} contracts from {CUT.date()} "
          f"({sum(1 for i in ids if i.startswith('H'))} holds) | priors: {'local' if (LOCAL / 'priors_world.json').exists() else 'repo'}")
    for k, lab in (("a", "without"), ("b", "with (held-out)"), ("m", "market")): print(f"  {lab:16} Brier {B(rows, k):.4f} logloss {LL(rows, k):.3f}")
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
    if adopt: shutil.copy(LOCAL / "hardening_candidate.json", LOCAL / "hardening.json"); print("  ADOPTION RULE -> hardening ADOPTED (local override)")
    else: (LOCAL / "hardening.json").unlink(missing_ok=True); print("  ADOPTION RULE -> hardening NOT adopted")
    (LOCAL / "hardening_compare_result.json").write_text(json.dumps({"n": len(rows), "brier": {k: round(B(rows, k), 4) for k in "abm"},
        "bootstrap": [round(float(lo), 4), round(float(hi), 4)], "adopted": adopt}, indent=2) + "\n")

if __name__ == "__main__":
    main()

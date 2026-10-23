"""docs/phase_prereg.md + amendment: choose the recency weighting (half-life H, pseudo-exposure kappa) of each pair's restart rate by
prequential cross-validation on the local data. Origins every 28 days from 2018-01-01; at each origin, every pair AT RISK (last strike
more than G = 30 days earlier) is scored on whether a new episode starts within 90 days, using only strikes before the origin:
  P = 1 - exp(-rho x phi x hardening exposure over the 90 days),  rho = (S + 1) / (E + 1 / rho_class)  (pair's long-run rate),
  phi = [(S_H + kappa rho) / (E_H + kappa)] / rho  (pilot/unified_price.py phase_ratio), "none" = phi 1.
Selection: the highest total log likelihood. Gitignored outputs:
  python analysis/phase_fit.py --heldout      data through 2026-06-30 -> pilot/local/phase_heldout.json
  python analysis/phase_fit.py --production   data through the last complete day -> pilot/local/phase_candidate.json
"""
import sys, json, math, datetime as dt
from pathlib import Path
import numpy as np
from scipy.signal import lfilter
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
import theory_test4 as T4, refit_local as RL, unified_price as UP

G, HORIZON, STEP, A = 30, 90, 28, 1.0
FIRST_ORIGIN = dt.date(2018, 1, 1)
H_GRID = (182, 365, 730, 1095, 1826)          # half-life, days
K_GRID = (26, 52, 104, 260)                   # pseudo-exposure, weeks
KEYS = ["none"] + [f"H{H}_k{k}" for H in H_GRID for k in K_GRID]

def disc_sum(x, H):
    """y[o] = sum_{i < o} 0.5^((o - i) / H) x[i], o = 0 .. len(x)."""
    d = 0.5 ** (1.0 / H)
    return lfilter([0.0, d], [1.0, -d], np.concatenate([x, [0.0]]))

def prep(days, D0, n, beta, K):
    ar, ev, m = UP.phase_arrays(sorted(days), D0, n, G, beta, K)
    s = np.zeros(n, bool)
    for d in days:
        if 0 <= (d - D0).days < n: s[(d - D0).days] = True
    last = np.concatenate([[-10 ** 9], np.maximum.accumulate(np.where(s, np.arange(n), -10 ** 9))[:-1]])
    return {"ar": ar, "ev": ev, "last": last, "cS": np.concatenate([[0.0], np.cumsum(ev)]), "cE": np.concatenate([[0.0], np.cumsum(m)]) / 7.0,
            "dS": {H: disc_sum(ev.astype(float), H) for H in H_GRID}, "dE": {H: disc_sum(m, H) / 7.0 for H in H_GRID}}

def cv(P, end, beta, K):
    D0 = min(min(v) for v in P.values()); n = (end - D0).days + 1
    arr = {p: prep(days, D0, n, beta, K) for p, days in P.items()}
    ll = {k: 0.0 for k in KEYS}; br = {k: 0.0 for k in KEYS}; N = Y = 0; o = (FIRST_ORIGIN - D0).days; origins = 0
    while o + HORIZON <= n:
        origins += 1
        rc = sum(a["cS"][o] for a in arr.values()) / max(1e-9, sum(a["cE"][o] for a in arr.values()))
        for a in arr.values():
            if not a["ar"][o] or a["cE"][o] <= 0: continue
            rho = (a["cS"][o] + A) / (a["cE"][o] + A / rc)
            t = np.maximum(1.0, (o - a["last"][o] + np.arange(HORIZON) - G) / 7.0); expo = float((t ** beta / K).sum()) / 7.0
            y = bool(a["ev"][o:o + HORIZON].any()); N += 1; Y += y
            for k in KEYS:
                if k == "none": phi = 1.0
                else:
                    H, kap = (int(x[1:]) for x in k.split("_"))
                    phi = ((a["dS"][H][o] + kap * rho) / (a["dE"][H][o] + kap)) / rho
                pr = min(1 - 1e-9, max(1e-9, 1 - math.exp(-rho * phi * expo)))
                ll[k] += math.log(pr if y else 1 - pr); br[k] += (pr - y) ** 2
        o += STEP
    rc_end = sum(a["cS"][n] for a in arr.values()) / max(1e-9, sum(a["cE"][n] for a in arr.values()))
    return {"origins": origins, "scored": N, "starts": Y, "rho_class": rc_end, "ll": ll, "brier": {k: v / max(1, N) for k, v in br.items()}}

def fit(end, out, hard_file):
    hard = json.loads(hard_file.read_text()) if hard_file.exists() else None
    beta, K = (hard["beta"], hard["K"]) if hard else (0.0, 1.0)
    P, cls, e = T4.strike_days(end)
    r = cv(P, e, beta, K); best = max(KEYS, key=lambda k: r["ll"][k])
    res = {"none": best == "none", "choice": best, "G": G, "beta": beta, "K": K, "rho_class": r["rho_class"],
           "scored": r["scored"], "starts": r["starts"], "origins": r["origins"],
           "ll_gain_vs_none": r["ll"][best] - r["ll"]["none"], "brier_none": r["brier"]["none"], "brier_choice": r["brier"][best],
           "cv": {k: [round(r["ll"][k], 2), round(r["brier"][k], 5)] for k in KEYS}, "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if best != "none":
        H, kap = (int(x[1:]) for x in best.split("_")); res.update({"H_days": H, "kappa_weeks": kap})
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(res, indent=1) + "\n")
    print(f"data through {e} | hardening beta {beta:+.3f} | {r['origins']} origins, {r['scored']:,} pair-origins at risk, {r['starts']} starts")
    print(f"  none        loglik {r['ll']['none']:10.2f}  Brier {r['brier']['none']:.5f}")
    for k in sorted(KEYS[1:], key=lambda k: -r["ll"][k])[:5]:
        print(f"  {k:11} loglik {r['ll'][k]:10.2f}  Brier {r['brier'][k]:.5f}")
    print(f"  CHOICE: {best} (log-lik gain vs none {res['ll_gain_vs_none']:+.2f}) -> {out}")
    return res

def show(res, day):
    """phi today for the pairs we trade (uses pilot/unified_price.py's own rule)."""
    if res["none"]: print("  phi = 1 for every pair (CV chose none)"); return
    UP.PHASE = res
    for p in ("israel->iran", "iran->israel", "unitedstates->iran", "unitedstates->yemen", "israel->syria", "israel->lebanon",
              "iran->saudiarabia", "saudiarabia->yemen", "iran->iraq", "pakistan->afghanistan"):
        wk, _ = UP.world_pair(p); d = UP.phase_detail(p, day)
        print(f"  {p:24} {str(wk):30} " + (f"phi {d['phi']:.2f} | starts {d['starts']} (discounted {d['starts_disc']}), long-run "
              f"{d['rho_per_yr']}/yr" if d else "phi 1 (no world pair or no strikes)"))

if __name__ == "__main__":
    if "--heldout" in sys.argv: fit(dt.date(2026, 6, 30), RL.LOCAL / "phase_heldout.json", RL.LOCAL / "hardening_heldout.json")
    elif "--production" in sys.argv:
        f = RL.LOCAL / "hardening.json"
        show(fit(None, RL.LOCAL / "phase_candidate.json", f if f.exists() else RL.LOCAL / "hardening_candidate.json"), dt.date.today())
    else: print(__doc__)

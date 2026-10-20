"""
Theory test 1 (Oct 20), PRE-REGISTERED before running. External data only (ACLED 2015-2025, worldwide cross-border).
H1 (information revelation; Slantchev 2003, Smith & Stam 2004, Powell 2004): within a fighting episode, the hazard that the
   episode ends tomorrow RISES with cumulative strike days so far, holding elapsed days fixed.
H2 (information vs commitment; Fearon 2004, Powell 2006): that effect is STRONGER for state_vs_state pairs than for
   cross_border_nonstate pairs (commitment problems typical with non-state armed groups).
Episodes, 4 definitions: (V) Viterbi path of each pair's fitted two-state model; (G7, G14, G30) gap rules: an episode ends
   after 7 / 14 / 30 quiet days. Caveat: V comes from a constant-hazard model, which can mute duration effects.
Model: discrete-time hazard logit, end_next ~ log1p(cum strikes) + log(elapsed) + class + class x log1p(cum), errors
   clustered by pair. DECISION: H1 supported if the log1p(cum) effect (baseline = state_vs_state) is > 0 with p < 0.05 under V
   AND at least 2 of 3 gap definitions; H2 supported if (state_vs_state minus cross_border_nonstate) slope > 0 by the same rule.
"""
import json, math, sys, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from scipy.linalg import expm
sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_fits as WF

ROOT = Path(__file__).resolve().parent.parent
FITS = json.loads((ROOT / "analysis" / "world_fits.json").read_text())

def viterbi(y, f):
    h, mu, pF, pN = f["h_per_day"], f["mu_per_day"], f["p_rec_F"], f["p_rec_N"]
    A = np.log(expm(np.array([[-h, h], [mu, -mu]])))
    def em(s, v):
        if v is None: return 0.0
        p = pF if s else pN; p = min(max(p, 1e-9), 1 - 1e-9); return math.log(p if v else 1 - p)
    d = np.array([math.log(mu / (h + mu)) + em(0, y[0]), math.log(h / (h + mu)) + em(1, y[0])]); back = []
    for v in y[1:]:
        c = d[:, None] + A; b = c.argmax(0); d = c.max(0) + np.array([em(0, v), em(1, v)]); back.append(b)
    s = [int(d.argmax())]
    for b in reversed(back): s.append(int(b[s[-1]]))
    return s[::-1]

def episodes_viterbi(y, path):
    out, i = [], 0
    while i < len(path):
        if path[i] == 1:
            j = i
            while j + 1 < len(path) and path[j + 1] == 1: j += 1
            out.append((i, j, j + 1 < len(path))); i = j + 1
        else: i += 1
    return out

def episodes_gap(y, G):
    act = [i for i, v in enumerate(y) if v == 1]; out = []
    if not act: return out
    s = p = act[0]
    for a in act[1:]:
        if a - p > G: out.append((s, p, p + G < len(y))); s = a
        p = a
    out.append((s, p, p + G < len(y)))
    return out

def panel(defn):
    rows = []
    for key, p in WF.build().items():
        f = FITS.get(key)
        if not f or f.get("class") not in ("state_vs_state", "cross_border_nonstate") or f["active_days"] < 30: continue
        y = WF.series(p)
        eps = episodes_viterbi(y, viterbi(y, f)) if defn == "V" else episodes_gap(y, int(defn[1:]))
        for a, b, observed_end in eps:
            cum = 0
            for t in range(a, b + 1):
                cum += 1 if y[t] == 1 else 0
                if t == b and not observed_end: break
                rows.append({"pair": key, "cls": f["class"], "end_next": int(t == b), "lcum": math.log1p(cum), "lel": math.log(t - a + 1)})
    return pd.DataFrame(rows)

def main():
    res = {}
    for defn in ("V", "G7", "G14", "G30"):
        df = panel(defn)
        df["cls"] = pd.Categorical(df["cls"], categories=["state_vs_state", "cross_border_nonstate"])
        m = smf.logit("end_next ~ lcum * cls + lel", data=df).fit(disp=0, cov_type="cluster", cov_kwds={"groups": pd.factorize(df["pair"])[0]})
        b1, p1 = m.params["lcum"], m.pvalues["lcum"]
        bi, pi = -m.params["lcum:cls[T.cross_border_nonstate]"], m.pvalues["lcum:cls[T.cross_border_nonstate]"]
        res[defn] = (b1 > 0 and p1 < 0.05, bi > 0 and pi < 0.05)
        print(f"  {defn:4} rows {len(df):6} pairs {df['pair'].nunique():2} episodes ended {int(df['end_next'].sum()):5} | "
              f"H1 slope(cum, state_vs_state) {b1:+.3f} (p {p1:.3f}) | H2 extra slope vs nonstate {bi:+.3f} (p {pi:.3f}) | elapsed {m.params['lel']:+.3f} (p {m.pvalues['lel']:.3f})")
    for h, k in (("H1", 0), ("H2", 1)):
        ok = res["V"][k] and sum(res[d][k] for d in ("G7", "G14", "G30")) >= 2
        print(f"  {h}: {'SUPPORTED' if ok else 'NOT SUPPORTED'} under the pre-registered rule ({[d for d in res if res[d][k]]} pass)")

if __name__ == "__main__":
    main()

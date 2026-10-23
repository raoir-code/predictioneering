"""Theory test 4 (pre-registered, docs/theory_test4_prereg.md): does peace harden? Discrete-time hazard of resuming strikes
over weeks of quiet spells, per directed pair, from the local offline pull (gitignored). Strike filter and actor rules as
analysis/world_fits.py. Output: analysis/theory_test4_results.json (coefficients and counts only).

  python analysis/theory_test4.py
"""
import sys, json, math, datetime as dt
from collections import defaultdict
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm
sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_fits as WF, refit_local as RL

def strike_days(end=None):
    end = end or RL.last_complete_day(); P = defaultdict(set); kind = {}; tk = defaultdict(lambda: defaultdict(int))
    for r in RL.rows():
        d = dt.date.fromisoformat(r["event_date"][:10])
        if d > end or r.get("sub_event_type") not in WF.SUBS or WF.MARITIME.search(r.get("country") or ""): continue
        key, k = WF.ident(r.get("actor1"))
        if not key or key == r.get("country"): continue
        n = f"{key}->{r['country']}"; P[n].add(d); kind[n] = k
        t = WF.target_kind(r.get("actor2"))
        if t: tk[n][t] += 1
    cls = {n: WF.klass(kind[n], tk[n]) for n in P}
    return P, cls, end

def spells(days, G, end):
    ds = sorted(days); eps = []; s = ds[0]; prev = ds[0]
    for d in ds[1:]:
        if (d - prev).days > G: eps.append((s, prev)); s = d
        prev = d
    eps.append((s, prev)); out = []
    for i, (a, b) in enumerate(eps):
        start = b + dt.timedelta(G + 1)        # amendment: the spell's clock starts once the episode counts as over (a restart is
                                               # impossible in the first G days by construction; starting earlier fakes rising hazards)
        if i + 1 < len(eps): out.append((start, eps[i + 1][0], 1, i + 1, (b - a).days + 1, eps[:i + 1]))
        elif start <= end: out.append((start, end, 0, i + 1, (b - a).days + 1, eps[:i + 1]))
    return out

def design(P, cls, end, G, robust=False):
    rows = []
    for n, days in P.items():
        for k, (s, e, ev, prior, plen, past) in enumerate(spells(days, G, end)):
            weeks = max(1, math.ceil(((e - s).days + 1) / 7))
            prev_rate = None
            if robust:
                done = past[:-1]                                           # spells that ended before this one began
                quiet = sum(((past[j + 1][0] - past[j][1]).days for j in range(len(done))), 0)
                prev_rate = (len(done) / (quiet / 365.25)) if quiet > 0 else 0.0
            for w in range(1, weeks + 1):
                rows.append({"pair": n, "y": int(ev and w == weeks), "lw": math.log(w), "lprior": math.log1p(prior), "lplen": math.log(plen),
                             "cls": cls[n], **({"lprev": math.log1p(prev_rate)} if robust else {})})
    return pd.DataFrame(rows)

def fit(df, robust=False):
    X = pd.get_dummies(df[["lw", "lprior", "lplen"] + (["lprev"] if robust else []) + ["cls"]], columns=["cls"], drop_first=True, dtype=float)
    r = sm.Logit(df["y"].astype(float), sm.add_constant(X)).fit(disp=0, cov_type="cluster", cov_kwds={"groups": pd.factorize(df["pair"])[0]})
    return r

def main():
    P, cls, end = strike_days(); out = {"data_end": "last complete day of the local data", "pairs": len(P)}
    print(f"pairs with strikes: {len(P)}")
    ok = True
    for G in (14, 30, 60):
        df = design(P, cls, end, G); r = fit(df)
        b, p = float(r.params["lw"]), float(r.pvalues["lw"])
        rb = fit(design(P, cls, end, G, robust=True), robust=True)
        out[f"G{G}"] = {"spell_weeks": int(len(df)), "events": int(df.y.sum()), "spells": int(df.groupby("pair").y.size().shape[0]),
                        "coef_log_weeks_since": b, "p": p, "coef_prior_episodes": float(r.params["lprior"]), "coef_prev_episode_len": float(r.params["lplen"]),
                        "robust_coef_log_weeks_since": float(rb.params["lw"]), "robust_p": float(rb.pvalues["lw"]), "robust_coef_prev_rate": float(rb.params["lprev"])}
        ok &= (b < 0 and p < 0.05)
        print(f"G{G:2}: {len(df):7,} spell-weeks, {int(df.y.sum()):5} restarts | log(weeks since) {b:+.3f} (p {p:.3g}) | prior eps {r.params['lprior']:+.3f} | "
              f"prev ep length {r.params['lplen']:+.3f} || robust: {rb.params['lw']:+.3f} (p {rb.pvalues['lw']:.3g}), prev rate {rb.params['lprev']:+.3f}")
    out["H5"] = "SUPPORTED" if ok else "NOT SUPPORTED"
    print("H5 (all three: coef < 0, p < .05):", out["H5"])
    (Path(__file__).resolve().parent / "theory_test4_results.json").write_text(json.dumps(out, indent=2) + "\n")

if __name__ == "__main__":
    main()

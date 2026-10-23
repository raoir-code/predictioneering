"""Theory test 5 (pre-registered, docs/theory_test5_prereg.md): does a pair's RECENT record of starting episodes predict resuming
strikes beyond its long-run record? Test 4's design plus two covariates built only from episodes that started before each spell-week.
Output: analysis/theory_test5_results.json (coefficients and counts only).

  python analysis/theory_test5.py
"""
import sys, json, math, bisect, datetime as dt
from pathlib import Path
import pandas as pd, statsmodels.api as sm
sys.path.insert(0, str(Path(__file__).resolve().parent))
import theory_test4 as T4

def episode_starts(days, G):
    ds = sorted(days); out = [ds[0]]; prev = ds[0]
    for d in ds[1:]:
        if (d - prev).days > G: out.append(d)
        prev = d
    return out

def design(P, cls, end, G):
    rows = []
    for n, days in P.items():
        starts = episode_starts(days, G); first = min(days)
        for s, e, ev, prior, plen, past in T4.spells(days, G, end):
            weeks = max(1, math.ceil(((e - s).days + 1) / 7))
            # Amendment (before real data): the record is measured at the START of the episode that opened this spell, EXCLUDING
            # that episode, and held fixed through the spell (otherwise `recent` falls to 0 exactly 730 days after it, a second
            # clock that absorbs the hardening shape: synthetic data with no regime shifts came out "supported").
            day = past[-1][0]; i = bisect.bisect_left(starts, day)
            recent = sum(1 for x in starts[:i] if (day - x).days <= 730)
            cut = day - dt.timedelta(730); older_n = sum(1 for x in starts[:i] if x < cut)
            span = (cut - first).days / 365.25
            older = (older_n / span) if (older_n and span > 0) else 0.0
            for w in range(1, weeks + 1):
                rows.append({"pair": n, "y": int(ev and w == weeks), "lw": math.log(w), "lprior": math.log1p(prior), "lplen": math.log(plen),
                             "recent": math.log1p(recent), "older": math.log1p(older), "cls": cls[n]})
    return pd.DataFrame(rows)

def fit(df):
    X = pd.get_dummies(df[["lw", "lprior", "lplen", "recent", "older", "cls"]], columns=["cls"], drop_first=True, dtype=float)
    return sm.Logit(df["y"].astype(float), sm.add_constant(X)).fit(disp=0, cov_type="cluster", cov_kwds={"groups": pd.factorize(df["pair"])[0]})

def main():
    P, cls, end = T4.strike_days(); out = {"pairs": len(P)}; ok = True
    for G in (14, 30, 60):
        df = design(P, cls, end, G); r = fit(df)
        b, p = float(r.params["recent"]), float(r.pvalues["recent"])
        out[f"G{G}"] = {"spell_weeks": int(len(df)), "restarts": int(df.y.sum()), "recent_coef": b, "recent_p": p,
                        "older_coef": float(r.params["older"]), "older_p": float(r.pvalues["older"]), "log_weeks_coef": float(r.params["lw"])}
        ok &= (b > 0 and p < 0.05)
        print(f"G{G:2}: {len(df):7,} spell-weeks, {int(df.y.sum()):5} restarts | recent {b:+.3f} (p {p:.3g}) | older {r.params['older']:+.3f} "
              f"(p {r.pvalues['older']:.3g}) | log(weeks since) {r.params['lw']:+.3f}")
    out["H6"] = "SUPPORTED" if ok else "NOT SUPPORTED"
    print("H6 (all three: recent coef > 0, p < .05):", out["H6"])
    (Path(__file__).resolve().parent / "theory_test5_results.json").write_text(json.dumps(out, indent=2) + "\n")

if __name__ == "__main__":
    main()

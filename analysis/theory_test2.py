"""Theory test 2 (pre-registered, docs/theory_test2_prereg.md): does recurrence predict longer episodes? UCDP GED v26.1."""
import json, numpy as np, pandas as pd, statsmodels.api as sm
g = pd.read_csv("data/external/ucdp/GEDEvent_v26_1.csv", low_memory=False,
                usecols=["dyad_new_id", "type_of_violence", "date_prec", "date_start"])
g = g[(g.type_of_violence == 1) & (g.date_prec <= 3)].copy()
g["d"] = pd.to_datetime(g.date_start).dt.normalize()
DATA_END = g.d.max(); BURN = pd.Timestamp("1992-01-01")
print(f"events {len(g):,} | dyads {g.dyad_new_id.nunique():,} | {g.d.min().date()} .. {DATA_END.date()}")
first = g.groupby("dyad_new_id").d.min()
days = g.groupby("dyad_new_id").d.apply(lambda s: np.sort(s.unique()))
out = {}
for G in (7, 14, 30):
    ys, el, pr, ag, cl = [], [], [], [], []; n_ep = 0; lens = []
    for dy, arr in days.items():
        gaps = np.diff(arr).astype("timedelta64[D]").astype(int)
        cuts = np.where(gaps > G)[0]
        starts = np.r_[arr[0], arr[cuts + 1]]; ends = np.r_[arr[cuts], arr[-1]]
        for k, (s, e) in enumerate(zip(starts, ends)):
            if pd.Timestamp(s) < BURN or (DATA_END - pd.Timestamp(e)).days <= G: continue
            L = int((e - s).astype("timedelta64[D]").astype(int)) + 1
            y = np.zeros(L); y[-1] = 1
            ys.append(y); el.append(np.log(np.arange(1, L + 1))); pr.append(np.full(L, np.log1p(k)))
            ag.append(np.full(L, np.log1p((pd.Timestamp(s) - first[dy]).days / 365.25))); cl.append(np.full(L, dy))
            n_ep += 1; lens.append(L)
    y = np.concatenate(ys); X = pd.DataFrame({"log_elapsed": np.concatenate(el), "log1p_prior": np.concatenate(pr),
                                               "log1p_age": np.concatenate(ag)})
    X = sm.add_constant(X); grp = np.concatenate(cl)
    r = sm.Logit(y, X).fit(disp=0, cov_type="cluster", cov_kwds={"groups": grp})
    b, p = float(r.params["log1p_prior"]), float(r.pvalues["log1p_prior"])
    out[f"G{G}"] = {"episodes": n_ep, "rows": int(len(y)), "median_len_days": float(np.median(lens)),
                    "prior_coef": b, "prior_p": p, "elapsed_coef": float(r.params["log_elapsed"]), "age_coef": float(r.params["log1p_age"])}
    print(f"G{G:2}: episodes {n_ep:6,} | median length {np.median(lens):5.0f} d | prior coef {b:+.3f} (p {p:.3g}) | "
          f"elapsed {r.params['log_elapsed']:+.3f} | age {r.params['log1p_age']:+.3f}")
ok = all(v["prior_coef"] < 0 and v["prior_p"] < 0.05 for v in out.values())
out["H3"] = "SUPPORTED" if ok else "NOT SUPPORTED"; print("H3 (all three: coef < 0, p < .05):", out["H3"])
json.dump(out, open("analysis/theory_test2_results.json", "w"), indent=2)

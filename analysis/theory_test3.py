"""Theory test 3 (pre-registered, docs/theory_test3_prereg.md): do recent power shifts predict longer state-vs-state episodes?
UCDP GED v26.1 + SIPRI Military Expenditure 1949-2025 v1.2 (constant 2024 US$). Mirrors analysis/theory_test2.py.

  python analysis/theory_test3.py [GED_CSV] [SIPRI_XLSX]
"""
import json, re, sys, hashlib, numpy as np, pandas as pd, statsmodels.api as sm
from collections import Counter

GED = sys.argv[1] if len(sys.argv) > 1 else "data/external/ucdp/GEDEvent_v26_1.csv"
SIPRI = sys.argv[2] if len(sys.argv) > 2 else "data/external/sipri/SIPRI-Milex-data-1949-2025_v1.2.xlsx"
SIPRI_SHA = "6cc3a30b1064f9f02e60236667eef82e08cad42910ce630909d004ad2c398a9d"
ALIAS = {"DR Congo": ["Congo, DR"], "Congo": ["Congo, Republic"], "Ivory Coast": ["Cote d'Ivoire"], "South Korea": ["Korea, South"],
         "Vietnam": ["Viet Nam"], "Kyrgyzstan": ["Kyrgyz Republic"], "Yugoslavia": ["Serbia"], "Turkey": ["Turkiye", "Türkiye", "Turkey"],
         "United States": ["United States of America"], "Czech Republic": ["Czechia"], "Macedonia": ["North Macedonia"],
         "Gambia": ["Gambia, The"], "Bosnia-Herzegovina": ["Bosnia and Herzegovina"]}          # lookup table (pre-registered)
BY_ERA = {("Russia", 1991): "USSR", ("Yemen", 1989): "Yemen, North"}                       # name for years <= the given year

def load_sipri(path):
    assert hashlib.sha256(open(path, "rb").read()).hexdigest() == SIPRI_SHA, "SIPRI file hash differs from the pre-registration"
    raw = pd.read_excel(path, sheet_name="Constant (2024) US$", header=None)
    hi = raw.index[raw[0] == "Country"][0]; hdr = raw.iloc[hi].tolist()
    M = {}
    for _, r in raw.iloc[hi + 1:].iterrows():
        if not isinstance(r[0], str): continue
        for j, y in enumerate(hdr):
            if isinstance(y, (int, float)) and not pd.isna(y) and isinstance(r[j], (int, float)) and not pd.isna(r[j]) and r[j] > 0:
                M[(r[0].strip(), int(y))] = float(r[j])
    return M

def govs(side):
    return [re.sub(r"\s*\(.*?\)\s*", "", g.replace("Government of", "")).strip()
            for g in re.split(r",\s*(?=Government of)", side or "") if g.strip().startswith("Government of")]

def milex(M, name, year, unmatched):
    cands = []
    for (n, upto), alt in BY_ERA.items():
        if name == n and year <= upto: cands.append(alt)
    cands += [name] + ALIAS.get(name, [])
    for c in cands:
        if (c, year) in M: return M[(c, year)]
    if not any(k[0] in cands for k in M): unmatched[name] += 1
    return None

def side_m(M, names, year, unmatched):
    vals = [milex(M, n, year, unmatched) for n in names]
    return None if any(v is None for v in vals) or not vals else sum(vals)

def main():
    M = load_sipri(SIPRI)
    g = pd.read_csv(GED, low_memory=False, usecols=["dyad_new_id", "type_of_violence", "date_prec", "date_start", "side_a", "side_b"])
    g = g[(g.type_of_violence == 1) & (g.date_prec <= 3) & g.side_b.astype(str).str.startswith("Government of")].copy()
    g["d"] = pd.to_datetime(g.date_start).dt.normalize()
    DATA_END = pd.to_datetime(pd.read_csv(GED, low_memory=False, usecols=["date_start"]).date_start).max().normalize()
    BURN = pd.Timestamp("1992-01-01")
    sides = g.groupby("dyad_new_id")[["side_a", "side_b"]].first()
    print(f"interstate events {len(g):,} | dyads {g.dyad_new_id.nunique():,} | data end {DATA_END.date()}")
    first = g.groupby("dyad_new_id").d.min()
    days = g.groupby("dyad_new_id").d.apply(lambda s: np.sort(s.unique()))
    out, unmatched = {}, Counter()
    for G in (7, 14, 30):
        ys, el, pr, ag, sh, lv, cl = [], [], [], [], [], [], []; n_ep = 0; lens = []; excl = Counter(); dy_used = set()
        for dy, arr in days.items():
            A, B = govs(sides.loc[dy, "side_a"]), govs(sides.loc[dy, "side_b"])
            gaps = np.diff(arr).astype("timedelta64[D]").astype(int); cuts = np.where(gaps > G)[0]
            starts = np.r_[arr[0], arr[cuts + 1]]; ends = np.r_[arr[cuts], arr[-1]]
            for k, (s, e) in enumerate(zip(starts, ends)):
                if pd.Timestamp(s) < BURN: excl["before 1992"] += 1; continue
                if (DATA_END - pd.Timestamp(e)).days <= G: excl["right-censored"] += 1; continue
                y0 = pd.Timestamp(s).year
                ma1, mb1, ma4, mb4 = (side_m(M, A, y0 - 1, unmatched), side_m(M, B, y0 - 1, unmatched),
                                      side_m(M, A, y0 - 4, unmatched), side_m(M, B, y0 - 4, unmatched))
                if None in (ma1, mb1, ma4, mb4): excl["missing expenditure"] += 1; continue
                r1, r4 = np.log(ma1 / mb1), np.log(ma4 / mb4)
                L = int((e - s).astype("timedelta64[D]").astype(int)) + 1
                y = np.zeros(L); y[-1] = 1
                ys.append(y); el.append(np.log(np.arange(1, L + 1))); pr.append(np.full(L, np.log1p(k)))
                ag.append(np.full(L, np.log1p((pd.Timestamp(s) - first[dy]).days / 365.25)))
                sh.append(np.full(L, abs(r1 - r4))); lv.append(np.full(L, abs(r1))); cl.append(np.full(L, dy))
                n_ep += 1; lens.append(L); dy_used.add(dy)
        if n_ep < 10:
            out[f"G{G}"] = {"episodes": n_ep, "excluded": dict(excl), "note": "too few episodes to fit"}; print(f"G{G}: {n_ep} episodes -- not fitted"); continue
        X = sm.add_constant(pd.DataFrame({"power_shift": np.concatenate(sh), "power_gap": np.concatenate(lv), "log_elapsed": np.concatenate(el),
                                          "log1p_prior": np.concatenate(pr), "log1p_age": np.concatenate(ag)}))
        yv = np.concatenate(ys); grp = np.concatenate(cl)
        r = sm.Logit(yv, X).fit(disp=0, cov_type="cluster", cov_kwds={"groups": grp})
        b, p = float(r.params["power_shift"]), float(r.pvalues["power_shift"])
        out[f"G{G}"] = {"episodes": n_ep, "dyads": len(dy_used), "rows": int(len(yv)), "median_len_days": float(np.median(lens)),
                        "excluded": dict(excl), "shift_coef": b, "shift_p": p, "gap_coef": float(r.params["power_gap"]),
                        "elapsed_coef": float(r.params["log_elapsed"]), "prior_coef": float(r.params["log1p_prior"])}
        print(f"G{G:2}: episodes {n_ep:5,} in {len(dy_used)} dyads | median {np.median(lens):4.0f} d | power shift {b:+.3f} (p {p:.3g}) | "
              f"gap {r.params['power_gap']:+.3f} | elapsed {r.params['log_elapsed']:+.3f} | excluded {dict(excl)}")
    fitted = [v for k, v in out.items() if "shift_coef" in v]
    ok = len(fitted) == 3 and all(v["shift_coef"] < 0 and v["shift_p"] < 0.05 for v in fitted)
    out["unmatched_names"] = dict(unmatched); out["H4"] = "SUPPORTED" if ok else "NOT SUPPORTED"
    print("unmatched government names:", dict(unmatched) or "none")
    print("H4 (all three: power-shift coef < 0, p < .05):", out["H4"])
    json.dump(out, open("analysis/theory_test3_results.json", "w"), indent=2)

if __name__ == "__main__":
    main()

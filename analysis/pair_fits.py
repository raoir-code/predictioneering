"""
Two-state (N/F) Markov-modulated model fitted to ACLED daily series, one initiator->territory pair at a time.
Exact daily matrices: M0 = expm(Q - D), M1 = expm(Q) - M0;  Q = [[-h, h], [mu, -mu]];  D = diag(rhoN, rhoF).
rho = rates of ACLED-RECORDED activity days: an observation process, never the contract strike rate.
Days with only imprecisely dated events (time_precision > 1) are unobserved (expm(Q)), never assigned to an invented day.
Identification: rhoF = rhoN + exp(d). Start: stationary distribution. Pairs with < 10 active days are skipped.
Primary activity = air/drone + shelling/artillery/missile (ACLED cannot split missiles from artillery; we take episode
timing from ACLED, not the contract rate). Variant: air/drone only.
Validation: fit 2015-2022; one-step-ahead log score and Brier on 2023-2025 vs a constant-rate baseline.
Data through 2025-12-31 only (2026 kept clean for replay). Output: analysis/pair_fits.json (unpooled).
"""
import json, math, sys, datetime as dt
from pathlib import Path
import numpy as np
from scipy.linalg import expm
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
ACLED, OUT = ROOT / "data" / "external" / "acled", ROOT / "analysis" / "pair_fits.json"
D0, D1, SPLIT = dt.date(2015, 1, 1), dt.date(2025, 12, 31), dt.date(2023, 1, 1)
ISR, US = ["Military Forces of Israel"], ["Military Forces of the United States"]
IRN, TUR, PAK = ["Military Forces of Iran"], ["Military Forces of Turkey"], ["Military Forces of Pakistan"]
PAIRS = {"Israel->Lebanon": (ISR, "Lebanon"), "Israel->Syria": (ISR, "Syria"), "Israel->Yemen": (ISR, "Yemen"),
         "Israel->Iran": (ISR, "Iran"), "SaudiCoalition->Yemen": (["Operation Restoring Hope", "Operation Decisive Storm", "Military Forces of Saudi Arabia"], "Yemen"),
         "US->Yemen": (US, "Yemen"), "US->Iraq": (US, "Iraq"), "Iran->Iraq": (IRN, "Iraq"), "Iran->Syria": (IRN, "Syria"),
         "Iran->Israel": (IRN, "Israel"), "Pakistan->Afghanistan": (PAK, "Afghanistan"), "Turkey->Iraq": (TUR, "Iraq"), "Turkey->Syria": (TUR, "Syria")}
SUBS = {"primary": {"Air/drone strike", "Shelling/artillery/missile attack"}, "air_only": {"Air/drone strike"}}

def series(pats, country, subs):
    exact, inexact = set(), set()
    for f in ACLED.glob(f"{country.replace(' ', '_')}_*.jsonl"):
        for l in f.read_text().splitlines():
            r = json.loads(l)
            if r.get("sub_event_type") in subs and any((r.get("actor1") or "").startswith(p) for p in pats):
                d = dt.date.fromisoformat(r["event_date"][:10])
                if D0 <= d <= D1:
                    (exact if str(r.get("time_precision")) == "1" else inexact).add(d)
    days = [D0 + dt.timedelta(i) for i in range((D1 - D0).days + 1)]
    return days, [1 if d in exact else (None if d in inexact else 0) for d in days]

def mats(th):
    h, mu, rN, d = np.exp(th); rF = rN + d
    Q = np.array([[-h, h], [mu, -mu]])
    E = expm(Q); M0 = expm(Q - np.diag([rN, rF]))
    return E.tolist(), M0.tolist(), (E - M0).tolist(), h, mu, rN, rF

def run(th, y, a=None):
    e, m0, m1, h, mu, *_ = mats(th)
    a0, a1 = a if a else (mu / (h + mu), h / (h + mu)); ll = 0.0
    for v in y:
        M = e if v is None else (m1 if v else m0)
        b0, b1 = a0 * M[0][0] + a1 * M[1][0], a0 * M[0][1] + a1 * M[1][1]; s = b0 + b1
        if not s > 0:
            return -1e18, (a0, a1)
        ll += math.log(s); a0, a1 = b0 / s, b1 / s
    return ll, (a0, a1)

def fit(y, starts):
    best = None
    for th0 in starts:
        r = minimize(lambda t: -run(t, y)[0], th0, method="Nelder-Mead", options={"maxiter": 3000, "xatol": 1e-4, "fatol": 1e-3})
        if best is None or r.fun < best.fun:
            best = r
    return best

def hess_sd(th, y, eps=1e-3):
    k = len(th); H = np.zeros((k, k)); f0 = run(th, y)[0]
    for i in range(k):
        for j in range(i, k):
            e_i, e_j = np.eye(k)[i] * eps, np.eye(k)[j] * eps
            v = (run(th + e_i + e_j, y)[0] - run(th + e_i, y)[0] - run(th + e_j, y)[0] + f0) / eps ** 2
            H[i, j] = H[j, i] = v
    try:
        C = np.linalg.inv(-H); sd = np.sqrt(np.diag(C))
        return [float(x) for x in sd] if np.all(np.isfinite(sd)) else None
    except np.linalg.LinAlgError:
        return None

def onestep(th, ytr, yte):
    e, m0, m1, *_ = mats(th); _, (a0, a1) = run(th, ytr)
    p1 = lambda: a0 * (m1[0][0] + m1[0][1]) + a1 * (m1[1][0] + m1[1][1])
    ls = br = n = 0
    for v in yte:
        if v is not None:
            p = min(max(p1(), 1e-9), 1 - 1e-9); ls += math.log(p if v else 1 - p); br += (p - v) ** 2; n += 1
        M = e if v is None else (m1 if v else m0)
        b0, b1 = a0 * M[0][0] + a1 * M[1][0], a0 * M[0][1] + a1 * M[1][1]; s = b0 + b1; a0, a1 = b0 / s, b1 / s
    return ls / n, br / n, n

def main():
    res = {}
    for name, (pats, country) in PAIRS.items():
        for var, subs in SUBS.items():
            days, y = series(pats, country, subs)
            act = sum(1 for v in y if v == 1); obs = sum(1 for v in y if v is not None)
            if act < 10:
                print(f"  {name} [{var}]: {act} active days -> skipped (too sparse)", flush=True); continue
            f = act / obs
            starts = [np.log([h, m, max(1e-4, f * 0.05), max(1e-3, -math.log(1 - min(0.9, 3 * f + 0.05)))]) for h, m in ((1/180, 1/30), (1/60, 1/14), (1/365, 1/120))]
            r = fit(y, starts if var == "primary" else starts[:1]); th = r.x
            h, mu, rN, d = np.exp(th); rF = rN + d
            out = {"active_days": act, "observed_days": obs, "loglik": -r.fun,
                   "h_per_day": h, "mu_per_day": mu, "onset_median_wait_days": math.log(2) / h, "episode_half_life_days": math.log(2) / mu,
                   "p_recorded_day_F": 1 - math.exp(-rF), "p_recorded_day_N": 1 - math.exp(-rN), "stationary_pF": h / (h + mu)}
            if var == "primary":
                sd = hess_sd(th, y); out["sd_log"] = dict(zip(["h", "mu", "rhoN", "d"], sd)) if sd else "hessian not invertible"
                cut = days.index(SPLIT); ytr, yte = y[:cut], y[cut:]
                atr = sum(1 for v in ytr if v == 1)
                if atr >= 5:
                    rt = fit(ytr, [th]); ls, br, n = onestep(rt.x, ytr, yte)
                    k, m = atr, sum(1 for v in ytr if v is not None); pc = (k + 1) / (m + 2)
                    base_ls = sum(math.log(pc if v else 1 - pc) for v in yte if v is not None) / n
                    base_br = sum((pc - v) ** 2 for v in yte if v is not None) / n
                    out["validation_2023_25"] = {"n_days": n, "logscore_model": ls, "logscore_constant": base_ls, "brier_model": br, "brier_constant": base_br,
                                                 "model_better": ls > base_ls}
                else:
                    out["validation_2023_25"] = "too few active days before 2023"
            res.setdefault(name, {})[var] = out
            v = out.get("validation_2023_25"); vtxt = (f"val logscore {v['logscore_model']:.3f} vs const {v['logscore_constant']:.3f}" if isinstance(v, dict) else (v or ""))
            print(f"  {name:24} [{var:8}] active {act:4} | onset wait {out['onset_median_wait_days']:8.1f}d | episode half-life {out['episode_half_life_days']:7.1f}d | "
                  f"P(rec|F) {out['p_recorded_day_F']:.2f} P(rec|N) {out['p_recorded_day_N']:.3f} | {vtxt}", flush=True)
    OUT.write_text(json.dumps({"_doc": __doc__.strip().splitlines()[0], "data": "ACLED 2015-2025 (data/external/acled/MANIFEST.json)", "pairs": res}, indent=2) + "\n")

if __name__ == "__main__":
    main()

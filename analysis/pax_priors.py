"""
Family C v1 priors (docs/c1_prereg.md): agreement-arrival rates from PA-X v10 linked to UCDP Conflict Termination v4-2024.

Event: a distinct (UCDP conflict, date) with >= 1 multiparty PA-X agreement of the mapped stage, dated in an active conflict-year
or the year after (1990-2025). Exposure: active UCDP conflict-years 1990-2024 (EXTENSION: only days within 365 days after a
ceasefire-stage agreement of the same conflict, inside active years).
  CEASEFIRE <- Stage "Cea"      EXTENSION <- Stage "Ren"      DEAL <- Stage "SubComp" or StageSub "FrAg"
Interstate and intrastate pooled (interstate: 5 ceasefire events in 48 conflict-years).
Prior: n_c ~ Poisson(exposure_c * exp(theta_c)), theta_c ~ N(mu, sigma); (mu, sigma) by marginal likelihood (Gauss-Hermite) on a grid.
Writes pilot/agreement_priors_pax.json. Data files are gitignored; their sha256 is recorded.

  python analysis/pax_priors.py PAX_CSV UCDP_TERMINATION_CSV
"""
import csv, sys, re, json, math, hashlib, datetime as dt
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pilot" / "agreement_priors_pax.json"
Y0, Y1 = 1990, 2024
STAGES = {"CEASEFIRE": lambda x: x["Stage"] == "Cea", "EXTENSION": lambda x: x["Stage"] == "Ren",
          "DEAL": lambda x: x["Stage"] == "SubComp" or x["StageSub"] == "FrAg"}

def fit(ns, ys):
    """Poisson-lognormal marginal likelihood over (mu, sigma); returns MLE and the grid's posterior mean under flat priors."""
    gh_x, gh_w = np.polynomial.hermite_e.hermegauss(30); gh_w = gh_w / gh_w.sum()
    ns, ys = np.asarray(ns, float), np.asarray(ys, float); lgam = np.array([math.lgamma(n + 1) for n in ns])
    MU, SG = np.linspace(-7, 2, 181), np.linspace(0.05, 4, 80); best, L = None, np.zeros((len(MU), len(SG)))
    for i, mu in enumerate(MU):
        for j, sg in enumerate(SG):
            lam = ys[:, None] * np.exp(mu + sg * gh_x[None, :])
            lp = ns[:, None] * np.log(lam) - lam - lgam[:, None]
            m = lp.max(axis=1, keepdims=True); L[i, j] = float(np.sum(m[:, 0] + np.log(np.exp(lp - m) @ gh_w)))
    i, j = np.unravel_index(np.argmax(L), L.shape)
    return float(MU[i]), float(SG[j]), float(L[i, j])

def main(pax, ucdp):
    P = list(csv.DictReader(open(pax, encoding="utf-8-sig", errors="replace")))
    U = list(csv.DictReader(open(ucdp, encoding="utf-8", errors="replace")))
    act = defaultdict(set)
    for x in U:
        y = int(x["year"])
        if Y0 <= y <= Y1: act[x["conflict_id"]].add(y)
    ids = lambda s: [c for c in re.findall(r"\d+", s or "") if c in act]
    ev = {k: defaultdict(set) for k in STAGES}
    for x in P:
        if not x["Status"].startswith("Multiparty"): continue
        try: d = dt.date.fromisoformat(x["Dat"][:10])
        except Exception: continue
        if not (Y0 <= d.year <= Y1 + 1): continue
        for c in ids(x["UcdpCon"]):
            if d.year in act[c] or (d.year - 1) in act[c]:
                for k, f in STAGES.items():
                    if f(x): ev[k][c].add(d)
    out = {"sources": {"pax": Path(pax).name, "pax_sha256": hashlib.sha256(Path(pax).read_bytes()).hexdigest(),
                       "ucdp": Path(ucdp).name, "ucdp_sha256": hashlib.sha256(Path(ucdp).read_bytes()).hexdigest()},
           "citation": "Bell & Badanjak (2019) PA-X, JPR 56(3); PA-X v10 codebook (PeaceRep). Kreutz (2010) UCDP Conflict Termination, JPR 47(2).",
           "rates": {}, "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    for k in STAGES:
        ns, ys = [], []
        for c, years in act.items():
            if k == "EXTENSION":
                days = set()
                for d0 in ev["CEASEFIRE"].get(c, ()):
                    for i in range(1, 366):
                        d = d0 + dt.timedelta(i)
                        if d.year in years or (d.year - 1) in years: days.add(d)
                if not days: continue
                n = sum(1 for d in ev[k].get(c, ()) if d in days); y = len(days) / 365.25
            else:
                n = len(ev[k].get(c, ())); y = float(len(years))
            ns.append(n); ys.append(y)
        mu, sg, ll = fit(ns, ys)
        out["rates"][k] = {"events": int(sum(ns)), "exposure_years": round(sum(ys), 1), "conflicts": len(ns),
                           "pooled_rate_per_year": round(sum(ns) / sum(ys), 4), "log_mu": round(mu, 3), "log_sigma": round(sg, 3),
                           "median_rate_per_year": round(math.exp(mu), 4)}
        print(k, out["rates"][k])
    OUT.write_text(json.dumps(out, indent=1) + "\n")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

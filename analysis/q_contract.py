"""docs/q_contract_prereg.md: emission rates on the contract definition, state on the broad definition (roadmap step 1).
The world fit's p_rec_F / p_rec_N are rates at which the event data RECORDS broad activity (air/drone + all shelling) on fighting /
quiet days (analysis/pair_fits.py: "an observation process, never the contract strike rate"), yet the engine uses them as the
prior centres of q and q0. Here the fitted state model (h, mu and the broad emission) is kept as is; the forward-backward
posterior of the fighting state is used to estimate how often a CONTRACT-qualifying strike (contract_def_refit.qualifies:
air/drone, plus missiles beyond artillery range) is recorded on fighting and on quiet days:
    q_contract  = sum_t P(F_t | broad series) * narrow_t / sum_t P(F_t | broad series)
    q0_contract = the same with P(N_t | broad series)
Only these two numbers change, written as p_rec_F / p_rec_N in a copy of world_fits.json. h, mu, priors_world.json, hardening and
anchors are untouched. Coalition pairs (q prior 0.5 in the engine) are unaffected.
  python analysis/q_contract.py --synthetic     estimator checks on simulated series
  python analysis/q_contract.py --describe      broad vs contract emission for the traded pairs (held-out window; no outcomes)
  python analysis/q_contract.py --heldout       -> pilot/local/heldout_qc/ (copy of heldout/ with contract emissions)
  python analysis/q_contract.py --production    -> pilot/local/candidate_qc/world_fits.json (from pilot/local/world_fits.json)
  python analysis/q_contract.py --compare       replay FULL vs QC; applies the adoption rule
"""
import sys, json, math, shutil, datetime as dt
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
LOCAL = ROOT / "pilot" / "local"
TRADED = ("Israel->Lebanon", "Israel->Syria", "Israel->Yemen", "Israel->Iran", "Iran->Israel", "Iran->Iraq", "Iran->Kuwait",
          "Iran->Jordan", "Iran->Bahrain", "Iran->United Arab Emirates", "Iran->Qatar", "Iran->Oman", "Iran->Saudi Arabia",
          "United States->Iran", "Pakistan->Afghanistan", "Yemen [Houthi]->Saudi Arabia", "Yemen [Houthi]->Israel")

# ── estimator (pure; synthetic-checked) ──────────────────────────────────────────────────────────────────────────────
def theta(fit):
    """Recover (h, mu, rhoN, d) on the log scale from a world_fits.json entry."""
    rN = -math.log(1 - fit["p_rec_N"]); rF = -math.log(1 - fit["p_rec_F"])
    return np.log([fit["h_per_day"], fit["mu_per_day"], max(rN, 1e-9), max(rF - rN, 1e-9)])

def posterior_F(th, y):
    """P(fighting at the end of day t | the whole broad series), forward-backward with the fit's exact daily matrices."""
    import pair_fits as PF
    e, m0, m1, h, mu, *_ = PF.mats(th); M = {None: np.array(e), 0: np.array(m0), 1: np.array(m1)}
    n = len(y); A = np.zeros((n, 2)); a = np.array([mu / (h + mu), h / (h + mu)])
    for t, v in enumerate(y):
        a = a @ M[v]; a = a / a.sum(); A[t] = a
    Bk = np.ones(2); G = np.zeros(n)
    for t in range(n - 1, -1, -1):
        g = A[t] * Bk; G[t] = g[1] / g.sum()
        Bk = M[y[t]] @ Bk; Bk = Bk / Bk.sum()
    return G

def emission(G, y, z):
    """Contract emission on fighting / quiet days: days where both series are observed (z is None on inexact-only days)."""
    num1 = den1 = num0 = den0 = 0.0
    for g, v, w in zip(G, y, z):
        if v is None or w is None: continue
        num1 += g * w; den1 += g; num0 += (1 - g) * w; den0 += (1 - g)
    return (num1 / den1 if den1 else None), (num0 / den0 if den0 else None)

def clip(x, lo, hi): return min(hi, max(lo, x))

# ── data ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def series_pair(end):
    """Broad and contract-definition sets per world pair, with refit_local.build's rules (window WF.D0 .. end)."""
    import refit_local as RL, world_fits as WF, contract_def_refit as CD
    P = defaultdict(lambda: {"bx": set(), "bi": set(), "nx": set(), "ni": set()})
    for r in RL.rows():
        d = dt.date.fromisoformat(r["event_date"][:10])
        if d > end or d < WF.D0: continue
        if r.get("sub_event_type") not in WF.SUBS or WF.MARITIME.search(r.get("country") or ""): continue
        key, kind = WF.ident(r.get("actor1"))
        if not key or key == r.get("country"): continue
        p = P[f"{key}->{r['country']}"]; ex = str(r.get("time_precision")) == "1"
        p["bx" if ex else "bi"].add(d)
        if CD.qualifies(r): p["nx" if ex else "ni"].add(d)
    days = [WF.D0 + dt.timedelta(i) for i in range((end - WF.D0).days + 1)]
    out = {}
    for k, p in P.items():
        y = [1 if d in p["bx"] else (None if d in p["bi"] else 0) for d in days]
        z = [1 if d in p["nx"] else (None if d in p["ni"] else 0) for d in days]
        out[k] = (y, z)
    return out

def build(fits_path, end, out_dir):
    fits = json.loads(Path(fits_path).read_text()); S = series_pair(end); new = {}; rep = {}
    for k, f in fits.items():
        if k not in S or not all(x in f for x in ("h_per_day", "mu_per_day", "p_rec_F", "p_rec_N")): new[k] = f; continue
        y, z = S[k]; G = posterior_F(theta(f), y); q1, q0 = emission(G, y, z)
        g = dict(f); g["p_rec_F_broad"], g["p_rec_N_broad"] = f["p_rec_F"], f["p_rec_N"]
        if q1 is not None: g["p_rec_F"] = clip(q1, 1e-4, 0.999)
        if q0 is not None: g["p_rec_N"] = clip(q0, 1e-6, g["p_rec_F"])
        new[k] = g; rep[k] = (f["p_rec_F"], g["p_rec_F"], f["p_rec_N"], g["p_rec_N"])
    out_dir.mkdir(parents=True, exist_ok=True); (out_dir / "world_fits.json").write_text(json.dumps(new, indent=1) + "\n")
    return rep

def show(rep):
    print(f"  {'pair':32} {'q broad':>8} {'q contract':>10} {'q0 broad':>9} {'q0 contract':>11}")
    for k in TRADED:
        if k in rep: a, b, c, d = rep[k]; print(f"  {k:32} {a:8.3f} {b:10.3f} {c:9.4f} {d:11.4f}")

def heldout():
    import refit_local as RL
    rep = build(LOCAL / "heldout" / "world_fits.json", RL.HELDOUT_END, LOCAL / "heldout_qc")
    shutil.copy(LOCAL / "heldout" / "priors_world.json", LOCAL / "heldout_qc" / "priors_world.json")
    print(f"held-out (data <= {RL.HELDOUT_END}) -> pilot/local/heldout_qc/"); show(rep)

def production():
    import refit_local as RL
    data = json.loads((LOCAL / "priors_world.json").read_text()).get("data", "")
    end = dt.date.fromisoformat(data.split("..")[-1].strip()) if ".." in data else RL.last_complete_day()
    rep = build(LOCAL / "world_fits.json", end, LOCAL / "candidate_qc"); print(f"production fit (data <= {end}) -> pilot/local/candidate_qc/"); show(rep)

def describe():
    import refit_local as RL
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rep = build(LOCAL / "heldout" / "world_fits.json", RL.HELDOUT_END, Path(td))
    print(f"held-out window (data <= {RL.HELDOUT_END}); no outcomes read"); show(rep)

def compare():
    import contract_def_refit as CD
    A = CD.arm(LOCAL / "heldout", LOCAL / "last_strike.json"); Bq = CD.arm(LOCAL / "heldout_qc", LOCAL / "last_strike.json")
    ids = sorted(set(A) & set(Bq)); rows = [{"pair": A[i]["pair"], "y": A[i]["y"], "a": A[i]["u"], "b": Bq[i]["u"], "m": A[i]["m"]} for i in ids]
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs if x[k] is not None) / max(1, sum(1 for x in xs if x[k] is not None))
    print(f"=== CONTRACT EMISSION (docs/q_contract_prereg.md): {len(rows)} contracts first forecast >= 2026-07-01")
    print(f"  FULL {B(rows, 'a'):.4f} | QC {B(rows, 'b'):.4f} | market {B(rows, 'm'):.4f}")
    for y in (1, 0):
        s = [x for x in rows if x["y"] == y]
        if s: print(f"  {'YES' if y else 'NO '} n={len(s):3} FULL {B(s, 'a'):.4f} QC {B(s, 'b'):.4f} market {B(s, 'm'):.4f}")
    for p in sorted({x["pair"] for x in rows}):
        s = [x for x in rows if x["pair"] == p]
        print(f"    {p:28} n={len(s):3} YES {sum(x['y'] for x in s):3} FULL {B(s, 'a'):.4f} QC {B(s, 'b'):.4f} market {B(s, 'm'):.4f}")
    adopt, worse, ci = CD.rule(rows)
    print(f"  bootstrap by pair: QC - FULL = {B(rows, 'b') - B(rows, 'a'):+.4f} 95% {list(ci)} | pairs worse by > 0.05 (n >= 3): {worse or 'none'}")
    if adopt:
        bk = LOCAL / f"backup_{dt.date.today():%Y%m%d}_qc"; bk.mkdir(exist_ok=True); shutil.copy(LOCAL / "world_fits.json", bk / "world_fits.json")
        shutil.copy(LOCAL / "candidate_qc" / "world_fits.json", LOCAL / "world_fits.json")
        print(f"  ADOPTION RULE -> ADOPTED: contract emissions copied to pilot/local/world_fits.json (previous file in {bk.name}/)")
    else:
        print("  ADOPTION RULE -> NOT adopted: production world_fits.json unchanged")
    (LOCAL / "q_contract_result.json").write_text(json.dumps({"n": len(rows), "brier": {k: round(B(rows, k), 4) for k in "abm"}, "ci_b_minus_a": list(ci),
        "worse_pairs": worse, "adopted": adopt, "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2) + "\n")

def synthetic():
    import pair_fits as PF
    rng = np.random.default_rng(3); h, mu, rN, d = 1 / 120, 1 / 25, 0.002, 1.2; th = np.log([h, mu, rN, d])
    s, y, z, F = 0, [], [], []
    for _ in range(6000):
        s = (1 if rng.random() < 1 - math.exp(-h) else 0) if s == 0 else (0 if rng.random() < 1 - math.exp(-mu) else 1)
        rate = rN + (d if s else 0); v = int(rng.random() < 1 - math.exp(-rate)); w = int(v and rng.random() < (0.4 if s else 0.5))
        F.append(s); y.append(v); z.append(w)
    G = posterior_F(th, y); q1, q0 = emission(G, y, z)
    true1 = (1 - math.exp(-(rN + d))) * 0.4
    assert abs(q1 - true1) < 0.06, (q1, true1)                                    # narrow emission on fighting days recovered
    assert q0 < 0.01, q0
    acc = np.mean([(g > 0.5) == f for g, f in zip(G, F)]); assert acc > 0.9, acc  # state posterior tracks the true state
    f = {"h_per_day": h, "mu_per_day": mu, "p_rec_N": 1 - math.exp(-rN), "p_rec_F": 1 - math.exp(-(rN + d))}
    assert np.allclose(np.exp(theta(f)), [h, mu, rN, d])
    assert emission([0.9, 0.9], [1, None], [1, 1]) == (1.0, 1.0)                  # unobserved broad day skipped
    print(f"synthetic: all checks pass (q_contract {q1:.3f} vs true {true1:.3f}; state accuracy {acc:.3f})")

if __name__ == "__main__":
    a = sys.argv[1:] or ["--synthetic"]
    {"--synthetic": synthetic, "--describe": describe, "--heldout": heldout, "--production": production, "--compare": compare}[a[0]]()

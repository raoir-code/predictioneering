"""docs/oracle_replay_prereg.md: how much Brier could perfect eyes buy? (quiet-days plan, adopted Oct 27 as the first step)
Same harness as analysis/quiet_calibration.py (Part 5): the production pricer (pilot/unified_price.price_group), held-out
world fit and hardening (data <= 2026-06-30), news and rivalry phase off. Each hot origin t is priced twice:
  ORACLE  every day t-60 .. t-1 is known: a resolved daily window carrying the true outcome (strike or quiet)
  BLIND   only days t-60 .. t-LAG-1 are known; the last LAG days are unobserved (no news, resolutions lagging). Primary LAG = 7,
          the engine's own last-strike horizon; LAG = 3 is reported as a secondary arm.
Priced: "at least one strike in [t, t+W-1]" for W = 1 (our dailies, primary), 7 and 30.
dBrier = Brier(BLIND) - Brier(ORACLE), paired by origin, 95% bootstrap over directions: the most better eyes could be worth.
  python analysis/oracle_replay.py --synthetic   harness checks (fabricated record, repo priors; no real data)
  python analysis/oracle_replay.py --real        -> pilot/local/oracle_replay.json (gitignored) + printed summary
Report only: nothing here touches production.
"""
import sys, json, random, datetime as dt
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
import quiet_calibration as QC                     # setup(), quiet_days(), outcome(), bin_of(), universe/origin rules

WS, LAGS, PRIMARY_W, PRIMARY_LAG = (1, 7, 30), (7, 3), 1, 7
MATTER = 0.02                                       # pre-registered: eyes matter if dBrier(W=1, LAG=7) >= 0.02 with CI lower > 0
UTC = dt.timezone.utc


# ── harness ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def group(K, truth, t, lag, L=QC.L, W=WS):
    """Daily windows t-L .. t-lag-1 carrying the true outcome (lag 0 = oracle), plus open by-date contracts [t, t+W-1]."""
    ini, ter = K.split("->"); key = lambda s: "".join(ch for ch in s.lower() if "a" <= ch <= "z")
    pair = f"{key(ini)}->{key(ter)}"; grp = []
    for i in range(L, lag, -1):
        d = t - dt.timedelta(i); s = dt.datetime.combine(d, dt.time(0), UTC); e = dt.datetime.combine(d, dt.time(23, 59, 59), UTC)
        grp.append({"id": f"d{d}", "pair": pair, "kind": "daily", "fp": "SYN", "sfp": "SYN", "tz": "UTC", "start": s, "end": e, "date": d,
                    "outcome": 1 if d in truth else 0, "known": e + dt.timedelta(hours=1), "open": False, "members": None})
    as_of = dt.datetime.combine(t, dt.time(13), UTC); opens = []
    for w in W:
        end = t + dt.timedelta(w - 1)
        opens.append({"id": f"W{w}", "pair": pair, "kind": "bydate", "fp": "SYN", "sfp": "SYN", "tz": "UTC", "start": as_of,
                      "end": dt.datetime.combine(end, dt.time(23, 59, 59), UTC), "date": end, "outcome": None, "known": None, "open": True,
                      "members": None})
    return pair, grp + opens, opens, as_of

def delta_stats(rows, w, lag, B=2000, seed=11):
    """rows: dicts (pair, w, lag, p_oracle, p_blind, y). -> n, Brier per arm, dBrier, 95% CI (bootstrap over directions)."""
    xs = [r for r in rows if r["w"] == w and r["lag"] == lag]
    if not xs: return None
    by = defaultdict(list)
    for r in xs: by[r["pair"]].append((r["p_blind"] - r["y"]) ** 2 - (r["p_oracle"] - r["y"]) ** 2)
    pairs = sorted(by); rng = np.random.default_rng(seed); ds = []
    for _ in range(B):
        s = [v for p in rng.choice(pairs, len(pairs)) for v in by[p]]; ds.append(np.mean(s))
    lo, hi = np.percentile(ds, [2.5, 97.5])
    bo = np.mean([(r["p_oracle"] - r["y"]) ** 2 for r in xs]); bb = np.mean([(r["p_blind"] - r["y"]) ** 2 for r in xs])
    return {"n": len(xs), "pairs": len(pairs), "brier_oracle": round(float(bo), 4), "brier_blind": round(float(bb), 4),
            "dbrier": round(float(bb - bo), 4), "ci": [round(float(lo), 4), round(float(hi), 4)]}

def verdict(st):
    """Pre-registered rule on the primary cell (W=1, LAG=7), needing >= QC.MIN_PAIRS directions and >= QC.MIN_N forecasts."""
    if not st or st["pairs"] < QC.MIN_PAIRS or st["n"] < QC.MIN_N: return "INCONCLUSIVE"
    if st["dbrier"] >= MATTER and st["ci"][0] > 0: return "EYES-MATTER"
    if st["ci"][1] < MATTER: return "EYES-DONT-MATTER"
    return "INCONCLUSIVE"


# ── engine wiring ────────────────────────────────────────────────────────────────────────────────────────────────────
def price_one(job):
    K, truth_list, t = job; truth = set(truth_list); UP = QC._UP
    out = {}
    for lag in (0,) + LAGS:
        pair, grp, opens, as_of = group(K, truth, t, lag)
        P = UP.params(pair)
        if not P or P.get("world_pair") != K: return []
        pr, _ = UP.price_group(grp, as_of, P, opens, {(pair, "SYN"): grp}, pair)
        out[lag] = pr
    k = QC.quiet_days(truth, t); rows = []
    for w in WS:
        cid = f"W{w}"
        if cid not in out[0]: continue
        for lag in LAGS:
            if cid in out[lag]:
                rows.append({"pair": K, "t": str(t), "w": w, "lag": lag, "k": k, "bin": QC.bin_of(k), "p_oracle": out[0][cid],
                             "p_blind": out[lag][cid], "y": QC.outcome(truth, t, w)})
    return rows

def run(jobs, cfg, procs=None):
    import multiprocessing as mp
    with mp.get_context("spawn").Pool(procs or max(1, mp.cpu_count() - 1), initializer=QC._init, initargs=(cfg,)) as pool:
        rows = []
        for i, r in enumerate(pool.imap_unordered(price_one, jobs, chunksize=2)):
            rows += r
            if i % 25 == 0: print(f"  {i}/{len(jobs)} origins priced", flush=True)
    return rows


# ── synthetic check ──────────────────────────────────────────────────────────────────────────────────────────────────
def synthetic():
    ok = True; rnd = random.Random(5)
    def chk(name, cond, detail):
        nonlocal ok; ok &= bool(cond); print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
    t = dt.date(2026, 8, 1); truth = {t - dt.timedelta(i) for i in (2, 9, 40)} | {t}
    _, g0, _, _ = group("Israel->Lebanon", truth, t, 0); _, g7, _, _ = group("Israel->Lebanon", truth, t, 7)
    d0 = [c for c in g0 if c["kind"] == "daily"]; d7 = [c for c in g7 if c["kind"] == "daily"]
    chk("oracle sees t-60 .. t-1", len(d0) == QC.L and max(c["date"] for c in d0) == t - dt.timedelta(1), f"{len(d0)} days")
    chk("blind (lag 7) stops at t-8", len(d7) == QC.L - 7 and max(c["date"] for c in d7) == t - dt.timedelta(8), f"{len(d7)} days")
    chk("no outcome from t onward", all(c["date"] < t for c in d0), "strike on t itself excluded")
    _, gq, _, _ = QC.synthetic_group("Israel->Lebanon", truth, t)
    chk("oracle arm = Part 5 evidence", [(c["date"], c["outcome"]) for c in gq if c["kind"] == "daily"] == [(c["date"], c["outcome"]) for c in d0], "identical")
    mk = lambda po, pb, n=300, pairs=6, py=0.3: [{"pair": f"p{i % pairs}", "w": 1, "lag": 7, "p_oracle": po, "p_blind": pb,
                                                 "y": int(rnd.random() < py)} for i in range(n)]
    v = verdict(delta_stats(mk(0.3, 0.75), 1, 7, B=300)); chk("big gap -> EYES-MATTER", v == "EYES-MATTER", v)
    v = verdict(delta_stats(mk(0.3, 0.31), 1, 7, B=300)); chk("no gap -> EYES-DONT-MATTER", v == "EYES-DONT-MATTER", v)
    v = verdict(delta_stats(mk(0.3, 0.75, pairs=1), 1, 7, B=100)); chk("one direction cannot decide", v == "INCONCLUSIVE", v)
    # engine wiring on repo priors: hot in June, then quiet. At k=10 the oracle has seen 9 more quiet days than blind (lag 7),
    # so its W=1 forecast should be lower; when the last strike was yesterday (k=1) the oracle sees it and blind does not.
    QC._init({"world": ROOT / "pilot" / "priors_world.json", "fits": ROOT / "analysis" / "world_fits.json"})
    K = next((k for k in QC._UP.W["pairs"] if k.startswith("Israel->Lebanon")), next(iter(QC._UP.W["pairs"])))
    hot = {dt.date(2026, 6, 1) + dt.timedelta(i) for i in range(30)}
    r10 = {x["lag"]: x for x in price_one((K, sorted(hot), dt.date(2026, 7, 10))) if x["w"] == 1}
    chk("engine prices both arms", 7 in r10 and 3 in r10, f"{K}: k=10 W=1 oracle {r10.get(7, {}).get('p_oracle')} blind7 {r10.get(7, {}).get('p_blind')} blind3 {r10.get(3, {}).get('p_blind')}")
    chk("quiet seen -> oracle lower than blind", 7 in r10 and r10[7]["p_oracle"] <= r10[7]["p_blind"], "k=10")
    hot2 = hot | {dt.date(2026, 7, 9)}
    r1 = {x["lag"]: x for x in price_one((K, sorted(hot2), dt.date(2026, 7, 10))) if x["w"] == 1}
    chk("strike yesterday seen -> oracle higher than blind", 7 in r1 and r1[7]["p_oracle"] >= r1[7]["p_blind"],
        f"k=1 W=1 oracle {r1.get(7, {}).get('p_oracle')} blind7 {r1.get(7, {}).get('p_blind')}")
    print("SYNTHETIC:", "ALL PASS" if ok else "FAILED"); return ok


# ── real data (local only) ───────────────────────────────────────────────────────────────────────────────────────────
def real():
    import refit_local as RL
    end = RL.last_complete_day(); hd = RL.LOCAL / "heldout"
    need = [hd / "priors_world.json", hd / "world_fits.json", RL.LOCAL / "hardening_heldout.json"]
    miss = [str(p.relative_to(ROOT)) for p in need if not p.exists()]
    if miss:
        sys.exit("missing held-out fits: " + ", ".join(miss) + "\n  run: python3.11 analysis/refit_local.py --heldout && python3.11 analysis/hardening_fit.py --heldout")
    P = RL.build(end)()
    truth = {k: v["exact"] | v["inexact"] for k, v in P.items()}
    W = json.loads((hd / "priors_world.json").read_text())
    universe = [k for k in W["pairs"] if sum(1 for d in truth.get(k, ()) if QC.HOT_WINDOW[0] <= d <= QC.HOT_WINDOW[1]) >= 5]
    last = {k: sorted(d.isoformat() for d in v) for k, v in truth.items()}
    cfg = {"world": hd / "priors_world.json", "fits": hd / "world_fits.json", "harden": RL.LOCAL / "hardening_heldout.json", "last": last}
    jobs, t = [], QC.TEST[0]
    while t + dt.timedelta(max(WS) - 1) <= end:
        for k in universe:
            if QC.quiet_days(truth[k], t) is not None:
                jobs.append((k, sorted(d for d in truth[k] if t - dt.timedelta(QC.L) <= d <= t + dt.timedelta(max(WS))), t))
        t += dt.timedelta(QC.STEP)
    print(f"[oracle] event data through {end}; universe {len(universe)} pairs; {len(jobs)} hot origins; arms oracle vs blind lag {LAGS}")
    rows = run(jobs, cfg)
    stats = {f"W{w}|lag{lag}": delta_stats(rows, w, lag) for w in WS for lag in LAGS}
    v = verdict(stats[f"W{PRIMARY_W}|lag{PRIMARY_LAG}"])
    byk = {}
    for b in sorted({r["bin"] for r in rows if r["bin"]}, key=lambda s: int(s.split("-")[0])):
        sub = [r for r in rows if r["bin"] == b]; byk[b] = delta_stats(sub, PRIMARY_W, PRIMARY_LAG, B=500)
    res = {"end": str(end), "universe": universe, "n_rows": len(rows), "verdict": v, "rule": f"W={PRIMARY_W}, lag={PRIMARY_LAG}: dBrier >= {MATTER} with CI lower > 0",
           "cells": stats, "primary_by_k": byk, "rows": rows}
    out = RL.LOCAL / "oracle_replay.json"; out.write_text(json.dumps(res, indent=1, default=str))
    print(f"  written {out.relative_to(ROOT)}; {len(rows)} paired forecasts")
    print(f"  {'cell':12} {'n':>5} {'pairs':>5} {'oracle':>8} {'blind':>8} {'dBrier':>8} {'95% CI':>18}")
    for name, s in stats.items():
        if s: print(f"  {name:12} {s['n']:5d} {s['pairs']:5d} {s['brier_oracle']:8.4f} {s['brier_blind']:8.4f} {s['dbrier']:+8.4f} {str(s['ci']):>18}")
    print("  primary cell by days since last strike (k):")
    for b, s in byk.items():
        if s: print(f"    k {b:6} n {s['n']:5d}  dBrier {s['dbrier']:+.4f} {s['ci']}")
    print(f"  VERDICT ({res['rule']}): {v}")


if __name__ == "__main__":
    if "--synthetic" in sys.argv: sys.exit(0 if synthetic() else 1)
    elif "--real" in sys.argv: real()
    else: print(__doc__)

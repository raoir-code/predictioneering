"""docs/quiet_calibration_prereg.md (quiet-days plan, Part 5): does the unified engine respond correctly to TRUE quiet?
The production pricer (pilot/unified_price.price_group) is given, for one direction, a synthetic group of daily contracts that
carry the true strike record of the 60 days before a forecast day t (local offline event data), and prices by-date contracts
"at least one strike in [t, t+W-1]" (W = 7 and 30). Forecasts are compared with what happened, by the number of quiet days k
since the last true strike. Nothing from after t enters a forecast:
  - parameters: the held-out world fit (pilot/local/heldout/, data <= 2026-06-30) and held-out hardening (hardening_heldout.json)
  - news reports: off (the true record replaces them); rivalry phase: off (not adopted)
  - last-strike table: built from the true record; the engine itself only reads strikes >= 7 days before t
  python analysis/quiet_calibration.py --synthetic   harness checks (fabricated record, repo priors; no real data)
  python analysis/quiet_calibration.py --real        -> pilot/local/quiet_calibration.json (gitignored) + printed summary
Report only: nothing here touches production.
"""
import sys, json, math, random, datetime as dt
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
L, WS, STEP = 60, (7, 30), 3                      # evidence lookback (days), contract lengths, days between forecast origins
TEST = (dt.date(2026, 7, 1), None)               # origins from Jul 1 until (last complete day - W)
HOT_WINDOW = (dt.date(2026, 4, 1), dt.date(2026, 6, 30))   # universe: >= 5 true strike days here (before the test)
BINS = ((1, 2), (3, 6), (7, 13), (14, 29), (30, 60))
TOL = 0.05
MIN_PAIRS, MIN_N = 5, 30                          # a cell decides only with >= 5 directions and >= 30 forecasts (else reported only)
UTC = dt.timezone.utc


# ── harness (pure parts synthetic-checked) ───────────────────────────────────────────────────────────────────────────
def synthetic_group(K, truth, t, L=L, W=WS):
    """Daily contracts for days t-L .. t-1 with their true outcome, plus open by-date contracts [t, t+W-1]."""
    ini, ter = K.split("->"); key = lambda s: "".join(ch for ch in s.lower() if "a" <= ch <= "z")
    pair = f"{key(ini)}->{key(ter)}"; grp = []
    for i in range(L, 0, -1):
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

def quiet_days(truth, t, L=L):
    """Days since the last true strike before t (1 = struck yesterday); None if none in the lookback (cold: out of this test)."""
    for k in range(1, L + 1):
        if t - dt.timedelta(k) in truth: return k
    return None

def outcome(truth, t, w):
    return int(any(t + dt.timedelta(i) in truth for i in range(w)))

def bin_of(k):
    return next((f"{a}-{b}" for a, b in BINS if a <= k <= b), None)

def calibration(rows, B=2000, seed=27):
    """rows: dicts (pair, w, bin, p, y). -> {(w, bin): n, mean p, observed, diff, 95% CI of diff (bootstrap over pairs)}."""
    out = {}; rng = np.random.default_rng(seed)
    for w in sorted({r["w"] for r in rows}):
        for a, b in BINS:
            bn = f"{a}-{b}"; xs = [r for r in rows if r["w"] == w and r["bin"] == bn]
            if not xs: continue
            pairs = sorted({r["pair"] for r in xs}); by = defaultdict(list)
            for r in xs: by[r["pair"]].append(r)
            diff = np.mean([r["p"] for r in xs]) - np.mean([r["y"] for r in xs]); ds = []
            for _ in range(B):
                s = [r for p in rng.choice(pairs, len(pairs)) for r in by[p]]
                ds.append(np.mean([r["p"] for r in s]) - np.mean([r["y"] for r in s]))
            lo, hi = np.percentile(ds, [2.5, 97.5])
            out[(w, bn)] = {"n": len(xs), "pairs": len(pairs), "mean_p": round(float(np.mean([r["p"] for r in xs])), 4),
                            "observed": round(float(np.mean([r["y"] for r in xs])), 4), "diff": round(float(diff), 4), "ci": [round(float(lo), 4), round(float(hi), 4)]}
    return out

def verdict(cal):
    """Pre-registered rule: over k >= 3 bins with >= MIN_PAIRS directions and >= MIN_N forecasts, a cell fails if |diff| > TOL
    and its 95% CI (bootstrap over directions) excludes 0. No deciding cell at all -> INCONCLUSIVE."""
    dec = {k: v for k, v in cal.items() if k[1] != "1-2" and v["pairs"] >= MIN_PAIRS and v["n"] >= MIN_N}
    if not dec: return "INCONCLUSIVE", {}
    bad = {k: v for k, v in dec.items() if abs(v["diff"]) > TOL and (v["ci"][0] > 0 or v["ci"][1] < 0)}
    if not bad: return "PASS", bad
    over = any(v["diff"] > 0 for v in bad.values()); under = any(v["diff"] < 0 for v in bad.values())
    return ("FAIL-OVERSHOOT" if over and not under else "FAIL-UNDERSHOOT" if under and not over else "FAIL-MIXED"), bad


# ── engine wiring ────────────────────────────────────────────────────────────────────────────────────────────────────
def setup(world=None, fits=None, harden=None, last=None):
    """Point the production pricer at held-out inputs and switch off live inputs. Returns the module."""
    import unified_price as UP
    if world: UP.W = json.loads(Path(world).read_text())
    if fits: UP.F = json.loads(Path(fits).read_text())
    UP.WK = {(UP.key(k.split("->")[0]), UP.key(k.split("->")[1])): k for k in UP.W["pairs"]}
    UP.CLS = defaultdict(list)
    for n, r in UP.F.items(): UP.CLS[r["class"]].append(r["p_rec_N"])
    UP.HARDEN = json.loads(Path(harden).read_text()) if harden else None
    UP.PHASE = None
    UP.news_dates = lambda *a, **k: set()
    UP.news_days = lambda *a, **k: set()
    UP._LAST = last if last is not None else {}
    return UP

_UP = None
def _init(cfg):
    global _UP; _UP = setup(**cfg)

def price_one(job):
    K, truth_list, t = job; truth = set(truth_list)
    pair, grp, opens, as_of = synthetic_group(K, truth, t)
    P = _UP.params(pair)
    if not P or P.get("world_pair") != K: return []
    G = {(pair, "SYN"): grp}
    pr, d = _UP.price_group(grp, as_of, P, opens, G, pair)
    k = quiet_days(truth, t); out = []
    for c in opens:
        if c["id"] in pr:
            w = int(c["id"][1:]); out.append({"pair": K, "t": str(t), "w": w, "k": k, "bin": bin_of(k), "p": pr[c["id"]], "y": outcome(truth, t, w)})
    return out

def run(jobs, cfg, procs=None):
    import multiprocessing as mp
    with mp.get_context("spawn").Pool(procs or max(1, mp.cpu_count() - 1), initializer=_init, initargs=(cfg,)) as pool:
        rows = []
        for i, r in enumerate(pool.imap_unordered(price_one, jobs, chunksize=2)):
            rows += r
            if i % 25 == 0: print(f"  {i}/{len(jobs)} origins priced", flush=True)
    return rows


# ── synthetic check ──────────────────────────────────────────────────────────────────────────────────────────────────
def synthetic():
    rnd = random.Random(3); ok = True
    def chk(name, cond, detail):
        nonlocal ok; ok &= bool(cond); print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
    t = dt.date(2026, 8, 1)
    truth = {t - dt.timedelta(i) for i in (3, 9, 10, 40)} | {t + dt.timedelta(2)}
    pair, grp, opens, as_of = synthetic_group("Israel->Lebanon", truth, t)
    days = [c for c in grp if c["kind"] == "daily"]
    chk("evidence ends the day before t", max(c["date"] for c in days) == t - dt.timedelta(1) and len(days) == L, f"{len(days)} daily windows")
    chk("no future outcome in the evidence", all(c["date"] < t for c in days if c["outcome"] == 1) and sum(c["outcome"] for c in days) == 4, "4 past strikes, 1 future excluded")
    chk("quiet days and outcomes", quiet_days(truth, t) == 3 and outcome(truth, t, 7) == 1 and outcome(truth, t + dt.timedelta(3), 7) == 0, "k=3; W=7 YES then NO")
    rows = [{"pair": f"p{i % 6}", "w": 7, "bin": "7-13", "p": 0.6, "y": int(rnd.random() < 0.3)} for i in range(600)]
    cal = calibration(rows, B=300); v, bad = verdict(cal)
    chk("overshoot detected", v == "FAIL-OVERSHOOT", f"{cal[(7, '7-13')]}")
    rows = [{"pair": f"p{i % 6}", "w": 7, "bin": "7-13", "p": 0.3, "y": int(rnd.random() < 0.3)} for i in range(600)]
    v, _ = verdict(calibration(rows, B=300)); chk("calibrated passes", v == "PASS", v)
    rows = [{"pair": "p0", "w": 7, "bin": "7-13", "p": 0.6, "y": 0} for i in range(100)]
    v, _ = verdict(calibration(rows, B=100)); chk("one direction cannot decide", v == "INCONCLUSIVE", v)
    # engine wiring on the repo priors (no real data): a hot direction that goes quiet should get lower forecasts as k grows
    UP = setup(world=ROOT / "pilot" / "priors_world.json", fits=ROOT / "analysis" / "world_fits.json", harden=None, last={})
    K = next(k for k in UP.W["pairs"] if k.startswith("Israel->Lebanon")) if any(k.startswith("Israel->Lebanon") for k in UP.W["pairs"]) else next(iter(UP.W["pairs"]))
    _init({"world": ROOT / "pilot" / "priors_world.json", "fits": ROOT / "analysis" / "world_fits.json"})
    hot = {dt.date(2026, 6, 1) + dt.timedelta(i) for i in range(30)}          # struck every day in June, then silence
    ps = []
    for gap in (2, 10, 25):
        r = price_one((K, sorted(hot), dt.date(2026, 7, 1) + dt.timedelta(gap - 1)))
        ps.append(next((x["p"] for x in r if x["w"] == 7), None))
    chk("engine runs on synthetic contracts", all(p is not None for p in ps), f"{K}: P(strike in 7d) at k=2,10,25 = {ps}")
    chk("forecast falls with quiet days", ps[0] is not None and ps[0] >= ps[1] >= ps[2], f"{ps}")
    print("SYNTHETIC:", "ALL PASS" if ok else "FAILED"); return ok


# ── real data (local only) ───────────────────────────────────────────────────────────────────────────────────────────
def real():
    import refit_local as RL
    end = RL.last_complete_day(); hd = RL.LOCAL / "heldout"
    need = [hd / "priors_world.json", hd / "world_fits.json", RL.LOCAL / "hardening_heldout.json"]
    miss = [str(p.relative_to(ROOT)) for p in need if not p.exists()]
    if miss:
        sys.exit("missing held-out fits: " + ", ".join(miss) + "\n  run: python3.11 analysis/refit_local.py --heldout && python3.11 analysis/hardening_fit.py --heldout")
    P = RL.build(end)()                                                   # world-fit truth: X's forces strike in Y (same definition as the fit)
    truth = {k: v["exact"] | v["inexact"] for k, v in P.items()}
    W = json.loads((hd / "priors_world.json").read_text())
    universe = [k for k in W["pairs"] if sum(1 for d in truth.get(k, ()) if HOT_WINDOW[0] <= d <= HOT_WINDOW[1]) >= 5]
    last = {k: sorted(d.isoformat() for d in v) for k, v in truth.items()}
    cfg = {"world": hd / "priors_world.json", "fits": hd / "world_fits.json", "harden": RL.LOCAL / "hardening_heldout.json", "last": last}
    jobs = []
    t = TEST[0]
    while t + dt.timedelta(max(WS) - 1) <= end:
        for k in universe:
            if quiet_days(truth[k], t) is not None:
                jobs.append((k, sorted(d for d in truth[k] if t - dt.timedelta(L) <= d <= t + dt.timedelta(max(WS))), t))
        t += dt.timedelta(STEP)
    print(f"[quiet] event data through {end}; universe {len(universe)} pairs (>= 5 strike days Apr-Jun); {len(jobs)} hot origins")
    rows = run(jobs, cfg)
    cal = calibration(rows); v, bad = verdict(cal)
    br = lambda xs: sum((r["p"] - r["y"]) ** 2 for r in xs) / max(1, len(xs))
    res = {"end": str(end), "universe": universe, "n_rows": len(rows), "verdict": v,
           "cells": {f"W{w}|k {b}": c for (w, b), c in cal.items()}, "failing_cells": [f"W{w}|k {b}" for (w, b) in bad],
           "brier": {f"W{w}": round(br([r for r in rows if r["w"] == w]), 4) for w in WS}, "rows": rows}
    out = RL.LOCAL / "quiet_calibration.json"; out.write_text(json.dumps(res, indent=1, default=str))
    print(f"  written {out.relative_to(ROOT)}; {len(rows)} forecasts")
    print(f"  {'cell':14} {'n':>5} {'pairs':>5} {'forecast':>9} {'observed':>9} {'diff':>7} {'95% CI':>18}")
    for (w, b), c in sorted(cal.items(), key=lambda kv: (kv[0][0], int(kv[0][1].split('-')[0]))):
        flag = "  <- fails" if (w, b) in bad else ("  (too few to decide)" if c["pairs"] < MIN_PAIRS or c["n"] < MIN_N else "")
        print(f"  W{w:<3} k {b:7} {c['n']:5d} {c['pairs']:5d} {c['mean_p']:9.3f} {c['observed']:9.3f} {c['diff']:+7.3f} {str(c['ci']):>18}{flag}")
    print(f"  VERDICT (k >= 3 cells, |diff| > {TOL} with CI excluding 0): {v}")


if __name__ == "__main__":
    if "--synthetic" in sys.argv: sys.exit(0 if synthetic() else 1)
    elif "--real" in sys.argv: real()
    else: print(__doc__)

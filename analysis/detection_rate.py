"""docs/detection_prereg.md: how well does our own live news stream see strikes? Measured against the local offline event data.
Two numbers per direction X -> Y (X's forces strike Y's territory), on each day f with a non-empty headline file:
  d     = P(news hit on f | a true strike in [f-2, f])      detection rate (same three days as the news hit window)
  alpha = P(news hit on f | no true strike in [f-2, f])     false-alarm rate
plus coverage (share of calendar days with a non-empty file) and the lag from a true strike day to the first headline.
A no-hit day is evidence of quiet only through these two numbers: P(strike | no hit) = pi (1-d) / (pi (1-d) + (1-pi)(1-alpha)).
  python analysis/detection_rate.py --synthetic    estimator checks on synthetic data only (no real data touched)
  python analysis/detection_rate.py --real         -> pilot/local/detection_rate.json (gitignored) + printed summary
Report only: nothing here touches production.
"""
import sys, json, math, random, datetime as dt
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLACK = 2            # truth window [f-2, f] = news window (a wider truth window counts strikes the stream could not yet report as misses)
MIN_STRIKE_DAYS = 5  # per-direction d is reported only with >= 5 strike days in the window
PRIMARY = {"Air/drone strike", "Shelling/artillery/missile attack"}
SENSITIVITY = {"Air/drone strike"}
NAMES = {"United Arab Emirates": "United Arab Emirates"}   # news_strikes names already match the event data's country names


# ── estimator (pure; synthetic-checked) ──────────────────────────────────────────────────────────────────────────────
def day_table(truth, files):
    """truth: set of dates with a true strike. files: {file_date: (n_articles, [pub dates of hit headlines])}.
    -> list of (f, S, O): S = true strike in [f-SLACK, f], O = a hit headline published in [f-2, f]. Empty files are skipped."""
    out = []
    for f, (n, pubs) in sorted(files.items()):
        if not n: continue
        S = any(f - dt.timedelta(k) in truth for k in range(SLACK + 1))
        O = any(f - dt.timedelta(2) <= p <= f for p in pubs)
        out.append((f, S, O))
    return out

def rates(table):
    s1 = [o for _, s, o in table if s]; s0 = [o for _, s, o in table if not s]
    return {"n_strike_days": len(s1), "n_quiet_days": len(s0),
            "d": (sum(s1) + 0.5) / (len(s1) + 1) if s1 else None, "alpha": (sum(s0) + 0.5) / (len(s0) + 1) if s0 else None,
            "hits_on_strike_days": sum(s1), "hits_on_quiet_days": sum(s0)}

CAP = 20   # pipeline/engine.py fetch_gnews: max 20 articles per dyad per day, covering the past 7 days

def crowding(table, files):
    """d on file days that hit the article cap vs days under it. Much lower d at the cap -> strike headlines crowded out
    (a news-gathering fix, not a model fix)."""
    at = [(s, o) for f, s, o in table if files[f][0] >= CAP]; under = [(s, o) for f, s, o in table if files[f][0] < CAP]
    d = lambda rows: (lambda s1: (round(sum(s1) / len(s1), 3), len(s1)) if s1 else (None, 0))([o for s, o in rows if s])
    return {"share_days_at_cap": round(len(at) / max(1, len(table)), 3), "d_at_cap": d(at), "d_under_cap": d(under)}

def persistence(table):
    """Are misses clustered? Among consecutive observed days that both had a true strike: P(miss today | missed yesterday) vs
    P(miss). Equal -> independent misses (k quiet days multiply); higher -> clustered (a run of no-hit days is worth less).
    The unified engine reads no-hit days as no information because it assumes clustering; this measures it."""
    prev = {f: (s, o) for f, s, o in table}; pairs = []
    for f, s, o in table:
        y = prev.get(f - dt.timedelta(1))
        if s and y and y[0]: pairs.append((not y[1], not o))
    miss = [b for _, b in pairs]; after = [b for a, b in pairs if a]
    return {"n_pairs": len(pairs), "p_miss": round(sum(miss) / len(miss), 3) if miss else None,
            "p_miss_after_miss": round(sum(after) / len(after), 3) if after else None, "n_after_miss": len(after)}

def jeffreys(k, n, z=1.96):
    """Approximate 95% interval (Wilson around the Jeffreys point estimate); fine for a report."""
    if not n: return None
    p = (k + 0.5) / (n + 1); h = z * math.sqrt(p * (1 - p) / (n + 1))
    return round(max(0.0, p - h), 3), round(min(1.0, p + h), 3)

def lags(truth, files, max_lag=7):
    """For each true strike day d inside file coverage: days until the first hit headline published in [d-1, d+max_lag]; None = never."""
    if not files: return []
    lo, hi = min(files), max(files)
    pubs = sorted({p for _, (n, ps) in files.items() for p in ps})
    out = []
    for d in sorted(truth):
        if not lo <= d <= hi - dt.timedelta(2): continue
        first = next((p for p in pubs if d - dt.timedelta(1) <= p <= d + dt.timedelta(max_lag)), None)
        out.append(None if first is None else max(0, (first - d).days))
    return out

def cluster_boot(tables, B=2000, seed=11):
    """Pooled d and alpha with a bootstrap over (direction, ISO week) blocks: consecutive days overlap, so days are not independent."""
    blocks = defaultdict(list)
    for name, t in tables.items():
        for f, s, o in t: blocks[(name, f.isocalendar()[:2])].append((s, o))
    keys = list(blocks); rnd = random.Random(seed); ds, als = [], []
    for _ in range(B):
        rows = [r for k in (rnd.choice(keys) for _ in keys) for r in blocks[k]]
        s1 = [o for s, o in rows if s]; s0 = [o for s, o in rows if not s]
        if s1: ds.append(sum(s1) / len(s1))
        if s0: als.append(sum(s0) / len(s0))
    q = lambda v: (round(sorted(v)[int(0.025 * len(v))], 3), round(sorted(v)[int(0.975 * len(v)) - 1], 3)) if v else None
    return q(ds), q(als)

def posterior_quiet(pi, d, alpha):
    """P(strike in the window | no hit) for prior pi."""
    return pi * (1 - d) / (pi * (1 - d) + (1 - pi) * (1 - alpha))


# ── synthetic check ──────────────────────────────────────────────────────────────────────────────────────────────────
def synthetic():
    rnd = random.Random(5); ok = True
    def chk(name, cond, detail):
        nonlocal ok; ok &= bool(cond); print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
    D0 = dt.date(2026, 1, 1); N = 280
    def world(p_strike, recall, false_alarm, coverage=1.0, lag_max=1):
        truth = {D0 + dt.timedelta(i) for i in range(N) if rnd.random() < p_strike}
        files = {}
        for i in range(N):
            f = D0 + dt.timedelta(i)
            if rnd.random() > coverage: continue
            pubs = [d + dt.timedelta(rnd.randint(0, lag_max)) for d in truth if f - dt.timedelta(2) <= d <= f and rnd.random() < recall]
            pubs = [p for p in pubs if p <= f]
            if rnd.random() < false_alarm: pubs.append(f)
            files[f] = (10, pubs)
        return truth, files
    # 1. perfect stream: d near 1, alpha near 0
    t, fl = world(0.3, 1.0, 0.0, lag_max=0); r = rates(day_table(t, fl))
    chk("perfect stream", r["d"] > 0.9 and r["alpha"] < 0.02, f"d={r['d']:.3f} alpha={r['alpha']:.3f}")
    # 2. blind stream: d near alpha, both near the false-alarm rate
    t, fl = world(0.3, 0.0, 0.05); r = rates(day_table(t, fl))
    chk("blind stream (recall 0)", abs(r["d"] - r["alpha"]) < 0.06, f"d={r['d']:.3f} alpha={r['alpha']:.3f} (equal: no information)")
    # 3. empty files are unobserved, never quiet
    t, fl = world(0.3, 0.7, 0.02); fl2 = {f: ((0, []) if i % 3 == 0 else v) for i, (f, v) in enumerate(sorted(fl.items()))}
    tab = day_table(t, fl2); chk("empty files skipped", len(tab) == sum(1 for v in fl2.values() if v[0]), f"{len(tab)} observed days")
    # 4. recovery: per-strike recall 0.6, strike rate 0.15/day, false alarms 0.02/day, no lag. Window-level truth:
    #    k ~ Bin(3, 0.15) strikes in the window; d = 1 - (1 - 0.02) * E[(1 - 0.6)^k | k >= 1]
    pk = {k: math.comb(3, k) * 0.15 ** k * 0.85 ** (3 - k) for k in (1, 2, 3)}
    true_d = 1 - 0.98 * sum(pk[k] * 0.4 ** k for k in pk) / sum(pk.values())
    est = [rates(day_table(*world(0.15, 0.6, 0.02, lag_max=0)))["d"] for _ in range(80)]
    m = sum(est) / len(est); chk("recall 0.6 per strike -> window-level d", abs(m - true_d) < 0.03, f"mean d={m:.3f} vs true {true_d:.3f}")
    # 4b. a one-day reporting lag lowers d (a strike on day f reported on f+1 is missed by file f): the estimand is what the file saw
    est = [rates(day_table(*world(0.15, 0.6, 0.02, lag_max=1)))["d"] for _ in range(80)]
    m2 = sum(est) / len(est); chk("reporting lag lowers d", m2 < m - 0.03, f"mean d={m2:.3f} with lag 0-1 vs {m:.3f} without")
    # 5. lags: lag_max=0 -> all lags 0
    t, fl = world(0.2, 1.0, 0.0, lag_max=0); L = lags(t, fl)
    chk("lag 0 stream", L and all(x == 0 for x in L), f"{len(L)} strike days, lags {sorted(set(L))}")
    # 6. posterior: d = 0.9, alpha = 0.05, pi = 0.5 -> 0.095
    p = posterior_quiet(0.5, 0.9, 0.05); chk("posterior arithmetic", abs(p - 0.1 / 1.05) < 1e-9, f"{p:.4f}")
    # 6b. persistence: independent misses -> P(miss | missed yesterday) ~ P(miss); a blackout process -> clearly higher
    t, fl = world(0.6, 0.5, 0.0, lag_max=0); r = persistence(day_table(t, fl))
    chk("independent misses", abs(r["p_miss_after_miss"] - r["p_miss"]) < 0.08, f"{r}")
    t, fl = world(0.6, 1.0, 0.0, lag_max=0); fs = sorted(fl); blind = set()
    for i in range(0, len(fs), 10): blind |= set(fs[i:i + 4])          # 4-day blackouts every 10 days
    fl = {f: ((v[0], []) if f in blind else v) for f, v in fl.items()}; r = persistence(day_table(t, fl))
    chk("clustered misses", r["p_miss_after_miss"] > r["p_miss"] + 0.3, f"{r}")
    # 6c. crowding: recall 0.9 on days under the cap, 0.3 on capped days -> d_at_cap clearly lower
    t, fl = world(0.4, 0.9, 0.0, lag_max=0); fs = sorted(fl)
    capped = set(fs[::2]); fl = {f: ((CAP, [p for p in v[1] if rnd.random() < 0.33]) if f in capped else (5, v[1])) for f, v in fl.items()}
    c = crowding(day_table(t, fl), fl)
    chk("crowding detected", c["d_at_cap"][0] < c["d_under_cap"][0] - 0.3, f"{c}")
    # 7. bootstrap returns ordered intervals
    t, fl = world(0.3, 0.7, 0.03); ci_d, ci_a = cluster_boot({"x": day_table(t, fl)}, B=300)
    chk("bootstrap intervals", ci_d[0] <= ci_d[1] and ci_a[0] <= ci_a[1], f"d {ci_d}, alpha {ci_a}")
    print("SYNTHETIC:", "ALL PASS" if ok else "FAILED"); return ok


# ── real data (local only) ───────────────────────────────────────────────────────────────────────────────────────────
def news_files(dyad, direction):
    sys.path.insert(0, str(ROOT / "pilot")); import news_strikes as NS
    lab = NS.load_labels(); out = {}
    for f, arts in NS.files(dyad):
        pubs = []
        for a in arts:
            if lab.get((dyad, NS.key(a["title"]))) == direction:
                try: pubs.append(dt.date.fromisoformat(str(a.get("publishedAt"))[:10]))
                except ValueError: pubs.append(f)
        out[f] = (len(arts), pubs)
    return out

def unlabeled_share(dyad):
    sys.path.insert(0, str(ROOT / "pilot")); import news_strikes as NS
    lab = NS.load_labels(); n = u = 0
    for f, arts in NS.files(dyad):
        for a in arts:
            n += 1; u += (dyad, NS.key(a["title"])) not in lab
    return u / n if n else None

def contract_directions():
    """Directions that strike contracts have priced ("X -> Y" with X, Y as the translator wrote them). The pooled numbers use only
    these: a reverse direction like Lebanon -> Israel has no state-forces truth while the news labels count armed groups."""
    full = {"US": "United States", "USA": "United States", "UK": "United Kingdom", "UAE": "United Arab Emirates"}
    out = set(); f = ROOT / "predictions" / "log.jsonl"
    if not f.exists(): return out
    for l in f.read_text().splitlines():
        if l.strip():
            r = json.loads(l); x, y = r.get("contract_initiator"), r.get("contract_target")
            if x and y: out.add(f"{full.get(x, x)}->{full.get(y, y)}")
    return out

def truth_days(subs, end):
    sys.path.insert(0, str(ROOT / "analysis")); import strike_given_war_fit as SGW, world_fits as WF
    S = defaultdict(set)
    for r, d in SGW._rows("explosions", end):
        if r.get("sub_event_type") not in subs or WF.MARITIME.search(r.get("country") or ""): continue
        for x in SGW._side(r, "actor1", "assoc_actor_1"):
            if x != r.get("country"): S[(x, r["country"])].add(d)
    return S

def real():
    sys.path.insert(0, str(ROOT / "pilot")); sys.path.insert(0, str(ROOT / "analysis"))
    import news_strikes as NS, refit_local as RL
    end = RL.last_complete_day(); res = {"end": end.isoformat(), "slack": SLACK, "directions": {}, "peaceful": {}}
    for tag, subs in (("primary", PRIMARY), ("air_drone_only", SENSITIVITY)):
        T = truth_days(subs, end); tables = {}
        for group, dyads in (("directions", NS.DYADS), ("peaceful", NS.PEACEFUL)):
            for dyad, (A, B) in dyads.items():
                for dirn, (x, y) in (("A_STRIKES_B", (A, B)), ("B_STRIKES_A", (B, A))):
                    fl = {f: v for f, v in news_files(dyad, dirn).items() if f <= end}
                    if not fl: continue
                    t = day_table(T.get((x, y), set()), fl); name = f"{x}->{y}"
                    r = rates(t); r["coverage"] = round(len(t) / max(1, (max(fl) - min(fl)).days + 1), 3)
                    r["window"] = [min(fl).isoformat(), max(fl).isoformat()]
                    r["d_ci"] = jeffreys(r["hits_on_strike_days"], r["n_strike_days"]); r["alpha_ci"] = jeffreys(r["hits_on_quiet_days"], r["n_quiet_days"])
                    L = lags(T.get((x, y), set()), fl); r["lag"] = {"n": len(L), "same_day": sum(1 for v in L if v == 0), "within_2": sum(1 for v in L if v is not None and v <= 2), "never": sum(1 for v in L if v is None)}
                    r["unlabeled_share"] = unlabeled_share(dyad); r["persistence"] = persistence(t); r["crowding"] = crowding(t, fl)
                    res[group].setdefault(name, {})[tag] = r
                    if group == "directions": tables[name] = t
        C = contract_directions(); keep = {k: v for k, v in tables.items() if k in C} or tables
        res["pooled_over"] = sorted(keep)
        pooled = rates([row for t in keep.values() for row in t]); pooled["d_ci_cluster"], pooled["alpha_ci_cluster"] = cluster_boot(keep)
        pooled["persistence"] = persistence([row for t in keep.values() for row in t]) if len(keep) == 1 else \
            {k: sum(persistence(t)[k] * persistence(t)["n_pairs"] for t in keep.values() if persistence(t)[k] is not None) /
                max(1, sum(persistence(t)["n_pairs"] for t in keep.values() if persistence(t)[k] is not None)) for k in ("p_miss", "p_miss_after_miss")}
        res[f"pooled_{tag}"] = pooled
    out = RL.LOCAL / "detection_rate.json"; out.write_text(json.dumps(res, indent=1, default=str))
    print(f"[detection] event data through {end}; written {out.relative_to(ROOT)}; pooled over {len(res['pooled_over'])} contract directions")
    for tag in ("primary", "air_drone_only"):
        p = res[f"pooled_{tag}"]
        print(f"  pooled ({tag}): d = {p['d']:.3f} {p['d_ci_cluster']}  alpha = {p['alpha']:.3f} {p['alpha_ci_cluster']}  "
              f"({p['n_strike_days']} strike days, {p['n_quiet_days']} quiet days)")
    print(f"  {'direction':34} {'cov':>5} {'strike d':>9} {'d':>6} {'95%':>14} {'alpha':>6} {'same-day':>9} {'<=2d':>5} {'never':>5} {'unlab':>6}")
    for group in ("directions", "peaceful"):
        for name, v in sorted(res[group].items(), key=lambda kv: -kv[1]["primary"]["n_strike_days"]):
            r = v["primary"]; dd = f"{r['d']:.2f}" if r["d"] is not None and r["n_strike_days"] >= MIN_STRIKE_DAYS else "  -"
            print(f"  {name[:34]:34} {r['coverage']:5.2f} {r['n_strike_days']:9d} {dd:>6} {str(r['d_ci']) if dd.strip() != '-' else '':>14} "
                  f"{(r['alpha'] or 0):6.3f} {r['lag']['same_day']:9d} {r['lag']['within_2']:5d} {r['lag']['never']:5d} "
                  f"{(r['unlabeled_share'] or 0):6.2f}" + ("  (peaceful)" if group == "peaceful" else ""))
    pp = res["pooled_primary"]["persistence"]
    print(f"  misses clustered? P(miss) = {pp['p_miss']:.3f}, P(miss | missed the day before) = {pp['p_miss_after_miss']:.3f} "
          f"(equal = independent; higher = clustered, a run of no-hit days is worth less than the product)")
    cr = [(n, v["primary"]["crowding"]) for n, v in res["directions"].items() if n in res["pooled_over"] and v["primary"]["n_strike_days"]]
    for n, c in sorted(cr, key=lambda x: -res["directions"][x[0]]["primary"]["n_strike_days"])[:8]:
        print(f"  crowding {n[:30]:30} days at the {CAP}-article cap {c['share_days_at_cap']:.2f}; d at cap {c['d_at_cap']}, under cap {c['d_under_cap']} (d, strike days)")
    # what a no-hit day is worth at the pooled rates
    p = res["pooled_primary"]
    for pi in (0.2, 0.5, 0.9):
        print(f"  no-hit day, prior {pi:.1f} -> posterior {posterior_quiet(pi, p['d'], p['alpha']):.3f}")


if __name__ == "__main__":
    if "--synthetic" in sys.argv: sys.exit(0 if synthetic() else 1)
    elif "--real" in sys.argv: real()
    else: print(__doc__)

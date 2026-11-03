"""docs/feed_gdelt_combined_prereg.md: can two independent eyes together make silence evidence of quiet?
Sensor 1: the new strike feed, backfilled (analysis/strike_feed_detection.py; pilot/local/strike_backfill + labels).
Sensor 2: GDELT with per-direction offsets (analysis/gdelt_baseline.py's primary rule), thresholds and code set re-learned
exactly as there on 2026-01-01..06-30 and then frozen. Test window: 2026-07-01 .. the event data's last complete day.
On each file day observed by both sensors: S = a true strike in [f-2, f] (detection_rate.PRIMARY); a joint SILENCE = neither
sensor hit. What quiet-day evidence needs is the joint-silence likelihood ratio LR = P(silence | S) / P(silence | not S).
  --synthetic   offline checks        --real   -> pilot/local/feed_gdelt_combined.json + printed summary (report only)
"""
import sys, json, random, datetime as dt
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
import detection_rate as DR

TEST_START = dt.date(2026, 7, 1)
LR_MAX, MIN_SD = 0.5, 5          # gates: pooled and macro joint-silence LR, upper 95% bound < 0.5; macro over directions with >= 5 strike days

def join(feed_tab, gdelt_tab):
    """(f, S, feed hit, gdelt hit) on days both sensors observed."""
    g = {f: o for f, s, o in gdelt_tab}
    return [(f, s, of, g[f]) for f, s, of in feed_tab if f in g]

def lr(rows):
    """Joint-silence likelihood ratio with Jeffreys-smoothed rates; None without strike or quiet days."""
    s1 = [not (a or b) for _, s, a, b in rows if s]; s0 = [not (a or b) for _, s, a, b in rows if not s]
    if not s1 or not s0: return None
    return ((sum(s1) + 0.5) / (len(s1) + 1)) / ((sum(s0) + 0.5) / (len(s0) + 1))

def boot(tables, B=2000, seed=31):
    """Pooled LR and macro LR (mean over directions with >= MIN_SD strike days); bootstrap over (direction, ISO week) blocks."""
    def macro(by):
        v = [lr(r) for r in by.values() if sum(1 for x in r if x[1]) >= MIN_SD]
        v = [x for x in v if x is not None]; return sum(v) / len(v) if v else None
    blocks = defaultdict(list)
    for k, t in tables.items():
        for row in t: blocks[(k, row[0].isocalendar()[:2])].append(row)
    keys = list(blocks); rnd = random.Random(seed); P, M = [], []
    for _ in range(B):
        by = defaultdict(list)
        for kk in (rnd.choice(keys) for _ in keys): by[kk[0]] += blocks[kk]
        p = lr([x for r in by.values() for x in r]); m = macro(by)
        if p is not None: P.append(p)
        if m is not None: M.append(m)
    q = lambda v: (round(sorted(v)[int(0.025 * len(v))], 3), round(sorted(v)[int(0.975 * len(v)) - 1], 3)) if v else None
    return lr([x for t in tables.values() for x in t]), q(P), macro(tables), q(M)

def verdict(p_ci, m_ci):
    if not p_ci or not m_ci: return "INCONCLUSIVE"
    return "PASS" if p_ci[1] < LR_MAX and m_ci[1] < LR_MAX else "FAIL"

def independence(rows):
    """On strike days: P(GDELT miss) vs P(GDELT miss | feed miss). Equal = independent misses."""
    s = [(a, b) for _, st, a, b in rows if st]
    gm = [not b for a, b in s]; gmf = [not b for a, b in s if not a]
    return {"n_strike_days": len(s), "p_gdelt_miss": round(sum(gm) / len(gm), 3) if gm else None,
            "p_gdelt_miss_given_feed_miss": round(sum(gmf) / len(gmf), 3) if gmf else None}

def real():
    import gdelt_detection as GD, gdelt_baseline as GB, strike_feed_detection as F, refit_local as RL
    G, _ = GD.load_gdelt(); GB.GAPS = GB.gap_days(G)
    end = RL.last_complete_day(); T = DR.truth_days(DR.PRIMARY, end); C = DR.contract_directions(); lab = F.bf_labels()
    dirs = [(n, *n.split("->")) for n in sorted(C) if all(x in GD.NAME for x in n.split("->"))]
    def vols(window, codes, cov):                                  # cov: countries the event data covers in the window (as in gdelt_baseline)
        D = GB.days_between(window[0] - dt.timedelta(GB.BASE_LO), window[1])
        return {n: (T.get((x, y), set()), GB.daily_volume(G.get((GD.NAME[x][0], GD.NAME[y][1]), []), D, codes), [d for d in D if d >= window[0]])
                for n, x, y in dirs if y in cov}
    cov_sel, cov_test = GB.covered(*GB.SEL), GB.covered(TEST_START, end)
    sel, fits = {}, {}
    for cname, codes in GD.CODESETS.items():                       # frozen selection, exactly as gdelt_baseline's primary rule
        V = vols(GB.SEL, codes, cov_sel); own, pooled = GB.fit_thresholds(V)
        sel[cname] = GD.youden([r for n, (tr, v, D) in V.items() for r in GB.thresh_table(tr, v, D, own.get(n, pooled))]); fits[cname] = (own, pooled)
    cname = max(sel, key=sel.get); own, pooled = fits[cname]
    V = vols((TEST_START, end), GD.CODESETS[cname], cov_test)
    sens = {}
    import news_strikes as NS
    for dyad, (A, B) in NS.DYADS.items():
        for dirn, (x, y) in (("A_STRIKES_B", (A, B)), ("B_STRIKES_A", (B, A))): sens[f"{x}->{y}"] = (dyad, dirn)
    tables, res = {}, {"end": str(end), "codeset": cname, "own_thresholds": own, "pooled_threshold": pooled, "directions": {}}
    for n, x, y in dirs:
        if n not in V or n not in sens: continue
        tr, v, D = V[n]; gt = GB.thresh_table(tr, v, D, own.get(n, pooled))
        fl = {f: z for f, z in F.files_for(*sens[n], lab, end).items() if f >= TEST_START}
        rows = join(DR.day_table(tr, fl), gt)
        if not rows: continue
        tables[n] = rows
        either = [(f, s, a or b) for f, s, a, b in rows]
        res["directions"][n] = {**DR.rates(either), "lr": lr(rows), **independence(rows), "tau": own.get(n, pooled)}
    p, pci, m, mci = boot(tables); eith = {n: [(f, s, a or b) for f, s, a, b in t] for n, t in tables.items()}
    R = DR.rates([r for t in eith.values() for r in t]); R["d_ci"], R["alpha_ci"] = DR.cluster_boot(eith)
    res.update({"pooled_lr": p, "pooled_lr_ci": pci, "macro_lr": m, "macro_lr_ci": mci, "either_stream": R,
                "independence": independence([r for t in tables.values() for r in t]), "verdict": verdict(pci, mci)})
    (ROOT / "pilot" / "local" / "feed_gdelt_combined.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"[feed+GDELT] test {TEST_START} .. {end}; GDELT code set {cname}, {len(own)} own thresholds; {len(tables)} contract directions")
    print(f"  joint-silence LR: pooled {p:.3f} {pci} | macro {m} {mci}   (gate: both upper bounds < {LR_MAX})")
    print(f"  either-stream hit: d {R['d']:.3f} {R['d_ci']}  alpha {R['alpha']:.3f} {R['alpha_ci']}  | independence {res['independence']}")
    print(f"  {'direction':28} {'strike d':>8} {'d':>5} {'alpha':>6} {'LR':>6} {'P(G miss)':>9} {'P(G miss|F miss)':>16}")
    for n, r in sorted(res["directions"].items(), key=lambda kv: -kv[1]["n_strike_days"]):
        if r["n_strike_days"]:
            print(f"  {n[:28]:28} {r['n_strike_days']:8d} {r['d']:5.2f} {r['alpha']:6.3f} {(r['lr'] if r['lr'] is not None else float('nan')):6.2f} "
                  f"{str(r['p_gdelt_miss']):>9} {str(r['p_gdelt_miss_given_feed_miss']):>16}")
    print(f"  VERDICT: {res['verdict']}")

def synthetic():
    ok = True
    def chk(name, cond, detail):
        nonlocal ok; ok &= bool(cond); print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
    rnd = random.Random(4); D0 = dt.date(2026, 7, 1)
    def world(d1, d2, a1, a2, n=110, ps=0.4, corr=False):
        feed, gd = [], []
        for i in range(n):
            f = D0 + dt.timedelta(i); s = rnd.random() < ps; u = rnd.random()
            h1 = (u < d1) if s else (rnd.random() < a1); h2 = ((u < d2) if corr else (rnd.random() < d2)) if s else (rnd.random() < a2)
            feed.append((f, s, h1)); gd.append((f, s, h2))
        return join(feed, gd)
    rows = world(0.5, 0.8, 0.05, 0.09)
    chk("join keeps days both observed", len(rows) == 110 and all(len(r) == 4 for r in rows), f"{len(rows)} rows")
    t = {f"p{i}": world(0.5, 0.8, 0.05, 0.09) for i in range(6)}; p, pci, m, mci = boot(t, B=300)
    chk("independent eyes (0.5, 0.8) -> joint d 0.9, LR ~0.12 -> PASS", verdict(pci, mci) == "PASS" and p < 0.25, f"LR {p:.3f} {pci}, macro {m:.3f} {mci}")
    t = {f"p{i}": world(0.5, 0.8, 0.05, 0.09, corr=True) for i in range(6)}; p2, *_ = boot(t, B=300)
    chk("correlated misses -> higher LR", p2 > p, f"{p2:.3f} vs {p:.3f}")
    t = {f"p{i}": world(0.1, 0.15, 0.05, 0.09) for i in range(6)}; p, pci, m, mci = boot(t, B=300)
    chk("weak eyes -> FAIL", verdict(pci, mci) == "FAIL", f"LR {p:.3f} {pci}")
    i = independence(world(0.5, 0.8, 0.05, 0.09, n=2000)); chk("independence check", abs(i["p_gdelt_miss"] - i["p_gdelt_miss_given_feed_miss"]) < 0.06, f"{i}")
    print("SYNTHETIC:", "ALL PASS" if ok else "FAILED"); return ok

if __name__ == "__main__":
    if "--synthetic" in sys.argv: sys.exit(0 if synthetic() else 1)
    elif "--real" in sys.argv: real()
    else: print(__doc__)

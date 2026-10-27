"""docs/gdelt_baseline_prereg.md: is GDELT's bias CONSISTENT per direction (a clock that is always an hour off can be read)?
docs/gdelt_detection_result.md failed on false alarms: in loud rivalries GDELT codes talk as strikes nearly every day
(United States -> Iran alpha 0.98). Primary rule here: each direction gets its OWN threshold on v_f, the articles of
strike-coded events dated [f-2, f] and published by 13:00 UTC on f (the 9am ET run), learned on 2026-01-01..06-30 where the
direction has >= 5 strike days and >= 5 quiet days there (else the pooled threshold). The thresholds are then applied, unchanged,
to 2025 (GDELT not yet looked at for 2025) against the local offline event data, with the same thresholds as the earlier
detection tests. If each direction's offset is stable across years, this passes; if not, the bias is not consistent.
Secondary (reported, no verdict): a spike above the direction's own trailing median (fails by construction in steady wars).
  python analysis/gdelt_baseline.py --synthetic    checks on synthetic data only
  python analysis/gdelt_baseline.py --real         -> pilot/local/gdelt_baseline.json (gitignored) + printed summary
Needs data/external/gdelt/strikes_20250101_20251231.jsonl and strikes_20260101_20261016.jsonl. Report only.
"""
import sys, json, random, statistics, datetime as dt
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
import detection_rate as DR, gdelt_detection as GD

SEL = (dt.date(2026, 1, 1), dt.date(2026, 6, 30))
TEST = (dt.date(2025, 1, 1), dt.date(2025, 12, 31))
BASE_LO, BASE_HI = 32, 3                       # baseline window: days f-32 .. f-3 (excludes the current 3-day window)
RATIOS = (1.5, 2.0, 3.0, 5.0)
MINART = (1, 5)
TAUS = (1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 75, 100, 150, 200, 300, 500, 750, 1000, 1500)   # candidate per-direction thresholds on v_f (articles)
MIN_DAYS = 5                                      # a direction gets its own threshold with >= 5 strike and >= 5 quiet days in SEL


# ── pure pieces (synthetic-checked) ──────────────────────────────────────────────────────────────────────────────────
def daily_volume(events, days, codes):
    """v[f] = articles of qualifying events dated [f-2, f] that GDELT had published by f's run."""
    ev = []
    for e in events:
        if e["base"] in codes:
            ev.append((dt.date(int(e["date"][:4]), int(e["date"][4:6]), int(e["date"][6:8])), e["articles"], e))
    by = defaultdict(list)
    for d, a, e in ev: by[d].append((a, e))
    v = {}
    for f in days:
        s = 0
        for k in range(3):
            for a, e in by.get(f - dt.timedelta(k), ()):
                if GD.available(e, f): s += a
        v[f] = s
    return v

def table(truth, v, days, ratio, minart):
    """(f, S, O) with O = spike above the direction's own trailing median. Days without a full baseline are skipped."""
    out = []
    for f in days:
        if not observed(f): continue
        base = [v.get(f - dt.timedelta(k)) for k in range(BASE_HI, BASE_LO + 1) if observed(f - dt.timedelta(k))]
        if len(base) < (BASE_LO - BASE_HI + 1) // 2 or len([k for k in range(BASE_HI, BASE_LO + 1) if f - dt.timedelta(k) in v]) < BASE_LO - BASE_HI + 1: continue
        b = statistics.median(base)
        S = any(f - dt.timedelta(k) in truth for k in range(3))
        O = v[f] >= minart and (v[f] + 1) / (b + 1) >= ratio
        out.append((f, S, O))
    return out

GAPS = set()   # amendment 1: days on which GDELT published nothing at all (upstream outage) are unobserved, never quiet

def gap_days(events_by_dir):
    """Days with zero GDELT rows added across ALL directions kept by the pull (a real zero is impossible at ~600 rows/day)."""
    added = set()
    for evs in events_by_dir.values():
        for e in evs: added.add(dt.date(int(e["added"][:4]), int(e["added"][4:6]), int(e["added"][6:8])))
    lo, hi = min(added), max(added)
    return {lo + dt.timedelta(i) for i in range((hi - lo).days + 1)} - added

def observed(f):
    return not any(f - dt.timedelta(k) in GAPS for k in range(3))

def thresh_table(truth, v, days, tau):
    return [(f, any(f - dt.timedelta(k) in truth for k in range(3)), v[f] >= tau) for f in days if f in v and observed(f)]

def fit_thresholds(sel_data, taus=TAUS, min_days=MIN_DAYS):
    """sel_data: {direction: (truth, v, days)} on the selection window. -> ({direction: tau}, pooled tau).
    Each direction with enough strike and quiet days gets the tau maximising its own Youden; the rest get the pooled tau."""
    pooled = max(taus, key=lambda t: GD.youden([r for tr, v, D in sel_data.values() for r in thresh_table(tr, v, D, t)]))
    own = {}
    for n, (tr, v, D) in sel_data.items():
        rows = thresh_table(tr, v, D, taus[0]); s1 = sum(1 for r in rows if r[1]); s0 = len(rows) - s1
        if s1 >= min_days and s0 >= min_days:
            own[n] = max(taus, key=lambda t: GD.youden(thresh_table(tr, v, D, t)))
    return own, pooled

def days_between(a, b):
    return [a + dt.timedelta(i) for i in range((b - a).days + 1)]


# ── synthetic check ──────────────────────────────────────────────────────────────────────────────────────────────────
def synthetic():
    rnd = random.Random(12); ok = True
    def chk(name, cond, detail):
        nonlocal ok; ok &= bool(cond); print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
    D = days_between(dt.date(2026, 1, 1), dt.date(2026, 9, 30))
    def ev(d, art, base="195"):
        return {"date": d.strftime("%Y%m%d"), "base": base, "articles": art, "added": d.strftime("%Y%m%d") + "100000"}
    # loud rivalry: ~40 strike-coded articles every day from talk alone; real strikes (episodes) add ~60
    truth = set()
    for i, d in enumerate(D):
        if (i // 10) % 6 == 0: truth.add(d)                              # 10-day strike episodes every 60 days
    E = [ev(d, max(0, int(rnd.gauss(40, 8)))) for d in D] + [ev(d, int(rnd.gauss(60, 10))) for d in truth]
    v = daily_volume(E, D, {"195"})
    raw = DR.rates([(f, any(f - dt.timedelta(k) in truth for k in range(3)), v[f] >= 10) for f in D])
    chk("raw threshold is useless on a loud pair", raw["alpha"] > 0.9, f"d={raw['d']:.2f} alpha={raw['alpha']:.2f}")
    r = DR.rates(table(truth, v, D, 2.0, 1))
    chk("own-baseline spike separates", r["d"] > 0.6 and r["alpha"] < 0.1, f"d={r['d']:.2f} alpha={r['alpha']:.2f}")
    # walk-forward: an event published after f's run does not count on f
    late = [{"date": "20260301", "base": "195", "articles": 50, "added": "20260301140000"}]
    v2 = daily_volume(late, [dt.date(2026, 3, 1), dt.date(2026, 3, 2)], {"195"})
    chk("published after the run excluded", v2[dt.date(2026, 3, 1)] == 0 and v2[dt.date(2026, 3, 2)] == 50, str(v2))
    # baseline needs 30 prior days
    chk("no baseline, no day", len(table(truth, v, D, 2.0, 1)) == len(D) - BASE_LO, f"{len(D) - BASE_LO} days scored")
    # a long war: strikes every day -> the baseline absorbs them (spike rule cannot see a steady war; reported, expected)
    steady = set(D); Es = [ev(d, 50) for d in D]; rs = DR.rates(table(steady, daily_volume(Es, D, {"195"}), D, 2.0, 1))
    chk("steady war is invisible to a spike rule (expected limit)", rs["d"] < 0.1, f"d={rs['d']:.2f}")
    # per-direction offsets: a loud pair (talk ~40/day) and a quiet pair (talk ~0) get different thresholds, and a loud pair's
    # learned threshold keeps alpha low on a later window when its offset is stable
    def world(talk, seed):
        r2 = random.Random(seed); tr = {d for i, d in enumerate(D) if (i // 7) % 4 == 0}
        E2 = [ev(d, max(0, int(r2.gauss(talk, 6)))) for d in D] + [ev(d, int(r2.gauss(60, 10))) for d in tr]
        return tr, daily_volume(E2, D, {"195"}), D
    own, pooled = fit_thresholds({"loud": world(40, 1), "quiet": world(0.5, 2)})
    chk("each direction learns its own offset", own["loud"] > own["quiet"], f"loud tau {own['loud']}, quiet tau {own['quiet']}, pooled {pooled}")
    tr, v3, D3 = world(40, 3); r3 = DR.rates(thresh_table(tr, v3, D3, own["loud"]))
    chk("stable offset carries to a new window", r3["alpha"] < 0.1 and r3["d"] > 0.7, f"d={r3['d']:.2f} alpha={r3['alpha']:.2f}")
    tr, v4, D4 = world(90, 4); r4 = DR.rates(thresh_table(tr, v4, D4, own["loud"]))
    chk("a shifted offset shows up as false alarms", r4["alpha"] > 0.5, f"talk 40 -> 90: alpha={r4['alpha']:.2f}")
    # amendment 1: an outage is unobserved, not quiet
    global GAPS
    gd = gap_days({"x": [ev(d, 5) for d in D if not (dt.date(2026, 6, 15) <= d <= dt.date(2026, 6, 20))]})
    chk("outage days found", gd == {dt.date(2026, 6, 15) + dt.timedelta(i) for i in range(6)}, f"{len(gd)} days")
    GAPS = gd; rows = thresh_table(truth, v, D, 5); GAPS = set()
    chk("outage days and the two after are skipped", not any(dt.date(2026, 6, 15) <= f <= dt.date(2026, 6, 22) for f, _, _ in rows), f"{len(rows)} days kept")
    print("SYNTHETIC:", "ALL PASS" if ok else "FAILED"); return ok


# ── real data (local only) ───────────────────────────────────────────────────────────────────────────────────────────
def covered(start, end):
    import strike_given_war_fit as SGW
    out = set()
    for kind in ("explosions", "battles"):
        for r, d in SGW._rows(kind, end):
            if d >= start: out.add(r.get("country"))
    return out

def real():
    import refit_local as RL
    G, files = GD.load_gdelt()
    if not any("2025" in Path(f).name for f in files):
        sys.exit("no 2025 GDELT pull: put strikes_20250101_20251231.jsonl in data/external/gdelt/")
    global GAPS
    GAPS = gap_days(G)
    end = RL.last_complete_day(); T = DR.truth_days(DR.PRIMARY, end); C = DR.contract_directions()
    dirs = [(n, *n.split("->")) for n in sorted(C) if all(x in GD.NAME for x in n.split("->"))]
    res = {"end": str(end), "gdelt_files": [Path(f).name for f in files], "gdelt_gap_days": sorted(str(d) for d in GAPS)}
    print(f"  GDELT outage days treated as unobserved: {len(GAPS)} ({min(GAPS) if GAPS else '-'} .. {max(GAPS) if GAPS else '-'})")
    def tabs(window, codes, ratio, minart, cov):
        D = days_between(window[0] - dt.timedelta(BASE_LO), window[1]); out = {}
        for n, x, y in dirs:
            if y not in cov: continue
            ev = G.get((GD.NAME[x][0], GD.NAME[y][1]), [])
            v = daily_volume(ev, D, codes)
            out[n] = [r for r in table(T.get((x, y), set()), v, D, ratio, minart) if r[0] >= window[0]]
        return out
    cov_sel, cov_test = covered(*SEL), covered(*TEST)
    def vols(window, codes, cov):
        D = days_between(window[0] - dt.timedelta(BASE_LO), window[1]); out = {}
        for n, x, y in dirs:
            if y not in cov: continue
            out[n] = (T.get((x, y), set()), daily_volume(G.get((GD.NAME[x][0], GD.NAME[y][1]), []), D, codes), [d for d in D if d >= window[0]], D)
        return out
    # PRIMARY: per-direction thresholds, code set chosen by pooled Youden on the selection window
    sel = {}; fits = {}
    for cname, codes in GD.CODESETS.items():
        V = vols(SEL, codes, cov_sel); own, pooled = fit_thresholds({n: (tr, v, D) for n, (tr, v, D, _) in V.items()})
        rows = [r for n, (tr, v, D, _) in V.items() for r in thresh_table(tr, v, D, own.get(n, pooled))]
        sel[cname] = round(GD.youden(rows), 4); fits[cname] = (own, pooled)
    cname = max(sel, key=sel.get); own, pooled = fits[cname]
    res["selection"] = {"window": [str(SEL[0]), str(SEL[1])], "youden_by_codeset": sel, "chosen": cname, "own_thresholds": own, "pooled_threshold": pooled}
    V = vols(TEST, GD.CODESETS[cname], cov_test)
    tb = {n: thresh_table(tr, v, D, own.get(n, pooled)) for n, (tr, v, D, _) in V.items()}
    P = DR.rates([r for t in tb.values() for r in t]); P["d_ci_cluster"], P["alpha_ci_cluster"] = DR.cluster_boot(tb)
    P["passes_rule"] = bool(P["d_ci_cluster"] and P["d_ci_cluster"][0] >= 0.50 and P["alpha"] is not None and P["alpha"] <= 0.10)
    P["no_hit_likelihood_ratio"] = round((1 - P["d"]) / (1 - P["alpha"]), 3) if P["d"] is not None and P["alpha"] is not None else None
    O = [r for n, t in tb.items() if n in own for r in t]
    res["test"] = {"window": [str(TEST[0]), str(TEST[1])], "pooled": P, "own_threshold_directions_only": DR.rates(O) if O else None,
                   "by_direction": {n: {**DR.rates(t), "tau": own.get(n, pooled), "own": n in own} for n, t in tb.items()},
                   "not_covered": [n for n, x, y in dirs if y not in cov_test]}
    # SECONDARY (report only): spike above the direction's own trailing median, same selection/test split
    sp = {}
    for c2, codes in GD.CODESETS.items():
        V2 = vols(SEL, codes, cov_sel)
        for ratio in RATIOS:
            for m in MINART:
                sp[f"{c2}|{ratio}|{m}"] = round(GD.youden([r for n, (tr, v, D, Dall) in V2.items() for r in table(tr, v, Dall, ratio, m) if r[0] >= SEL[0]]), 4)
    b2 = max(sp, key=sp.get); c2, r2, m2 = b2.split("|")
    V3 = vols(TEST, GD.CODESETS[c2], cov_test)
    S2 = DR.rates([r for n, (tr, v, D, Dall) in V3.items() for r in table(tr, v, Dall, float(r2), int(m2)) if r[0] >= TEST[0]])
    res["secondary_spike"] = {"chosen": b2, "test": S2}
    out = RL.LOCAL / "gdelt_baseline.json"; out.write_text(json.dumps(res, indent=1, default=str))
    print(f"[gdelt-baseline] event data through {end}; written {out.relative_to(ROOT)}")
    print(f"  selection (2026 Jan-Jun): code set {cname}; {len(own)} directions with their own threshold, pooled threshold {pooled} for the rest")
    print(f"  TEST (2025, unseen): d = {P['d']:.3f} {P['d_ci_cluster']}  alpha = {P['alpha']:.3f} {P['alpha_ci_cluster']}  "
          f"({P['n_strike_days']} strike days, {P['n_quiet_days']} quiet days)  -> {'PASSES' if P['passes_rule'] else 'FAILS'} the rule")
    print(f"  a no-hit day multiplies the odds of a strike by {P['no_hit_likelihood_ratio']}")
    if res["test"]["own_threshold_directions_only"]:
        o = res["test"]["own_threshold_directions_only"]; print(f"  directions with their own threshold only: d = {o['d']:.3f}, alpha = {o['alpha']:.3f}")
    print(f"  secondary (spike rule {b2}): d = {S2['d']:.3f}, alpha = {S2['alpha']:.3f} (report only)")
    print(f"  {'direction':30} {'own?':>5} {'tau':>5} {'strike d':>9} {'d':>6} {'alpha':>6}")
    for n, r in sorted(res["test"]["by_direction"].items(), key=lambda kv: -kv[1]["n_strike_days"]):
        if r["n_strike_days"] or (r["alpha"] or 0) > 0.05:
            print(f"  {n[:30]:30} {'yes' if r['own'] else 'no':>5} {r['tau']:5d} {r['n_strike_days']:9d} {(r['d'] or 0):6.2f} {(r['alpha'] or 0):6.3f}")

if __name__ == "__main__":
    if "--synthetic" in sys.argv: sys.exit(0 if synthetic() else 1)
    elif "--real" in sys.argv: real()
    else: print(__doc__)

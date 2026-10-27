"""docs/gdelt_detection_prereg.md: can GDELT be the second, independent live source that sees strikes (and so quiet days)?
Same estimands as docs/detection_prereg.md (d, alpha, per direction X -> Y, on each day f), measured against the local
offline event data. GDELT's evidence rule (event codes x minimum article count) is selected on 2026-01-01..06-30 and
tested once on 2026-07-01..the event data's last complete day. Walk-forward: an event counts on day f only if GDELT had
published it (DATEADDED) by 13:00 UTC on f, i.e. by the 9am ET run.
  python analysis/gdelt_detection.py --synthetic    checks on synthetic data only (no real data touched)
  python analysis/gdelt_detection.py --real         -> pilot/local/gdelt_detection.json (gitignored) + printed summary
Needs data/external/gdelt/strikes_*.jsonl (analysis/gdelt_pull.py). Report only: nothing here touches production.
"""
import sys, json, glob, random, datetime as dt
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import detection_rate as DR

SEL = (dt.date(2026, 1, 1), dt.date(2026, 6, 30))
TEST_START = dt.date(2026, 7, 1)
CUTOFF_UTC = dt.time(13, 0)                                   # 9am EDT; the daily run's news files are written then
CODESETS = {"air_artillery": {"194", "195"}, "plus_generic_force": {"190", "194", "195"}}
KS = (1, 2, 3, 5, 10)                                         # minimum NumArticles for an event to count
NAME = {   # event-data country name -> (CAMEO actor code, FIPS location code)
    "Israel": ("ISR", "IS"), "Lebanon": ("LBN", "LE"), "Syria": ("SYR", "SY"), "Iran": ("IRN", "IR"), "Oman": ("OMN", "MU"),
    "Saudi Arabia": ("SAU", "SA"), "Yemen": ("YEM", "YM"), "Iraq": ("IRQ", "IZ"), "Kuwait": ("KWT", "KU"),
    "United Arab Emirates": ("ARE", "AE"), "Jordan": ("JOR", "JO"), "Bahrain": ("BHR", "BA"), "Qatar": ("QAT", "QA"),
    "Egypt": ("EGY", "EG"), "Pakistan": ("PAK", "PK"), "Afghanistan": ("AFG", "AF"), "Eritrea": ("ERI", "ER"),
    "Ethiopia": ("ETH", "ET"), "United States": ("USA", "US"), "United Kingdom": ("GBR", "UK"), "France": ("FRA", "FR"),
    "Germany": ("DEU", "GM"), "Turkey": ("TUR", "TU"), "China": ("CHN", "CH"), "Taiwan": ("TWN", "TW"), "Japan": ("JPN", "JA"),
    "India": ("IND", "IN"), "Russia": ("RUS", "RS"), "Ukraine": ("UKR", "UP"), "Philippines": ("PHL", "RP"),
    "North Korea": ("PRK", "KN"), "South Korea": ("KOR", "KS"), "Cuba": ("CUB", "CU"), "Colombia": ("COL", "CO"),
    "Mexico": ("MEX", "MX"), "Venezuela": ("VEN", "VE"), "Denmark": ("DNK", "DA"), "Panama": ("PAN", "PM"),
}


# ── pure pieces (synthetic-checked) ──────────────────────────────────────────────────────────────────────────────────
def available(ev, f):
    """GDELT had published the event by the morning run on day f."""
    a = ev["added"]
    t = dt.datetime(int(a[:4]), int(a[4:6]), int(a[6:8]), int(a[8:10] or 0), int(a[10:12] or 0))
    return t <= dt.datetime.combine(f, CUTOFF_UTC)

def gdelt_files(events, days, codes, k):
    """events: list of dicts for ONE direction. -> {f: (1, [event dates available by f's run])}: GDELT has no coverage gaps."""
    evs = [e for e in events if e["base"] in codes and e["articles"] >= k]
    for e in evs:
        e["_d"] = dt.date(int(e["date"][:4]), int(e["date"][4:6]), int(e["date"][6:8]))
    out = {}
    for f in days:
        out[f] = (1, [e["_d"] for e in evs if f - dt.timedelta(2) <= e["_d"] <= f and available(e, f)])
    return out

def youden(table):
    r = DR.rates(table)
    return (r["d"] or 0) - (r["alpha"] or 0)

def combine(news_tab, gdelt_tab):
    """On days with a news file: (f, S, news O, GDELT O). -> tables for 'either' and the miss-independence check."""
    g = {f: o for f, s, o in gdelt_tab}
    rows = [(f, s, on, g[f]) for f, s, on in news_tab if f in g]
    either = [(f, s, on or og) for f, s, on, og in rows]
    s1 = [(on, og) for f, s, on, og in rows if s]
    gm = [not og for on, og in s1]; gm_nm = [not og for on, og in s1 if not on]
    return either, {"n_strike_days": len(s1), "p_gdelt_miss": round(sum(gm) / len(gm), 3) if gm else None,
                    "p_gdelt_miss_given_news_miss": round(sum(gm_nm) / len(gm_nm), 3) if gm_nm else None, "n_news_miss": len(gm_nm)}

def days_between(a, b):
    return [a + dt.timedelta(i) for i in range((b - a).days + 1)]


# ── synthetic check ──────────────────────────────────────────────────────────────────────────────────────────────────
def synthetic():
    rnd = random.Random(9); ok = True
    def chk(name, cond, detail):
        nonlocal ok; ok &= bool(cond); print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
    D = days_between(dt.date(2026, 1, 1), dt.date(2026, 9, 30))
    truth = {d for d in D if rnd.random() < 0.3}
    def ev(d, base, art, add_delay_h):
        t = dt.datetime.combine(d, dt.time(10)) + dt.timedelta(hours=add_delay_h)
        return {"date": d.strftime("%Y%m%d"), "base": base, "articles": art, "added": t.strftime("%Y%m%d%H%M%S")}
    # true strikes: reported with code 195, 1-20 articles, published 0-30h later; noise: code 190 every day, 1-2 articles
    E = [ev(d, "195", rnd.randint(1, 20), rnd.uniform(0, 30)) for d in truth if rnd.random() < 0.85]
    E += [ev(d, "190", rnd.randint(1, 2), 1) for d in D if rnd.random() < 0.5]
    # 1. walk-forward: an event published after 13:00 UTC on f does not count on f
    e = ev(dt.date(2026, 3, 1), "195", 5, 4)                   # event day 10:00 + 4h = 14:00 UTC
    chk("published after the run is excluded", not available(e, dt.date(2026, 3, 1)) and available(e, dt.date(2026, 3, 2)), e["added"])
    # 2. the article threshold filters
    fl = gdelt_files([ev(dt.date(2026, 3, 1), "195", 2, 0)], [dt.date(2026, 3, 1)], {"195"}, 3)
    chk("article threshold", fl[dt.date(2026, 3, 1)][1] == [], "2 articles < k=3 -> no hit")
    # 3. selection: the generic-force code set adds pure noise here, so air/artillery must win on Youden
    best = max(((name, k) for name in CODESETS for k in KS),
               key=lambda c: youden(DR.day_table(truth, gdelt_files([dict(x) for x in E], D, CODESETS[c[0]], c[1]))))
    chk("selection prefers the informative code set", best[0] == "air_artillery", f"chosen {best}")
    # 4. combination: news with recall 0.4 independent of GDELT -> P(GDELT miss | news miss) ~ P(GDELT miss)
    g_tab = DR.day_table(truth, gdelt_files([dict(x) for x in E], D, {"195"}, 1))
    news = {f: (10, [d for d in truth if f - dt.timedelta(2) <= d <= f and rnd.random() < 0.4]) for f in D}
    n_tab = DR.day_table(truth, news)
    either, ind = combine(n_tab, g_tab)
    dn, dg, de = DR.rates(n_tab)["d"], DR.rates(g_tab)["d"], DR.rates(either)["d"]
    chk("independent misses", abs(ind["p_gdelt_miss_given_news_miss"] - ind["p_gdelt_miss"]) < 0.08, str(ind))
    chk("combined d ~ 1-(1-d1)(1-d2)", abs(de - (1 - (1 - dn) * (1 - dg))) < 0.06, f"news {dn:.2f}, gdelt {dg:.2f}, either {de:.2f}")
    print("SYNTHETIC:", "ALL PASS" if ok else "FAILED"); return ok


# ── real data (local only) ───────────────────────────────────────────────────────────────────────────────────────────
def load_gdelt():
    files = sorted(glob.glob(str(ROOT / "data" / "external" / "gdelt" / "strikes_*.jsonl")))
    if not files:
        sys.exit("no GDELT pull found: run analysis/gdelt_pull.py 2026-01-01 2026-10-16 (or put the provided file in data/external/gdelt/)")
    by = defaultdict(list); seen = set()
    for fn in files:
        for l in open(fn):
            if l.strip():
                e = json.loads(l)
                if e["id"] in seen: continue
                seen.add(e["id"]); by[(e["actor"], e["geo"])].append(e)
    return by, files

def covered_countries(end):
    """Countries the local event data has ANY located event in during the test window (a coverage check, not truth)."""
    import strike_given_war_fit as SGW
    out = set()
    for kind in ("explosions", "battles"):
        for r, d in SGW._rows(kind, end):
            if d >= SEL[0]: out.add(r.get("country"))
    return out

def real():
    import refit_local as RL, news_strikes as NS
    end = RL.last_complete_day(); G, gfiles = load_gdelt()
    T = DR.truth_days(DR.PRIMARY, end); C = DR.contract_directions(); cov = covered_countries(end)
    dirs = []
    for name in sorted(C):
        x, y = name.split("->")
        if x in NAME and y in NAME: dirs.append((name, x, y))
    pooled = [n for n, x, y in dirs if y in cov]
    res = {"end": str(end), "gdelt_files": [Path(f).name for f in gfiles], "directions": [n for n, _, _ in dirs],
           "pooled_over": pooled, "excluded_not_covered": [n for n, x, y in dirs if y not in cov]}
    def tables(window, codes, k):
        D = days_between(*window); out = {}
        for n, x, y in dirs:
            ev = [dict(e) for e in G.get((NAME[x][0], NAME[y][1]), [])]
            out[n] = DR.day_table(T.get((x, y), set()), gdelt_files(ev, D, codes, k))
        return out
    # 1. selection on the first half of 2026 (pooled Youden over covered contract directions)
    sel = {}
    for cname, codes in CODESETS.items():
        for k in KS:
            tb = tables(SEL, codes, k); sel[f"{cname}|k={k}"] = round(youden([r for n in pooled for r in tb[n]]), 4)
    best = max(sel, key=sel.get); cname, k = best.split("|k="); k = int(k)
    res["selection"] = {"window": [str(SEL[0]), str(SEL[1])], "youden": sel, "chosen": best}
    # 2. one test on Jul 1 .. end
    tb = tables((TEST_START, end), CODESETS[cname], k); keep = {n: tb[n] for n in pooled}
    P = DR.rates([r for t in keep.values() for r in t]); P["d_ci_cluster"], P["alpha_ci_cluster"] = DR.cluster_boot(keep)
    P["passes_rule"] = bool(P["d_ci_cluster"] and P["d_ci_cluster"][0] >= 0.50 and P["alpha"] is not None and P["alpha"] <= 0.10)
    res["test"] = {"window": [str(TEST_START), str(end)], "pooled": P,
                   "by_direction": {n: DR.rates(t) for n, t in tb.items()}}
    # 3. with our news stream: misses independent? combined d and alpha, on test-window days with a news file
    comb_tabs = {}; indep = {}
    news_dir = {}
    for dy, (A, B) in NS.DYADS.items():
        news_dir[f"{A}->{B}"] = (dy, "A_STRIKES_B"); news_dir[f"{B}->{A}"] = (dy, "B_STRIKES_A")
    for n, x, y in dirs:
        if n not in pooled or n not in news_dir: continue
        fl = {f: v for f, v in DR.news_files(*news_dir[n]).items() if TEST_START <= f <= end}
        n_tab = DR.day_table(T.get((x, y), set()), fl)
        either, ind = combine(n_tab, tb[n]); comb_tabs[n] = either; indep[n] = ind
    E = DR.rates([r for t in comb_tabs.values() for r in t]); E["d_ci_cluster"], E["alpha_ci_cluster"] = DR.cluster_boot(comb_tabs) if comb_tabs else (None, None)
    E["passes_rule"] = bool(E["d_ci_cluster"] and E["d_ci_cluster"][0] >= 0.50 and E["alpha"] is not None and E["alpha"] <= 0.10)
    s1 = sum(v["n_strike_days"] for v in indep.values())
    pm = sum((v["p_gdelt_miss"] or 0) * v["n_strike_days"] for v in indep.values()) / max(1, s1)
    nm = sum(v["n_news_miss"] for v in indep.values())
    pmn = sum((v["p_gdelt_miss_given_news_miss"] or 0) * v["n_news_miss"] for v in indep.values()) / max(1, nm)
    res["combined"] = {"pooled_either": E, "independence": {"p_gdelt_miss": round(pm, 3), "p_gdelt_miss_given_news_miss": round(pmn, 3),
                       "n_strike_days": s1, "n_news_miss": nm}, "by_direction": indep}
    out = RL.LOCAL / "gdelt_detection.json"; out.write_text(json.dumps(res, indent=1, default=str))
    # report
    print(f"[gdelt] event data through {end}; {len(pooled)} covered contract directions pooled; written {out.relative_to(ROOT)}")
    if res["excluded_not_covered"]: print(f"  not covered by the local event data (excluded from pooling): {res['excluded_not_covered']}")
    print(f"  selection (Jan-Jun, Youden d - alpha): chosen {best}; " + ", ".join(f"{c} {v:+.3f}" for c, v in sorted(sel.items(), key=lambda kv: -kv[1])[:4]))
    print(f"  TEST (Jul 1-{end}): GDELT alone d = {P['d']:.3f} {P['d_ci_cluster']}  alpha = {P['alpha']:.3f} {P['alpha_ci_cluster']}"
          f"  ({P['n_strike_days']} strike days)  -> {'PASSES' if P['passes_rule'] else 'FAILS'} the rule")
    if comb_tabs:
        print(f"  TEST news OR GDELT (days with a news file): d = {E['d']:.3f} {E['d_ci_cluster']}  alpha = {E['alpha']:.3f} {E['alpha_ci_cluster']}"
              f"  -> {'PASSES' if E['passes_rule'] else 'FAILS'} the rule")
        i = res["combined"]["independence"]
        print(f"  misses independent? P(GDELT miss) = {i['p_gdelt_miss']}, P(GDELT miss | news missed) = {i['p_gdelt_miss_given_news_miss']}")
    print(f"  {'direction':30} {'strike d':>9} {'d':>6} {'alpha':>6}")
    for n, r in sorted(res["test"]["by_direction"].items(), key=lambda kv: -kv[1]["n_strike_days"]):
        if n in pooled and r["n_strike_days"]:
            print(f"  {n[:30]:30} {r['n_strike_days']:9d} {(r['d'] or 0):6.2f} {(r['alpha'] or 0):6.3f}")


if __name__ == "__main__":
    if "--synthetic" in sys.argv: sys.exit(0 if synthetic() else 1)
    elif "--real" in sys.argv:
        sys.path.insert(0, str(ROOT / "pilot")); real()
    else: print(__doc__)

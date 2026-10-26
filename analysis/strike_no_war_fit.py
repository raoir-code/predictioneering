"""docs/strike_no_war_prereg.md: empirical P(B|not A) = P(X's forces air/drone-strike Y's territory in the next W days | no war
episode between X and Y), as a window hit rate over a lookback L, from the local offline pull. Gitignored outputs:
  python analysis/strike_no_war_fit.py --synthetic    estimator checks on synthetic data only (no real data touched)
  python analysis/strike_no_war_fit.py --validate     select L (origins 2019-2022), gate 1 (origins 2023 .. 2026-05) -> pilot/local/strike_no_war_validation.json
  python analysis/strike_no_war_fit.py --production   frozen table at the last complete day, selected L -> pilot/local/strike_no_war_candidate.json
"""
import sys, re, json, math, random, datetime as dt
from collections import defaultdict
from pathlib import Path

LS = (90, 180, 365, 730)
WS = (7, 30, 60)
GAP, MIN_FAT = 30, 25
MIN_REF = 7          # markets with a shorter LLM reference period (daily contracts) are not in the universe
NAMES = {"US": "United States", "USA": "United States", "UK": "United Kingdom", "UAE": "United Arab Emirates"}
D0 = dt.date(2015, 1, 1)

# ── estimator (pure; synthetic-checked) ──────────────────────────────────────────────────────────────────────────────
def prefix(flags):
    p = [0]
    for f in flags: p.append(p[-1] + (1 if f else 0))
    return p

def estimate(ps, pw, t, L, W):
    """ps/pw: prefix sums of daily strike / war flags (index 0 = D0). t: index of the forecast day (inclusive, lookback ends at t).
    Returns (p, share, n) or None. Windows [s, s+W-1] inside (t-L, t], war-free; n = non-war days in the lookback / W."""
    lo = max(0, t - L + 1)
    nonwar = (t + 1 - lo) - (pw[t + 1] - pw[lo])
    if nonwar < W: return None
    hits = tot = 0
    for s in range(lo, t - W + 2):
        if pw[s + W] - pw[s]: continue
        tot += 1; hits += 1 if ps[s + W] - ps[s] else 0
    if not tot: return None
    share = hits / tot; n = nonwar / W
    return (share * n + 0.5) / (n + 1), share, n

def outcome(ps, pw, t, W):
    """1/0 for a strike in (t, t+W]; None if that window has a war day (the estimand conditions on no war)."""
    if pw[t + W + 1] - pw[t + 1]: return None
    return 1 if ps[t + W + 1] - ps[t + 1] else 0

def llm_window(h, ref, W, cap=True):
    """Production conversion of the LLM rate: 1 - (1 - p)^(min(W, ref)/ref) == 1 - (1 - h)^min(W, ref), h the daily hazard.
    cap=False: the LLM's implied belief at W (no cap); the gate uses it (most favourable reading of the LLM)."""
    return 1 - (1 - h) ** (min(W, ref) if cap else W)

# ── synthetic check ──────────────────────────────────────────────────────────────────────────────────────────────────
def synthetic():
    rnd = random.Random(7); N = 3000; ok = True
    def chk(name, cond, detail):
        nonlocal ok; ok &= bool(cond); print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
    nowar = prefix([0] * N)
    # 1. zero-rate pair: estimate is the Jeffreys floor, near 0
    ps = prefix([0] * N); e = estimate(ps, nowar, N - 1, 365, 30)
    chk("zero-rate pair", e[0] < 0.05 and e[1] == 0, f"p={e[0]:.4f} (floor 0.5/(n+1), n={e[2]:.1f})")
    # 2. Bernoulli daily rate 0.02: true P(>=1 in 30) = 1 - 0.98^30; mean estimate over replications
    true = 1 - 0.98 ** 30; est = []
    for _ in range(200):
        ps = prefix([rnd.random() < 0.02 for _ in range(N)]); est.append(estimate(ps, nowar, N - 1, 365, 30)[0])
    m = sum(est) / len(est); chk("Bernoulli 0.02/day, W=30, L=365", abs(m - true) < 0.05, f"mean est {m:.3f} vs true {true:.3f}")
    # 3. bursty: bursts start w.p. 0.01/day, each lasts 5 days with a strike every day. Daily-rate conversion overstates P(>=1).
    def bursty():
        f = [0] * N; i = 0
        while i < N:
            if rnd.random() < 0.01:
                for k in range(5):
                    if i + k < N: f[i + k] = 1
                i += 5
            else: i += 1
        return f
    sims = [bursty() for _ in range(300)]
    # true P(>=1 in next 30 | stationary), by simulation at a fixed point
    truth = sum(1 for f in sims if any(f[2000:2030])) / len(sims)
    est = []; naive = []
    for f in sims[:150]:
        ps = prefix(f); est.append(estimate(ps, nowar, 1999, 365, 30)[0])
        h = sum(f[1635:2000]) / 365; naive.append(1 - (1 - h) ** 30)
    m, mn = sum(est) / len(est), sum(naive) / len(naive)
    chk("bursty strikes, W=30", abs(m - truth) < 0.06 and abs(m - truth) < abs(mn - truth),
        f"window hit rate {m:.3f}, daily-rate conversion {mn:.3f}, true {truth:.3f}")
    # 4. rate drop at day 2500 (0.05/day -> 0.002/day): short lookback tracks, long lookback lags
    f = [rnd.random() < (0.05 if i < 2500 else 0.002) for i in range(N)]; ps = prefix(f)
    true = 1 - (1 - 0.002) ** 30; e90, e730 = estimate(ps, nowar, N - 1, 90, 30)[0], estimate(ps, nowar, N - 1, 730, 30)[0]
    chk("rate drop, L=90 vs L=730", abs(e90 - true) < abs(e730 - true), f"L=90 {e90:.3f}, L=730 {e730:.3f}, true now {true:.3f}")
    # 5. strikes inside war episodes are not counted; outcome windows with war days are skipped
    war = [1 if 2700 <= i < 2900 else 0 for i in range(N)]; pw = prefix(war)
    ps = prefix([1 if 2700 <= i < 2900 else 0 for i in range(N)])
    e = estimate(ps, pw, N - 1, 365, 30)
    chk("war-day strikes masked", e is not None and e[1] == 0, f"share {e[1] if e else None} (all strikes are on war days)")
    chk("outcome window with war day skipped", outcome(ps, pw, 2690, 30) is None and outcome(ps, pw, 2950, 30) == 0, "")
    # 6. too little non-war lookback -> no estimate (LLM value stays)
    war = [1 if i >= N - 340 else 0 for i in range(N)]
    chk("lookback mostly war -> None", estimate(prefix([0] * N), prefix(war), N - 1, 365, 30) is None, "")
    # 7. the LLM conversion caps at the reference period (documented production behaviour)
    chk("LLM conversion caps at ref", abs(llm_window(0.01, 30, 66) - llm_window(0.01, 30, 30)) < 1e-12, "")
    print("SYNTHETIC CHECK:", "ALL PASS" if ok else "FAILURES (amend before any real data)")
    return ok

# ── real data (local, gitignored) ────────────────────────────────────────────────────────────────────────────────────
def _parse(q):
    m = re.match(r"^(?:Will )?(.+?) (?:military action against|target|strike|attack) (.+?) (?:by|on|before) ", q or "")
    if not m: return None, None
    ini = [x.strip() for x in re.split(r",\s*(?:or\s+)?|\s+or\s+", m.group(1)) if x.strip()]
    tgt = re.sub(r"^(?:the|on) ", "", m.group(2).strip())
    return [NAMES.get(x, x) for x in ini], NAMES.get(tgt, tgt)

def universe():
    """Directions from qualifying contracts in predictions/log.jsonl (first logged forecast per market), with the LLM daily hazard."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pilot")); from strike_given_war import qualifies
    first = {}
    for l in (Path(__file__).resolve().parent.parent / "predictions" / "log.jsonl").read_text().splitlines():
        if l.strip():
            r = json.loads(l); mid = str(r.get("market_id"))
            if mid not in first and r.get("pricing_component") in (None, "engine") and qualifies(r) and r.get("p_b_given_not_a") is not None:
                first[mid] = r
    pairs = defaultdict(lambda: {"h": [], "ref": [], "markets": [], "fields": set()})
    daily = set()
    for mid, r in first.items():
        ini, tgt = _parse(r.get("market_label"))
        if not ini or not tgt or tgt.startswith(("a ", "an ")): continue
        k = (tuple(sorted(ini)), tgt); p, ref = float(r["p_b_given_not_a"]), float(r.get("p_b_given_not_a_reference_days") or 365)
        if ref < MIN_REF: daily.add(k); continue
        pairs[k]["h"].append(1 - (1 - min(p, 0.999999)) ** (1 / ref)); pairs[k]["ref"].append(ref); pairs[k]["markets"].append(mid)
        pairs[k]["fields"].add((NAMES.get(r.get("contract_initiator"), r.get("contract_initiator")), NAMES.get(r.get("contract_target"), r.get("contract_target"))))
    if daily - set(pairs): print("  daily-contract-only directions (excluded):", sorted(daily - set(pairs)))
    return {k: {"h": sum(v["h"]) / len(v["h"]), "ref": sorted(v["ref"])[len(v["ref"]) // 2], "markets": v["markets"], "fields": v["fields"]} for k, v in pairs.items()}

def series(end, subs):
    """(initiators, target) -> (prefix strikes, prefix war) over D0..end, for every universe direction found in the data."""
    sys.path.insert(0, str(Path(__file__).resolve().parent)); import strike_given_war_fit as SGW, world_fits as WF
    U = universe(); N = (end - D0).days + 1
    strike = defaultdict(set); countries = set()
    for r, d in SGW._rows("explosions", end):
        countries.add(r.get("country")); countries |= SGW._side(r, "actor1", "assoc_actor_1") | SGW._side(r, "actor2", "assoc_actor_2")
        if d < D0 or r.get("sub_event_type") not in subs or WF.MARITIME.search(r.get("country") or ""): continue
        for x in SGW._side(r, "actor1", "assoc_actor_1"):
            if x != r.get("country"): strike[(x, r["country"])].add((d - D0).days)
    E = SGW.episodes(end); out = {}; skipped = []
    for (ini, tgt), v in U.items():
        # Amendment 1 (Oct 26): a name is matched if the event data knows it (as a location or a state's forces) OR it is the
        # contract's own translated initiator/target field; a country with no events is a matched name with zero strikes, not
        # an unmatched name. A target that differs from the contract's target field (e.g. "Greater Beirut" vs Lebanon) is sub-state.
        ti, tt = {f[0] for f in v["fields"]}, {f[1] for f in v["fields"]}
        if tgt not in tt or not any(x in countries or x in ti for x in ini): skipped.append((ini, tgt)); continue
        if any(x not in countries for x in ini): print(f"  initiator(s) with no events in the data (zero strikes): {[x for x in ini if x not in countries]} -> {tgt}")
        sd = set().union(*(strike.get((x, tgt), set()) for x in ini)); wd = set()
        for x in ini:
            for s, e, fat in E.get(tuple(sorted((x, tgt))), []):
                if fat < MIN_FAT: continue
                for i in range((max(s, D0) - D0).days, min((e - D0).days + GAP, N - 1) + 1): wd.add(i)
        out[(ini, tgt)] = (prefix([i in sd for i in range(N)]), prefix([i in wd for i in range(N)]), v)
    if skipped: print("  not in the event data (excluded):", skipped)
    return out

def monthly(a, b):
    d = a
    while d <= b:
        yield d; d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)

def score(S, origins, end, L, use_llm):
    rows = []
    for k, (ps, pw, v) in S.items():
        for o in origins:
            t = (o - D0).days
            for W in WS:
                if o + dt.timedelta(W) > end or pw[t + 1] - pw[t]: continue
                y = outcome(ps, pw, t, W); e = estimate(ps, pw, t, L, W)
                if y is None or e is None: continue
                rows.append({"pair": f"{'+'.join(k[0])}->{k[1]}", "W": W, "y": y, "emp": e[0], "llm": llm_window(v["h"], v["ref"], W, cap=False) if use_llm else None,
                             "llm_capped": llm_window(v["h"], v["ref"], W) if use_llm else None})
    return rows

def brier(rows, key): return sum((r[key] - r["y"]) ** 2 for r in rows) / max(1, len(rows))
def logloss(rows, key): return -sum(math.log(max(1e-6, r[key] if r["y"] else 1 - r[key])) for r in rows) / max(1, len(rows))

def validate():
    sys.path.insert(0, str(Path(__file__).resolve().parent)); import refit_local as RL
    sel_end, test_end = dt.date(2022, 12, 31), dt.date(2026, 6, 30)
    S = series(test_end, {"Air/drone strike"})
    sel = {L: brier(score(S, list(monthly(dt.date(2019, 1, 1), dt.date(2022, 12, 1))), sel_end, L, False), "emp") for L in LS}
    L = min(sel, key=sel.get)
    print("SELECTION (origins 2019-01 .. 2022-12):", {k: round(v, 4) for k, v in sel.items()}, "-> L =", L)
    rows = score(S, list(monthly(dt.date(2023, 1, 1), dt.date(2026, 5, 1))), test_end, L, True)
    be, bl = brier(rows, "emp"), brier(rows, "llm")
    pairs = sorted({r["pair"] for r in rows}); rnd = random.Random(1); by = defaultdict(list)
    for r in rows: by[r["pair"]].append(r)
    diffs = []
    for _ in range(2000):
        smp = [r for p in (rnd.choice(pairs) for _ in pairs) for r in by[p]]
        diffs.append(brier(smp, "emp") - brier(smp, "llm"))
    diffs.sort(); ci = (diffs[49], diffs[1949])
    res = {"L": L, "selection": sel, "n": len(rows), "yes": sum(r["y"] for r in rows), "pairs": len(pairs),
           "brier_emp": be, "brier_llm": bl, "brier_llm_capped": brier(rows, "llm_capped"), "logloss_emp": logloss(rows, "emp"), "logloss_llm": logloss(rows, "llm"),
           "boot95_emp_minus_llm": ci, "gate1_pass": be <= bl and len(rows) > 0,
           "by_pair": {p: {"n": len(by[p]), "yes": sum(r["y"] for r in by[p]), "emp": brier(by[p], "emp"), "llm": brier(by[p], "llm")} for p in pairs},
           "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    print(f"GATE 1 (origins 2023-01 .. 2026-05, W in {WS}): {res['n']} pair-windows ({res['yes']} YES) over {res['pairs']} pairs | "
          f"Brier empirical {be:.4f} vs LLM {bl:.4f} (log loss {res['logloss_emp']:.4f} vs {res['logloss_llm']:.4f}) | "
          f"bootstrap emp-llm 95% [{ci[0]:+.4f}, {ci[1]:+.4f}] -> {'PASS' if res['gate1_pass'] else 'FAIL'}")
    for p, v in res["by_pair"].items(): print(f"    {p:40} n {v['n']:4} yes {v['yes']:4} emp {v['emp']:.4f} llm {v['llm']:.4f}")
    up = score(series(test_end, {"Air/drone strike", "Shelling/artillery/missile attack"}), list(monthly(dt.date(2023, 1, 1), dt.date(2026, 5, 1))), test_end, L, True)
    print(f"  reported: LLM with the production cap: Brier {brier(rows, 'llm_capped'):.4f}")
    print(f"  reported: B incl. shelling/missile (upper bound): Brier empirical {brier(up, 'emp'):.4f} vs LLM {brier(up, 'llm'):.4f}")
    out = RL.LOCAL / "strike_no_war_validation.json"; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + "\n"); print("  ->", out)

def production():
    sys.path.insert(0, str(Path(__file__).resolve().parent)); import refit_local as RL
    v = json.loads((RL.LOCAL / "strike_no_war_validation.json").read_text()); L = v["L"]
    end = RL.last_complete_day(); S = series(end, {"Air/drone strike"}); t = (end - D0).days; table = {}
    for (ini, tgt), (ps, pw, _) in S.items():
        rates = {W: (lambda e: round(e[0], 6) if e else None)(estimate(ps, pw, t, L, W)) for W in range(1, 121)}
        table[f"{'+'.join(ini)}->{tgt}"] = {"initiators": list(ini), "target": tgt, "rates": rates, "in_war_now": bool(pw[t + 1] - pw[t])}
        print(f"  {'+'.join(ini):28} -> {tgt:22} W=7 {rates[7]}  W=30 {rates[30]}  W=60 {rates[60]}  {'(war now)' if table[f'{chr(43).join(ini)}->{tgt}']['in_war_now'] else ''}")
    out = RL.LOCAL / "strike_no_war_candidate.json"
    out.write_text(json.dumps({"L": L, "data_end": end.isoformat(), "table": table, "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=1) + "\n")
    print("  ->", out)

if __name__ == "__main__":
    if "--synthetic" in sys.argv: sys.exit(0 if synthetic() else 1)
    elif "--validate" in sys.argv: validate()
    elif "--production" in sys.argv: production()
    else: print(__doc__)

"""docs/strike_given_war_prereg.md: empirical P(B|A) = P(X air/drone-strikes Y's territory | interstate war episode between X and Y),
from the local offline pull (Battles define A, Explosions define B). Gitignored outputs:
  python analysis/strike_given_war_fit.py --heldout      episodes starting <= 2026-06-30, data <= 2026-06-30 -> pilot/local/strike_given_war_heldout.json
  python analysis/strike_given_war_fit.py --production   data through the last complete day -> pilot/local/strike_given_war_candidate.json
"""
import sys, re, json, datetime as dt
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import refit_local as RL, world_fits as WF

MIL = re.compile(r"^Military Forces of (?:the )?(.+?) \(")
GAP, MIN_FAT = 30, 25

def _rows(kind, end):
    for f in sorted(RL.SRC.glob(f"*_{kind}.jsonl")):
        for l in f.read_text().splitlines():
            if l.strip():
                r = json.loads(l); d = dt.date.fromisoformat(r["event_date"][:10])
                if d <= end: yield r, d

def _side(r, a, b):
    return {m.group(1) for k in (a, b) for part in re.split(r";\s*", r.get(k) or "") if (m := MIL.match(part.strip()))}

def episodes(end):
    """Unordered state pairs -> list of (start, end, fatalities) from Battles between the two states' militaries."""
    days = defaultdict(lambda: defaultdict(int))
    for r, d in _rows("battles", end):
        s1, s2 = _side(r, "actor1", "assoc_actor_1"), _side(r, "actor2", "assoc_actor_2")
        for x in s1:
            for y in s2:
                if x != y: days[tuple(sorted((x, y)))][d] += int(r.get("fatalities") or 0)
    out = {}
    for p, dd in days.items():
        ds = sorted(dd); eps = []; s = prev = ds[0]; fat = dd[ds[0]]
        for d in ds[1:]:
            if (d - prev).days > GAP: eps.append((s, prev, fat)); s, fat = d, 0
            fat += dd[d]; prev = d
        eps.append((s, prev, fat)); out[p] = eps
    return out

def strikes(end, subs):
    """(X, Y) -> sorted days with a strike by X's state forces located in country Y."""
    S = defaultdict(set)
    for r, d in _rows("explosions", end):
        if r.get("sub_event_type") not in subs or WF.MARITIME.search(r.get("country") or ""): continue
        key, kind = WF.ident(r.get("actor1"))
        if kind == "state" and key != r.get("country"): S[(key, r["country"])].add(d)
    return S

def estimate(end, start_max):
    E = episodes(end); air = strikes(end, {"Air/drone strike"}); both = strikes(end, WF.SUBS)
    rows = []
    for (x, y), eps in E.items():
        for s, e, fat in eps:
            if s > start_max: continue
            for a, b in ((x, y), (y, x)):
                hit = lambda S, lo, hi: any(lo <= d <= hi for d in S.get((a, b), ()))
                rows.append({"dir": f"{a}->{b}", "start": s.isoformat(), "end": e.isoformat(), "fat": fat,
                             "air": hit(air, s, e + dt.timedelta(GAP)), "air30": hit(air, s, s + dt.timedelta(29)), "any": hit(both, s, e + dt.timedelta(GAP))})
    rate = lambda xs, k: ((sum(x[k] for x in xs) + 0.5) / (len(xs) + 1), sum(x[k] for x in xs), len(xs))
    main = [x for x in rows if x["fat"] >= MIN_FAT]; big = [x for x in rows if x["fat"] >= 100]
    res = {"p": rate(main, "air")[0], "k": rate(main, "air")[1], "n": rate(main, "air")[2],
           "reported": {"incl_shelling_missile": rate(main, "any")[:3], "first_30_days": rate(main, "air30")[:3],
                        "fat_ge_100": rate(big, "air")[:3], "all_episodes_no_fatality_floor": rate(rows, "air")[:3]},
           "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    return res, main

def fit(end, start_max, out):
    res, main = estimate(end, start_max)
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(res, indent=1) + "\n")
    print(f"data through {end}, episodes starting <= {start_max}: {res['n']} war directions (>= {MIN_FAT} fatalities), {res['k']} with an "
          f"air/drone strike on the other's territory -> P(B|A) = {res['p']:.3f}")
    for k, (p, kk, n) in res["reported"].items(): print(f"  reported: {k:32} {p:.3f} ({kk}/{n})")
    for x in sorted(main, key=lambda x: x["start"])[-25:]:
        print(f"    {x['start']} .. {x['end']} {x['dir']:34} fat {x['fat']:6} air {'Y' if x['air'] else '-'} any {'Y' if x['any'] else '-'}")
    print(f"  -> {out}")

def llm_reference():
    """The engine's typical P(B|A) on strike contracts: mean over qualifying logged engine forecasts (one per market, first logged)."""
    sys.path.insert(0, str(RL.ROOT / "pilot")); from strike_given_war import qualifies
    seen = {}
    for l in (RL.ROOT / "predictions" / "log.jsonl").read_text().splitlines():
        if l.strip():
            r = json.loads(l); mid = str(r.get("market_id"))
            if mid not in seen and r.get("pricing_component") in (None, "engine") and qualifies(r):
                seen[mid] = r.get("p_b_given_a_pre_empirical") or r["p_b_given_a"]
    return sum(seen.values()) / len(seen), len(seen)

def validate(fit_end=dt.date(2022, 12, 31), test_end=dt.date(2026, 6, 30)):
    """Amendment 2: out-of-time test. Rate fitted on episodes starting <= fit_end (data <= fit_end); scored on war directions of
    episodes starting after fit_end and <= test_end (data <= test_end) against the engine's typical LLM P(B|A)."""
    fit, _ = estimate(fit_end, fit_end); _, test = estimate(test_end, test_end)
    test = [x for x in test if x["start"] > fit_end.isoformat()]
    c, nc = llm_reference(); y = [int(x["air"]) for x in test]
    br = lambda p: sum((p - v) ** 2 for v in y) / max(1, len(y))
    res = {"fit_p": fit["p"], "fit_k": fit["k"], "fit_n": fit["n"], "test_n": len(y), "test_k": sum(y), "llm_ref": c, "llm_ref_n": nc,
           "brier_empirical": br(fit["p"]), "brier_llm": br(c), "pass": br(fit["p"]) <= br(c) and len(y) > 0}
    print(f"OUT-OF-TIME WAR TEST: fit on episodes <= {fit_end}: P(B|A) {fit['p']:.3f} ({fit['k']}/{fit['n']}) | test episodes "
          f"{fit_end} .. {test_end}: {sum(y)}/{len(y)} directions with an air/drone strike | Brier empirical {res['brier_empirical']:.4f} vs "
          f"engine's typical LLM P(B|A) {c:.3f} (mean of {nc} contracts) {res['brier_llm']:.4f} -> {'PASS' if res['pass'] else 'FAIL'}")
    return res

if __name__ == "__main__":
    if "--heldout" in sys.argv:
        c = dt.date(2026, 6, 30); fit(c, c, RL.LOCAL / "strike_given_war_heldout.json")
    elif "--production" in sys.argv:
        e = RL.last_complete_day(); fit(e, e, RL.LOCAL / "strike_given_war_candidate.json")
    else: print(__doc__)

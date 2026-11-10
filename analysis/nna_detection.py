"""docs/nna_detection_prereg.md (8b72238): can NNA (English) see Israel->Lebanon strike days, and quiet ones?

  python3.11 analysis/nna_detection.py --synthetic   offline checks of the statistics
  python3.11 analysis/nna_detection.py --real        key 1 (local event data) + key 2 (resolved dailies) -> pilot/local/nna_detection.json

Hits come from pilot/nna_label.py (prompt nna-v1). Key 1: a hit = QUALIFYING or BORDERLINE (the event data's "air/drone strike"
includes drone-dropped munitions). Key 2: a hit = QUALIFYING (the contract's reading); BORDERLINE-counts as a sensitivity.
"""
import sys, re, json, math, random, datetime as dt
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
J = lambda k, n: (k + 0.5) / (n + 1)


def rates(rows):
    """rows: [(day, strike: bool, hit: bool)]"""
    s = [r for r in rows if r[1]]; q = [r for r in rows if not r[1]]
    d = J(sum(r[2] for r in s), len(s)); a = J(sum(r[2] for r in q), len(q))
    return {"n_strike_days": len(s), "hits_on_strike_days": sum(r[2] for r in s), "n_quiet_days": len(q),
            "hits_on_quiet_days": sum(r[2] for r in q), "d": round(d, 4), "alpha": round(a, 4), "lr_no_hit": round((1 - d) / (1 - a), 4)}


def week_boot(rows, B=2000, seed=1110):
    by = defaultdict(list)
    for r in rows: by[dt.date.fromisoformat(r[0]).isocalendar()[:2]].append(r)
    ks = list(by); rng = random.Random(seed); D, A, L = [], [], []
    for _ in range(B):
        s = [r for k in rng.choices(ks, k=len(ks)) for r in by[k]]; x = rates(s)
        D.append(x["d"]); A.append(x["alpha"]); L.append(x["lr_no_hit"])
    q = lambda v: (round(sorted(v)[int(.025 * B)], 4), round(sorted(v)[int(.975 * B) - 1], 4))
    return {"d_ci": q(D), "alpha_ci": q(A), "lr_no_hit_ci": q(L)}


def clustering(rows):
    s = [r for r in sorted(rows) if r[1]]; miss = [not r[2] for r in s]
    pairs = [(a, b) for a, b in zip(miss, miss[1:])]
    after = [b for a, b in pairs if a]
    return {"p_miss": round(sum(miss) / len(miss), 4) if miss else None,
            "p_miss_after_miss": round(sum(after) / len(after), 4) if after else None, "n_after_miss": len(after)}


def decide(k1, k1ci, k2):
    rule1 = k1ci["d_ci"][0] >= 0.50; rule2 = k1ci["lr_no_hit_ci"][1] < 0.5
    conflict = None
    if k2:
        conflict = not (k1ci["d_ci"][0] <= k2["d"] <= k1ci["d_ci"][1] and k1ci["alpha_ci"][0] <= k2["alpha"] <= k1ci["alpha_ci"][1])
    return {"d_lower_ge_0.50": rule1, "lr_upper_lt_0.5": rule2, "key2_conflict": conflict,
            "verdict": "PASS" if rule1 and rule2 and not conflict else ("CONFLICT" if rule1 and rule2 else "FAIL")}


def synthetic():
    rng = random.Random(5); rows = []
    d0 = dt.date(2026, 7, 1)
    for i in range(100):
        day = (d0 + dt.timedelta(i)).isoformat(); s = rng.random() < 0.7
        rows.append((day, s, (rng.random() < 0.9) if s else (rng.random() < 0.05)))
    r = rates(rows); ci = week_boot(rows, B=500)
    ok = 0.8 < r["d"] < 0.97 and r["alpha"] < 0.15 and r["lr_no_hit"] < 0.3 and ci["d_ci"][0] < r["d"] < ci["d_ci"][1]
    print(f"  {'PASS' if ok else 'FAIL'}  good sensor recovered: {r} {ci}")
    blind = [(d, s, False) for d, s, _ in rows]; rb = rates(blind)
    ok2 = rb["d"] < 0.02 and rb["lr_no_hit"] > 0.95
    print(f"  {'PASS' if ok2 else 'FAIL'}  blind sensor: d {rb['d']} LR {rb['lr_no_hit']}")
    v = decide(r, ci, None)["verdict"]; vb = decide(rb, week_boot(blind, B=200), None)["verdict"]
    print(f"  {'PASS' if v == 'PASS' and vb == 'FAIL' else 'FAIL'}  decision: good {v}, blind {vb}")
    c = clustering([("2026-07-01", True, False), ("2026-07-02", True, False), ("2026-07-03", True, True), ("2026-07-04", True, False)])
    print(f"  {'PASS' if c == {'p_miss': 0.75, 'p_miss_after_miss': 0.5, 'n_after_miss': 2} else 'FAIL'}  clustering {c}")
    return ok and ok2 and v == "PASS" and vb == "FAIL"


MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September",
                                      "October", "November", "December"], 1)}


def key2_days():
    out = {}
    for l in (ROOT / "predictions" / "brier_log.jsonl").read_text().splitlines():
        if not l.strip(): continue
        b = json.loads(l); m = re.search(r"Israel military action against Lebanon on ([A-Z][a-z]+) (\d{1,2})\?", b.get("market_label") or "")
        if m and b.get("outcome") is not None:
            out[dt.date(2026, MONTHS[m.group(1)], int(m.group(2))).isoformat()] = int(b["outcome"])
    return out


def real():
    sys.path.insert(0, str(ROOT / "pilot")); sys.path.insert(0, str(ROOT / "analysis"))
    import nna_label as NL, refit_local as RL, detection_rate as DR
    end = RL.last_complete_day().isoformat()
    T = DR.truth_days({"Air/drone strike"}, RL.last_complete_day())
    keys = [k for k in T if "Israel" in k[0] and "Lebanon" in k[1]]
    print(f"[nna] event data through {end}; Israel->Lebanon keys in the event data: {keys}")
    truth = set().union(*(T[k] for k in keys)) if keys else set()
    truth = {d.isoformat() if hasattr(d, "isoformat") else str(d) for d in truth}
    res = {"prereg": "8b72238", "labels": NL.PROMPT_VERSION, "event_data_end": end}
    # key 1
    H1 = NL.day_hits("2026-07-01", end, borderline_counts=True)
    rows1 = [(d, d in truth, h) for d, h in H1.items()]
    cal = (dt.date.fromisoformat(end) - dt.date(2026, 7, 1)).days + 1
    k1 = rates(rows1); k1ci = week_boot(rows1)
    res["key1"] = {**k1, **k1ci, "coverage": round(len(rows1) / cal, 3), "clustering": clustering(rows1),
                   "qualifying_only": rates([(d, d in truth, h) for d, h in NL.day_hits("2026-07-01", end).items()])}
    # key 2
    K2 = key2_days(); H2 = NL.day_hits(min(K2), max(K2)); H2b = NL.day_hits(min(K2), max(K2), borderline_counts=True)
    rows2 = [(d, bool(y), H2[d]) for d, y in K2.items() if d in H2]
    rows2b = [(d, bool(y), H2b[d]) for d, y in K2.items() if d in H2b]
    k2 = rates(rows2) if rows2 else None
    lab = NL.load_labels(); arts = {a["id"]: a for a in NL.articles(min(K2), max(K2))}
    cls_by_day = defaultdict(list)
    for i, x in lab.items():
        if i in arts and x["cls"] in ("QUALIFYING", "BORDERLINE"): cls_by_day[x["event_date"]].append(x["cls"])
    res["key2"] = {**(k2 or {}), "n_days": len(rows2), "borderline_counts": rates(rows2b) if rows2b else None,
                   "no_days": {d: sorted(set(cls_by_day.get(d, []))) or ["nothing qualifying or borderline"] for d, y in K2.items() if not y}}
    res["decision"] = decide(k1, k1ci, k2)
    out = ROOT / "pilot" / "local" / "nna_detection.json"; out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(res, indent=1))
    k = res["key1"]
    print(f"\nKEY 1 (event data, Jul 1 - {end}; hit = QUALIFYING or BORDERLINE): coverage {k['coverage']}")
    print(f"  d {k['d']} {k['d_ci']}  ({k['hits_on_strike_days']}/{k['n_strike_days']} strike days)   alpha {k['alpha']} {k['alpha_ci']}  ({k['hits_on_quiet_days']}/{k['n_quiet_days']} quiet days)")
    print(f"  LR(no hit) {k['lr_no_hit']} {k['lr_no_hit_ci']}   clustering {k['clustering']}")
    print(f"  qualifying only: {k['qualifying_only']}")
    if k2:
        print(f"\nKEY 2 (resolved dailies, hit = QUALIFYING): {res['key2']['n_days']} days  d {k2['d']}  alpha {k2['alpha']}  LR {k2['lr_no_hit']}")
        print(f"  borderline counts: {res['key2']['borderline_counts']}")
        print(f"  NO days and what NNA reported: {res['key2']['no_days']}")
    d = res["decision"]
    print(f"\nDECISION: {d['verdict']}  (d lower >= 0.50: {d['d_lower_ge_0.50']}; LR upper < 0.5: {d['lr_upper_lt_0.5']}; key 2 conflict: {d['key2_conflict']})")
    print(f"written {out.relative_to(ROOT)}")


if __name__ == "__main__":
    if "--synthetic" in sys.argv: sys.exit(0 if synthetic() else 1)
    elif "--real" in sys.argv: real()
    else: print(__doc__)

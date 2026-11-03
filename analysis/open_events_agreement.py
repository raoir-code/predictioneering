"""docs/open_events_agreement_prereg.md: can an open event dataset (UCDP GED Candidate, CC BY 4.0) stand in for the local event
data as the source of strike days for refits and strike-date anchors? Day-level agreement by direction, Jan 1 - Sep 30, 2026.
  python analysis/open_events_agreement.py --synthetic   estimator checks on synthetic data only
  python analysis/open_events_agreement.py --describe    open data only: strike days per direction and month (no local data read)
  python analysis/open_events_agreement.py --measure     joins the local data -> pilot/local/open_events_agreement.json
Report only: nothing here touches production.
"""
import sys, re, csv, json, random, datetime as dt
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
GED = ROOT / "data" / "external" / "ucdp" / "GEDEvent_v26_01_26_09.csv"
OUT = ROOT / "pilot" / "local" / "open_events_agreement.json"
START, STOP = dt.date(2026, 1, 1), dt.date(2026, 9, 30)
TOL, MIN_DAYS = 1, 5                      # +-1 day match; a direction is scored with >= 5 reference strike days
GATE_RECALL, GATE_PREC, GATE_SHARE = 0.6, 0.8, 0.5
TYPES = {"1", "3"}                        # state-based and one-sided violence
NAME = {"United States of America": "United States", "DR Congo": "Democratic Republic of Congo",
        "Bosnia-Herzegovina": "Bosnia and Herzegovina"}
FACTION_GOV = {"Yemen": "Yemen [Houthi]"}  # UCDP's Government of Yemen (Sanaa) acting outside Yemen = the reference's Houthi key

def norm(n):
    n = re.sub(r"\s*\(.*\)\s*$", "", (n or "").strip()); return NAME.get(n, n)

def govs(side):
    return [norm(x) for x in re.findall(r"Government of (.+?)(?=, Government of |$)", side or "")]

def attackers(row):
    """-> (location, attacker set, ambiguous). The location's government on one side: the other side's governments strike it.
    Not a party: a single government side strikes it (Israel vs Hezbollah in Lebanon -> Israel); governments on both sides
    (Iran vs Israel+US in Kuwait) cannot be told apart, so every government counts and the event is flagged ambiguous."""
    loc = norm(row["country"]); a, b = govs(row["side_a"]), govs(row["side_b"])
    if loc in a: att, amb = b, False
    elif loc in b: att, amb = a, False
    else: att, amb = a + b, bool(a and b)
    return loc, {FACTION_GOV.get(g, g) for g in att if g != loc}, amb

def open_days(exact_only=True, drop_ambiguous=False):
    S = defaultdict(set)
    with open(GED, newline="") as f:
        for r in csv.DictReader(f):
            if r["type_of_violence"] not in TYPES: continue
            if exact_only and r["date_prec"] != "1": continue
            d = dt.date.fromisoformat(r["date_start"][:10])
            if not START <= d <= STOP: continue
            loc, att, amb = attackers(r)
            if amb and drop_ambiguous: continue
            for a in att: S[(a, loc)].add(d)
    return S

def local_days(end):
    """The world-fit strike series (refit_local.build's rules): actor1's key, its home for coalitions, exact dates only."""
    import refit_local as RL, world_fits as WF, contract_def_refit as CD
    S = defaultdict(set)
    for r in RL.rows():
        d = dt.date.fromisoformat(r["event_date"][:10])
        if not START <= d <= min(STOP, end) or str(r.get("time_precision")) != "1": continue
        if r.get("sub_event_type") not in WF.SUBS or WF.MARITIME.search(r.get("country") or ""): continue
        key, kind = WF.ident(r.get("actor1"))
        if not key: continue
        a = CD.COALITION_HOME.get(key, key) if kind == "coalition" else key
        if a != r.get("country"): S[(a, r["country"])].add(d)
    return S

# ── estimator (pure; synthetic-checked) ──────────────────────────────────────────────────────────────────────────────
def flags(R, U):
    """(day, kind, hit): kind 'r' = reference day matched by an open day within TOL; kind 'u' = open day matched by a reference day."""
    near = lambda d, S: any((d + dt.timedelta(k)) in S for k in range(-TOL, TOL + 1))
    return [(d, "r", near(d, U)) for d in sorted(R)] + [(d, "u", near(d, R)) for d in sorted(U)]

def rate(rows, kind):
    v = [h for _, k, h in rows if k == kind]; return round(sum(v) / len(v), 3) if v else None

def boot(tables, B=2000, seed=29):
    """Recall and precision with a bootstrap over (direction, ISO week) blocks."""
    blocks = defaultdict(list)
    for name, rows in tables.items():
        for x in rows: blocks[(name, x[0].isocalendar()[:2])].append(x)
    keys = list(blocks); rnd = random.Random(seed); rc, pr = [], []
    for _ in range(B):
        rows = [x for k in (rnd.choice(keys) for _ in keys) for x in blocks[k]]
        a, b = rate(rows, "r"), rate(rows, "u")
        if a is not None: rc.append(a)
        if b is not None: pr.append(b)
    q = lambda v: (round(sorted(v)[int(0.025 * len(v))], 3), round(sorted(v)[int(0.975 * len(v)) - 1], 3)) if v else None
    return q(rc), q(pr)

def grade(rc_ci, pr_ci):
    if rc_ci and pr_ci and rc_ci[0] >= GATE_RECALL and pr_ci[0] >= GATE_PREC: return "REFIT-GRADE"
    if pr_ci and pr_ci[0] >= GATE_PREC: return "ANCHOR-GRADE"
    return "NONE"

def plan_verdict(dirs, contract):
    tot = sum(v["ref_days"] for k, v in dirs.items() if k in contract)
    ok = sum(v["ref_days"] for k, v in dirs.items() if k in contract and v["grade"] == "REFIT-GRADE")
    share = round(ok / tot, 3) if tot else None
    return share, ("OPEN-DATA REFITS for REFIT-GRADE directions" if share is not None and share >= GATE_SHARE
                   else "NO OPEN-DATA REFITS: priors stay frozen")

def score(R, U, names, contract):
    dirs, tables = {}, {}
    for k in names:
        r, u = R.get(k, set()), U.get(k, set())
        if len(r) < MIN_DAYS: continue
        t = flags(r, u); tables[k] = t; rc, pr = boot({k: t})
        dirs[f"{k[0]}->{k[1]}"] = {"ref_days": len(r), "open_days": len(u), "recall": rate(t, "r"), "recall_ci": rc,
                                   "precision": rate(t, "u"), "precision_ci": pr, "grade": grade(rc, pr)}
    pooled = boot(tables) if tables else (None, None)
    share, verdict = plan_verdict(dirs, contract)
    return {"directions": dirs, "pooled_recall_ci": pooled[0], "pooled_precision_ci": pooled[1],
            "contract_share_refit_grade": share, "verdict": verdict}

def contract_dirs():
    import detection_rate as DR
    fac = {"Houthi": "Yemen [Houthi]", "Houthis": "Yemen [Houthi]"}
    return {"->".join(fac.get(x, x) for x in p.split("->")) for p in DR.contract_directions()}

def describe():
    U, Uall = open_days(True), open_days(False)
    print(f"open data {GED.name}: {len(Uall)} directions (all precisions); exact-date share by direction below")
    for k in sorted(Uall, key=lambda k: -len(Uall[k])):
        if len(Uall[k]) < 3: continue
        m = defaultdict(int)
        for d in Uall[k]: m[d.month] += 1
        print(f"  {k[0]:>24} -> {k[1]:<22} days {len(Uall[k]):3}  exact {len(U.get(k, ())):3}  by month {dict(sorted(m.items()))}")

def measure():
    import refit_local as RL
    end = RL.last_complete_day(); R, U = local_days(end), open_days(True)
    U = {k: {d for d in v if d <= end} for k, v in U.items()}
    contract = contract_dirs(); res = score(R, U, set(R), contract)
    U2 = {k: {d for d in v if d <= end} for k, v in open_days(True, True).items()}
    s2 = score(R, U2, set(R), contract)
    res["sensitivity_drop_ambiguous"] = {"directions": {k: {x: v[x] for x in ("open_days", "recall", "precision", "grade")}
                                                        for k, v in s2["directions"].items()},
                                         "contract_share_refit_grade": s2["contract_share_refit_grade"], "verdict": s2["verdict"]}
    res.update({"window": [START.isoformat(), min(STOP, end).isoformat()], "tol_days": TOL, "contract_directions": sorted(contract),
                "open_only": {f"{k[0]}->{k[1]}": len(v) for k, v in U.items() if len(v) >= MIN_DAYS and len(R.get(k, ())) < MIN_DAYS}})
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(res, indent=1))
    print(f"window {res['window']}  pooled recall {res['pooled_recall_ci']}  pooled precision {res['pooled_precision_ci']}")
    for k, v in sorted(res["directions"].items(), key=lambda kv: -kv[1]["ref_days"]):
        star = "*" if k in contract else " "
        print(f" {star}{k:<40} ref {v['ref_days']:3} open {v['open_days']:3}  recall {v['recall']} {v['recall_ci']}  "
              f"precision {v['precision']} {v['precision_ci']}  {v['grade']}")
    print("open-only directions (naming check):", res["open_only"])
    print(f"contract strike days in REFIT-GRADE directions: {res['contract_share_refit_grade']}  ->  {res['verdict']}")
    sd = res["sensitivity_drop_ambiguous"]
    print(f"sensitivity (ambiguous events dropped): {sd['contract_share_refit_grade']} -> {sd['verdict']}; grade changes:",
          {k: (res["directions"][k]["grade"], v["grade"]) for k, v in sd["directions"].items() if v["grade"] != res["directions"][k]["grade"]})

def synthetic():
    rnd = random.Random(5); d0 = dt.date(2026, 1, 1)
    R = {d0 + dt.timedelta(i) for i in range(0, 270, 3)}                       # 90 reference days
    U = {d + dt.timedelta(rnd.choice((-1, 0, 1))) for d in R if rnd.random() < 0.7} | {d0 + dt.timedelta(1 + 3 * i) + dt.timedelta(400) for i in range(5)}
    t = flags(R, U); rc, pr = rate(t, "r"), rate(t, "u")
    assert 0.6 < rc < 0.8, rc                                                  # ~70% matched within +-1
    assert 0.85 < pr < 0.99, pr                                                # 5 unmatched open days out of ~68
    assert flags({d0}, {d0 + dt.timedelta(2)}) == [(d0, "r", False), (d0 + dt.timedelta(2), "u", False)]   # TOL = 1
    assert grade((0.61, 0.8), (0.81, 0.9)) == "REFIT-GRADE" and grade((0.3, 0.5), (0.85, 0.9)) == "ANCHOR-GRADE"
    assert grade((0.7, 0.9), (0.7, 0.9)) == "NONE"
    assert attackers({"country": "Iran", "side_a": "Government of Iran", "side_b": "Government of Israel, Government of United States of America"}) == ("Iran", {"Israel", "United States"}, False)
    assert attackers({"country": "Israel", "side_a": "Government of Yemen (North Yemen)", "side_b": "Government of Israel"}) == ("Israel", {"Yemen [Houthi]"}, False)
    assert attackers({"country": "Israel", "side_a": "Government of Iran", "side_b": "Government of Israel, Government of United States of America"}) == ("Israel", {"Iran"}, False)
    assert attackers({"country": "Kuwait", "side_a": "Government of Iran", "side_b": "Government of Israel, Government of United States of America"}) == ("Kuwait", {"Iran", "Israel", "United States"}, True)
    assert attackers({"country": "Lebanon", "side_a": "Government of Israel", "side_b": "Hezbollah"}) == ("Lebanon", {"Israel"}, False)
    s, v = plan_verdict({"A->B": {"ref_days": 60, "grade": "REFIT-GRADE"}, "C->D": {"ref_days": 40, "grade": "NONE"}}, {"A->B", "C->D"})
    assert s == 0.6 and v.startswith("OPEN-DATA")
    print("synthetic: all checks pass")

if __name__ == "__main__":
    a = sys.argv[1:] or ["--synthetic"]
    {"--synthetic": synthetic, "--describe": describe, "--measure": measure}[a[0]]()

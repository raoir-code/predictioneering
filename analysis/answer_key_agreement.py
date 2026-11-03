"""docs/answer_key_agreement_prereg.md: do the local strike days agree with how Polymarket resolved our strike contracts?
After the local data ends, resolved contracts become the answer key; this measures whether that switch is continuous.
  python analysis/answer_key_agreement.py --synthetic   estimator checks on synthetic data only
  python analysis/answer_key_agreement.py --measure     joins the local data -> pilot/local/answer_key_agreement.json
Report only: nothing here touches production.
"""
import sys, re, json, random, datetime as dt
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
OUT = ROOT / "pilot" / "local" / "answer_key_agreement.json"
GATE = 0.9                                   # both lower bounds >= 0.9 -> CONTINUOUS
key = lambda s: re.sub(r"[^a-z]", "", (s or "").lower())
FACTION = {"houthi": "yemenhouthi", "houthis": "yemenhouthi"}
LEADS = {"saudiarabia": ["operationrestoringhope", "operationdecisivestorm"], "turkey": ["operationpeacespring"]}

def ref_keys(pair, K):
    """Contract pair 'ini->ter' (normalized) -> every reference key it covers: the state or faction itself plus coalitions it leads."""
    ini, ter = pair.split("->"); out = []
    for a in [FACTION.get(ini, ini)] + LEADS.get(ini, []):
        if (a, ter) in K: out.append(K[(a, ter)])
    return out

def window_days(c):
    """Whole days in the rules' time zone, as unified_data.windows: a YES window uses every touched day, a NO window only fully
    covered days (a by-date listed mid-day starts the next day)."""
    z = ZoneInfo(c["tz"]); s, e = c["start"].astimezone(z), c["end"].astimezone(z)
    if c["outcome"] == 1: return s.date(), e.date()
    a = s.date() if s.time() == dt.time(0) else s.date() + dt.timedelta(1)
    b = e.date() if e.time() >= dt.time(23, 59) else e.date() - dt.timedelta(1)
    return a, b

def ref_yes(days, a, b, tol=0):
    lo, hi = a - dt.timedelta(tol), b + dt.timedelta(tol)
    return any(lo <= d <= hi for d in days)

# ── estimator (pure; synthetic-checked) ──────────────────────────────────────────────────────────────────────────────
def rates(rows):
    """rows: (cluster, contract_y, ref_y). -> sens = P(ref yes | contract yes), spec = P(ref no | contract no), agreement, kappa."""
    y1 = [r for _, c, r in rows if c == 1]; y0 = [r for _, c, r in rows if c == 0]; n = len(rows)
    sens = sum(y1) / len(y1) if y1 else None; spec = (len(y0) - sum(y0)) / len(y0) if y0 else None
    agree = sum(1 for _, c, r in rows if c == r) / n if n else None
    pc = sum(c for _, c, _ in rows) / n if n else 0; pr = sum(r for _, _, r in rows) / n if n else 0
    pe = pc * pr + (1 - pc) * (1 - pr); kappa = (agree - pe) / (1 - pe) if n and pe < 1 else None
    rd = lambda x: round(x, 3) if x is not None else None
    return {"n": n, "n_yes": len(y1), "n_no": len(y0), "sens": rd(sens), "spec": rd(spec), "agree": rd(agree), "kappa": rd(kappa)}

def boot(rows, B=2000, seed=37):
    bl = defaultdict(list)
    for r in rows: bl[r[0]].append(r)
    keys = list(bl); rnd = random.Random(seed); S, P = [], []
    for _ in range(B):
        x = rates([r for k in (rnd.choice(keys) for _ in keys) for r in bl[k]])
        if x["sens"] is not None: S.append(x["sens"])
        if x["spec"] is not None: P.append(x["spec"])
    q = lambda v: (round(sorted(v)[int(0.025 * len(v))], 3), round(sorted(v)[int(0.975 * len(v)) - 1], 3)) if v else None
    return q(S), q(P)

def verdict(s_ci, p_ci):
    if s_ci and p_ci and s_ci[0] >= GATE and p_ci[0] >= GATE: return "CONTINUOUS"
    return "BREAK"

def measure():
    import refit_local as RL, unified_data as UD
    end = RL.last_complete_day(); P = RL.build(end)()
    exact = {k: v["exact"] for k, v in P.items()}; anyd = {k: v["exact"] | v["inexact"] for k, v in P.items()}
    K = {(key(k.split("->")[0]), key(k.split("->")[1])): k for k in P}
    first = min(d for v in anyd.values() for d in v if d.year >= 2026) if anyd else None
    cs, _ = UD.load(); rows, rows_s, detail, unmapped = [], [], [], defaultdict(int)
    for c in cs:
        if c.get("outcome") not in (0, 1) or str(c.get("fp")) == "H": continue
        a, b = window_days(c)
        if b < a or b > end or (first and a < first): continue
        pairs = [f"{c['pair'].split('->')[0]}->{m}" for m in c["members"]] if c.get("members") else [c["pair"]]
        ks = [k for p in pairs for k in ref_keys(p, K)]
        if not ks: unmapped[c["pair"]] += 1; continue
        ex = set().union(*[exact[k] for k in ks]); an = set().union(*[anyd[k] for k in ks])
        r0, r1 = int(ref_yes(ex, a, b)), int(ref_yes(an, a, b, 1))
        cl = (c["pair"], b.isocalendar()[:2])
        rows.append((cl, c["outcome"], r0)); rows_s.append((cl, c["outcome"], r1))
        detail.append({"id": c["id"], "q": c["question"], "pair": c["pair"], "kind": c["kind"], "a": a.isoformat(), "b": b.isoformat(),
                       "contract": c["outcome"], "ref": r0, "ref_sens": r1, "keys": ks,
                       "ref_days_near": sorted(d.isoformat() for d in an if a - dt.timedelta(3) <= d <= b + dt.timedelta(3))[:10]})
    s_ci, p_ci = boot(rows); s2, p2 = boot(rows_s)
    bypair = {}
    for p in sorted({d["pair"] for d in detail}):
        sub = [r for r, d in zip(rows, detail) if d["pair"] == p]; bypair[p] = rates(sub)
    bykind = {k: rates([r for r, d in zip(rows, detail) if d["kind"] == k]) for k in ("daily", "bydate")}
    res = {"end": end.isoformat(), "first": first.isoformat() if first else None, "overall": rates(rows), "sens_ci": s_ci, "spec_ci": p_ci,
           "verdict": verdict(s_ci, p_ci), "sensitivity_inexact_tol1": {**rates(rows_s), "sens_ci": s2, "spec_ci": p2, "verdict": verdict(s2, p2)},
           "by_kind": bykind, "by_pair": bypair, "unmapped": dict(unmapped),
           "disagreements": [d for d in detail if d["contract"] != d["ref"]], "contracts": detail}
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(res, indent=1))
    o = res["overall"]
    print(f"local data through {end}; {o['n']} resolved strike contracts ({o['n_yes']} YES, {o['n_no']} NO); unmapped {dict(unmapped)}")
    print(f"P(local yes | contract YES) {o['sens']} {s_ci}   P(local no | contract NO) {o['spec']} {p_ci}   agree {o['agree']}  kappa {o['kappa']}")
    print(f"VERDICT: {res['verdict']}   (sensitivity, any precision +-1 day: sens {res['sensitivity_inexact_tol1']['sens']} {s2}, spec {res['sensitivity_inexact_tol1']['spec']} {p2} -> {res['sensitivity_inexact_tol1']['verdict']})")
    for k, v in bykind.items(): print(f"  {k:7} n {v['n']:4}  sens {v['sens']}  spec {v['spec']}")
    for p, v in sorted(bypair.items(), key=lambda kv: -kv[1]["n"]): print(f"  {p:34} n {v['n']:4} (YES {v['n_yes']:3})  sens {v['sens']}  spec {v['spec']}")
    print(f"disagreements: {len(res['disagreements'])} (listed in {OUT.name})")
    for d in res["disagreements"][:25]:
        print(f"  {'YES' if d['contract'] else 'NO ':3} vs local {'yes' if d['ref'] else 'no '}  {d['kind']:6} {d['a']}..{d['b']}  {d['q'][:70]}  near {d['ref_days_near'][:4]}")

def synthetic():
    rows = [((f"p{i % 4}", (2026, i % 10)), 1, 1) for i in range(90)] + [((f"p{i % 4}", (2026, i % 10)), 1, 0) for i in range(10)] \
         + [((f"p{i % 4}", (2026, i % 10)), 0, 0) for i in range(45)] + [((f"p{i % 4}", (2026, i % 10)), 0, 1) for i in range(5)]
    r = rates(rows); assert r["sens"] == 0.9 and r["spec"] == 0.9 and r["n"] == 150, r
    assert verdict((0.91, 0.99), (0.9, 0.95)) == "CONTINUOUS" and verdict((0.85, 0.99), (0.95, 1)) == "BREAK"
    d = dt.date(2026, 10, 1)
    assert ref_yes({d}, d, d) and not ref_yes({d + dt.timedelta(1)}, d, d) and ref_yes({d + dt.timedelta(1)}, d, d, 1)
    K = {("israel", "lebanon"): "Israel->Lebanon", ("operationrestoringhope", "yemen"): "Operation Restoring Hope->Yemen",
         ("saudiarabia", "yemen"): "Saudi Arabia->Yemen", ("yemenhouthi", "israel"): "Yemen [Houthi]->Israel"}
    assert ref_keys("israel->lebanon", K) == ["Israel->Lebanon"]
    assert ref_keys("saudiarabia->yemen", K) == ["Saudi Arabia->Yemen", "Operation Restoring Hope->Yemen"]
    U = dt.timezone.utc; z = "Asia/Jerusalem"; mk = lambda s, e, y: {"tz": z, "outcome": y, "start": s, "end": e}
    s0, e0 = dt.datetime(2026, 9, 30, 21, 0, tzinfo=U), dt.datetime(2026, 10, 1, 20, 59, 59, tzinfo=U)   # Oct 1 00:00 .. 23:59:59 Jerusalem
    assert window_days(mk(s0, e0, 0)) == (d, d) and window_days(mk(s0, e0, 1)) == (d, d)
    s1 = dt.datetime(2026, 10, 1, 9, 0, tzinfo=U)                                                          # listed mid-day Oct 1
    assert window_days(mk(s1, e0 + dt.timedelta(2), 0)) == (d + dt.timedelta(1), d + dt.timedelta(2))
    assert window_days(mk(s1, e0 + dt.timedelta(2), 1))[0] == d
    assert ref_keys("houthi->israel", K) == ["Yemen [Houthi]->Israel"] and ref_keys("iran->qatar", K) == []
    print("synthetic: all checks pass")

if __name__ == "__main__":
    a = sys.argv[1:] or ["--synthetic"]
    {"--synthetic": synthetic, "--measure": measure}[a[0]]()

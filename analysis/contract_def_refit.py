"""docs/contract_def_refit_prereg.md: refit the unified world priors and the last-strike anchors on the contracts' own definition of
a strike. Polymarket's strike contracts count air strikes (incl. one-way attack drones) and surface-to-surface missiles, and exclude
artillery, mortars, rocket artillery, ground incursions, small arms and ATGMs. Our fits count every "Air/drone strike" and every
"Shelling/artillery/missile attack" event, so where a side mostly shells (Israel->Syria: Sep 2026 19 broad days, 0 air/drone days,
three contracts resolved NO) the priors are fitted to a different event than the contract pays on.
CONTRACT definition (amendment 1, Nov 3: the local tables carry no notes text): every Air/drone strike event, plus
Shelling/artillery/missile attack events only where the attacker's home state shares no land border with the target (beyond
artillery range, so a missile). Bordering pairs and forces fighting in their own country keep air/drone events only.
Everything else is unchanged (analysis/world_fits.py).
  --describe   monthly 2026 strike days, broad vs contract, for the tracked pairs (no outcomes)
  --fit        held-out (<= 2026-06-30) and production fits + anchors on the contract definition -> pilot/local/*_contract (gitignored)
  --compare    pre-registered replay and adoption rule (copies the production contract fit into pilot/local/ only if adopted)
  --synthetic  offline checks
"""
import sys, re, json, shutil, datetime as dt
from collections import defaultdict, Counter
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
import refit_local as RL

LOCAL = RL.LOCAL; TAG = "_contract"
_raw = RL.rows

# Land borders (a fact table, symmetric) for the countries in the world fit's region. A pair not covered keeps air/drone only.
BORDERS = {
    "Israel": "Lebanon Syria Jordan Egypt Palestine", "Palestine": "Israel Egypt Jordan", "Lebanon": "Israel Syria",
    "Syria": "Israel Lebanon Jordan Iraq Turkey", "Jordan": "Israel Palestine Syria Iraq Saudi_Arabia",
    "Iraq": "Syria Jordan Saudi_Arabia Kuwait Iran Turkey", "Iran": "Iraq Turkey Armenia Azerbaijan Turkmenistan Afghanistan Pakistan",
    "Saudi_Arabia": "Jordan Iraq Kuwait Qatar United_Arab_Emirates Oman Yemen", "Yemen": "Saudi_Arabia Oman",
    "Oman": "Yemen Saudi_Arabia United_Arab_Emirates", "United_Arab_Emirates": "Saudi_Arabia Oman", "Qatar": "Saudi_Arabia",
    "Kuwait": "Iraq Saudi_Arabia", "Bahrain": "", "Egypt": "Israel Palestine Libya Sudan", "Libya": "Egypt Sudan Chad Niger Algeria Tunisia",
    "Sudan": "Egypt Libya Chad Central_African_Republic South_Sudan Ethiopia Eritrea",
    "South_Sudan": "Sudan Ethiopia Kenya Uganda Democratic_Republic_of_Congo Central_African_Republic",
    "Ethiopia": "Eritrea Djibouti Somalia Kenya South_Sudan Sudan", "Eritrea": "Ethiopia Sudan Djibouti", "Somalia": "Ethiopia Kenya Djibouti Somaliland",
    "Somaliland": "Somalia Ethiopia Djibouti", "Kenya": "Somalia Ethiopia South_Sudan Uganda Tanzania",
    "Uganda": "Kenya South_Sudan Democratic_Republic_of_Congo Rwanda Tanzania",
    "Democratic_Republic_of_Congo": "Uganda Rwanda Burundi South_Sudan Central_African_Republic Republic_of_Congo Angola Zambia Tanzania",
    "Mali": "Niger Burkina_Faso Algeria Mauritania Senegal Guinea Ivory_Coast", "Niger": "Mali Burkina_Faso Algeria Libya Chad Nigeria Benin",
    "Burkina_Faso": "Mali Niger Benin Togo Ghana Ivory_Coast", "Afghanistan": "Pakistan Iran Turkmenistan Uzbekistan Tajikistan China",
    "Pakistan": "Afghanistan Iran India China", "India": "Pakistan China Nepal Bhutan Bangladesh Myanmar",
    "Turkey": "Syria Iraq Iran Armenia Azerbaijan Georgia Greece Bulgaria", "Armenia": "Azerbaijan Turkey Iran Georgia Artsakh",
    "Azerbaijan": "Armenia Iran Russia Georgia Turkey Artsakh", "Artsakh": "Azerbaijan Armenia",
    "Russia": "Ukraine Belarus Georgia Azerbaijan Kazakhstan China Finland Estonia Latvia Lithuania Poland Norway Mongolia North_Korea",
    "Ukraine": "Russia Belarus Poland Slovakia Hungary Romania Moldova"}
NB = {}
for a, bs in BORDERS.items():
    for b in bs.split():
        NB.setdefault(a.replace("_", " "), set()).add(b.replace("_", " ")); NB.setdefault(b.replace("_", " "), set()).add(a.replace("_", " "))
COALITION_HOME = {"Operation Restoring Hope": "Saudi Arabia", "Operation Decisive Storm": "Saudi Arabia", "Operation Peace Spring": "Turkey",
                  "Global Coalition Against Daesh": "United States", "NATO": "United States", "Operation Libya Dawn": "Libya"}

def home(key):
    k = re.sub(r"\s*\[.*\]$", "", key or "").strip(); return COALITION_HOME.get(k, k)

def beyond_artillery(attacker_key, target):
    """True when the attacker's home state shares no land border with the target (and is not fighting in its own country).
    None when either side is outside the border table (then only air/drone events count)."""
    h = home(attacker_key)
    if h == target: return False
    if h not in NB or target not in NB: return None
    return target not in NB[h]

def qualifies(r):
    s = r.get("sub_event_type")
    if s == "Air/drone strike": return True
    if s == "Shelling/artillery/missile attack":
        import world_fits as WF
        return beyond_artillery(WF.ident(r.get("actor1"))[0], r.get("country")) is True
    return False

def contract_rows():
    """The raw rows with non-qualifying strike events relabeled out of WF.SUBS, so every fit that filters on WF.SUBS
    (refit_local.build, theory_test4.strike_days) sees the contract definition."""
    for r in _raw():
        if r.get("sub_event_type") in ("Air/drone strike", "Shelling/artillery/missile attack") and not qualifies(r):
            r = dict(r, sub_event_type="Shelling/artillery (not a contract strike)")
        yield r

def describe():
    import theory_test4 as T4
    Pb, _, end = T4.strike_days(); RL.rows = contract_rows; Pc, _, _ = T4.strike_days(end); RL.rows = _raw
    for n in ("Israel->Syria", "Israel->Lebanon", "Israel->Iran", "Iran->Israel", "Saudi Arabia->Yemen", "Pakistan->Afghanistan", "Iran->Iraq"):
        b = Counter(d.strftime("%m") for d in Pb.get(n, ()) if d.year == 2026); c = Counter(d.strftime("%m") for d in Pc.get(n, ()) if d.year == 2026)
        print(f"  {n:24} broad {dict(sorted(b.items()))}\n  {'':24} contr {dict(sorted(c.items()))}")
    import world_fits as WF
    unk = Counter(f"{home(WF.ident(r.get('actor1'))[0])}->{r.get('country')}" for r in _raw() if r["event_date"][:4] == "2026"
                  and r.get("sub_event_type") == "Shelling/artillery/missile attack" and beyond_artillery(WF.ident(r.get("actor1"))[0], r.get("country")) is None)
    print(f"  event data through {end} | 2026 shelling/missile events on pairs outside the border table (counted as non-strikes): {dict(unk.most_common(8))}")

def fit():
    import theory_test4 as T4
    RL.rows = contract_rows
    try:
        RL.run(RL.HELDOUT_END, LOCAL / ("heldout" + TAG)); e = RL.last_complete_day(); RL.run(e, LOCAL / ("candidate" + TAG))
        P, _, _ = T4.strike_days()
        (LOCAL / ("last_strike" + TAG + ".json")).write_text(json.dumps({n: sorted(d.isoformat() for d in v) for n, v in P.items()}) + "\n")
        print(f"anchors -> pilot/local/last_strike{TAG}.json ({len(P)} pairs); Israel->Syria last {max(P.get('Israel->Syria', [None]))}")
    finally:
        RL.rows = _raw

def arm(world_dir, anchors):
    import refit_compare as RC, unified_price as UP
    RC.use_priors(world_dir / "priors_world.json", world_dir / "world_fits.json")
    UP._LAST = {k: sorted(v) for k, v in json.loads(Path(anchors).read_text()).items()}
    return RC.score_rows()

def rule(rows, seed=20261103):
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs)
    worse = [p for p in sorted({x["pair"] for x in rows}) if len(s := [x for x in rows if x["pair"] == p]) >= 3 and B(s, "b") - B(s, "a") > 0.05]
    pairs = sorted({x["pair"] for x in rows}); rng = np.random.default_rng(seed); ds = []
    for _ in range(2000):
        xs = [x for p in rng.choice(pairs, len(pairs)) for x in rows if x["pair"] == p]; ds.append(B(xs, "b") - B(xs, "a"))
    lo, hi = np.percentile(ds, [2.5, 97.5])
    return B(rows, "b") <= B(rows, "a") and not worse, worse, (round(float(lo), 4), round(float(hi), 4))

def compare():
    A = arm(LOCAL / "heldout", LOCAL / "last_strike.json"); Bc = arm(LOCAL / ("heldout" + TAG), LOCAL / ("last_strike" + TAG + ".json"))
    ids = sorted(set(A) & set(Bc)); rows = [{"pair": A[i]["pair"], "y": A[i]["y"], "a": A[i]["u"], "b": Bc[i]["u"], "m": A[i]["m"]} for i in ids]
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs if x[k] is not None) / max(1, sum(1 for x in xs if x[k] is not None))
    print(f"=== CONTRACT-DEFINITION REFIT (docs/contract_def_refit_prereg.md): {len(rows)} contracts first forecast >= 2026-07-01")
    print(f"  broad {B(rows, 'a'):.4f} | contract {B(rows, 'b'):.4f} | market {B(rows, 'm'):.4f}")
    for y in (1, 0):
        s = [x for x in rows if x["y"] == y]
        if s: print(f"  {'YES' if y else 'NO '} n={len(s):3} broad {B(s, 'a'):.4f} contract {B(s, 'b'):.4f} market {B(s, 'm'):.4f}")
    for p in sorted({x["pair"] for x in rows}):
        s = [x for x in rows if x["pair"] == p]
        print(f"    {p:28} n={len(s):3} YES {sum(x['y'] for x in s):3} broad {B(s, 'a'):.4f} contract {B(s, 'b'):.4f} market {B(s, 'm'):.4f}")
    adopt, worse, ci = rule(rows)
    print(f"  bootstrap by pair: contract - broad = {B(rows, 'b') - B(rows, 'a'):+.4f} 95% {list(ci)} | pairs worse by > 0.05 (n >= 3): {worse or 'none'}")
    if adopt:
        bk = LOCAL / f"backup_{dt.date.today():%Y%m%d}"; bk.mkdir(exist_ok=True)
        for f in ("priors_world.json", "world_fits.json", "last_strike.json"):
            if (LOCAL / f).exists(): shutil.copy(LOCAL / f, bk / f)
        for f in ("priors_world.json", "world_fits.json"): shutil.copy(LOCAL / ("candidate" + TAG) / f, LOCAL / f)
        shutil.copy(LOCAL / ("last_strike" + TAG + ".json"), LOCAL / "last_strike.json")
        print(f"  ADOPTION RULE -> ADOPTED: contract-definition fit and anchors copied to pilot/local/ (previous files in {bk.name}/)")
    else:
        print("  ADOPTION RULE -> NOT adopted: production priors and anchors unchanged")
    (LOCAL / "contract_def_refit_result.json").write_text(json.dumps({"n": len(rows), "brier": {k: round(B(rows, k), 4) for k in "abm"}, "ci_b_minus_a": list(ci),
        "worse_pairs": worse, "adopted": adopt, "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2) + "\n")

def synthetic():
    ok = True
    def chk(name, cond, detail):
        nonlocal ok; ok &= bool(cond); print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
    S = "Shelling/artillery/missile attack"
    import world_fits as WF
    I = lambda c: WF.ident(c)[0]
    cases = [("Air/drone strike", "Military Forces of Israel (2022-)", "Syria", True),
             (S, "Military Forces of Israel (2022-)", "Syria", False), (S, "Military Forces of Iran (1989-)", "Israel", True),
             (S, "Military Forces of Iran (1989-)", "Iraq", False), (S, "Military Forces of Pakistan (2024-)", "Afghanistan", False),
             (S, "Military Forces of Saudi Arabia (2017-)", "Yemen", False), ("Armed clash", "Military Forces of Iran (1989-)", "Israel", False)]
    for st, a1, c, want in cases:
        got = qualifies({"sub_event_type": st, "actor1": a1, "country": c})
        chk(f"qualifies: {st[:12]} {I(a1)}->{c}", got == want, f"want {want}, got {got}")
    chk("home(): faction and coalition", home("Yemen [Houthi]") == "Yemen" and home("Operation Restoring Hope") == "Saudi Arabia", "")
    chk("borders symmetric; unknown pair -> None", "Israel" in NB["Syria"] and beyond_artillery("Nowhere", "Israel") is None, "")
    global _raw
    raw0 = _raw; _raw = lambda: iter([{"sub_event_type": S, "actor1": "Military Forces of Israel (2022-)", "country": "Syria"},
                                      {"sub_event_type": S, "actor1": "Military Forces of Iran (1989-)", "country": "Israel"}, {"sub_event_type": "Air/drone strike"}])
    try:
        import world_fits as WF
        out = [r["sub_event_type"] in WF.SUBS for r in contract_rows()]
        chk("relabeled rows drop out of WF.SUBS", out == [False, True, True], f"{out}")
    finally:
        _raw = raw0
    rows = [{"pair": f"p{i % 4}", "y": i % 2, "a": 0.6 if i % 2 else 0.4, "b": 0.8 if i % 2 else 0.2} for i in range(40)]
    a, w, ci = rule(rows); chk("better everywhere -> adopt", a and not w, f"{a} {w} {ci}")
    rows = [dict(x, b=(0.95 if x["pair"] == "p0" and not x["y"] else x["b"])) for x in rows]
    a, w, ci = rule(rows); chk("one pair much worse -> not adopted", (not a) and w == ["p0"], f"{a} {w}")
    print("SYNTHETIC:", "ALL PASS" if ok else "FAILED"); return ok

if __name__ == "__main__":
    a = sys.argv
    if "--synthetic" in a: sys.exit(0 if synthetic() else 1)
    elif "--describe" in a: describe()
    elif "--fit" in a: fit()
    elif "--compare" in a: compare()
    else: print(__doc__)

"""docs/ucdp_refit_prereg.md: the open-data contingency for the local tables (world priors, hardening beta and K, strike-date anchors).
UCDP GED 26.1 (1989-2025) + GED Candidate (2026-01 .. 2026-09), CC BY 4.0 (Davies, Pettersson, Sollenberg & Oberg 2025; Hegre et
al. 2020). Same per-pair strike series and the same estimators as the local fits; only the event source changes:
  pairs, attacker, location   analysis/open_events_agreement.attackers (T1's rules): the location's government on one side -> the
                              other side's governments strike it; not a party -> every government side strikes it (Yemen's
                              government acting abroad = Yemen [Houthi], as in T1)
  ambiguous events            dropped (governments on both sides and the location not a party: the attacker can't be told apart)
  events                      type_of_violence 1 (state-based) and 3 (one-sided); exact dates (date_prec 1) observed, others
                              unobserved; window from 2015-01-01 (world_fits.D0)
  class                       world_fits.klass with the target read from the event: location's government a party -> state;
                              attacker a faction -> defacto; else -> nonstate; one-sided -> no named target
  world priors + fits         analysis/world_fits.py, unchanged (two-state model, >= 10 active days, class shrinkage)
  hardening                   analysis/hardening_fit.py's estimator (theory test 4's robust G = 30 coefficient; K over spell-weeks)
  anchors                     every pair's strike dates (all precisions, as the local table)

  python analysis/ucdp_refit.py --describe     pairs, classes, strike days per pair (open data only)
  python analysis/ucdp_refit.py --heldout      window ends 2026-06-30   -> pilot/local/ucdp/heldout/  (priors, fits, hardening)
  python analysis/ucdp_refit.py --production   window ends 2026-09-30 (the Candidate file's end) -> pilot/local/ucdp/production/
  python analysis/ucdp_refit.py --anchors      -> pilot/local/ucdp/last_strike.json
Outputs are gitignored while this is a candidate. Nothing here touches production.
"""
import sys, csv, json, datetime as dt
from collections import defaultdict, Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_fits as WF, open_events_agreement as OEA

ROOT = Path(__file__).resolve().parent.parent
SRC = [ROOT / "data" / "external" / "ucdp" / "GEDEvent_v26_1.csv", ROOT / "data" / "external" / "ucdp" / "GEDEvent_v26_01_26_09.csv"]
OUT = ROOT / "pilot" / "local" / "ucdp"
HELDOUT_END, DATA_END = dt.date(2026, 6, 30), dt.date(2026, 9, 30)
TYPES = {"1", "3"}
OEA.NAME.setdefault("Kingdom of eSwatini", "eSwatini")         # UCDP's location name for eSwatini (else a fake cross-border pair)

def events(end):
    """(pair, date, exact, attacker kind, target kind) per attacker, window WF.D0 .. end; the Candidate file only after GED's end."""
    ged_end = None
    for i, f in enumerate(SRC):
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["type_of_violence"] not in TYPES: continue
                d = dt.date.fromisoformat(r["date_start"][:10])
                if d < WF.D0 or d > end: continue
                if i == 0: ged_end = max(ged_end or d, d)
                elif ged_end and d <= ged_end: continue          # Candidate rows inside GED's span are superseded by GED
                loc, att, amb = OEA.attackers(r)
                if amb: continue                                   # governments on both sides, location not a party: attacker unknown
                a, b = OEA.govs(r["side_a"]), OEA.govs(r["side_b"])
                one_sided = r["type_of_violence"] == "3"
                for g in att:
                    kind = "defacto" if "[" in g else "state"
                    tk = None if one_sided else ("defacto" if kind == "defacto" else ("state" if (loc in a or loc in b) else "nonstate"))
                    yield f"{g}->{loc}", d, r["date_prec"] == "1", kind, tk

def build(end):
    P = defaultdict(lambda: {"exact": set(), "inexact": set(), "tk": Counter(), "kind": None})
    for n, d, exact, kind, tk in events(end):
        p = P[n]; p["kind"] = kind
        (p["exact"] if exact else p["inexact"]).add(d)
        if tk: p["tk"][tk] += 1
    for p in P.values(): p["inexact"] -= p["exact"]
    return P

def strike_days(end):
    """theory_test4.strike_days's shape: {pair: all strike dates}, {pair: class}, end."""
    P = build(end)
    return {n: p["exact"] | p["inexact"] for n, p in P.items()}, {n: WF.klass(p["kind"], p["tk"]) for n, p in P.items()}, end

def priors(end, outdir):
    import refit_local as RL
    outdir.mkdir(parents=True, exist_ok=True)
    WF.D1 = end; WF.build = lambda: build(end); WF.OUT = outdir / "priors_world.json"; WF.TAB = outdir / "world_fits.json"
    WF.main()
    d = json.loads(WF.OUT.read_text()); d["data"] = f"UCDP GED 26.1 + Candidate 26.01-26.09 (CC BY 4.0), window {WF.D0} .. {end}"
    d["frozen"] = dt.date.today().isoformat(); WF.OUT.write_text(json.dumps(d, indent=1) + "\n")

def hardening(end, out):
    import theory_test4 as T4, numpy as np
    P, cls, e = strike_days(end)
    df = T4.design(P, cls, e, 30, robust=True); r = T4.fit(df, robust=True)
    beta = float(r.params["lw"]); K = float(np.mean(np.exp(df["lw"].values) ** beta))
    res = {"beta": beta, "K": K, "G": 30, "spell_weeks": int(len(df)), "restarts": int(df.y.sum()), "p": float(r.pvalues["lw"]),
           "source": "UCDP GED 26.1 + Candidate", "window_end": end.isoformat(), "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    out.write_text(json.dumps(res, indent=2) + "\n")
    print(f"hardening: beta {beta:+.4f} (p {res['p']:.3g}) | K {K:.4f} | {res['spell_weeks']} spell-weeks, {res['restarts']} restarts -> {out}")

def anchors():
    P, _, _ = strike_days(DATA_END)
    out = {n: sorted(d.isoformat() for d in days) for n, days in P.items()}
    f = OUT / "last_strike.json"; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(out) + "\n")
    for n in ("Israel->Lebanon", "Israel->Iran", "United States->Iran", "Pakistan->Afghanistan", "Israel->Syria", "Iran->Iraq"):
        print(f"  {n:24} last strike {out.get(n, ['none'])[-1]}")
    print(f"{len(out)} pairs -> {f}")

def describe():
    P = build(DATA_END)
    rows = sorted(((len(p["exact"]), n, WF.klass(p["kind"], p["tk"])) for n, p in P.items()), reverse=True)
    print(f"{len(P)} directed pairs, {sum(1 for r in rows if r[0] >= 10)} with >= 10 exact strike days (fitted); window {WF.D0} .. {DATA_END}")
    print("classes (fitted pairs):", dict(Counter(c for k, _, c in rows if k >= 10)))
    for k, n, c in rows[:45]: print(f"  {n:40} {c:22} exact days {k:5}")

if __name__ == "__main__":
    a = sys.argv[1:] or ["--describe"]
    if a[0] == "--describe": describe()
    elif a[0] == "--heldout":
        priors(HELDOUT_END, OUT / "heldout"); hardening(HELDOUT_END, OUT / "heldout" / "hardening.json")
    elif a[0] == "--production":
        priors(DATA_END, OUT / "production"); hardening(DATA_END, OUT / "production" / "hardening.json")
    elif a[0] == "--anchors": anchors()
    else: print(__doc__)

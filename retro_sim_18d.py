"""
retro_sim_18d.py  —  Two-date residual Weibull CDF sensitivity simulator
Uses Run 18 backtest_results.json (OperationalPreparation / RoutineMilitaryPressure split).

Gate:   crisis_onset_date  → ICB episode clock allowed to start (binary)
Clock:  acute_phase_onset_date → timing reference for Weibull residual CDF
        (falls back to crisis_onset_date if acute_phase not specified)

Tests 6 onset-date scenarios × rho grid [1,2,3,4,5]
Reports full Brier table + Iran HOT row detail at best candidate.

Run from ~/predictioneering/:
    python3.11 retro_sim_18d.py
"""

import json, math
from collections import defaultdict
from datetime import date, datetime

# ── helpers ───────────────────────────────────────────────────────────────────

def sigmoid(x):
    return 1 / (1 + math.exp(-max(-50, min(50, x))))

def logit(p, eps=1e-6):
    p = max(eps, min(1 - eps, p))
    return math.log(p / (1 - p))

def weibull_F(D, scale=14.2, shape=0.65):
    """Unconditional ICB violent-response CDF."""
    return 1 - math.exp(-((max(D, 0) / scale) ** shape))

def weibull_residual(A, D, scale=14.2, shape=0.65):
    """
    Residual CDF: P(violence within next D days | no violence in first A days).
    A = days elapsed since acute phase onset (crisis age).
    D = days remaining before contract close.
    """
    FA  = 1 - math.exp(-((max(A, 0) / scale) ** shape))
    FAD = 1 - math.exp(-((max(A + D, 0) / scale) ** shape))
    denom = 1 - FA
    if denom < 1e-9:
        return 1.0   # crisis so old all residual mass is exhausted → treat as 1
    return (FAD - FA) / denom

def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None

def days_between(d1_str, d2_str):
    """Days from d1 to d2 (positive if d2 > d1)."""
    if not d1_str or not d2_str:
        return None
    d1 = parse_date(d1_str)
    d2 = parse_date(d2_str)
    return (d2 - d1).days

def brier(rows_subset):
    if not rows_subset:
        return float("nan")
    return sum((r["p_new"] - r["resolution"]) ** 2 for r in rows_subset) / len(rows_subset)

def mean_p(rows_subset):
    if not rows_subset:
        return float("nan")
    return sum(r["p_new"] for r in rows_subset) / len(rows_subset)

# ── load & filter ─────────────────────────────────────────────────────────────

with open("pipeline/backtest_results.json") as f:
    raw = json.load(f)

POST_RES = {"US-Venezuela": "2026-01-03"}

def is_post_resolution(r):
    cutoff = POST_RES.get(r.get("dyad"))
    if cutoff is None:
        return False
    d = r.get("snapshot_date") or r.get("date") or ""
    return d >= cutoff

rows = []
for r in raw:
    if r.get("z_t") == 2:
        continue
    if r.get("resolution") is None:
        continue
    if is_post_resolution(r):
        continue
    rows.append(r)

print(f"Working rows: {len(rows)}  "
      f"YES={sum(1 for r in rows if r['resolution']==1)}  "
      f"NO={sum(1 for r in rows if r['resolution']==0)}")
print()

# ── contract labelling ────────────────────────────────────────────────────────

IRAN_HOT_START = "2026-01-20"
IRAN_HOT_END   = "2026-02-01"

def label(r):
    dyad = r.get("dyad", "")
    d    = r.get("snapshot_date") or r.get("date") or ""
    if dyad == "US-Iran":
        return "Iran-HOT" if IRAN_HOT_START <= d <= IRAN_HOT_END else "Iran-COLD"
    if dyad == "US-Venezuela":    return "Venezuela"
    if dyad == "China-Taiwan":    return "China-Taiwan"
    if dyad == "India-Pakistan":  return "India-Pakistan"
    return "Other"

# ── signal extraction ─────────────────────────────────────────────────────────

def extract(r):
    qc  = r.get("q_components", {})
    op  = qc.get("OperationalPreparation", 0)
    rmp = qc.get("RoutineMilitaryPressure", 0)
    vio = qc.get("LiveViolenceObserved",    0)
    ult = qc.get("LiveUltimatumDeadline",   0)
    abt = abs(qc.get("LiveAbatementSignal", 0))
    # acute_core = pure operational signals (gate/boost variable)
    acute_core = op + vio + ult
    boost_raw  = op + vio + ult + 0.10 * rmp - abt
    return acute_core, boost_raw

# ── onset-date scenarios ──────────────────────────────────────────────────────
# crisis_onset_date      : ICB-codable breakpoint → gates whether boost activates
# acute_phase_onset_date : operational/ultimatum phase → Weibull timing clock
#                          (None → fall back to crisis_onset_date)
# Dyads without an entry get no boost (Taiwan, India-Pakistan).

SCENARIOS = {
    # Iran: crisis onset brackets + fixed acute phase = Jan 20 (HOT window open)
    "Iran(Nov)+Ven(Nov)": {
        "US-Iran":        {"crisis": "2025-11-01", "acute": "2026-01-20"},
        "US-Venezuela":   {"crisis": "2025-11-15", "acute": "2025-12-13"},
    },
    "Iran(Dec)+Ven(Nov)": {
        "US-Iran":        {"crisis": "2025-12-01", "acute": "2026-01-20"},
        "US-Venezuela":   {"crisis": "2025-11-15", "acute": "2025-12-13"},
    },
    "Iran(Jan)+Ven(Nov)": {
        "US-Iran":        {"crisis": "2026-01-20", "acute": None},           # onset = acute
        "US-Venezuela":   {"crisis": "2025-11-15", "acute": "2025-12-13"},
    },
    "Iran(Nov)+Ven(Dec)": {
        "US-Iran":        {"crisis": "2025-11-01", "acute": "2026-01-20"},
        "US-Venezuela":   {"crisis": "2025-12-01", "acute": "2025-12-13"},
    },
    "Iran(Dec)+Ven(Dec)": {
        "US-Iran":        {"crisis": "2025-12-01", "acute": "2026-01-20"},
        "US-Venezuela":   {"crisis": "2025-12-01", "acute": "2025-12-13"},
    },
    "Iran(Jan)+Ven(Dec)": {
        "US-Iran":        {"crisis": "2026-01-20", "acute": None},
        "US-Venezuela":   {"crisis": "2025-12-13", "acute": None},           # onset = acute
    },
}

RHO_GRID = [1, 2, 3, 4, 5]
NO_CONSTRAINT = 0.004

# ── compute Weibull F for a row given scenario ────────────────────────────────

def compute_F(r, dyad_config):
    """
    Returns Weibull transport value for this row.
    0.0 if no crisis onset defined (episode gate closed).
    """
    if dyad_config is None:
        return 0.0

    crisis_onset = dyad_config.get("crisis")
    acute_onset  = dyad_config.get("acute")

    if crisis_onset is None:
        return 0.0

    snap_date = r.get("snapshot_date") or r.get("date") or ""
    if not snap_date:
        return 0.0

    # Gate: snapshot must be on or after crisis onset
    if snap_date < crisis_onset:
        return 0.0

    days = r.get("days_remaining") or r.get("t_minus") or 30

    # Clock: use acute_onset if defined, else crisis_onset
    clock_date = acute_onset if acute_onset else crisis_onset

    if snap_date < clock_date:
        # Before acute phase — episode active but acute phase hasn't started
        # Use unconditional F from crisis onset (A computed from crisis_onset)
        A = days_between(crisis_onset, snap_date)
        A = max(A, 0)
        return weibull_residual(A, days)
    else:
        A = days_between(clock_date, snap_date)
        A = max(A, 0)
        return weibull_residual(A, days)

# ── main grid ─────────────────────────────────────────────────────────────────

all_candidates = []

for scen_name, dyad_configs in SCENARIOS.items():
    print(f"=== Scenario: {scen_name} ===")
    print(f"  {'rho':>3}  {'Overall':>8}  {'YES':>8}  {'NO':>8}  "
          f"{'IranHOT-p':>10}  {'IranHOT-B':>9}  {'IranCLD-B':>9}  "
          f"{'Ven-B':>7}  {'TW-B':>7}  {'IP-B':>7}  {'NO<=.004':>9}")
    print("  " + "-"*99)

    for rho in RHO_GRID:
        tagged = []
        for r in rows:
            dyad       = r.get("dyad", "")
            p_base     = r.get("engine_p", 0.05)
            dc         = dyad_configs.get(dyad)   # None for Taiwan, India-Pak
            F          = compute_F(r, dc)
            ac, boost_raw = extract(r)
            boost      = F * boost_raw             # no OP gate needed: F=0 for non-crisis dyads
            p_new      = sigmoid(logit(p_base) + rho * boost)
            tagged.append({**r,
                "p_new": p_new, "label": label(r),
                "F": F, "boost": boost, "acute_core": ac})

        yes_r = [r for r in tagged if r["resolution"] == 1]
        no_r  = [r for r in tagged if r["resolution"] == 0]
        ih    = [r for r in tagged if r["label"] == "Iran-HOT"]
        ic    = [r for r in tagged if r["label"] == "Iran-COLD"]
        vn    = [r for r in tagged if r["label"] == "Venezuela"]
        tw    = [r for r in tagged if r["label"] == "China-Taiwan"]
        ip    = [r for r in tagged if r["label"] == "India-Pakistan"]

        b_ov  = brier(tagged)
        b_yes = brier(yes_r)
        b_no  = brier(no_r)
        b_ih  = brier(ih)
        b_ic  = brier(ic)
        b_vn  = brier(vn)
        b_tw  = brier(tw)
        b_ip  = brier(ip)
        ih_p  = mean_p(ih)
        no_ok = "✓" if b_no <= NO_CONSTRAINT else "✗"

        print(f"  {rho:>3}  {b_ov:>8.4f}  {b_yes:>8.4f}  {b_no:>8.4f}  "
              f"{ih_p:>10.1%}  {b_ih:>9.4f}  {b_ic:>9.4f}  "
              f"{b_vn:>7.4f}  {b_tw:>7.4f}  {b_ip:>7.4f}  {no_ok:>9}")

        if b_no <= NO_CONSTRAINT:
            all_candidates.append({
                "scenario": scen_name, "rho": rho,
                "b_yes": b_yes, "b_no": b_no, "b_ov": b_ov,
                "ih_p": ih_p, "b_ih": b_ih, "tagged": tagged,
            })
    print()

# ── robustness summary ────────────────────────────────────────────────────────

print("=" * 80)
print("ROBUSTNESS SUMMARY — all candidates passing NO <= 0.004")
print("=" * 80)
if all_candidates:
    print(f"  {'Scenario':<30}  {'rho':>3}  {'YES':>8}  {'NO':>8}  "
          f"{'IranHOT-p':>10}  {'Overall':>8}")
    print("  " + "-"*75)
    for c in sorted(all_candidates, key=lambda x: x["b_yes"]):
        print(f"  {c['scenario']:<30}  {c['rho']:>3}  {c['b_yes']:>8.4f}  "
              f"{c['b_no']:>8.4f}  {c['ih_p']:>10.1%}  {c['b_ov']:>8.4f}")
    print()

    # Swing analysis: how much does Iran HOT p vary across scenarios at same rho?
    print("SWING ANALYSIS — Iran HOT avg p by scenario at each rho")
    print(f"  {'rho':>3}  {'min_p':>8}  {'max_p':>8}  {'swing':>8}  scenarios_passing")
    for rho in RHO_GRID:
        rho_cands = [c for c in all_candidates if c["rho"] == rho]
        if rho_cands:
            ps = [c["ih_p"] for c in rho_cands]
            print(f"  {rho:>3}  {min(ps):>8.1%}  {max(ps):>8.1%}  "
                  f"{max(ps)-min(ps):>8.1%}  {len(rho_cands)}/{len(SCENARIOS)}")
    print()
else:
    print("  No candidates passed NO <= 0.004 constraint.")
    print()

# ── Weibull F distribution check ──────────────────────────────────────────────

print("WEIBULL F VALUES by group — best passing scenario (or first scenario if none)")
ref_scen_name = all_candidates[0]["scenario"] if all_candidates else list(SCENARIOS.keys())[0]
ref_dc = SCENARIOS[ref_scen_name]
print(f"  (Reference scenario: {ref_scen_name})")

f_groups = defaultdict(list)
for r in rows:
    dyad = r.get("dyad", "")
    dc   = ref_dc.get(dyad)
    F    = compute_F(r, dc)
    f_groups[label(r)].append(F)

for name, vals in sorted(f_groups.items()):
    nonzero = [v for v in vals if v > 0]
    mean_f  = sum(vals) / len(vals)
    mean_nz = sum(nonzero) / len(nonzero) if nonzero else 0
    pct_nz  = len(nonzero) / len(vals)
    print(f"  {name:<18}: mean_F={mean_f:.3f}  mean_when_active={mean_nz:.3f}  "
          f"pct_active={pct_nz:.1%}  n={len(vals)}")
print()

# ── best candidate detail ─────────────────────────────────────────────────────

if all_candidates:
    best = min(all_candidates, key=lambda x: x["b_yes"])
    print(f"BEST CANDIDATE: scenario={best['scenario']}  rho={best['rho']}")
    print(f"  Overall={best['b_ov']:.4f}  YES={best['b_yes']:.4f}  "
          f"NO={best['b_no']:.4f}  Iran-HOT avg p={best['ih_p']:.1%}")
    print()

    print("  Iran HOT row detail:")
    print(f"  {'date':<14} {'days':>5}  {'A_days':>7}  {'F':>6}  "
          f"{'p_base':>8}  {'p_new':>8}  {'market':>8}  {'boost':>8}")
    iran_hot = sorted(
        [r for r in best["tagged"] if r["label"] == "Iran-HOT"],
        key=lambda x: x.get("snapshot_date") or x.get("date") or ""
    )
    ref_dc_best = SCENARIOS[best["scenario"]]
    for r in iran_hot:
        d    = r.get("snapshot_date") or r.get("date") or "?"
        days = r.get("days_remaining") or r.get("t_minus") or 30
        dc   = ref_dc_best.get("US-Iran")
        F    = r.get("F", 0)
        # compute A for display
        clock = dc.get("acute") or dc.get("crisis") if dc else None
        A_disp = days_between(clock, d) if (clock and d != "?") else "?"
        _, boost_raw = extract(r)
        print(f"  {str(d):<14} {days:>5}  {str(A_disp):>7}  {F:>6.3f}  "
              f"{r.get('engine_p',0):>8.1%}  {r['p_new']:>8.1%}  "
              f"{r.get('market_p',0):>8.1%}  {r['boost']:>8.4f}")

    print()
    print("  Venezuela pre-resolution:")
    vn = [r for r in best["tagged"] if r["label"] == "Venezuela"]
    print(f"  n={len(vn)}  avg p_new={mean_p(vn):.1%}  Brier={brier(vn):.4f}")

    print()
    print("  China-Taiwan (should be unchanged from Run 18 base):")
    tw = [r for r in best["tagged"] if r["label"] == "China-Taiwan"]
    print(f"  n={len(tw)}  avg p_new={mean_p(tw):.1%}  Brier={brier(tw):.4f}")

    print()
    print("  India-Pakistan (should be unchanged from Run 18 base):")
    ip = [r for r in best["tagged"] if r["label"] == "India-Pakistan"]
    print(f"  n={len(ip)}  avg p_new={mean_p(ip):.1%}  Brier={brier(ip):.4f}")

else:
    print("No candidates passed constraint. Inspect scenario grids above.")
    print("Consider relaxing NO constraint to 0.005 or 0.006.")

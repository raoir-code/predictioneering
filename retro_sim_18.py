"""
retro_sim_18.py  —  ICB Weibull transport retrospective simulator
Run from ~/predictioneering/:
    python3.11 retro_sim_18.py

Tests rho in [0, 1, 2, 3, 4, 5, 6, 8] against saved Run 17 rows.
No API calls. No backtest rerun. Pure arithmetic over backtest_results.json.
"""

import json, math
from collections import defaultdict

# ── helpers ───────────────────────────────────────────────────────────────────

def sigmoid(x):
    return 1 / (1 + math.exp(-max(-50, min(50, x))))

def logit(p, eps=1e-6):
    p = max(eps, min(1 - eps, p))
    return math.log(p / (1 - p))

def weibull_F(D, scale=14.2, shape=0.65):
    """ICB violent-response CDF.  A=0 (treat every snapshot as fresh trigger)."""
    return 1 - math.exp(-((max(D, 0) / scale) ** shape))

def brier(rows_subset):
    if not rows_subset:
        return float("nan")
    return sum((r["p_new"] - r["resolution"]) ** 2 for r in rows_subset) / len(rows_subset)

# ── load ──────────────────────────────────────────────────────────────────────

with open("pipeline/backtest_results.json") as f:
    raw = json.load(f)

# ── post-resolution strip: Venezuela resolved 2026-01-03 ─────────────────────
POST_RES = {
    "US-Venezuela": "2026-01-03",
}

def is_post_resolution(row):
    cutoff = POST_RES.get(row.get("dyad"))
    if cutoff is None:
        return False
    d = row.get("date") or row.get("snapshot_date") or ""
    return d >= cutoff

# ── build working rows ────────────────────────────────────────────────────────
# Keep: z_t != 2, has resolution, not post-resolution
# Drop: z_t == 2 (Russia-Ukraine / Trump-Ukraine)

rows = []
for r in raw:
    if r.get("z_t") == 2:
        continue
    if r.get("resolution") is None:
        continue
    if is_post_resolution(r):
        continue
    rows.append(r)

print(f"Working rows (excl Z_t=2, post-res): {len(rows)}")
print(f"  YES rows: {sum(1 for r in rows if r['resolution'] == 1)}")
print(f"  NO  rows: {sum(1 for r in rows if r['resolution'] == 0)}")
print()

# ── contract labels ───────────────────────────────────────────────────────────
# Classify each row for per-contract reporting

IRAN_HOT_START  = "2026-01-20"
IRAN_HOT_END    = "2026-02-01"
IRAN_COLD_START = "2026-02-02"
IRAN_COLD_END   = "2026-02-28"

def contract_label(r):
    dyad = r.get("dyad", "")
    d    = r.get("date") or r.get("snapshot_date") or ""
    if dyad == "US-Iran":
        if IRAN_HOT_START <= d <= IRAN_HOT_END:
            return "Iran-HOT"
        return "Iran-COLD"
    if dyad == "US-Venezuela":
        return "Venezuela"
    if dyad == "China-Taiwan":
        return "China-Taiwan"
    if dyad == "India-Pakistan":
        return "India-Pakistan"
    return "Other"

# ── live_boost computation ────────────────────────────────────────────────────
# Uses already-shrinkage-weighted q_components from saved rows.
# Key mapping (Patch 17 changed rubric, not key names):
#   LiveNonviolentMilitaryPressure ≈ OperationalPrep(1.0) + RoutineMP(0.25) blend
#   We apply a 0.50 weight to capture that it's a mix, not pure operational.
#   LiveViolenceObserved, LiveUltimatumDeadline, LiveAbatementSignal direct.

def compute_live_boost(r, F):
    qc = r.get("q_components", {})
    boost_raw = (
          qc.get("LiveNonviolentMilitaryPressure", 0) * 0.50   # mixed operational+routine
        + qc.get("LiveViolenceObserved",           0) * 1.00
        + qc.get("LiveUltimatumDeadline",          0) * 1.00
        - abs(qc.get("LiveAbatementSignal",        0))         # abatement is a penalty
        # LiveMediationAccepted intentionally excluded: Patch 17 showed talks ≠ de-escalation
    )
    return F * boost_raw

# ── rho grid simulation ───────────────────────────────────────────────────────

RHO_GRID = [0, 1, 2, 3, 4, 5, 6, 8]

print("=" * 80)
print(f"{'rho':>4}  {'Overall':>9}  {'YES':>9}  {'NO':>9}  "
      f"{'IranHOT-p':>10}  {'IranHOT-B':>10}  {'IranCOLD-B':>11}  "
      f"{'Ven-B':>7}  {'TW-B':>7}  {'IP-B':>7}  {'NO-OK':>6}")
print("-" * 80)

results_by_rho = {}

for rho in RHO_GRID:
    tagged = []
    for r in rows:
        p_base        = r.get("engine_p", 0.05)
        days_remaining = r.get("days_remaining") or r.get("t_minus") or 30
        F             = weibull_F(days_remaining)
        live_boost    = compute_live_boost(r, F)
        new_logit     = logit(p_base) + rho * live_boost
        p_new         = sigmoid(new_logit)
        tagged.append({**r, "p_new": p_new, "label": contract_label(r)})

    yes_rows    = [r for r in tagged if r["resolution"] == 1]
    no_rows     = [r for r in tagged if r["resolution"] == 0]
    iran_hot    = [r for r in tagged if r["label"] == "Iran-HOT"]
    iran_cold   = [r for r in tagged if r["label"] == "Iran-COLD"]
    venezuela   = [r for r in tagged if r["label"] == "Venezuela"]
    taiwan      = [r for r in tagged if r["label"] == "China-Taiwan"]
    india_pak   = [r for r in tagged if r["label"] == "India-Pakistan"]

    b_overall   = brier(tagged)
    b_yes       = brier(yes_rows)
    b_no        = brier(no_rows)
    b_iran_hot  = brier(iran_hot)
    b_iran_cold = brier(iran_cold)
    b_ven       = brier(venezuela)
    b_tw        = brier(taiwan)
    b_ip        = brier(india_pak)

    iran_hot_avg_p = (sum(r["p_new"] for r in iran_hot) / len(iran_hot)) if iran_hot else float("nan")
    no_ok = "✓" if b_no <= 0.0035 else "✗"

    print(f"{rho:>4}  {b_overall:>9.4f}  {b_yes:>9.4f}  {b_no:>9.4f}  "
          f"{iran_hot_avg_p:>10.1%}  {b_iran_hot:>10.4f}  {b_iran_cold:>11.4f}  "
          f"{b_ven:>7.4f}  {b_tw:>7.4f}  {b_ip:>7.4f}  {no_ok:>6}")

    results_by_rho[rho] = tagged

print()

# ── live_boost distribution check ────────────────────────────────────────────
# Sanity check: is boost well-separated between YES and NO dyads?

print("=== live_boost distribution (at rho=1, i.e. raw boost values) ===")
groups = {
    "Iran YES"        : [],
    "Venezuela YES"   : [],
    "China-Taiwan NO" : [],
    "India-Pakistan NO": [],
}
for r in rows:
    days_remaining = r.get("days_remaining") or r.get("t_minus") or 30
    F    = weibull_F(days_remaining)
    lb   = compute_live_boost(r, F)
    lab  = contract_label(r)
    res  = r["resolution"]
    if lab == "Iran-HOT" and res == 1:       groups["Iran YES"].append(lb)
    elif lab == "Venezuela" and res == 1:    groups["Venezuela YES"].append(lb)
    elif lab == "China-Taiwan" and res == 0: groups["China-Taiwan NO"].append(lb)
    elif lab == "India-Pakistan" and res == 0: groups["India-Pakistan NO"].append(lb)

for name, vals in groups.items():
    if vals:
        mean_v = sum(vals) / len(vals)
        p95    = sorted(vals)[int(0.95 * len(vals))]
        print(f"  {name:<22}: n={len(vals):>3}  mean={mean_v:+.4f}  p95={p95:+.4f}")
print()

# ── per-row detail for Iran HOT at best rho ───────────────────────────────────
# Find best rho: max YES improvement subject to NO <= 0.0035
valid_rhos = [(rho, results_by_rho[rho]) for rho in RHO_GRID
              if brier([r for r in results_by_rho[rho] if r["resolution"]==0]) <= 0.0035]

if valid_rhos:
    best_rho, best_tagged = max(
        valid_rhos,
        key=lambda x: -brier([r for r in x[1] if r["resolution"]==1])
    )
    print(f"=== Best rho under NO constraint: rho={best_rho} ===")
    print(f"    YES Brier: {brier([r for r in best_tagged if r['resolution']==1]):.4f}")
    print(f"    NO  Brier: {brier([r for r in best_tagged if r['resolution']==0]):.4f}")
    print()
    print("    Iran HOT row detail:")
    print(f"    {'date':<12} {'days':>5}  {'p_base':>8}  {'p_new':>8}  {'market':>8}  {'res':>4}  {'live_boost':>11}")
    for r in sorted([r for r in best_tagged if r["label"]=="Iran-HOT"], key=lambda x: x.get("date","") or ""):
        days_remaining = r.get("days_remaining") or r.get("t_minus") or 30
        F    = weibull_F(days_remaining)
        lb   = compute_live_boost(r, F)
        print(f"    {str(r.get('date','?')):<12} {days_remaining:>5}  "
              f"{r.get('engine_p',0):>8.1%}  {r['p_new']:>8.1%}  "
              f"{r.get('market_p',0):>8.1%}  {r['resolution']:>4}  {lb:>+11.4f}")
else:
    print("No rho passed the NO <= 0.0035 constraint. Inspect the grid above.")

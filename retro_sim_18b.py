"""
retro_sim_18b.py  —  ICB transport + acute-core activation gate grid
Tests:
  - rho in [1, 2, 3, 4, 5]
  - activation in [none, hard_threshold, soft_sigmoid, boost_threshold]
Reports full Brier table + per-group activation rates + row detail at best candidate.
Run from ~/predictioneering/:
    python3.11 retro_sim_18b.py
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
    return 1 - math.exp(-((max(D, 0) / scale) ** shape))

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

# ── contract labelling ────────────────────────────────────────────────────────

IRAN_HOT_START  = "2026-01-20"
IRAN_HOT_END    = "2026-02-01"

def contract_label(r):
    dyad = r.get("dyad", "")
    d    = r.get("snapshot_date") or r.get("date") or ""
    if dyad == "US-Iran":
        if IRAN_HOT_START <= d <= IRAN_HOT_END:
            return "Iran-HOT"
        return "Iran-COLD"
    if dyad == "US-Venezuela":  return "Venezuela"
    if dyad == "China-Taiwan":  return "China-Taiwan"
    if dyad == "India-Pakistan": return "India-Pakistan"
    return "Other"

# ── acute_core + live_boost from q_components ─────────────────────────────────
# NOTE: Patch 17 split LiveNonviolentMilitaryPressure in the rubric only.
# The stored key is still LiveNonviolentMilitaryPressure.
# We treat it as: 0.70 * OperationalPrep signal + 0.30 * RoutineMP signal
# For the acute_core gate, use only the operational portion (0.70 weight).

def extract_signals(r):
    qc = r.get("q_components", {})
    lnvm        = qc.get("LiveNonviolentMilitaryPressure", 0)
    live_vio    = qc.get("LiveViolenceObserved",           0)
    live_ult    = qc.get("LiveUltimatumDeadline",          0)
    live_abt    = abs(qc.get("LiveAbatementSignal",        0))

    # acute_core: only signals that reflect active crisis commitment
    # LNVM gets 0.70 weight (operational portion); routine excluded from gate
    acute_core  = (lnvm * 0.70) + live_vio + live_ult

    # full boost term (including weak routine component)
    boost_raw   = (lnvm * 0.50) + live_vio + live_ult - live_abt

    return acute_core, boost_raw

# ── activation functions ──────────────────────────────────────────────────────

def activation_none(acute_core):
    return 1.0

def activation_hard(acute_core, threshold=0.15):
    return 1.0 if acute_core >= threshold else 0.0

def activation_soft(acute_core, center=0.15, scale=0.05):
    # sigmoid gate centered on acute_core = center
    return sigmoid((acute_core - center) / scale)

ACTIVATION_MODES = {
    "none"       : activation_none,
    "hard(0.15)" : lambda ac: activation_hard(ac, threshold=0.15),
    "soft(0.15)" : lambda ac: activation_soft(ac, center=0.15, scale=0.05),
    "hard(0.10)" : lambda ac: activation_hard(ac, threshold=0.10),
}

RHO_GRID = [1, 2, 3, 4, 5]

# ── main grid ─────────────────────────────────────────────────────────────────

print(f"Working rows: {len(rows)}  "
      f"YES={sum(1 for r in rows if r['resolution']==1)}  "
      f"NO={sum(1 for r in rows if r['resolution']==0)}")
print()

# Collect candidates that pass NO constraint
candidates = []

for act_name, act_fn in ACTIVATION_MODES.items():
    print(f"=== Activation: {act_name} ===")
    print(f"  {'rho':>3}  {'Overall':>8}  {'YES':>8}  {'NO':>8}  "
          f"{'IranHOT-p':>10}  {'IranHOT-B':>9}  {'IranCLD-B':>9}  "
          f"{'Ven-B':>7}  {'TW-B':>7}  {'IP-B':>7}  {'NO<=.005':>9}")
    print("  " + "-"*95)

    for rho in RHO_GRID:
        tagged = []
        for r in rows:
            p_base = r.get("engine_p", 0.05)
            days   = r.get("days_remaining") or r.get("t_minus") or 30
            F      = weibull_F(days)
            acute_core, boost_raw = extract_signals(r)
            act    = act_fn(acute_core)
            live_boost = F * act * boost_raw
            p_new  = sigmoid(logit(p_base) + rho * live_boost)
            tagged.append({
                **r,
                "p_new"      : p_new,
                "label"      : contract_label(r),
                "live_boost" : live_boost,
                "acute_core" : acute_core,
                "activated"  : act > 0.5,
            })

        yes_r  = [r for r in tagged if r["resolution"]==1]
        no_r   = [r for r in tagged if r["resolution"]==0]
        ih     = [r for r in tagged if r["label"]=="Iran-HOT"]
        ic     = [r for r in tagged if r["label"]=="Iran-COLD"]
        vn     = [r for r in tagged if r["label"]=="Venezuela"]
        tw     = [r for r in tagged if r["label"]=="China-Taiwan"]
        ip     = [r for r in tagged if r["label"]=="India-Pakistan"]

        b_ov   = brier(tagged)
        b_yes  = brier(yes_r)
        b_no   = brier(no_r)
        b_ih   = brier(ih)
        b_ic   = brier(ic)
        b_vn   = brier(vn)
        b_tw   = brier(tw)
        b_ip   = brier(ip)
        ih_p   = mean_p(ih)
        no_ok  = "✓" if b_no <= 0.005 else "✗"

        print(f"  {rho:>3}  {b_ov:>8.4f}  {b_yes:>8.4f}  {b_no:>8.4f}  "
              f"{ih_p:>10.1%}  {b_ih:>9.4f}  {b_ic:>9.4f}  "
              f"{b_vn:>7.4f}  {b_tw:>7.4f}  {b_ip:>7.4f}  {no_ok:>9}")

        if b_no <= 0.005:
            candidates.append({
                "act": act_name, "rho": rho,
                "b_yes": b_yes, "b_no": b_no, "b_overall": b_ov,
                "ih_p": ih_p, "b_ih": b_ih,
                "tagged": tagged,
            })
    print()

# ── activation rate table ─────────────────────────────────────────────────────

print("=== Activation rates by group (soft 0.15 gate) ===")
groups_act = {
    "Iran-HOT"       : [],
    "Iran-COLD"      : [],
    "Venezuela"      : [],
    "China-Taiwan"   : [],
    "India-Pakistan" : [],
}
for r in rows:
    acute_core, _ = extract_signals(r)
    act = activation_soft(acute_core)
    lab = contract_label(r)
    if lab in groups_act:
        groups_act[lab].append(act)

for name, vals in groups_act.items():
    if vals:
        mean_act = sum(vals) / len(vals)
        pct_above_half = sum(1 for v in vals if v > 0.5) / len(vals)
        print(f"  {name:<18}: n={len(vals):>3}  mean_activation={mean_act:.3f}  "
              f"rows>0.5={pct_above_half:.1%}")
print()

# ── live_boost distribution by group (soft gate, rho=3) ──────────────────────

print("=== live_boost distribution by group (soft 0.15 gate, for reference) ===")
group_boosts = defaultdict(list)
for r in rows:
    days = r.get("days_remaining") or r.get("t_minus") or 30
    F = weibull_F(days)
    acute_core, boost_raw = extract_signals(r)
    act = activation_soft(acute_core)
    lb = F * act * boost_raw
    lab = contract_label(r)
    group_boosts[lab].append(lb)

for name, vals in group_boosts.items():
    if vals:
        svals = sorted(vals)
        p95 = svals[int(0.95*len(vals))]
        print(f"  {name:<18}: mean={sum(vals)/len(vals):+.4f}  p95={p95:+.4f}")
print()

# ── best candidate detail ─────────────────────────────────────────────────────

if candidates:
    best = max(candidates, key=lambda x: -x["b_yes"])
    print(f"=== Best candidate: activation={best['act']}  rho={best['rho']} ===")
    print(f"    Overall={best['b_overall']:.4f}  YES={best['b_yes']:.4f}  "
          f"NO={best['b_no']:.4f}  Iran-HOT avg p={best['ih_p']:.1%}")
    print()
    print("    Iran HOT row detail:")
    print(f"    {'date':<14} {'days':>5}  {'p_base':>8}  {'p_new':>8}  "
          f"{'market':>8}  {'res':>4}  {'acute':>7}  {'boost':>8}  {'act':>6}")
    iran_hot_rows = sorted(
        [r for r in best["tagged"] if r["label"]=="Iran-HOT"],
        key=lambda x: x.get("snapshot_date") or x.get("date") or ""
    )
    for r in iran_hot_rows:
        d = r.get("snapshot_date") or r.get("date") or "?"
        days = r.get("days_remaining") or r.get("t_minus") or 30
        F = weibull_F(days)
        acute_core, boost_raw = extract_signals(r)
        act = activation_soft(acute_core)
        lb = F * act * boost_raw
        print(f"    {str(d):<14} {days:>5}  "
              f"{r.get('engine_p',0):>8.1%}  {r['p_new']:>8.1%}  "
              f"{r.get('market_p',0):>8.1%}  {r['resolution']:>4}  "
              f"{acute_core:>7.4f}  {lb:>8.4f}  {act:>6.3f}")
    print()
    print("    Venezuela pre-resolution row summary:")
    ven_rows = [r for r in best["tagged"] if r["label"]=="Venezuela"]
    if ven_rows:
        print(f"    n={len(ven_rows)}  avg p_new={mean_p(ven_rows):.1%}  "
              f"Brier={brier(ven_rows):.4f}")
    print()
    print("    China-Taiwan summary:")
    tw_rows = [r for r in best["tagged"] if r["label"]=="China-Taiwan"]
    if tw_rows:
        print(f"    n={len(tw_rows)}  avg p_new={mean_p(tw_rows):.1%}  "
              f"Brier={brier(tw_rows):.4f}")
else:
    print("No candidates passed NO <= 0.005. Inspect table above — may need to relax constraint.")

"""
retro_sim_18c.py  —  ICB transport simulator with true OP/RMP split gate
Uses Run 18 backtest_results.json which has OperationalPreparation and
RoutineMilitaryPressure stored as separate keys.

Run from ~/predictioneering/:
    python3.11 retro_sim_18c.py
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
    """ICB violent-response CDF. A=0: treat every snapshot as fresh trigger."""
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
    if dyad == "US-Venezuela":   return "Venezuela"
    if dyad == "China-Taiwan":   return "China-Taiwan"
    if dyad == "India-Pakistan": return "India-Pakistan"
    return "Other"

# ── signal extraction using split keys ───────────────────────────────────────

def extract(r):
    qc  = r.get("q_components", {})
    op  = qc.get("OperationalPreparation", 0)   # already shrinkage-weighted (×0.80)
    rmp = qc.get("RoutineMilitaryPressure", 0)   # already shrinkage-weighted (×0.20)
    vio = qc.get("LiveViolenceObserved",    0)
    ult = qc.get("LiveUltimatumDeadline",   0)
    abt = abs(qc.get("LiveAbatementSignal", 0))

    # acute_core: pure operational signals only — the gate variable
    acute_core = op + vio + ult

    # boost_raw: full live signal including weak routine component
    boost_raw  = op + vio + ult + 0.10 * rmp - abt

    return acute_core, boost_raw

# ── activation functions ──────────────────────────────────────────────────────

def act_none(ac):   return 1.0
def act_soft(ac, center=0.08, scale=0.04):
    return sigmoid((ac - center) / scale)
def act_hard(ac, thresh=0.08):
    return 1.0 if ac >= thresh else 0.0
def act_soft_hi(ac, center=0.12, scale=0.04):
    return sigmoid((ac - center) / scale)
def act_hard_hi(ac, thresh=0.12):
    return 1.0 if ac >= thresh else 0.0

ACTIVATION_MODES = {
    "none"         : act_none,
    "soft(0.08)"   : act_soft,
    "hard(0.08)"   : act_hard,
    "soft(0.12)"   : act_soft_hi,
    "hard(0.12)"   : act_hard_hi,
}

RHO_GRID = [1, 2, 3, 4, 5, 6]

# ── main grid ─────────────────────────────────────────────────────────────────

candidates = []  # (act_name, rho, tagged) passing NO constraint

for act_name, act_fn in ACTIVATION_MODES.items():
    print(f"=== Activation: {act_name} ===")
    print(f"  {'rho':>3}  {'Overall':>8}  {'YES':>8}  {'NO':>8}  "
          f"{'IranHOT-p':>10}  {'IranHOT-B':>9}  {'IranCLD-B':>9}  "
          f"{'Ven-B':>7}  {'TW-B':>7}  {'IP-B':>7}  {'NO<=.004':>9}")
    print("  " + "-"*97)

    for rho in RHO_GRID:
        tagged = []
        for r in rows:
            p_base = r.get("engine_p", 0.05)
            days   = r.get("days_remaining") or r.get("t_minus") or 30
            F      = weibull_F(days)
            ac, boost_raw = extract(r)
            act    = act_fn(ac)
            boost  = F * act * boost_raw
            p_new  = sigmoid(logit(p_base) + rho * boost)
            tagged.append({**r,
                "p_new": p_new, "label": label(r),
                "boost": boost, "acute_core": ac, "act": act})

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
        no_ok = "✓" if b_no <= 0.004 else "✗"

        print(f"  {rho:>3}  {b_ov:>8.4f}  {b_yes:>8.4f}  {b_no:>8.4f}  "
              f"{ih_p:>10.1%}  {b_ih:>9.4f}  {b_ic:>9.4f}  "
              f"{b_vn:>7.4f}  {b_tw:>7.4f}  {b_ip:>7.4f}  {no_ok:>9}")

        if b_no <= 0.004:
            candidates.append((act_name, rho, b_yes, b_no, b_ov, ih_p, tagged))
    print()

# ── activation rate table (soft 0.08) ────────────────────────────────────────

print("=== Activation rates by group (soft 0.08 gate on OP-based acute_core) ===")
group_acts = defaultdict(list)
for r in rows:
    ac, _ = extract(r)
    act   = act_soft(ac)
    group_acts[label(r)].append(act)

for name, vals in sorted(group_acts.items()):
    mean_act = sum(vals) / len(vals)
    pct_hi   = sum(1 for v in vals if v > 0.5) / len(vals)
    print(f"  {name:<18}: n={len(vals):>3}  mean_act={mean_act:.3f}  rows>0.5={pct_hi:.1%}")
print()

# ── boost distribution by group ───────────────────────────────────────────────

print("=== live_boost distribution by group (soft 0.08 gate) ===")
group_boosts = defaultdict(list)
for r in rows:
    days = r.get("days_remaining") or r.get("t_minus") or 30
    F    = weibull_F(days)
    ac, boost_raw = extract(r)
    act  = act_soft(ac)
    lb   = F * act * boost_raw
    group_boosts[label(r)].append(lb)

for name, vals in sorted(group_boosts.items()):
    svals = sorted(vals)
    p95   = svals[int(0.95 * len(vals))]
    print(f"  {name:<18}: mean={sum(vals)/len(vals):+.4f}  p95={p95:+.4f}")
print()

# ── best candidate detail ─────────────────────────────────────────────────────

if candidates:
    # best = lowest YES Brier subject to NO <= 0.004
    best = min(candidates, key=lambda x: x[2])
    act_name, rho, b_yes, b_no, b_ov, ih_p, tagged = best

    print(f"=== Best candidate: activation={act_name}  rho={rho} ===")
    print(f"    Overall={b_ov:.4f}  YES={b_yes:.4f}  NO={b_no:.4f}  "
          f"Iran-HOT avg p={ih_p:.1%}")
    print()

    print("    Iran HOT row detail:")
    print(f"    {'date':<14} {'days':>5}  {'p_base':>8}  {'p_new':>8}  "
          f"{'market':>8}  {'res':>4}  {'OP':>7}  {'ac':>7}  {'boost':>8}  {'act':>6}")
    iran_hot = sorted(
        [r for r in tagged if r["label"] == "Iran-HOT"],
        key=lambda x: x.get("snapshot_date") or x.get("date") or ""
    )
    for r in iran_hot:
        d    = r.get("snapshot_date") or r.get("date") or "?"
        days = r.get("days_remaining") or r.get("t_minus") or 30
        F    = weibull_F(days)
        ac, boost_raw = extract(r)
        act  = act_soft(ac)
        lb   = F * act * boost_raw
        op   = r.get("q_components", {}).get("OperationalPreparation", 0)
        print(f"    {str(d):<14} {days:>5}  "
              f"{r.get('engine_p',0):>8.1%}  {r['p_new']:>8.1%}  "
              f"{r.get('market_p',0):>8.1%}  {r['resolution']:>4}  "
              f"{op:>7.4f}  {ac:>7.4f}  {lb:>8.4f}  {act:>6.3f}")

    print()
    print("    Venezuela summary:")
    vn = [r for r in tagged if r["label"] == "Venezuela"]
    print(f"    n={len(vn)}  avg p_new={mean_p(vn):.1%}  Brier={brier(vn):.4f}")

    print()
    print("    China-Taiwan summary:")
    tw = [r for r in tagged if r["label"] == "China-Taiwan"]
    print(f"    n={len(tw)}  avg p_new={mean_p(tw):.1%}  Brier={brier(tw):.4f}")

    print()
    print("    India-Pakistan summary:")
    ip = [r for r in tagged if r["label"] == "India-Pakistan"]
    print(f"    n={len(ip)}  avg p_new={mean_p(ip):.1%}  Brier={brier(ip):.4f}")

else:
    print("No candidates passed NO <= 0.004.")
    print("Relax constraint or inspect activation rates above.")

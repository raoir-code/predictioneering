"""
patch_19_icb_transport.py  —  ICB Weibull transport with crisis_onset_date gate
Run from ~/predictioneering/:
    python3.11 patch_19_icb_transport.py

What this patch does:
  1. Adds crisis_onset_date, acute_phase_onset_date, event_date to dyad_configs.json
     for US-Iran and US-Venezuela.
  2. Adds weibull_residual() helper to backtest.py.
  3. Replaces the output layer (lines 847-853) with:
       - Keep existing horizon-scaled SSPE formula as p_base (unchanged for quiet dyads)
       - If crisis_onset_date defined and snapshot >= onset:
           compute A from acute_phase_onset (or crisis_onset)
           compute F = weibull_residual(A, days_remaining)
           compute acute_core from OP + LiveViolence + LiveUltimatum + MobilizationSignal
           apply live_boost = F * max(0, acute_core - LiveAbatementSignal)
           engine_p = sigmoid(logit(p_base) + RHO * live_boost)
       - Otherwise: engine_p = p_base (no change from Run 18)
  4. Adds post-resolution row stripping: rows after event_date are excluded from
     Brier scoring (engine_p stored but b_engine set to None).

NO changes to:
  - Node scoring prompts (Call A / Call B)
  - SSPE formula / predict_probability()
  - Q_SHRINKAGE / HALF_LIFE_DAYS
  - Z_t=2 exclusion logic
  - Contamination check
  - Taiwan / India-Pakistan output (no onset dates -> no change)

RHO = 3.0  (validated in retro_sim_18d; matches Iran HOT market avg at 49% vs 47.6%)
"""

import json, re
from pathlib import Path

ROOT   = Path(".")
PATCH  = "patch_19_icb_transport"
TARGET = ROOT / "pipeline" / "backtest.py"
CONFIG = ROOT / "pipeline" / "dyad_configs.json"

# ── 19-CONFIG: add onset/event dates to dyad_configs.json ────────────────────

with open(CONFIG) as f:
    cfg = json.load(f)

assert "US-Iran" in cfg,      f"[{PATCH}] US-Iran not found in dyad_configs.json"
assert "US-Venezuela" in cfg, f"[{PATCH}] US-Venezuela not found in dyad_configs.json"

# Only add if not already present (idempotent)
iran_dates = {
    "crisis_onset_date":       "2025-11-01",   # ICB-codable breakpoint: nuclear deadline pressure
    "acute_phase_onset_date":  "2026-01-20",   # HOT window: operational strike posture
    "event_date":              None,            # Iran: no pre-deadline resolution
}
ven_dates = {
    "crisis_onset_date":       "2025-11-15",   # ICB-codable: carrier + 15k troops deployed
    "acute_phase_onset_date":  "2025-12-13",   # Acute: blockade + oil cutoff operational
    "event_date":              "2026-01-03",   # Operation Absolute Resolve — strip post-res rows
}

for key, val in iran_dates.items():
    if key not in cfg["US-Iran"]:
        cfg["US-Iran"][key] = val

for key, val in ven_dates.items():
    if key not in cfg["US-Venezuela"]:
        cfg["US-Venezuela"][key] = val

with open(CONFIG, "w") as f:
    json.dump(cfg, f, indent=2)

print(f"applied: Patch 19-CONFIG — crisis/acute/event dates added to dyad_configs.json")
print(f"  US-Iran:      crisis={cfg['US-Iran']['crisis_onset_date']}  "
      f"acute={cfg['US-Iran']['acute_phase_onset_date']}  "
      f"event={cfg['US-Iran']['event_date']}")
print(f"  US-Venezuela: crisis={cfg['US-Venezuela']['crisis_onset_date']}  "
      f"acute={cfg['US-Venezuela']['acute_phase_onset_date']}  "
      f"event={cfg['US-Venezuela']['event_date']}")

# ── load backtest.py ──────────────────────────────────────────────────────────

with open(TARGET) as f:
    src = f.read()
original = src

# ── 19A: add imports (datetime) if not present ────────────────────────────────

if "from datetime import" not in src and "import datetime" not in src:
    OLD_19A = "import json"
    NEW_19A = "import json\nfrom datetime import date, datetime as _dt"
    assert OLD_19A in src, f"[{PATCH}] 19A: 'import json' not found"
    src = src.replace(OLD_19A, NEW_19A, 1)
    print(f"applied: Patch 19A — added datetime import")
else:
    print(f"skipped: Patch 19A — datetime already imported")

# ── 19B: add weibull_residual() and RHO constant after existing imports/consts ─
# Insert after the DECAY_FACTOR block (which references HALF_LIFE_DAYS)

WEIBULL_BLOCK = '''
# ── ICB Weibull transport (Patch 19) ─────────────────────────────────────────
ICB_TRANSPORT_RHO = 3.0   # logit boost strength; validated in retro_sim_18d

def _weibull_residual(A, D, scale=14.2, shape=0.65):
    """
    Residual ICB violent-response CDF.
    P(violence within next D days | no violence in first A days of acute episode).
    Derived from ICB2 TRGRESRA actor-level timing distribution.
    scale=14.2, shape=0.65 fit to empirical CDF:
      F(7)≈0.47, F(14)≈0.63, F(39)≈0.85, F(90)≈0.95
    """
    import math
    FA  = 1 - math.exp(-((max(A, 0) / scale) ** shape))
    FAD = 1 - math.exp(-((max(A + D, 0) / scale) ** shape))
    denom = 1 - FA
    if denom < 1e-9:
        return 1.0
    return (FAD - FA) / denom

def _parse_date(s):
    """Parse YYYY-MM-DD string to date, return None if falsy."""
    if not s:
        return None
    return _dt.strptime(s, "%Y-%m-%d").date()

def _icb_transport(engine_p_base, days_remaining, q_components, dyad_meta):
    """
    Apply ICB Weibull logit boost if crisis_onset_date is defined and active.
    Returns (engine_p_final, icb_boost_applied).
    dyad_meta: dict from dyad_configs.json for this dyad (may be None).
    """
    import math
    if not dyad_meta:
        return engine_p_base, 0.0

    crisis_onset = _parse_date(dyad_meta.get("crisis_onset_date"))
    acute_onset  = _parse_date(dyad_meta.get("acute_phase_onset_date"))

    if crisis_onset is None:
        return engine_p_base, 0.0  # no episode gate defined

    # snapshot_date not directly available here; caller passes days_remaining
    # and computes A externally. This function takes pre-computed A.
    return engine_p_base, 0.0   # placeholder; actual call done inline in loop

# ── end ICB transport helpers ─────────────────────────────────────────────────
'''

# Insert after DECAY_FACTOR definition
DECAY_ANCHOR = "DECAY_FACTOR = {k: 0.5 ** (1 / v) if v else 1.0"
assert DECAY_ANCHOR in src, f"[{PATCH}] 19B: DECAY_FACTOR anchor not found"
# Find the end of the DECAY_FACTOR dict comprehension line
decay_line_end = src.index(DECAY_ANCHOR)
decay_line_end = src.index("\n", decay_line_end) + 1  # end of that line

src = src[:decay_line_end] + WEIBULL_BLOCK + src[decay_line_end:]
print(f"applied: Patch 19B — weibull_residual helper and RHO constant added")

# ── 19C: load crisis dates from dyad_configs when loading dyad metadata ───────
# The existing code loads dyad_configs.json in load_sspe_priors().
# We need crisis dates available inside the main backtest loop.
# Strategy: load them once at market/dyad level from the already-loaded config.

# Find where the dyad loop reads crisis_context from config
OLD_19C = '''    config_path = ROOT / "pipeline" / "dyad_configs.json"'''

# There are two occurrences; we want the one inside the main scoring loop (line ~656)
# Use the second occurrence
occurrences = [i for i in range(len(src)) if src[i:i+len(OLD_19C)] == OLD_19C]
assert len(occurrences) >= 2, f"[{PATCH}] 19C: expected >= 2 occurrences of config_path line"

# The second occurrence is inside the main loop
second_occ = occurrences[1]
# Find the block that reads crisis_context — look for _crisis_ctx assignment near this
ctx_anchor = src.index("_crisis_ctx = ", second_occ - 500)

# Find the line that reads crisis_context and add dyad_meta loading after it
OLD_19C_CTX = '    _crisis_ctx = dyad_cfg.get("crisis_context", "") if dyad_cfg else ""'
NEW_19C_CTX = ('    _crisis_ctx = dyad_cfg.get("crisis_context", "") if dyad_cfg else ""\n'
               '    _dyad_meta  = dyad_cfg if dyad_cfg else None  # for ICB transport')

assert OLD_19C_CTX in src, f"[{PATCH}] 19C: crisis_context line not found"
src = src.replace(OLD_19C_CTX, NEW_19C_CTX, 1)
print(f"applied: Patch 19C — _dyad_meta loaded from dyad_cfg")

# ── 19D: replace output formula (the core patch) ──────────────────────────────
# Target block (lines 847-853 in original):
#   engine_p_raw = predict_probability(toggles, days_remaining, q_logit=q_logit)
#   # Horizon scaling: ...
#   horizon_scale = max(days_remaining, 1) / market_window
#   engine_p_scaled = 1 - (1 - engine_p_raw) ** horizon_scale
#   engine_p = round(1 - engine_p_scaled, 4) if z_t == 2 else round(engine_p_scaled, 4)

OLD_19D = (
    "            engine_p_raw = predict_probability(toggles, days_remaining, q_logit=q_logit)\n"
    "            # Horizon scaling: convert 90-day probability to days_remaining probability.\n"
    "            # p_contract = 1 - (1-p_90)^(days_remaining/90)\n"
    "\n"
    "            horizon_scale = max(days_remaining, 1) / market_window\n"
    "            engine_p_scaled = 1 - (1 - engine_p_raw) ** horizon_scale\n"
    "            engine_p = round(1 - engine_p_scaled, 4) if z_t == 2 else round(engine_p_scaled, 4)"
)

NEW_19D = (
    "            engine_p_raw = predict_probability(toggles, days_remaining, q_logit=q_logit)\n"
    "            # Horizon scaling: convert raw probability to days_remaining probability.\n"
    "            # Applied to SSPE structural prior only — NOT to live acute signals.\n"
    "            horizon_scale = max(days_remaining, 1) / market_window\n"
    "            engine_p_scaled = 1 - (1 - engine_p_raw) ** horizon_scale\n"
    "            engine_p_base = round(1 - engine_p_scaled, 4) if z_t == 2 else round(engine_p_scaled, 4)\n"
    "\n"
    "            # ── ICB Weibull transport (Patch 19) ──────────────────────────\n"
    "            # Apply live acute logit boost gated by crisis_onset_date.\n"
    "            # Taiwan/India-Pakistan: no onset date -> no boost -> unchanged.\n"
    "            # Iran/Venezuela: onset date + acute clock -> Weibull residual CDF.\n"
    "            import math as _math\n"
    "            _crisis_onset = _parse_date(_dyad_meta.get('crisis_onset_date') if _dyad_meta else None)\n"
    "            _acute_onset  = _parse_date(_dyad_meta.get('acute_phase_onset_date') if _dyad_meta else None)\n"
    "            _event_date   = _parse_date(_dyad_meta.get('event_date') if _dyad_meta else None)\n"
    "\n"
    "            _icb_boost = 0.0\n"
    "            if _crisis_onset and snapshot_date >= _crisis_onset:\n"
    "                _clock = _acute_onset if (_acute_onset and snapshot_date >= _acute_onset) else _crisis_onset\n"
    "                _A = max((_clock and (snapshot_date - _clock).days) or 0, 0)\n"
    "                _D = max(days_remaining, 0)\n"
    "                _F = _weibull_residual(_A, _D)\n"
    "                _qc = q_components\n"
    "                _acute_core = (\n"
    "                    _qc.get('OperationalPreparation', 0)\n"
    "                  + _qc.get('LiveViolenceObserved',   0)\n"
    "                  + _qc.get('LiveUltimatumDeadline',  0)\n"
    "                  + _qc.get('MobilizationSignal',     0)\n"
    "                )\n"
    "                _abatement = abs(_qc.get('LiveAbatementSignal', 0))\n"
    "                _live_boost = _F * max(0.0, _acute_core - _abatement)\n"
    "                _icb_boost  = ICB_TRANSPORT_RHO * _live_boost\n"
    "                _base_logit = _math.log(max(engine_p_base, 1e-6) / max(1 - engine_p_base, 1e-6))\n"
    "                engine_p = round(1 / (1 + _math.exp(-(_base_logit + _icb_boost))), 4)\n"
    "            else:\n"
    "                engine_p = engine_p_base\n"
    "            # ── end ICB transport ──────────────────────────────────────────"
)

assert OLD_19D in src, f"[{PATCH}] 19D: output formula block not found — check line numbers"
src = src.replace(OLD_19D, NEW_19D, 1)
print(f"applied: Patch 19D — ICB Weibull transport in output layer")

# ── 19E: post-resolution row stripping ────────────────────────────────────────
# After engine_p is computed, if event_date is set and snapshot >= event_date,
# set b_engine = None so the row is stored but excluded from Brier scoring.

OLD_19E = "            b_engine = (engine_p - resolution)**2 if resolution is not None else None"
NEW_19E = (
    "            # Post-resolution stripping: exclude rows after event_date from Brier\n"
    "            _post_resolution = (_event_date is not None and snapshot_date >= _event_date)\n"
    "            b_engine = None if _post_resolution else (\n"
    "                (engine_p - resolution)**2 if resolution is not None else None\n"
    "            )"
)

assert OLD_19E in src, f"[{PATCH}] 19E: b_engine line not found"
src = src.replace(OLD_19E, NEW_19E, 1)
print(f"applied: Patch 19E — post-resolution row stripping via event_date")

# ── 19F: store icb_boost and event_date flag in output row ───────────────────
OLD_19F = '                "q_full":        round(q_full, 4),'
NEW_19F = ('                "q_full":        round(q_full, 4),\n'
           '                "icb_boost":     round(_icb_boost, 4),\n'
           '                "post_res":      _post_resolution,')

assert OLD_19F in src, f"[{PATCH}] 19F: q_full storage line not found"
src = src.replace(OLD_19F, NEW_19F, 1)
print(f"applied: Patch 19F — icb_boost and post_res stored in output rows")

# ── safety asserts ────────────────────────────────────────────────────────────
assert "ICB_TRANSPORT_RHO = 3.0" in src,        f"[{PATCH}] RHO not found"
assert "_weibull_residual" in src,               f"[{PATCH}] weibull_residual not found"
assert "_crisis_onset" in src,                   f"[{PATCH}] crisis_onset logic not found"
assert "_post_resolution" in src,                f"[{PATCH}] post_resolution logic not found"
assert "_icb_boost" in src,                      f"[{PATCH}] icb_boost not found"
assert src != original,                          f"[{PATCH}] no changes made"
print(f"assert: all safety checks passed ✓")

# ── write ─────────────────────────────────────────────────────────────────────
with open(TARGET, "w") as f:
    f.write(src)

print(f"\nAll patches applied. Run:")
print(f"  python3.11 -m py_compile pipeline/backtest.py && echo OK")
print(f"  grep -n 'ICB_TRANSPORT_RHO\\|_weibull_residual\\|_crisis_onset\\|_post_resolution' pipeline/backtest.py | head -20")

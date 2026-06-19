#!/usr/bin/env python3.11
"""
Patches 11, 12, 13 for pipeline/backtest.py
Provenance: June 18 2026 evening session.
"""

import re

PATCH_FILE = "pipeline/backtest.py"

with open(PATCH_FILE, "r") as f:
    src = f.read()

original_src = src

# ── PATCH 11 ── Fix +sign parse error ─────────────────────────────────────────
OLD_11 = '        lo, hi = t.find("{"), t.rfind("}")'
NEW_11 = '        lo, hi = t.find("{"), t.rfind("}")\n        if lo != -1 and hi != -1:\n            t = t[lo:hi+1]\n        t = re.sub(r\':\\s*\\+(\\d)\', r\': \\1\', t)  # Patch 11: strip leading + from numerics'

assert OLD_11 in src, f"PATCH 11 FAILED: target string not found"
src = src.replace(OLD_11, NEW_11, 1)
print("applied: Patch 11 — +sign parse fix")

# ── PATCH 12 ── Drop peacetime intercept, Q0 anchor, 0.25*SSPE ────────────────
OLD_12 = '''        p_window_base = 1 - (1 - BASE_RATE_ANNUAL) ** (days_remaining / 365)
        base_window_log_odds = math.log(p_window_base / (1 - p_window_base))
        log_odds_shift = WarPayoff + WarPolitics + HardlineDirect + q_logit
        final_log_odds = base_window_log_odds + log_odds_shift'''

NEW_12 = '''        # Patch 12: Drop peacetime intercept entirely.
        # Q0 = -3.407 inside q_logit is the sole anchor (crisis-conditioned ICB intercept).
        # SSPE deviations shrunk by rho=0.25 — signs transport, magnitudes uncertain.
        # Formula: engine_p = sigmoid(Q0 + ICB_features + 0.25 * SSPE_deviations)
        SSPE_SHRINKAGE = 0.25
        sspe_deviations = WarPayoff + WarPolitics + HardlineDirect
        log_odds_shift = q_logit + SSPE_SHRINKAGE * sspe_deviations
        final_log_odds = log_odds_shift  # no peacetime intercept'''

assert OLD_12 in src, f"PATCH 12 FAILED: target string not found"
src = src.replace(OLD_12, NEW_12, 1)
print("applied: Patch 12 — drop peacetime intercept, Q0 anchor, 0.25*SSPE")

# ── PATCH 13A ── Unified formula + polarity flip ───────────────────────────────
OLD_13 = '''        z_t = DYAD_REGIME.get(dyad, 0)
        if z_t == 1:
            engine_p = round(q_full, 4)   # crisis regime: q_full IS the probability
        else:
            engine_p = predict_probability(toggles, days_remaining, q_logit=q_logit)'''

NEW_13 = '''        z_t = DYAD_REGIME.get(dyad, 0)
        # Patch 12/13: unified formula for all dyads
        # engine_p = sigmoid(Q0 + ICB_features + 0.25*SSPE) via predict_probability
        # Patch 13: Z_t=2 gets polarity flip (peace market), not exclusion
        engine_p = predict_probability(toggles, days_remaining, q_logit=q_logit)
        polarity = "violence"
        if z_t == 2:
            engine_p = round(1.0 - engine_p, 4)  # Patch 13: flip for peace/de-escalation
            polarity = "peace"'''

assert OLD_13 in src, f"PATCH 13A FAILED: target string not found"
src = src.replace(OLD_13, NEW_13, 1)
print("applied: Patch 13A — unified formula + polarity flip")

# ── PATCH 13B ── Store diagnostic fields ──────────────────────────────────────
OLD_13B = '                "z_t": z_t'
NEW_13B = '''                "z_t": z_t,
                "polarity": polarity,
                "sspe_raw": round(WarPayoff + WarPolitics + HardlineDirect, 4),
                "q_logit_raw": round(q_logit, 4)'''

assert OLD_13B in src, f"PATCH 13B FAILED: target string not found"
src = src.replace(OLD_13B, NEW_13B, 1)
print("applied: Patch 13B — diagnostic fields stored in results")

# ── PATCH 13C ── Remove Z_t=2 exclusion ───────────────────────────────────────
OLD_13C = '''        resolved  = [r for r in all_resolved if r.get("z_t", 0) != 2]
        excluded2 = [r for r in all_resolved if r.get("z_t", 0) == 2]'''

NEW_13C = '''        resolved  = all_resolved  # Patch 13: Z_t=2 scored with polarity flip, not excluded
        excluded2 = []  # nothing excluded'''

assert OLD_13C in src, f"PATCH 13C FAILED: target string not found"
src = src.replace(OLD_13C, NEW_13C, 1)
print("applied: Patch 13C — Z_t=2 exclusion removed")

# ── Header update ──────────────────────────────────────────────────────────────
OLD_HDR = 'BACKTEST RESULTS — Mach 3 (regime-switched)'
NEW_HDR = 'BACKTEST RESULTS — Mach 3.1 (unified formula, polarity flip)'
if OLD_HDR in src:
    src = src.replace(OLD_HDR, NEW_HDR, 1)
    print("applied: header → Mach 3.1")

# ── Ensure re is imported ──────────────────────────────────────────────────────
if 'import re' not in src:
    src = 'import re\n' + src
    print("applied: added import re")

# ── Write ──────────────────────────────────────────────────────────────────────
assert src != original_src, "FATAL: no changes made to file"
with open(PATCH_FILE, "w") as f:
    f.write(src)

print("\nAll patches applied successfully.")

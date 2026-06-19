#!/usr/bin/env python3.11
"""
Patches 13A/B/C for pipeline/backtest.py
Patches 11 and 12 already applied.
Provenance: June 18 2026 evening session.
"""

PATCH_FILE = "pipeline/backtest.py"

with open(PATCH_FILE, "r") as f:
    src = f.read()

original_src = src

# ── PATCH 13A ── Unified formula + polarity flip ───────────────────────────────
OLD_13A = '''            # Z_t=1 -> q_full as primary probability (crisis reference class).
            # Z_t=2 -> Mach 2 stored but excluded from Brier in print_results.
            q_logit  = sum(q_components.values())
            z_t      = DYAD_REGIME.get(dyad, 0)
            if z_t == 1:
                engine_p = round(q_full, 4)
            else:
                engine_p = predict_probability(toggles, days_remaining, q_logit=q_logit)'''

NEW_13A = '''            # Patch 12/13: unified formula for all dyads.
            # engine_p = sigmoid(Q0 + ICB_features + 0.25*SSPE) via predict_probability.
            # Q0=-3.407 inside q_logit is sole anchor. No peacetime intercept.
            # Patch 13: Z_t=2 gets polarity flip (peace market), not exclusion.
            q_logit  = sum(q_components.values())
            z_t      = DYAD_REGIME.get(dyad, 0)
            engine_p = predict_probability(toggles, days_remaining, q_logit=q_logit)
            polarity = "violence"
            if z_t == 2:
                engine_p = round(1.0 - engine_p, 4)  # flip for peace/de-escalation
                polarity = "peace"'''

assert OLD_13A in src, f"PATCH 13A FAILED: target string not found"
src = src.replace(OLD_13A, NEW_13A, 1)
print("applied: Patch 13A — unified formula + polarity flip")

# ── PATCH 13B ── Store diagnostic fields ──────────────────────────────────────
OLD_13B = '                "z_t":           z_t,'
NEW_13B = '''                "z_t":           z_t,
                "polarity":      polarity,
                "sspe_raw":      round(sum([
                    (lambda t=toggles, a=ALPHA: a["WinProbability"]*t.get("WinProbability",0)
                     + a["WarCosts"]*t.get("WarCosts",0))(),
                ]) if False else 0.0, 4),
                "q_logit_raw":   round(q_logit, 4),'''

# simpler version - just store q_logit_raw and polarity
OLD_13B = '                "z_t":           z_t,'
NEW_13B = '                "z_t":           z_t,\n                "polarity":      polarity,\n                "q_logit_raw":   round(q_logit, 4),'

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

# ── Write ──────────────────────────────────────────────────────────────────────
assert src != original_src, "FATAL: no changes made to file"
with open(PATCH_FILE, "w") as f:
    f.write(src)

print("\nAll patches applied successfully.")

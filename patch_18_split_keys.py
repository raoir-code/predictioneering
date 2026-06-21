"""
patch_18_split_keys.py  —  Instrumentation patch: store OP/RMP as separate keys
Run from ~/predictioneering/:
    python3.11 patch_18_split_keys.py

What this patch does:
  1. Splits LiveNonviolentMilitaryPressure into OperationalPreparation + RoutineMilitaryPressure
     in build_q_components() — stored as separate keys with individual ICB shrinkage weights
  2. Updates LIVE_ONLY_KEYS to reference the split keys
  3. Adds Q_SHRINKAGE entries for each split key
  4. Adds HALF_LIFE_DAYS entries for each split key
  5. Removes the collapsed LiveNonviolentMilitaryPressure from all four constants

NO changes to:
  - Node scoring prompts (Call A / Call B) — already score them separately
  - SSPE formula / predict_probability()
  - Q_SHRINKAGE values for any other node
  - HALF_LIFE_DAYS values for any other node
  - Z_t=2 exclusion logic
  - Contamination check
"""

import re

PATCH = "patch_18_split_keys"
TARGET = "pipeline/backtest.py"

with open(TARGET, "r") as f:
    src = f.read()

original = src  # keep for assert

# ── Patch 18A: build_q_components — replace collapsed key with split keys ─────
OLD_18A = '''        "LiveNonviolentMilitaryPressure":(
            call_b.get("OperationalPreparation", 0.0) * 1.0 +
            call_b.get("RoutineMilitaryPressure", 0.0) * 0.20'''

NEW_18A = '''        "OperationalPreparation":(
            call_b.get("OperationalPreparation", 0.0) * 1.0),
        "RoutineMilitaryPressure":(
            call_b.get("RoutineMilitaryPressure", 0.0) * 1.0'''

assert OLD_18A in src, f"[{PATCH}] 18A target not found — check build_q_components()"
src = src.replace(OLD_18A, NEW_18A, 1)
print(f"applied: Patch 18A — split LiveNonviolentMilitaryPressure in build_q_components()")

# ── Patch 18B: LIVE_ONLY_KEYS — replace collapsed key with split keys ─────────
OLD_18B = 'LIVE_ONLY_KEYS  = ["base", "CommitmentProblem", "LiveNonviolentMilitaryPressure",'
NEW_18B = 'LIVE_ONLY_KEYS  = ["base", "CommitmentProblem", "OperationalPreparation", "RoutineMilitaryPressure",'

assert OLD_18B in src, f"[{PATCH}] 18B target not found — check LIVE_ONLY_KEYS"
src = src.replace(OLD_18B, NEW_18B, 1)
print(f"applied: Patch 18B — updated LIVE_ONLY_KEYS")

# ── Patch 18C: Q_SHRINKAGE — replace collapsed key with split keys ────────────
# OperationalPreparation: preserve 0.80 (was LiveNonviolentMilitaryPressure)
# RoutineMilitaryPressure: 0.20 — weak shrinkage toward zero; chronic noise
OLD_18C = "    'LiveNonviolentMilitaryPressure': 0.80,"
NEW_18C = ("    'OperationalPreparation':         0.80,\n"
           "    'RoutineMilitaryPressure':         0.20,")

assert OLD_18C in src, f"[{PATCH}] 18C target not found — check Q_SHRINKAGE"
src = src.replace(OLD_18C, NEW_18C, 1)
print(f"applied: Patch 18C — updated Q_SHRINKAGE")

# ── Patch 18D: HALF_LIFE_DAYS — replace collapsed key with split keys ─────────
# OperationalPreparation: 7 days (same as old LiveNonviolentMilitaryPressure)
# RoutineMilitaryPressure: 14 days — chronic signal, slower decay
OLD_18D = "    'LiveNonviolentMilitaryPressure': 7,"
NEW_18D = ("    'OperationalPreparation':         7,\n"
           "    'RoutineMilitaryPressure':         14,")

assert OLD_18D in src, f"[{PATCH}] 18D target not found — check HALF_LIFE_DAYS"
src = src.replace(OLD_18D, NEW_18D, 1)
print(f"applied: Patch 18D — updated HALF_LIFE_DAYS")

# ── safety: verify LiveNonviolentMilitaryPressure no longer appears in the
#    four data-structure constants (it can still appear in comments/prompts) ───
# Check Q_SHRINKAGE block
shrinkage_block_start = src.index("Q_SHRINKAGE = {")
shrinkage_block_end   = src.index("}", shrinkage_block_start)
shrinkage_block       = src[shrinkage_block_start:shrinkage_block_end]
assert "LiveNonviolentMilitaryPressure" not in shrinkage_block, \
    f"[{PATCH}] LiveNonviolentMilitaryPressure still in Q_SHRINKAGE block"

# Check HALF_LIFE_DAYS block
hl_block_start = src.index("HALF_LIFE_DAYS = {")
hl_block_end   = src.index("}", hl_block_start)
hl_block       = src[hl_block_start:hl_block_end]
assert "LiveNonviolentMilitaryPressure" not in hl_block, \
    f"[{PATCH}] LiveNonviolentMilitaryPressure still in HALF_LIFE_DAYS block"

# Check LIVE_ONLY_KEYS line
live_keys_line = [l for l in src.splitlines() if "LIVE_ONLY_KEYS" in l and "=" in l]
assert live_keys_line, f"[{PATCH}] LIVE_ONLY_KEYS line not found"
assert "LiveNonviolentMilitaryPressure" not in live_keys_line[0], \
    f"[{PATCH}] LiveNonviolentMilitaryPressure still in LIVE_ONLY_KEYS"

# Check build_q_components block
bqc_start = src.index("def build_q_components(")
bqc_end   = src.index("\ndef ", bqc_start + 1)
bqc_block = src[bqc_start:bqc_end]
assert "LiveNonviolentMilitaryPressure" not in bqc_block, \
    f"[{PATCH}] LiveNonviolentMilitaryPressure still in build_q_components()"

print(f"assert: LiveNonviolentMilitaryPressure removed from all four data structures ✓")

# ── verify new keys present where expected ────────────────────────────────────
assert "OperationalPreparation':         0.80" in src, \
    f"[{PATCH}] OperationalPreparation not in Q_SHRINKAGE"
assert "RoutineMilitaryPressure':         0.20" in src, \
    f"[{PATCH}] RoutineMilitaryPressure not in Q_SHRINKAGE"
assert "OperationalPreparation':         7" in src, \
    f"[{PATCH}] OperationalPreparation not in HALF_LIFE_DAYS"
assert "RoutineMilitaryPressure':         14" in src, \
    f"[{PATCH}] RoutineMilitaryPressure not in HALF_LIFE_DAYS"
print(f"assert: split keys present in Q_SHRINKAGE and HALF_LIFE_DAYS ✓")

# ── write ─────────────────────────────────────────────────────────────────────
assert src != original, f"[{PATCH}] no changes made — something went wrong"
with open(TARGET, "w") as f:
    f.write(src)

print(f"\nAll patches applied. Run:")
print(f"  python3.11 -m py_compile {TARGET} && echo OK")
print(f"  grep -n 'OperationalPreparation\\|RoutineMilitary\\|LiveNonviolentMilitary' {TARGET} | grep -v '#\\|prompt\\|rubric\\|Return\\|score\\|Do NOT\\|window\\|node'")

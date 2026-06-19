PATCH_FILE = "pipeline/backtest.py"

with open(PATCH_FILE, "r") as f:
    src = f.read()

original_src = src

OLD_13C = '''    resolved  = [r for r in all_resolved if r.get("z_t", 0) != 2]
    excluded2 = [r for r in all_resolved if r.get("z_t", 0) == 2]'''

NEW_13C = '''    resolved  = all_resolved  # Patch 13: Z_t=2 scored with polarity flip, not excluded
    excluded2 = []  # nothing excluded'''

assert OLD_13C in src, f"PATCH 13C FAILED: not found"
src = src.replace(OLD_13C, NEW_13C, 1)
print("applied: Patch 13C — Z_t=2 exclusion removed")

OLD_HDR = 'BACKTEST RESULTS — Mach 3 (regime-switched)'
NEW_HDR = 'BACKTEST RESULTS — Mach 3.1 (unified formula, polarity flip)'
if OLD_HDR in src:
    src = src.replace(OLD_HDR, NEW_HDR, 1)
    print("applied: header → Mach 3.1")

assert src != original_src
with open(PATCH_FILE, "w") as f:
    f.write(src)

print("Done.")

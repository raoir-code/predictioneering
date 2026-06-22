import pathlib

path = pathlib.Path("pipeline/backtest.py")
src  = path.read_text()

OLD = """\
def predict_probability(toggles, days_remaining, q_logit=0.0):"""

assert OLD in src, "ABORT: function signature not found"

OLD2 = """\
    # Mach 3.1: Q0 (ICB crisis-conditioned) is sole anchor; peacetime intercept dropped.
    # SSPE structural deviations at 0.25 shrinkage (signs transport, magnitudes dont).
    SSPE_SHRINKAGE  = 0.25
    sspe_deviations = WarPayoff + WarPolitics + HardlineDirect
    window_log_odds = q_logit + SSPE_SHRINKAGE * sspe_deviations

    p = 1 / (1 + math.exp(-window_log_odds))
    return round(p, 4)"""

NEW2 = """\
    # Run 18: SSPE structural deviations are horizon-scaled here.
    # q_logit already contains the semantic split (structural horizon-scaled,
    # live acute unscaled) — so SSPE deviations get the same treatment:
    # they are chronic baseline signals, not episode-clock evidence.
    SSPE_SHRINKAGE  = 0.25
    horizon = max(days_remaining, 1) / max(days_remaining + 1, 90)
    sspe_deviations = WarPayoff + WarPolitics + HardlineDirect
    window_log_odds = q_logit + SSPE_SHRINKAGE * sspe_deviations * horizon

    p = 1 / (1 + math.exp(-window_log_odds))
    return round(p, 4)"""

assert OLD2 in src, "ABORT: SSPE block not found verbatim"
src = src.replace(OLD2, NEW2, 1)
assert NEW2 in src, "ABORT: Patch 18b did not land"

path.write_text(src)
print("Patch 18b applied — SSPE deviations now horizon-scaled inside predict_probability")
print("Run: python3.11 -m py_compile pipeline/backtest.py && echo OK")

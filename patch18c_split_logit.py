import pathlib

path = pathlib.Path("pipeline/backtest.py")
src  = path.read_text()

# Revert 18b's broken horizon inside predict_probability
OLD_B = """\
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

NEW_B = """\
    # Run 18c: SSPE deviations enter WITHOUT q_logit — returned as raw logit.
    # Caller applies horizon scaling to SSPE component separately.
    SSPE_SHRINKAGE  = 0.25
    sspe_deviations = WarPayoff + WarPolitics + HardlineDirect
    sspe_logit = SSPE_SHRINKAGE * sspe_deviations
    # q_logit injected by caller after horizon split
    window_log_odds = q_logit + sspe_logit
    p = 1 / (1 + math.exp(-window_log_odds))
    return round(p, 4)"""

assert OLD_B in src, "ABORT: 18b block not found"
src = src.replace(OLD_B, NEW_B, 1)
print("Reverted 18b broken horizon inside predict_probability")

# Now fix the call site — split q_logit into sspe_logit (horizon-scaled) + live_logit (not)
OLD_CALL = """\
            engine_p_raw = predict_probability(toggles, days_remaining, q_logit=q_logit)
            # Run 18: horizon scaling now lives inside _q_structural only.
            # Live acute q enters logit at full weight — no post-hoc crush.
            engine_p = round(1 - engine_p_raw, 4) if z_t == 2 else round(engine_p_raw, 4)"""

NEW_CALL = """\
            # Run 18c: two-component logit split.
            # SSPE deviations (chronic baseline) → horizon-scaled before adding.
            # Live acute q (_q_live, _q_trigger) → full weight, no horizon crush.
            # _q_structural already horizon-scaled inside q_logit assembly above.
            _horizon = max(days_remaining, 1) / market_window

            # Pass only live+trigger+structural q to predict_probability (no SSPE yet)
            # Then horizon-scale the SSPE component at the call site
            engine_p_raw_no_sspe = predict_probability(
                {k: 0.0 for k in toggles},  # zero toggles → sspe_logit=0
                days_remaining,
                q_logit=q_logit              # our semantically-split q
            )
            # Get SSPE-only logit by calling with real toggles, q_logit=0
            engine_p_sspe_only = predict_probability(toggles, days_remaining, q_logit=0.0)

            import math as _math
            sspe_logit_raw = _math.log(max(engine_p_sspe_only, 1e-9) /
                                       max(1 - engine_p_sspe_only, 1e-9))
            q_live_logit = _math.log(max(engine_p_raw_no_sspe, 1e-9) /
                                     max(1 - engine_p_raw_no_sspe, 1e-9))

            combined_logit = _horizon * sspe_logit_raw + q_live_logit
            engine_p_raw = 1 / (1 + _math.exp(-combined_logit))
            engine_p = round(1 - engine_p_raw, 4) if z_t == 2 else round(engine_p_raw, 4)"""

assert OLD_CALL in src, "ABORT: call site block not found"
src = src.replace(OLD_CALL, NEW_CALL, 1)
print("Patched call site — SSPE horizon-scaled, live q preserved")

path.write_text(src)
print("Patch 18c written.")
print("Run: python3.11 -m py_compile pipeline/backtest.py && echo OK")

import pathlib

path = pathlib.Path("pipeline/backtest.py")
src  = path.read_text()

# ── ASSERT: exact verbatim strings from sed output ──
assert "            q_logit  = sum(v * Q_SHRINKAGE.get(k, 0.50) for k, v in node_memory.items())" in src, \
    "ABORT: q_logit line not found verbatim"
assert "            horizon_scale = max(days_remaining, 1) / market_window" in src, \
    "ABORT: horizon_scale line not found verbatim"
assert "            engine_p_scaled = 1 - (1 - engine_p_raw) ** horizon_scale" in src, \
    "ABORT: engine_p_scaled line not found verbatim"

print("Assertions passed — patching...")

# ── PATCH A: replace q_logit assembly ──
OLD_A = "            q_logit  = sum(v * Q_SHRINKAGE.get(k, 0.50) for k, v in node_memory.items())"

NEW_A = """\
            # ── Run 18: SSPE-compatible semantic logit assembly ──────────────────
            # ICB base intercept (-3.407) lives in node_memory['base'] — excluded below.
            # Structural/chronic: horizon-scaled (calendar risk, already shrunk toward 0).
            # Trigger/onset: moderate weight, no horizon crush.
            # Live acute: full shrinkage weight, NO horizon crush (episode-clock evidence).
            # Abatement: strong negative, no horizon crush.
            _c = node_memory
            _horizon = max(days_remaining, 1) / market_window

            _q_structural = _horizon * (
                Q_SHRINKAGE.get('GeographicProximity', 0.00)            * _c.get('GeographicProximity', 0.0)
              + Q_SHRINKAGE.get('ProtractedConflict', 0.00)              * _c.get('ProtractedConflict', 0.0)
              + Q_SHRINKAGE.get('ValueThreatGravity', 0.06)              * _c.get('ValueThreatGravity', 0.0)
              + Q_SHRINKAGE.get('ThirdPartyMilitaryInvolvement', 0.20)   * _c.get('ThirdPartyMilitaryInvolvement', 0.0)
            )

            _q_trigger = (
                Q_SHRINKAGE.get('TriggerType', 0.08)       * _c.get('TriggerType', 0.0)
              + Q_SHRINKAGE.get('CommitmentProblem', 0.25) * _c.get('CommitmentProblem', 0.0)
            )

            _q_live = (
                Q_SHRINKAGE.get('LiveNonviolentMilitaryPressure', 0.80) * _c.get('LiveNonviolentMilitaryPressure', 0.0)
              + Q_SHRINKAGE.get('LiveViolenceObserved', 0.90)            * _c.get('LiveViolenceObserved', 0.0)
              + Q_SHRINKAGE.get('LiveUltimatumDeadline', 0.90)           * _c.get('LiveUltimatumDeadline', 0.0)
              + Q_SHRINKAGE.get('MobilizationSignal', 0.70)              * _c.get('MobilizationSignal', 0.0)
            )

            _q_abatement = (
                Q_SHRINKAGE.get('LiveMediationAccepted', 0.15) * abs(_c.get('LiveMediationAccepted', 0.0))
              + Q_SHRINKAGE.get('LiveAbatementSignal', 0.20)   * abs(_c.get('LiveAbatementSignal', 0.0))
            )

            q_logit = _q_structural + _q_trigger + _q_live - _q_abatement"""

src = src.replace(OLD_A, NEW_A, 1)
assert NEW_A in src, "ABORT: Patch A did not land"
print("Patch A applied — q_logit assembly replaced")

# ── PATCH B: remove standalone horizon scaling (now inside _q_structural) ──
OLD_B = """\
            # Horizon scaling: convert 90-day probability to days_remaining probability.
            # p_contract = 1 - (1-p_90)^(days_remaining/90)
            # Collapses near-zero events toward zero as deadline approaches.
            horizon_scale = max(days_remaining, 1) / market_window
            engine_p_scaled = 1 - (1 - engine_p_raw) ** horizon_scale
            engine_p = round(1 - engine_p_scaled, 4) if z_t == 2 else round(engine_p_scaled, 4)"""

NEW_B = """\
            # Run 18: horizon scaling now lives inside _q_structural only.
            # Live acute q enters logit at full weight — no post-hoc crush.
            engine_p = round(1 - engine_p_raw, 4) if z_t == 2 else round(engine_p_raw, 4)"""

assert OLD_B in src, "ABORT: Patch B horizon block not found verbatim"
src = src.replace(OLD_B, NEW_B, 1)
assert NEW_B in src, "ABORT: Patch B did not land"
print("Patch B applied — standalone horizon scaling removed")

path.write_text(src)
print("Patch 18 written to disk.")
print("Run: python3.11 -m py_compile pipeline/backtest.py && echo OK")

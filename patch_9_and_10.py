#!/usr/bin/env python3
"""
Apply Patches 9 + 10 to pipeline/backtest.py.
Run from repo root: python3.11 /tmp/patch_9_and_10.py
"""
import pathlib, sys

TARGET = pathlib.Path("pipeline/backtest.py")
src = TARGET.read_text()
original = src

# ── PATCH 9 ── three-tier JSON extractor + raw response logging ─────────────
OLD9 = (
    '    text = resp["content"][0]["text"].strip()\n'
    '\n'
    '    try:\n'
    '        if "```" in text:\n'
    '            text = text.split("```")[1]\n'
    '            if text.startswith("json"):\n'
    '                text = text[4:]\n'
    '        parsed = json.loads(text.strip())\n'
    '        return {n: float(parsed.get(n, 0.0)) for n in expected_fields}\n'
    '    except Exception:\n'
    '        print(f"    [warn] Node scoring parse error, using zeros")\n'
    '        return {n: 0.0 for n in expected_fields}'
)
NEW9 = (
    '    text = resp["content"][0]["text"].strip()\n'
    '\n'
    '    # Three-tier JSON extraction (June 18 2026):\n'
    '    # Tier 1 -- direct parse (clean JSON, happy path).\n'
    '    # Tier 2 -- strip markdown code fences (```json...```).\n'
    '    # Tier 3 -- brace extraction: find first { and last } and parse\n'
    '    #   that substring -- handles preamble text before the JSON object.\n'
    '    # On total failure: log first 300 chars of raw response.\n'
    '    def _fence_strip(t):\n'
    '        if "```" not in t:\n'
    '            return t\n'
    '        part = t.split("```")[1]\n'
    '        return part.lstrip("json").strip()\n'
    '\n'
    '    def _brace_extract(t):\n'
    '        lo, hi = t.find("{"), t.rfind("}")\n'
    '        return t[lo:hi+1] if lo != -1 and hi != -1 else ""\n'
    '\n'
    '    for label, candidate in [\n'
    '        ("direct",        text),\n'
    '        ("fence-strip",   _fence_strip(text)),\n'
    '        ("brace-extract", _brace_extract(text)),\n'
    '    ]:\n'
    '        try:\n'
    '            parsed = json.loads(candidate)\n'
    '            return {n: float(parsed.get(n, 0.0)) for n in expected_fields}\n'
    '        except Exception:\n'
    '            continue\n'
    '    print(f"    [warn] Node scoring parse error (all 3 tiers), using zeros")\n'
    '    print(f"    [warn] raw response (first 300 chars): {text[:300]!r}")\n'
    '    return {n: 0.0 for n in expected_fields}'
)

# ── PATCH 10A ── DYAD_REGIME dict after ICB_COEF ───────────────────────────
OLD10A = (
    'ICB_COEF = {\n'
    '    "TriggerType":                   3.680,  # SE 0.455, robustly significant\n'
    '    "ValueThreatGravity":            3.674,  # SE 0.620, robustly significant\n'
    '    "ThirdPartyMilitaryInvolvement": 2.474,  # SE 0.771, significant, medium-confidence mapping (GPINVTP/USINV/SUINV/CHINV aggregated)\n'
    '    "ProtractedConflict":            0.535,  # SE 0.715 -- NOT significant, use with caution\n'
    '    "GeographicProximity":           1.045,  # SE 0.757 -- NOT significant, use with caution\n'
    '}'
)
NEW10A = (
    'ICB_COEF = {\n'
    '    "TriggerType":                   3.680,  # SE 0.455, robustly significant\n'
    '    "ValueThreatGravity":            3.674,  # SE 0.620, robustly significant\n'
    '    "ThirdPartyMilitaryInvolvement": 2.474,  # SE 0.771, significant, medium-confidence mapping (GPINVTP/USINV/SUINV/CHINV aggregated)\n'
    '    "ProtractedConflict":            0.535,  # SE 0.715 -- NOT significant, use with caution\n'
    '    "GeographicProximity":           1.045,  # SE 0.757 -- NOT significant, use with caution\n'
    '}\n'
    '\n'
    '# Mach 3 regime classification (June 18 2026).\n'
    '# Z_t=0: quiet dyad -- use Mach 2 structural formula.\n'
    '# Z_t=1: active pre-war crisis -- use q_full as primary probability.\n'
    '#        Counterfactual validated: Brier 0.0675 vs market 0.1043.\n'
    '# Z_t=2: ongoing war, inverted-polarity market -- exclude from Brier.\n'
    'DYAD_REGIME = {\n'
    '    "China-Taiwan":   0,\n'
    '    "India-Pakistan": 0,\n'
    '    "US-Iran":        1,\n'
    '    "US-Venezuela":   1,\n'
    '    "Russia-Ukraine": 2,\n'
    '}'
)

# ── PATCH 10B ── regime routing in run_backtest() loop ──────────────────────
OLD10B = (
    '            # Run Mach 2 -- June 18 2026: q-submodel now wired in. q_logit is\n'
    '            # the same additive sum q_full is built from (sigmoid of it IS\n'
    '            # q_full), passed straight into log_odds_shift, weight 1.0, no\n'
    '            # separate calibration factor invented for this.\n'
    '            q_logit  = sum(q_components.values())\n'
    '            engine_p = predict_probability(toggles, days_remaining, q_logit=q_logit)\n'
    '\n'
    '            # Brier scores (only for resolved markets)\n'
    '            b_engine = (engine_p - resolution)**2 if resolution is not None else None\n'
    '            b_market = (mkt_price - resolution)**2 if resolution is not None else None\n'
    '\n'
    '            row = {\n'
    '                "market":        mkt["label"],\n'
    '                "dyad":          dyad,\n'
    '                "snapshot_date": snapshot_date.isoformat(),\n'
    '                "days_remaining":days_remaining,\n'
    '                "resolution":    resolution,\n'
    '                "engine_p":      engine_p,\n'
    '                "market_p":      mkt_price,\n'
    '                "b_engine":      b_engine,\n'
    '                "b_market":      b_market,\n'
    '                "n_articles":    len(articles),\n'
    '                "q_components":  q_components,\n'
    '                "q_full":        round(q_full, 4),\n'
    '                "q_onset_only":  round(q_onset_only, 4),\n'
    '                "q_live_only":   round(q_live_only, 4),\n'
    '            }'
)
NEW10B = (
    '            # Mach 3 regime routing (June 18 2026):\n'
    '            # Z_t=0 -> Mach 2 structural formula.\n'
    '            # Z_t=1 -> q_full as primary probability (crisis reference class).\n'
    '            # Z_t=2 -> Mach 2 stored but excluded from Brier in print_results.\n'
    '            q_logit  = sum(q_components.values())\n'
    '            z_t      = DYAD_REGIME.get(dyad, 0)\n'
    '            if z_t == 1:\n'
    '                engine_p = round(q_full, 4)\n'
    '            else:\n'
    '                engine_p = predict_probability(toggles, days_remaining, q_logit=q_logit)\n'
    '\n'
    '            # Brier scores (resolved markets; Z_t=2 filtered in print_results)\n'
    '            b_engine = (engine_p - resolution)**2 if resolution is not None else None\n'
    '            b_market = (mkt_price - resolution)**2 if resolution is not None else None\n'
    '\n'
    '            row = {\n'
    '                "market":        mkt["label"],\n'
    '                "dyad":          dyad,\n'
    '                "snapshot_date": snapshot_date.isoformat(),\n'
    '                "days_remaining":days_remaining,\n'
    '                "resolution":    resolution,\n'
    '                "z_t":           z_t,\n'
    '                "engine_p":      engine_p,\n'
    '                "market_p":      mkt_price,\n'
    '                "b_engine":      b_engine,\n'
    '                "b_market":      b_market,\n'
    '                "n_articles":    len(articles),\n'
    '                "q_components":  q_components,\n'
    '                "q_full":        round(q_full, 4),\n'
    '                "q_onset_only":  round(q_onset_only, 4),\n'
    '                "q_live_only":   round(q_live_only, 4),\n'
    '            }'
)

# ── PATCH 10C ── filter Z_t=2 in print_results() ───────────────────────────
OLD10C = (
    'def print_results(rows):\n'
    '    resolved = [r for r in rows if r["resolution"] is not None]\n'
    '    live     = [r for r in rows if r["resolution"] is None]\n'
    '\n'
    '    if not resolved:\n'
    '        print("\\nNo resolved markets to score yet.")\n'
    '        return\n'
    '\n'
    '    mean_b_engine = sum(r["b_engine"] for r in resolved) / len(resolved)\n'
    '    mean_b_market = sum(r["b_market"] for r in resolved) / len(resolved)\n'
    '    wins = sum(1 for r in resolved if r["b_engine"] < r["b_market"])\n'
    '\n'
    '    print("\\n" + "\u2588"*60)\n'
    '    print("  BACKTEST RESULTS \u2014 Mach 2")\n'
    '    print("\u2588"*60)\n'
    '    print(f"\\n  Resolved rows:  {len(resolved)}")\n'
    '    print(f"  Live rows:      {len(live)}")'
)
NEW10C = (
    'def print_results(rows):\n'
    '    all_resolved = [r for r in rows if r["resolution"] is not None]\n'
    '    live         = [r for r in rows if r["resolution"] is None]\n'
    '    resolved  = [r for r in all_resolved if r.get("z_t", 0) != 2]\n'
    '    excluded2 = [r for r in all_resolved if r.get("z_t", 0) == 2]\n'
    '\n'
    '    if not resolved:\n'
    '        print("\\nNo resolved markets to score yet.")\n'
    '        return\n'
    '\n'
    '    mean_b_engine = sum(r["b_engine"] for r in resolved) / len(resolved)\n'
    '    mean_b_market = sum(r["b_market"] for r in resolved) / len(resolved)\n'
    '    wins = sum(1 for r in resolved if r["b_engine"] < r["b_market"])\n'
    '\n'
    '    print("\\n" + "\u2588"*60)\n'
    '    print("  BACKTEST RESULTS \u2014 Mach 3 (regime-switched)")\n'
    '    print("\u2588"*60)\n'
    '    print(f"\\n  Resolved rows:  {len(resolved)}  (Z_t=2 excluded: {len(excluded2)})")\n'
    '    print(f"  Live rows:      {len(live)}")'
)

patches = [
    ("Patch 9  — three-tier JSON extractor",  OLD9,   NEW9),
    ("Patch 10A — DYAD_REGIME dict",          OLD10A, NEW10A),
    ("Patch 10B — regime routing in loop",    OLD10B, NEW10B),
    ("Patch 10C — Z_t=2 exclusion in print",  OLD10C, NEW10C),
]

ok = True
for label, old, new in patches:
    if old not in src:
        print(f"ABORT: {label} — old string not found in file")
        ok = False

if not ok:
    sys.exit(1)

for label, old, new in patches:
    src = src.replace(old, new)
    print(f"  applied: {label}")

TARGET.write_text(src)
print("\nAll patches applied. Run: python3.11 -m py_compile pipeline/backtest.py")

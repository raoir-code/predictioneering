#!/usr/bin/env python3.11
"""
Patch 1 — add q_static (ProtractedConflict, GeographicProximity) to the
5 backtest-slate dyads in pipeline/dyad_configs.json.

ProtractedConflict per ICB's "extended, fluctuating, indefinite" definition:
  India-Pakistan, China-Taiwan, Russia-Ukraine, US-Iran -> 0.30 (clear fits)
  US-Venezuela -> 0.0 (lacks the multi-decade recurring-crisis history the
    other four have — flag for override if you read it differently)

GeographicProximity:
  India-Pakistan, China-Taiwan, Russia-Ukraine -> 0.35 (contiguous; Taiwan
    Strait treated as contiguous per conflict-studies convention)
  US-Venezuela -> 0.15 (near neighbor, Caribbean basin)
  US-Iran -> 0.0 (distant)

Run from repo root: python3.11 patch_1_dyad_configs.py
"""
import json
from pathlib import Path

path = Path("pipeline/dyad_configs.json")
configs = json.loads(path.read_text())

Q_STATIC = {
    "India-Pakistan": {"ProtractedConflict": 0.30, "GeographicProximity": 0.35},
    "China-Taiwan":   {"ProtractedConflict": 0.30, "GeographicProximity": 0.35},
    "Russia-Ukraine": {"ProtractedConflict": 0.30, "GeographicProximity": 0.35},
    "US-Iran":        {"ProtractedConflict": 0.30, "GeographicProximity": 0.0},
    "US-Venezuela":   {"ProtractedConflict": 0.0,  "GeographicProximity": 0.15},
}

for dyad, q_static in Q_STATIC.items():
    assert dyad in configs, f"Dyad '{dyad}' not found in dyad_configs.json — aborting, no changes made"
    assert "q_static" not in configs[dyad], (
        f"'{dyad}' already has a q_static block — aborting to avoid silently "
        f"overwriting. Remove it manually first if you want to re-run this."
    )
    configs[dyad]["q_static"] = q_static

path.write_text(json.dumps(configs, indent=2))
print("Patch 1 applied — q_static added to 5 dyads:")
for dyad, q_static in Q_STATIC.items():
    print(f"  {dyad:<16} {q_static}")

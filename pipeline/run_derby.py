"""
run_derby.py
------------
Runs the estimation derby and saves alpha_star + edge results to alpha/.

Usage:
    cd predictioneering/
    python pipeline/run_derby.py

Output:
    alpha/conflict_onset.json   ← pipeline/backtest_venezuela.py reads from here
"""

import sys, json
import numpy as np
sys.path.insert(0, "engine")
sys.path.insert(0, "engine/derbies")

# Import and run the derby
import conflict_onset as derby

results = derby.results   # GodsDagEngine.run() returns this dict

# Pull out what the pipeline needs
alpha_out = {}
ci_out = {}
for (src, tgt), res in results["edge_results"].items():
    node = src  # edge src → Conflict; key by src node name
    alpha_out[node] = float(res["alpha_star"])
    ci_out[node] = {
        "ci_lo": float(res["ci_95"][0]) if not np.isnan(res["ci_95"][0]) else None,
        "ci_hi": float(res["ci_95"][1]) if not np.isnan(res["ci_95"][1]) else None,
        "boot_se": float(res["boot_se"]) if not np.isnan(res["boot_se"]) else None,
    }

output = {
    "derby": "conflict_onset",
    "alpha": alpha_out,
    "ci": ci_out,
    "diagnostics": {
        "n_moments": results["diagnostics"]["n_moments"],
        "jacobian_rank": results["diagnostics"]["jacobian_rank"],
        "condition_number": float(results["diagnostics"]["condition_number"])
            if results["diagnostics"]["condition_number"] != float("inf") else None,
        "is_identified": results["diagnostics"]["is_identified"],
    },
    "counts": results["counts"],
}

import os
os.makedirs("alpha", exist_ok=True)
with open("alpha/conflict_onset.json", "w") as f:
    json.dump(output, f, indent=2)

print("\n[run_derby] Alpha saved to alpha/conflict_onset.json")
print(json.dumps(output["alpha"], indent=2))

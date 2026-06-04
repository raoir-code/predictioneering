"""
load_alpha.py
-------------
Single function that both the backtest and any future pipeline script
use to load alpha. Reads from alpha/conflict_onset.json.

Also supports manual overrides — for expert-elicited nodes that have
no published study (e.g. AudienceCosts).

Usage:
    from pipeline.load_alpha import load_alpha
    alpha = load_alpha(overrides={"AudienceCosts": 0.35})
"""

import json
import os


ALPHA_FILE = "alpha/conflict_onset.json"

# Expert-elicited priors — nodes with no published study in the library.
# These are manual overrides with documented provenance.
# Format: { node_name: { "beta": float, "se": float, "source": str } }
EXPERT_PRIORS = {
    # AudienceCosts (v2 legacy) — deactivated in v3.
    # Mechanism now covered by DemocraticPeace node, estimated from studies.
    # Keeping for provenance. Re-activate if DAG splits alpha_A/alpha_B.
    # "AudienceCosts": {
    #     "beta": 0.35,
    #     "se": 0.50,
    #     "source": "Expert elicitation — [name/affiliation of your friend here]",
    #     "note": "No published study found for AudienceCosts as of v2."
    # },

    # Credibility / settlement implementation (pi_A, pi_B)
    # No published study cleanly identifies this channel.
    # Prior: low credibility raises effective outside option -> more conflict.
    # Wide SE reflects genuine uncertainty.
    "Credibility_A": {
        "beta": -0.30,
        "se":    0.30,
        "source": "expert_prior_v3",
        "note": "pi_A: challenger credibility / settlement implementation. "
                "Derived from bargaining model comparative statics. "
                "No clean empirical proxy in hazard library v4."
    },
    "Credibility_B": {
        "beta": -0.30,
        "se":    0.30,
        "source": "expert_prior_v3",
        "note": "pi_B: target credibility / settlement implementation. "
                "Symmetric to Credibility_A pending asymmetric study identification."
    },
}


def load_alpha(alpha_file: str = ALPHA_FILE,
               overrides: dict | None = None) -> dict:
    """
    Load alpha from the derby output file.
    Applies expert-prior overrides for any node missing from the derby.

    Parameters
    ----------
    alpha_file : path to the derby output JSON
    overrides  : optional dict of {node: value} to override specific nodes.
                 Pass overrides={} to skip all overrides.
                 Default (None) applies EXPERT_PRIORS.

    Returns
    -------
    dict mapping node names to alpha values
    """
    if not os.path.exists(alpha_file):
        raise FileNotFoundError(
            f"Alpha file not found: {alpha_file}\n"
            f"Run: python pipeline/run_derby.py"
        )

    with open(alpha_file) as f:
        data = json.load(f)

    alpha = dict(data["alpha"])

    # Apply overrides
    applied_overrides = EXPERT_PRIORS if overrides is None else overrides
    for node, val in applied_overrides.items():
        if isinstance(val, dict):
            alpha[node] = val["beta"]
        else:
            alpha[node] = float(val)

    return alpha


def describe_alpha(alpha_file: str = ALPHA_FILE) -> None:
    """Print a summary of current alpha values + provenance."""
    alpha = load_alpha(alpha_file)
    with open(alpha_file) as f:
        data = json.load(f)

    print(f"\n[Alpha] Derby: {data.get('derby', '?')}")
    print(f"  Identified: {data['diagnostics']['is_identified']}")
    print(f"  Jacobian rank: {data['diagnostics']['jacobian_rank']} / {data['diagnostics']['n_moments']} moments\n")

    print("  Node                  alpha     source")
    print("  " + "-" * 55)
    for node, val in alpha.items():
        source = "derby" if node in data["alpha"] else "expert prior"
        print(f"  {node:<22} {val:+.4f}   [{source}]")

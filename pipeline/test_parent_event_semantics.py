#!/usr/bin/env python3

from pipeline.clergyman_ontology import (
    derive_parent_event_relation,
    derive_severity_band,
)
from pipeline.translator import (
    _derive_route,
    ENGINE_EVENT_A_DEFINITION,
    LEGAL_SCHOLAR_SYSTEM,
    CLERGYMAN_SYSTEM,
)

CASES = [
    ("political_act", "broad", "unknown", "overlap", "overlap"),

    # Discrete / limited physical incidents can occur below A.
    ("kinetic_or_coercive_action", "broad",
     "limited", "overlap", "overlap"),
    ("kinetic_or_coercive_action", "method_specific",
     "discrete_kinetic", "overlap", "overlap"),
    ("kinetic_or_coercive_action", "target_specific",
     "discrete_kinetic", "overlap", "overlap"),

    # Persistent low-level coercion is not automatically VIOL>=3.
    ("kinetic_or_coercive_action", "persistent",
     "limited", "overlap", "overlap"),

    # Sustained kinetic fighting does cross A.
    ("kinetic_or_coercive_action", "persistent",
     "discrete_kinetic", "subset", "conflict_bound"),

    # Blockade / territorial war cross A.
    ("kinetic_or_coercive_action", "method_specific",
     "persistent_campaign", "subset", "conflict_bound"),
    ("kinetic_or_coercive_action", "method_specific",
     "territorial_war", "subset", "conflict_bound"),

    # Explicit territorial-control burden crosses A.
    ("kinetic_or_coercive_action", "territorial_control",
     "limited", "subset", "conflict_bound"),

    # B == A.
    ("kinetic_or_coercive_action", "broad",
     "unknown", "equivalent", "equivalent"),
]

for case in CASES:
    got = derive_parent_event_relation(*case[:-1])
    expected = case[-1]
    assert got == expected, f"{case}: got {got}"

assert derive_severity_band("direct_engagement") == "discrete_kinetic"

# Physical conflict-overlap contracts must reach Clergyman.
assert _derive_route(
    "overlap", "high", "conflict", "binary_threshold"
) == "TRANSLATE"

assert _derive_route(
    "overlap", "high", "conflict", "binary_onset"
) == "TRANSLATE"

# Bargaining/deal overlap stays outside this route.
assert _derive_route(
    "overlap", "high", "ambiguous", "negotiation_deal"
) == "PASS_TRANSLATION"

assert _derive_route(
    "subset", "high", "conflict", "territorial_control"
) == "TRANSLATE"

# Same definition of A must literally reach both agents.
assert ENGINE_EVENT_A_DEFINITION in LEGAL_SCHOLAR_SYSTEM
assert ENGINE_EVENT_A_DEFINITION in CLERGYMAN_SYSTEM

assert (
    "discrete physical incidents below the serious-clash threshold"
    in LEGAL_SCHOLAR_SYSTEM
)

print("PARENT EVENT SEMANTICS: PASS")
print(f"{len(CASES)} deterministic relation cases passed")


# Prompt-level regression: physical overlap must not be blanket-zeroed.
assert "A physical action does NOT automatically imply A" in CLERGYMAN_SYSTEM
assert (
    "Discrete or limited actions can occur below the serious-conflict threshold"
    in CLERGYMAN_SYSTEM
)
assert "kinetic_or_coercive_action subsets: P(B|¬A) ≈ 0" not in CLERGYMAN_SYSTEM

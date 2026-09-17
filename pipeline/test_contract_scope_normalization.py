#!/usr/bin/env python3

from pipeline.contract_scope import (
    apply_direction_authority,
    scope_fingerprint,
)


def base_scope():
    return {
        "initiator_scope": {
            "mode": "single_actor",
            "canonical_actor": "United States",
            "entity_type": "state",
            "members": [],
            "group_names": [],
        },
        "target_scope": {
            "mode": "single_actor",
            "canonical_actor": "Pakistan",
            "entity_type": "state",
            "members": [],
            "group_names": [],
        },
        "geography": {
            "mode": "target_wide",
            "places": ["Pakistan"],
            "prior_relevance": "resolution_only",
        },
        "direction_compatible": True,
        "confidence": "high",
        "reasoning": "irrelevant prose A",
    }


# ------------------------------------------------------------
# Assigned direction beats LLM naming variation.
# target_wide places are normalized away.
# ------------------------------------------------------------

a = apply_direction_authority(
    base_scope(),
    "US",
    "Pakistan",
)

b_raw = base_scope()
b_raw["initiator_scope"]["canonical_actor"] = "US"
b_raw["geography"]["places"] = []

b = apply_direction_authority(
    b_raw,
    "US",
    "Pakistan",
)

assert a["initiator_scope"]["canonical_actor"] == "US"
assert a["geography"]["places"] == []
assert scope_fingerprint(a) == scope_fingerprint(b)


# ------------------------------------------------------------
# Ordering of union members and group names cannot alter hash.
# ------------------------------------------------------------

u1 = {
    "initiator_scope": {
        "mode": "enumerable_union",
        "canonical_actor": None,
        "entity_type": "state",
        "members": ["France", "Germany", "Italy"],
        "group_names": [],
    },
    "target_scope": {
        "mode": "single_actor",
        "canonical_actor": "Iran",
        "entity_type": "state",
        "members": [],
        "group_names": [],
    },
    "geography": {
        "mode": "target_wide",
        "places": [],
        "prior_relevance": "resolution_only",
    },
    "direction_compatible": True,
}

u2 = {
    "initiator_scope": {
        "mode": "enumerable_union",
        "canonical_actor": None,
        "entity_type": "state",
        "members": ["Italy", "France", "Germany", "France"],
        "group_names": [],
    },
    "target_scope": {
        "mode": "single_actor",
        "canonical_actor": "Iran",
        "entity_type": "state",
        "members": [],
        "group_names": [],
    },
    "geography": {
        "mode": "target_wide",
        "places": ["Iran"],
        "prior_relevance": "resolution_only",
    },
    "direction_compatible": True,
}

u1 = apply_direction_authority(u1, "Europe", "Iran")
u2 = apply_direction_authority(u2, "Europe", "Iran")

assert u1["initiator_scope"]["members"] == [
    "France",
    "Germany",
    "Italy",
]
assert scope_fingerprint(u1) == scope_fingerprint(u2)


# ------------------------------------------------------------
# Real scope differences MUST change the fingerprint.
# ------------------------------------------------------------

greenland = base_scope()
greenland["target_scope"]["canonical_actor"] = "Denmark"
greenland["geography"] = {
    "mode": "subterritory",
    "places": ["Greenland"],
    "prior_relevance": "structural_theater",
}

denmark_wide = base_scope()
denmark_wide["target_scope"]["canonical_actor"] = "Denmark"
denmark_wide["geography"] = {
    "mode": "target_wide",
    "places": ["Denmark"],
    "prior_relevance": "resolution_only",
}

greenland = apply_direction_authority(
    greenland,
    "US",
    "Denmark",
)
denmark_wide = apply_direction_authority(
    denmark_wide,
    "US",
    "Denmark",
)

assert (
    scope_fingerprint(greenland)
    != scope_fingerprint(denmark_wide)
)

print("CONTRACT SCOPE NORMALIZATION: PASS")

#!/usr/bin/env python3

from pipeline.contract_scope import (
    action_prior_fingerprint,
    action_prior_scope_core,
)


def party(name):
    return {
        "mode": "single_actor",
        "canonical_actor": name,
        "entity_type": "state",
        "members": [],
        "group_names": [],
    }


# Same actors, different resolution-only legal geography.
# Must collapse to ONE structural action prior.

invasion_definition = {
    "initiator_scope": party("China"),
    "target_scope": party("Taiwan"),
    "geography": {
        "mode": "target_wide",
        "places": [],
        "prior_relevance": "resolution_only",
    },
    "direction_compatible": True,
}

blockade_definition = {
    "initiator_scope": party("China"),
    "target_scope": party("Taiwan"),
    "geography": {
        "mode": "subterritory",
        "places": [
            "Taiwan main island",
            "ports",
            "airports",
        ],
        "prior_relevance": "resolution_only",
    },
    "direction_compatible": True,
}

assert (
    action_prior_fingerprint(invasion_definition)
    == action_prior_fingerprint(blockade_definition)
)


# Genuine operational geography must survive.

denmark_wide = {
    "initiator_scope": party("US"),
    "target_scope": party("Denmark"),
    "geography": {
        "mode": "target_wide",
        "places": [],
        "prior_relevance": "resolution_only",
    },
    "direction_compatible": True,
}

greenland = {
    "initiator_scope": party("US"),
    "target_scope": party("Denmark"),
    "geography": {
        "mode": "subterritory",
        "places": ["Greenland"],
        "prior_relevance": "structural_theater",
    },
    "direction_compatible": True,
}

assert (
    action_prior_fingerprint(denmark_wide)
    != action_prior_fingerprint(greenland)
)

assert action_prior_scope_core(
    blockade_definition
)["geography"] == {
    "mode": "target_wide",
    "places": [],
}

assert action_prior_scope_core(
    greenland
)["geography"] == {
    "mode": "subterritory",
    "places": ["Greenland"],
}

print("ACTION PRIOR SCOPE PROJECTION: PASS")

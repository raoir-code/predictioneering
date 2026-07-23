"""
Deterministic contract-severity ontology for Clergyman.

Design per ChatGPT review, 2026-07-23: severity and conditional-probability-
given-A are NOT the same axis and can point in opposite directions (a naval
blockade is more severe than a single airstrike but LESS likely given conflict
occurs, because it requires persistence + geographic coverage + command
commitment -- additional conjunctive requirements that lower its probability,
not raise it). The original single "escalation ladder" draft would have
recreated the July 13 blockade-vs-invasion bug in a different form.

Two axes:
- manifestation_family: is this contract asking about a POLITICAL act
  (announcement, declaration, authorization) or a PHYSICAL action? These are
  different event families with different causal requirements and timing --
  not points on one scale. Political acts are typically MORE likely than the
  physical act they describe (cheap to announce, no operational commitment),
  and are NOT subject to the operational-lag gate.
- requirement_burden: how many additional necessary conditions does the
  contract impose beyond "some qualifying action occurred"? This is the axis
  that actually governs P(B|A), per the conjunctive-event logic:
      B = A ∩ C_1 ∩ C_2 ∩ ... ∩ C_k  =>  P(B|A) = P(C_1,...,C_k | A)
  which falls (or stays flat) as more necessary conditions are added, never
  rises. Ranges below are therefore monotonically non-increasing by burden
  tier -- this is what actually enforces the nested-subset invariant
  (P(B_2|A) <= P(B_1|A) when B_2 is a strict subset of B_1), NOT a global
  ranking by severity/drama.

severity_band is still recorded (derived mostly from action_type) for
diagnostics/audit purposes and because ICB's GRAVCR literature supports using
a coarse ordinal severity ontology -- but per the same review, GRAVCR's
ordinal SHAPE is legitimate inspiration for how many bins to use; its fitted
coefficients and category boundaries are NOT evidence for these probability
ranges, since GRAVCR estimates a different reference class (P(violence |
ICB crisis), not P(this specific contract | engine event)). Treat
severity_band as documentation, not the thing that sets the range.

These ranges are explicitly NOT empirical estimates. They are transparent,
logic-derived priors (conjunctive event structure), to be refined once enough
resolved markets exist to check them against real outcomes. Do not tune them
to match market prices -- that was already explicitly rejected elsewhere in
this project as intellectually hollow.
"""

MANIFESTATION_FAMILIES = {"political_act", "kinetic_or_coercive_action"}

REQUIREMENT_BURDENS = {
    "broad",               # any qualifying action in a wide category
    "method_specific",     # a particular method/action_type named
    "target_specific",     # a particular target/location/actor named
    "persistent",          # requires duration/sustained operation
    "territorial_control", # requires establishing/holding territory
}

SEVERITY_BANDS = {
    "limited",              # gray_zone_incident, seizure_boarding
    "discrete_kinetic",     # raid, missile_strike, airstrike
    "persistent_campaign",  # naval_blockade
    "territorial_war",      # ground_invasion
}

# action_type -> severity_band, for auto-deriving the diagnostic field
# (does NOT set the anchor range -- requirement_burden does that)
ACTION_TYPE_TO_SEVERITY_BAND = {
    "gray_zone_incident": "limited",
    "seizure_boarding":   "limited",
    "raid":               "discrete_kinetic",
    "missile_strike":     "discrete_kinetic",
    "airstrike":          "discrete_kinetic",
    "naval_blockade":     "persistent_campaign",
    "ground_invasion":    "territorial_war",
}

# The core deterministic table. Ranges are non-increasing down the list --
# this ordering IS the monotonicity enforcement mechanism.
# Format: requirement_burden -> (low, high)
ANCHOR_RANGES_KINETIC = {
    "broad":               (0.60, 0.95),
    "method_specific":     (0.25, 0.70),
    "target_specific":     (0.10, 0.45),
    "persistent":          (0.08, 0.35),
    "territorial_control": (0.02, 0.20),
}

# Political acts are a different event family entirely -- not on the kinetic
# ladder. An announcement/declaration is typically cheap and often PRECEDES
# or ACCOMPANIES physical action, so it can be more likely than the physical
# act itself given conflict occurs. Single wide range for now; refine once
# resolved political-act markets exist to check against.
ANCHOR_RANGE_POLITICAL_ACT = (0.30, 0.90)


def get_anchor_range(manifestation_family: str, requirement_burden: str) -> tuple:
    """
    Returns (low, high) for P(B|A), deterministically, from the two
    classification axes. Clergyman does NOT get to pick its own range --
    it only picks a value INSIDE the range it's assigned, and must explain
    which modifier moved it (this prevents the same model from inventing
    both its ruler and its measurement).
    """
    if manifestation_family == "political_act":
        return ANCHOR_RANGE_POLITICAL_ACT

    if requirement_burden not in ANCHOR_RANGES_KINETIC:
        raise ValueError(
            f"Unknown requirement_burden '{requirement_burden}' -- add it to "
            f"ANCHOR_RANGES_KINETIC deliberately rather than defaulting."
        )
    return ANCHOR_RANGES_KINETIC[requirement_burden]


def clamp_to_range(value: float, range_tuple: tuple) -> tuple:
    """
    Clamps value into [low, high]. Returns (clamped_value, was_clamped: bool)
    so callers can log/monitor how often Clergyman's raw guess disagrees with
    the deterministic range -- a useful drift signal over time, not just a
    silent correction.
    """
    low, high = range_tuple
    if value is None:
        return None, False
    if value < low:
        return low, True
    if value > high:
        return high, True
    return value, False


def derive_severity_band(action_type: str) -> str:
    """Best-effort diagnostic label from action_type. Returns 'unknown' for
    unrecognized action types rather than raising -- this field is for audit
    trails, not for gating logic, so a soft failure is acceptable here."""
    return ACTION_TYPE_TO_SEVERITY_BAND.get(action_type, "unknown")

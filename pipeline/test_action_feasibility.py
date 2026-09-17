#!/usr/bin/env python3

from pipeline.action_selector import (
    ACTION_TYPES,
    FEASIBILITY_CAPS,
    apply_feasibility_guards,
    normalize_feasibility_profile,
    select_distribution,
)

uniform = {a: 1.0 for a in ACTION_TYPES}

tiers = {a: "feasible" for a in ACTION_TYPES}
tiers["ground_invasion"] = "unavailable"
tiers["naval_blockade"] = "severely_constrained"

guarded = apply_feasibility_guards(uniform, tiers)

assert abs(sum(guarded.values()) - 1.0) < 1e-9

# Actual hard sanity guard.
assert (
    guarded["ground_invasion"]
    <= FEASIBILITY_CAPS["unavailable"] + 1e-9
)

# Severe constraint is metadata, NOT an arbitrary 3% ceiling.
assert guarded["naval_blockade"] > 0.03
assert FEASIBILITY_CAPS["severely_constrained"] == 1.0

# Feasible actions retain their raw structural ranking.
raw = {a: 0.01 for a in ACTION_TYPES}
raw["missile_strike"] = 0.93

all_feasible = {a: "feasible" for a in ACTION_TYPES}
g2 = apply_feasibility_guards(raw, all_feasible)

assert g2["missile_strike"] > 0.9

# Even extreme live evidence cannot blow through an unavailable-action guard.
live = {a: 0.0 for a in ACTION_TYPES}
live["ground_invasion"] = 20.0

g3 = select_distribution(
    uniform,
    live_scores=live,
    feasibility=tiers,
)

assert abs(sum(g3.values()) - 1.0) < 1e-9
assert (
    g3["ground_invasion"]
    <= FEASIBILITY_CAPS["unavailable"] + 1e-9
)

# Profiles must cover all eight actions.
bad = dict(tiers)
del bad["raid"]

try:
    normalize_feasibility_profile(bad)
except ValueError:
    pass
else:
    raise AssertionError("Incomplete feasibility profile was accepted")

print("ACTION FEASIBILITY: PASS")
print("unavailable cap: PASS")
print("severely_constrained audit-only: PASS")
print(f"{len(ACTION_TYPES)} action types validated")


from pipeline.action_selector import (
    DIRECT_ENGAGEMENT_NO_CONTACT_CAP,
    apply_structural_prerequisites,
)

contact_test = {a: 0.10 for a in ACTION_TYPES}
contact_test["direct_engagement"] = 0.30

no_contact = apply_structural_prerequisites(
    contact_test,
    {"direct_engagement_contact_pathway": False},
)

assert no_contact["direct_engagement"] <= (
    DIRECT_ENGAGEMENT_NO_CONTACT_CAP + 1e-9
)
assert abs(sum(no_contact.values()) - 1.0) < 1e-9

with_contact = apply_structural_prerequisites(
    contact_test,
    {"direct_engagement_contact_pathway": True},
)

assert with_contact["direct_engagement"] > 0.20

print("direct_engagement contact prerequisite: PASS")

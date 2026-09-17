#!/usr/bin/env python3

from pipeline.contract_scope import (
    resolve_contract_scope,
    scope_fingerprint,
)


def run(name, initiator, target, question, description):
    s = resolve_contract_scope(
        initiator=initiator,
        target=target,
        question=question,
        description=description,
    )

    print(f"\n{name}")
    print(" initiator:", s["initiator_scope"])
    print(" target:   ", s["target_scope"])
    print(" geography:", s["geography"])
    print(" compatible:", s["direction_compatible"])
    print(" fingerprint:", s["scope_fingerprint"])
    print(" reasoning:", s["reasoning"])

    assert (
        s["scope_fingerprint"]
        == scope_fingerprint(s)
    )

    return s


# ------------------------------------------------------------
# 1. Ordinary bilateral
# ------------------------------------------------------------

s = run(
    "ORDINARY BILATERAL",
    "India",
    "Pakistan",
    "Will India strike Pakistan?",
    """
    Resolves Yes if India initiates a drone, missile, or air strike
    that impacts Pakistani territory.
    """,
)

assert s["initiator_scope"]["mode"] == "single_actor"
assert s["target_scope"]["mode"] == "single_actor"
assert s["geography"]["mode"] == "target_wide"


# ------------------------------------------------------------
# 2. Explicit enumerable OR-set
# ------------------------------------------------------------

s = run(
    "ENUMERABLE INITIATOR UNION",
    "Europe",
    "Iran",
    "Will a European country take military action on Iran?",
    """
    Resolves Yes if any European country takes qualifying military
    action against Iran.

    For this market European country means:
    France, Germany, Italy, Poland, Spain, United Kingdom.
    """,
)

assert (
    s["initiator_scope"]["mode"]
    == "enumerable_union"
)
assert set(s["initiator_scope"]["members"]) == {
    "France",
    "Germany",
    "Italy",
    "Poland",
    "Spain",
    "United Kingdom",
}
assert s["target_scope"]["mode"] == "single_actor"


# ------------------------------------------------------------
# 3. Named group OR-set
# ------------------------------------------------------------

s = run(
    "NAMED GROUP TARGET UNION",
    "Russia",
    "NATO",
    "Will Russia invade a NATO country?",
    """
    Resolves Yes if Russia commences a military offensive intended
    to establish control over any portion of any NATO country.
    """,
)

assert s["initiator_scope"]["mode"] == "single_actor"
assert (
    s["target_scope"]["mode"]
    == "named_group_union"
)
assert "NATO" in s["target_scope"]["group_names"]


# ------------------------------------------------------------
# 4. Narrow subterritory
# ------------------------------------------------------------

s = run(
    "SUBTERRITORY",
    "US",
    "Denmark",
    "Will the U.S. invade Greenland?",
    """
    Resolves Yes if the United States commences a military offensive
    intended to establish control over any portion of the land
    territory of Greenland. Greenland is the autonomous territory
    within the Kingdom of Denmark.
    """,
)

assert s["initiator_scope"]["mode"] == "single_actor"
assert s["target_scope"]["mode"] == "single_actor"
assert s["geography"]["mode"] == "subterritory"
assert "Greenland" in s["geography"]["places"]


# ------------------------------------------------------------
# 5. Named groups acting in third-party theater
# ------------------------------------------------------------

s = run(
    "GROUP UNION IN THIRD-PARTY THEATER",
    "NATO",
    "Russia",
    "NATO/EU troops fighting in Ukraine?",
    """
    Resolves Yes if active military personnel officially affiliated
    with any NATO or EU country enter Ukraine for combat-related
    military purposes directly pertaining to the conflict with Russia.
    """,
)

assert (
    s["initiator_scope"]["mode"]
    == "named_group_union"
)
assert set(
    s["initiator_scope"]["group_names"]
) == {"NATO", "EU"}

assert s["target_scope"]["mode"] == "single_actor"

assert (
    s["geography"]["mode"]
    == "third_party_theater"
)
assert "Ukraine" in s["geography"]["places"]


# ------------------------------------------------------------
# 6. Collective organization != member union
# ------------------------------------------------------------

s = run(
    "COLLECTIVE ACTOR",
    "NATO",
    "Russia",
    "Will NATO begin a military operation against Russia?",
    """
    Resolves Yes only if NATO itself formally authorizes and conducts
    a NATO military operation against Russian forces. Unilateral
    action by an individual NATO member does not qualify.
    """,
)

assert (
    s["initiator_scope"]["mode"]
    == "collective_actor"
)


# ------------------------------------------------------------
# 7. Undefined open set must fail into undefined_union
# ------------------------------------------------------------

s = run(
    "UNDEFINED UNION",
    "Unknown",
    "Iran",
    "Will any country attack Iran?",
    """
    Resolves Yes if any country in the world attacks Iran.
    No country list or named organization limits qualification.
    """,
)

assert (
    s["initiator_scope"]["mode"]
    == "undefined_union"
)

print("\nCONTRACT SCOPE SEMANTICS: PASS")

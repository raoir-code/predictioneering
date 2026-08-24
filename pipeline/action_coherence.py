"""
ACTION-TYPE PAIR RELATIONS AND CROSS-MARKET COHERENCE CHECK

Static, hand-authored relation table over the 7 action_type categories,
21 unordered pairs. Built 2026-08-24, cross-validated with ChatGPT. NOT
derived from data -- declared priors, same honesty-note category as
clergyman_ontology.py's war_costs_range_multiplier bend points. Revisit
once enough resolved same-dyad multi-market cases exist.

Five relation types:
- EXCLUSIVE: alternative initial-move campaign choices. Siblings sharing
  this relation get a soft co-occurrence ceiling on the SUM of their
  p_b_given_a -- a declared prior on P(A intersect B), not a hard logical
  constraint (real crises can see sequential multi-modal action within a
  long contract window -- see HORIZON_DEPENDENT_PAIRS).
- COMPONENT: B tends to be entailed by / accompany A (the "whole"). A's
  p_b_given_a floors B's -- B should not sit below floor_fraction * A.
  Asymmetric: does not constrain A from B.
- CONDITIONAL_COMPONENT: like COMPONENT, but entailment genuinely depends
  on an unobserved factor (blockade intensity/type) this system doesn't
  score. Weaker floor than COMPONENT -- directional nudge, not a real
  constraint.
- SEQUENTIAL: reserved, no pair landed here in the first cut.
- ONTOLOGY_OVERLAP: labels genuinely collide on the same physical event.
  No probability constraint -- flag for manual audit, never auto-correct.

Two EXCLUSIVE pairs are horizon-dependent (raid-invasion, blockade-
invasion): substitution at the initial-move decision, but not mutually
exclusive across a long contract window. Ceiling only applies when the
tighter market's days_remaining is below the threshold.
"""

from collections import defaultdict

EXCLUSIVE_CEILING = 1.25

COMPONENT_FRACTIONS = {
    ("airstrike", "ground_invasion"):       0.65,
    ("missile_strike", "ground_invasion"):  0.50,
    ("seizure_boarding", "naval_blockade"): 0.40,
}
CONDITIONAL_COMPONENT_FRACTIONS = {
    ("missile_strike", "naval_blockade"): 0.25,
    ("airstrike", "naval_blockade"):      0.25,
}

ACTION_PAIR_RELATIONS = {
    frozenset({"gray_zone_incident", "seizure_boarding"}):  "ONTOLOGY_OVERLAP",
    frozenset({"gray_zone_incident", "raid"}):               "EXCLUSIVE",
    frozenset({"gray_zone_incident", "missile_strike"}):     "EXCLUSIVE",
    frozenset({"gray_zone_incident", "airstrike"}):          "EXCLUSIVE",
    frozenset({"gray_zone_incident", "naval_blockade"}):     "ONTOLOGY_OVERLAP",
    frozenset({"gray_zone_incident", "ground_invasion"}):    "EXCLUSIVE",
    frozenset({"seizure_boarding", "raid"}):                 "EXCLUSIVE",
    frozenset({"seizure_boarding", "missile_strike"}):       "EXCLUSIVE",
    frozenset({"seizure_boarding", "airstrike"}):            "EXCLUSIVE",
    frozenset({"seizure_boarding", "naval_blockade"}):       "COMPONENT",
    frozenset({"seizure_boarding", "ground_invasion"}):      "EXCLUSIVE",
    frozenset({"raid", "missile_strike"}):                   "EXCLUSIVE",
    frozenset({"raid", "airstrike"}):                        "EXCLUSIVE",
    frozenset({"raid", "naval_blockade"}):                   "EXCLUSIVE",
    frozenset({"raid", "ground_invasion"}):                  "EXCLUSIVE",
    frozenset({"missile_strike", "airstrike"}):               "ONTOLOGY_OVERLAP",
    frozenset({"missile_strike", "naval_blockade"}):          "CONDITIONAL_COMPONENT",
    frozenset({"missile_strike", "ground_invasion"}):         "COMPONENT",
    frozenset({"airstrike", "naval_blockade"}):               "CONDITIONAL_COMPONENT",
    frozenset({"airstrike", "ground_invasion"}):              "COMPONENT",
    frozenset({"naval_blockade", "ground_invasion"}):        "EXCLUSIVE",
}

HORIZON_DEPENDENT_PAIRS = {
    frozenset({"raid", "ground_invasion"}):            60,
    frozenset({"naval_blockade", "ground_invasion"}):  60,
}

_TYPES = ["gray_zone_incident", "seizure_boarding", "raid", "missile_strike",
          "airstrike", "naval_blockade", "ground_invasion"]
_ALL_PAIRS = {frozenset({a, b}) for i, a in enumerate(_TYPES) for b in _TYPES[i+1:]}
assert _ALL_PAIRS == set(ACTION_PAIR_RELATIONS.keys()), \
    f"action_coherence.py: pair table incomplete or has stray keys: " \
    f"{_ALL_PAIRS ^ set(ACTION_PAIR_RELATIONS.keys())}"
assert len(ACTION_PAIR_RELATIONS) == 21


def check_action_coherence(dyad_markets: list) -> list:
    """
    Takes all currently-active method_specific/target_specific kinetic
    markets for ONE dyad. Applies EXCLUSIVE ceiling rescaling and
    COMPONENT/CONDITIONAL_COMPONENT floor bumps in place, flags
    ONTOLOGY_OVERLAP pairs for audit. Returns the same list; each market
    dict gains a 'coherence_notes' list (empty if untouched). Skips
    markets with action_type=None.

    ONLY adjusts p_b_given_a. Does NOT recompute conditional_p -- caller
    must do that via the real bettor() for any market whose p_b_given_a
    changed. See _run_action_coherence_pass() in translator.py.
    """
    scored = [m for m in dyad_markets
              if m.get("action_type") and m.get("p_b_given_a") is not None]
    for m in dyad_markets:
        m.setdefault("coherence_notes", [])
    if len(scored) < 2:
        return dyad_markets

    linked_ids = set()
    for i, m1 in enumerate(scored):
        for m2 in scored[i + 1:]:
            key = frozenset({m1["action_type"], m2["action_type"]})
            if ACTION_PAIR_RELATIONS.get(key) != "EXCLUSIVE":
                continue
            threshold = HORIZON_DEPENDENT_PAIRS.get(key)
            if threshold is not None:
                days = min(m1.get("days_remaining", 999), m2.get("days_remaining", 999))
                if days >= threshold:
                    continue
            linked_ids.add(m1["market_id"])
            linked_ids.add(m2["market_id"])

    if linked_ids:
        linked = [m for m in scored if m["market_id"] in linked_ids]
        total = sum(m["p_b_given_a"] for m in linked)
        if total > EXCLUSIVE_CEILING:
            scale = EXCLUSIVE_CEILING / total
            for m in linked:
                old = m["p_b_given_a"]
                m["p_b_given_a"] = round(old * scale, 4)
                m["coherence_notes"].append(
                    f"EXCLUSIVE ceiling: {old}->{m['p_b_given_a']} "
                    f"(sibling sum {total:.3f} > {EXCLUSIVE_CEILING})"
                )

    for m1 in scored:
        for m2 in scored:
            if m1 is m2:
                continue
            rel = ACTION_PAIR_RELATIONS.get(
                frozenset({m1["action_type"], m2["action_type"]}))
            if rel not in ("COMPONENT", "CONDITIONAL_COMPONENT"):
                continue
            table = COMPONENT_FRACTIONS if rel == "COMPONENT" else CONDITIONAL_COMPONENT_FRACTIONS
            key_fwd = (m1["action_type"], m2["action_type"])
            key_rev = (m2["action_type"], m1["action_type"])
            if key_fwd in table:
                part, whole, frac = m1, m2, table[key_fwd]
            elif key_rev in table:
                part, whole, frac = m2, m1, table[key_rev]
            else:
                continue
            floor = round(frac * whole["p_b_given_a"], 4)
            if part["p_b_given_a"] < floor:
                old = part["p_b_given_a"]
                part["p_b_given_a"] = floor
                part["coherence_notes"].append(
                    f"{rel} floor: {old}->{floor} "
                    f"({frac} x {whole['action_type']}'s p_b_given_a={whole['p_b_given_a']})"
                )

    for i, m1 in enumerate(scored):
        for m2 in scored[i + 1:]:
            rel = ACTION_PAIR_RELATIONS.get(
                frozenset({m1["action_type"], m2["action_type"]}))
            if rel == "ONTOLOGY_OVERLAP":
                m1["coherence_notes"].append(
                    f"ONTOLOGY_OVERLAP with {m2['market_id']} ({m2['action_type']}) "
                    f"-- possible Legal Scholar mislabel, audit, no auto-correction")
                m2["coherence_notes"].append(
                    f"ONTOLOGY_OVERLAP with {m1['market_id']} ({m1['action_type']}) "
                    f"-- possible Legal Scholar mislabel, audit, no auto-correction")

    return dyad_markets

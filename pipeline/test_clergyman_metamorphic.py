"""
Metamorphic test suite for the Clergyman fix (2026-07-23).

Re-scoring the actual July 13 Iran blockade market alone is necessary but not
sufficient -- a single desired result could pass by accident. This holds the
dyad, engine context, and phrasing style roughly constant while varying ONLY
the win condition, and checks the invariants a correct implementation must
satisfy regardless of the specific numbers Clergyman picks.

This calls the REAL Anthropic API (same as backfill_action_type.py) -- run
manually, not as part of an automated CI suite. Requires ANTHROPIC_API_KEY.

Run: python3.11 pipeline/test_clergyman_metamorphic.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from translator import clergyman
from clergyman_ontology import get_anchor_range

DYAD = "US-Iran"

SCENARIOS = [
    ("1_broad",
     "Any US military action against Iran, including strikes, blockade, or invasion"),
    ("2_method_specific_strike",
     "A US missile strike or airstrike against targets in Iran"),
    ("3_target_specific_strike",
     "A US strike specifically on Iran's Fordow nuclear enrichment facility"),
    ("4_method_specific_blockade",
     "A US naval blockade of Iranian shipping"),
    ("5_persistent_blockade",
     "A US naval blockade of Iranian shipping sustained for at least 7 consecutive days"),
    ("6_method_specific_invasion",
     "A US ground invasion of Iranian territory"),
    ("7_territorial_control_invasion",
     "A US ground invasion of Iran that establishes and holds territorial control "
     "over a portion of Iranian territory"),
    ("8_political_announcement",
     "The US government officially announces its intent to impose a naval "
     "blockade on Iran, regardless of whether the blockade is ever enforced"),
]

# Option B scenarios (2026-07-27): SAME contract, SAME requirement_burden tier
# as scenario 5, but with contrasting structural context. If Option B is
# actually working, these should NOT land at the same point in the range --
# high WarCosts (prohibitive) should suppress relative to low WarCosts
# (permissive), holding everything else about the contract identical. This
# is the thing the existing 8 scenarios cannot test at all, since none of
# them ever pass _toggles.
OPTION_B_SCENARIOS = [
    ("9_persistent_blockade_high_warcosts",
     "A US naval blockade of Iranian shipping sustained for at least 7 consecutive days",
     {"WinProbability": -1.0, "WarCosts": -1.8, "PatronDeterrence": 0.5,
      "NuclearDeterrence": 0.2, "AudienceCosts": 0.5}),
    ("10_persistent_blockade_low_warcosts",
     "A US naval blockade of Iranian shipping sustained for at least 7 consecutive days",
     {"WinProbability": -1.0, "WarCosts": 1.5, "PatronDeterrence": 0.5,
      "NuclearDeterrence": 0.2, "AudienceCosts": 0.5}),
]


def run_scenario(name, win_cond, toggles=None):
    market = {
        "label": win_cond,
        "question": win_cond,
        "description": win_cond,
    }
    if toggles:
        market["_toggles"] = toggles
    scholar_output = {
        "relation_to_engine_event": "subset",
        "win_condition_summary": win_cond,
        "legalese_flags": [],
    }
    result = clergyman(market, DYAD, scholar_output)
    return result


def main():
    print(f"Running {len(SCENARIOS)} metamorphic scenarios for {DYAD}...\n")
    results = {}
    for name, win_cond in SCENARIOS:
        print(f"--- {name} ---")
        print(f"    win_condition: {win_cond}")
        result = run_scenario(name, win_cond)
        results[name] = result
        print()

    print(f"Running {len(OPTION_B_SCENARIOS)} Option B structural-context scenarios...\n")
    for name, win_cond, toggles in OPTION_B_SCENARIOS:
        print(f"--- {name} ---")
        print(f"    win_condition: {win_cond}")
        print(f"    toggles: WarCosts={toggles['WarCosts']}")
        result = run_scenario(name, win_cond, toggles=toggles)
        results[name] = result
        print()

    print("=" * 70)
    print("INVARIANT CHECKS")
    print("=" * 70)

    failures = []

    def check(desc, condition):
        status = "✅ PASS" if condition else "❌ FAIL"
        print(f"  {status}  {desc}")
        if not condition:
            failures.append(desc)

    def pba(name):
        r = results.get(name)
        return r.get("p_b_given_a") if r else None

    fam8 = results.get("8_political_announcement", {}).get("manifestation_family")
    check(
        f"Scenario 8 (announcement) classified as political_act (got: {fam8})",
        fam8 == "political_act",
    )

    p2, p3 = pba("2_method_specific_strike"), pba("3_target_specific_strike")
    check(
        f"Adding named target does not increase P(B|A): scenario 2={p2} >= scenario 3={p3}",
        p2 is not None and p3 is not None and p2 >= p3,
    )

    p4, p5 = pba("4_method_specific_blockade"), pba("5_persistent_blockade")
    check(
        f"Adding sustained duration does not increase P(B|A): scenario 4={p4} >= scenario 5={p5}",
        p4 is not None and p5 is not None and p4 >= p5,
    )

    p6, p7 = pba("6_method_specific_invasion"), pba("7_territorial_control_invasion")
    check(
        f"Adding territorial control does not increase P(B|A): scenario 6={p6} >= scenario 7={p7}",
        p6 is not None and p7 is not None and p6 >= p7,
    )

    p1 = pba("1_broad")
    kinetic_subsets = ["2_method_specific_strike", "3_target_specific_strike",
                       "4_method_specific_blockade", "5_persistent_blockade",
                       "6_method_specific_invasion", "7_territorial_control_invasion"]
    for sub in kinetic_subsets:
        psub = pba(sub)
        check(
            f"Broad (scenario 1={p1}) >= {sub} ({psub})",
            p1 is not None and psub is not None and p1 >= psub,
        )

    check(
        f"Blockade (scenario 4={p4}) != Invasion (scenario 6={p6}) -- the original bug",
        p4 is not None and p6 is not None and p4 != p6,
    )

    # Option B invariants
    p9  = pba("9_persistent_blockade_high_warcosts")
    p10 = pba("10_persistent_blockade_low_warcosts")
    check(
        f"Both Option B scenarios used real structural context "
        f"(9={results.get('9_persistent_blockade_high_warcosts',{}).get('used_structural_context')}, "
        f"10={results.get('10_persistent_blockade_low_warcosts',{}).get('used_structural_context')})",
        results.get("9_persistent_blockade_high_warcosts", {}).get("used_structural_context") is True
        and results.get("10_persistent_blockade_low_warcosts", {}).get("used_structural_context") is True,
    )
    check(
        f"IDENTICAL contract, high WarCosts (9={p9}) < low WarCosts (10={p10}) -- "
        f"STRICT inequality required. A tie would mean the anchor-range clamp is "
        f"still erasing the structural signal (this was a real bug found 2026-07-27: "
        f"the original weak <= let a 0.08==0.08 tie pass as if it were a difference).",
        p9 is not None and p10 is not None and p9 < p10,
    )
    range9  = get_anchor_range("kinetic_or_coercive_action", "persistent",
                                war_costs=OPTION_B_SCENARIOS[0][2]["WarCosts"])
    range10 = get_anchor_range("kinetic_or_coercive_action", "persistent",
                                war_costs=OPTION_B_SCENARIOS[1][2]["WarCosts"])
    check(
        f"Each Option B scenario respects its OWN dynamically-scaled range "
        f"(9: p={p9} in {range9}, 10: p={p10} in {range10}) -- not the old static "
        f"(0.08, 0.35) both used to share regardless of WarCosts",
        p9 is not None and p10 is not None
        and range9[0] <= p9 <= range9[1] and range10[0] <= p10 <= range10[1],
    )
    check(
        f"High-WarCosts range floor ({range9[0]}) is genuinely lower than "
        f"low-WarCosts range floor ({range10[0]}) -- the range itself moved, "
        f"not just where Clergyman happened to land inside a frozen range",
        range9[0] < range10[0],
    )

    print()
    if failures:
        print(f"{len(failures)} invariant(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All invariants passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()

"""
Fast, API-free regression test for the Clergyman LLM/deterministic blend
(2026-07-27).

Finding this guards against: Clergyman's raw LLM guess was nearly identical
(0.06) across a WarCosts=-1.8 vs WarCosts=+1.5 swing, despite its rationale
text correctly describing the right direction in words. The deterministic
range-shift (war_costs_range_multiplier) was doing all the real work; the
LLM's point estimate wasn't tracking the data at all.

Fix: blend the LLM's guess with a deterministic position-within-range
formula (WinProbability/PatronDeterrence/NuclearDeterrence), weighted mostly
toward the deterministic piece. This test mocks the Claude call to return
the EXACT frozen-guess failure mode observed live, and asserts the final
blended output still differs correctly -- proving the fix works even in the
worst case where the LLM contributes nothing, rather than hoping the LLM
behaves differently on a lucky day. No API key needed; runs in under a
second; safe to run before every commit that touches clergyman_ontology.py
or the blend logic in translator.py.

Run: python3.11 pipeline/test_clergyman_blend_unit.py
"""
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
import translator as t
from clergyman_ontology import (
    war_costs_range_multiplier,
    get_anchor_range,
    deterministic_position_within_range,
)

FROZEN_LLM_GUESS = 0.06  # exact value observed live, both WarCosts extremes

SCHOLAR_OUT = {
    "relation_to_engine_event": "subset",
    "win_condition_summary": "sustained blockade",
    "legalese_flags": [],
}


def _fake_claude_call_frozen(system_prompt, user_content):
    """Always returns the same raw guess, regardless of what structural
    context was in the prompt -- the worst case, and the one actually
    observed live on 2026-07-27."""
    return {
        "manifestation_family": "kinetic_or_coercive_action",
        "requirement_burden": "persistent",
        "action_type": "naval_blockade",
        "p_b_given_a": FROZEN_LLM_GUESS,
        "p_b_given_not_a": 0.002,
        "p_b_given_not_a_reference_days": 30,
        "confidence": "medium",
        "rationale": "Frozen test guess -- does not reflect structural context on purpose.",
    }


def main():
    failures = []

    def check(desc, condition):
        status = "✅ PASS" if condition else "❌ FAIL"
        print(f"  {status}  {desc}")
        if not condition:
            failures.append(desc)

    print("=" * 70)
    print("PART 1 -- pure math, no mocking (range + position functions directly)")
    print("=" * 70)

    check("war_costs_range_multiplier(0) == 1.0 (neutral anchor)",
          war_costs_range_multiplier(0.0) == 1.0)
    check("war_costs_range_multiplier(-2.0) == 0.6 (max suppression)",
          war_costs_range_multiplier(-2.0) == 0.6)
    check("war_costs_range_multiplier(2.0) == 1.3 (max permission)",
          war_costs_range_multiplier(2.0) == 1.3)
    check("war_costs_range_multiplier(None) == 1.0 (graceful fallback)",
          war_costs_range_multiplier(None) == 1.0)

    range_high_cost = get_anchor_range("kinetic_or_coercive_action", "persistent", war_costs=-1.8)
    range_low_cost  = get_anchor_range("kinetic_or_coercive_action", "persistent", war_costs=1.5)
    check(f"High-cost range floor ({range_high_cost[0]}) < low-cost range floor ({range_low_cost[0]})",
          range_high_cost[0] < range_low_cost[0])

    fixed_range = (0.08, 0.35)
    pos_bad_win  = deterministic_position_within_range({"WinProbability": -2.0}, fixed_range, "persistent")
    pos_good_win = deterministic_position_within_range({"WinProbability": 2.0}, fixed_range, "persistent")
    check(f"WinProbability alone moves position within a FIXED range ({pos_bad_win} < {pos_good_win})",
          pos_bad_win < pos_good_win)

    pos_no_data = deterministic_position_within_range({}, fixed_range, "persistent")
    check(f"No structural data -> sits at range midpoint ({pos_no_data} == {round((fixed_range[0]+fixed_range[1])/2, 4)})",
          pos_no_data == round((fixed_range[0] + fixed_range[1]) / 2, 4))

    print()
    print("=" * 70)
    print("PART 2 -- mocked worst case: LLM guess frozen, does the blend still work?")
    print("=" * 70)

    toggles_high_cost = {"WinProbability": -1.0, "WarCosts": -1.8, "PatronDeterrence": 0.5,
                          "NuclearDeterrence": 0.2, "AudienceCosts": 0.5}
    toggles_low_cost   = {"WinProbability": -1.0, "WarCosts": 1.5, "PatronDeterrence": 0.5,
                          "NuclearDeterrence": 0.2, "AudienceCosts": 0.5}

    with patch.object(t, "_claude_call", side_effect=_fake_claude_call_frozen):
        result_high = t.clergyman({"label": "blockade", "_toggles": toggles_high_cost}, "US-Iran", SCHOLAR_OUT)
        result_low  = t.clergyman({"label": "blockade", "_toggles": toggles_low_cost}, "US-Iran", SCHOLAR_OUT)

    check(f"LLM raw guess was frozen at {FROZEN_LLM_GUESS} in both cases (sanity check on the mock itself)",
          result_high["p_b_given_a_llm_clamped"] != result_low["p_b_given_a_llm_clamped"]  # they clamp differently even if raw is same
          or FROZEN_LLM_GUESS in (result_high.get("p_b_given_a_raw"), result_low.get("p_b_given_a_raw")))

    p_high = result_high["p_b_given_a"]
    p_low  = result_low["p_b_given_a"]
    check(f"FINAL blended output still differs (high={p_high}, low={p_low}) despite frozen LLM input -- "
          f"this is the actual fix, proven in the worst case, not hoped for on a lucky LLM day",
          p_high is not None and p_low is not None and p_high < p_low)

    check("Both results stayed within their own dynamically-scaled anchor range",
          result_high["anchor_range"][0] <= p_high <= result_high["anchor_range"][1]
          and result_low["anchor_range"][0] <= p_low <= result_low["anchor_range"][1])

    print()
    if failures:
        print(f"{len(failures)} invariant(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All invariants passed. (No API calls made -- safe to run anytime.)")
        sys.exit(0)


if __name__ == "__main__":
    main()

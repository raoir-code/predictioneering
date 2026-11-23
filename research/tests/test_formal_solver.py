"""No-network falsification tests for generalized calendar pure Markov bargaining."""
import copy
import unittest

from research.factory import formal_solver as solver
from research.factory import formal_workbench as wb


class FormalSolverTests(unittest.TestCase):
    sha = "signed-test-blueprint"
    def scenario(self, **updates):
        x = {
            "schema": wb.CASE_SCHEMA, "blueprint_sha256": self.sha,
            "delta": 0.9, "p0": 0.5,
            "d_A": 0.1, "d_B": 0.1, "c_A": 0.5, "c_B": 0.5,
            "calendar_cycle": list(wb.STATES),
        }
        x.update(updates)
        return x

    def test_claude_worked_example_has_exactly_one_pure_mpe(self):
        r = solver.audit_case(self.scenario(), self.sha)
        self.assertEqual(r["pure_mpe_masks"], [7])
        self.assertFalse(r["contradictions"])
        self.assertEqual(r["masks_checked"], 16)

    def test_multiple_pure_equilibria(self):
        x = self.scenario(delta=0.7, p0=0.4, d_A=0.2,
                          d_B=0.1, c_A=0.1, c_B=0.3)
        r = solver.audit_case(x, self.sha)
        self.assertEqual(r["pure_mpe_masks"], [0, 6])
        self.assertFalse(r["contradictions"])
        self.assertEqual(r["equilibrium_selection_bounds"][
                         "first_phase_possible_war_lags"], [1, "never"])

    def test_revised_proposition_3_expands_unique_peace_guarantee(self):
        # delta=0.7; D=0.022 exceeds the earlier 0.018 bound but
        # falls below the new 0.018/0.7 bound from Claude's revision.
        case = self.scenario(delta=0.7, p0=0.5, d_A=0.0,
                             d_B=0.022, c_A=0.2, c_B=0.3)
        result = solver.audit_case(case, self.sha)
        self.assertEqual(result["pure_mpe_masks"], [0])
        self.assertFalse(result["contradictions"])
        self.assertTrue(result["proposition_3_bound_holds"])
        self.assertTrue(result["proposition_3_improvement_eligible"])
        self.assertLess(result["proposition_3_old_bound"], 0.022)
        self.assertGreater(result["proposition_3_revised_bound"], 0.022)

    def test_just_outside_revised_bound_is_not_certified(self):
        case = self.scenario(delta=0.7, p0=0.5, d_A=0.0,
                             d_B=0.03, c_A=0.2, c_B=0.3)
        result = solver.audit_case(case, self.sha)
        self.assertFalse(result["proposition_3_bound_holds"])
        # Outside a sufficient condition means unclassified, NOT war.
        self.assertFalse(result["contradictions"])

    def test_selection_is_set_valued_without_selection_assumption(self):
        cycle = list(wb.STATES)
        s = solver.selection_bounds(cycle, [0, 6])
        self.assertEqual(s["classification_from_first_phase"],
                         "PEACE_OR_WAR_DEPENDS_ON_EQUILIBRIUM_SELECTION")
        self.assertEqual(s["first_phase_possible_war_lags"], [1, "never"])
        self.assertFalse(s["first_phase_invariant"])
        self.assertEqual(s["per_start_phase"][1]["possible_first_war_lags"],
                         [0, "never"])
        all_peace = solver.selection_bounds(cycle, [0])
        self.assertEqual(all_peace["first_phase_possible_war_lags"], ["never"])
        self.assertTrue(all_peace["first_phase_invariant"])
        all_war = solver.selection_bounds(cycle, [7])
        self.assertEqual(all_war["first_phase_possible_war_lags"], [0])
        self.assertTrue(all_war["first_phase_invariant"])
        self.assertEqual(all_war["per_start_phase"][3]["possible_first_war_lags"],
                         [1])
        self.assertEqual(solver.selection_bounds(cycle, [])[
                         "classification_from_first_phase"],
                         "NO_PURE_EQUILIBRIUM_FOUND")

    def test_constant_power_repeated_ordinary_states(self):
        for n in (1, 2, 3, 6):
            with self.subTest(n=n):
                x = self.scenario(d_A=0.0, d_B=0.0,
                                  calendar_cycle=["ordinary"]*n)
                r = solver.audit_case(x, self.sha)
                self.assertEqual(r["pure_mpe_masks"], [0])
                self.assertFalse(r["contradictions"])

    def test_heterogeneous_repeated_states(self):
        for cycle in (
            ["ordinary", "ordinary", "A_holiday", "ordinary", "B_holiday"],
            ["A_holiday", "A_holiday", "A_holiday", "B_holiday"],
            ["B_holiday", "ordinary", "both_holiday", "both_holiday"],
            ["ordinary", "B_holiday"],
        ):
            with self.subTest(cycle=cycle):
                x = self.scenario(calendar_cycle=cycle)
                r = solver.audit_case(x, self.sha)
                self.assertEqual(r["masks_checked"], 1 << len(cycle))
                self.assertFalse(r["contradictions"])

    def test_reproducible_parameter_sampling_and_effect_guards(self):
        import random
        a = solver.sample_case(random.Random(71), self.sha, 8)
        b = solver.sample_case(random.Random(71), self.sha, 8)
        self.assertEqual(a, b)
        for seed in range(25):
            x = solver.sample_case(random.Random(seed), self.sha, 8)
            r = solver.audit_case(x, self.sha)
            self.assertEqual(r["contradiction_count"], 0)

    def test_tie_break_rejects_unjustified_war_masks(self):
        # With constant p and positive costs, a war-on-path candidate
        # cannot become a valid pure MPE just because a zero residual was
        # obtained at an exactly-indifferent response.
        values = {"delta": 0.7, "p0": 0.5, "d_A": 0.0, "d_B": 0.0,
                  "c_A": 0.5, "c_B": 0.5}
        probabilities = {"ordinary": 0.5}
        r = wb.policy_candidate(values, ["ordinary"], probabilities, 1)
        self.assertFalse(r["passes_numeric_sequential_rationality"])
        t = solver.theorem_predicate(values, ["ordinary"], probabilities, 1)
        self.assertFalse(t["equilibrium_by_draft_fixed_point"])


if __name__ == "__main__":
    unittest.main()

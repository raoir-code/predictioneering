"""Conditional 2x2 game calculations: exact algebra, no inferred novelty."""
import json
from pathlib import Path
import unittest
from copy import deepcopy

from research.factory import paper_sprint, science_mvp, two_by_two_game


MODEL_FILE = Path(__file__).resolve().parents[1] / "examples" / "HOLY_DAYS_2X2_MODEL_CANDIDATE.json"


class HolidayInspectionGameTests(unittest.TestCase):
    def setUp(self):
        self.model = json.loads(MODEL_FILE.read_text())

    def test_mixed_indifference_and_holiday_derivative(self):
        audit = two_by_two_game.verify(self.model)
        self.assertEqual(audit["status"],
                         "symbolic_indifference_verified_INTERIOR_ADMISSIBILITY_PENDING")
        self.assertTrue(audit["algebraic_indifference_identically_zero"])
        self.assertEqual(audit["row_player_first_action_probability"], "(c0 + d*h)/L")
        self.assertEqual(audit["column_player_first_action_probability"], "v/(ell + v)")
        self.assertFalse(audit["full_equilibrium_optimality_verified"])
        self.assertFalse(audit["complete_equilibrium_classification_verified"])
        checks = science_mvp.model_checks(self.model)
        self.assertTrue(checks["all_derivative_signs_verified"])
        self.assertEqual(checks["derivatives"][0]["derivative_sympy"], "d/L")

    def test_disagrees_with_payoffs_fail_closed(self):
        changed = deepcopy(self.model)
        changed["equilibrium"]["expression"] = "v/(v+ell)"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            two_by_two_game.verify(changed)
        changed = deepcopy(self.model)
        changed["normal_form_2x2"]["column_mix_probability"] = "0"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            two_by_two_game.verify(changed)

    def test_unsafe_payoff_expression_blocked(self):
        changed = deepcopy(self.model)
        changed["normal_form_2x2"]["row_payoffs"][0][0] = "__import__('os').system('true')"
        with self.assertRaisesRegex(ValueError, "arithmetic"):
            two_by_two_game.verify(changed)

    def test_no_claim_of_general_holiday_effect(self):
        self.assertIn("condition", self.model["note"].lower())
        self.assertIn("conditional", self.model["comparative_statics"][0]["interpretation"].lower())
        self.assertIn("readiness costs", self.model["comparative_statics"][0]["hypothesis_text"].lower())


if __name__ == "__main__":
    unittest.main()

"""Offline regression tests for source-checked scholarly model records.

These test internal transcription structure and algebraic bookkeeping.
They do not independently establish that the published theorem is true.
"""
import json
from pathlib import Path
import unittest


AUDIT_PATH = Path(__file__).resolve().parents[1] / "model_audits" / "bas_coe_2016_jstor32.json"


class BasCoeModelAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_identity_and_edition_not_conflated_with_indexed_pdf(self):
        source = self.audit
        self.assertEqual(source["paper"]["year"], 2016)
        self.assertEqual(source["edition"]["inspected_pdf_page_count"], 32)
        self.assertFalse(source["edition"]["original_file_committed"])
        self.assertIn("50-page", source["edition"]["caveat"])
        self.assertEqual(source["model"]["proposition_1"]["source"]["jstor_pdf_page"], 9)
        self.assertEqual(source["model"]["game_tree"]["source"]["jstor_pdf_page"], 8)

    def test_stage_transitions_form_valid_probability_distribution(self):
        transition = self.audit["model"]["game_tree"]["stage_transition_probabilities"]
        for epsilon, lam in ((0.1, 0.2), (0.5, 0.5), (0.9, 0.25), (1, 1)):
            first = (1-epsilon) + epsilon*(1-lam) + epsilon*lam
            second = (1-lam) + lam
            self.assertAlmostEqual(first, 1)
            self.assertAlmostEqual(second, 1)
        self.assertEqual(transition["initial_stage_1"]["advance_to_stage_2"],
                         "epsilon * (1 - lambda)")
        self.assertEqual(transition["initial_stage_2"]["acquire_nuclear_weapons"],
                         "lambda")

    def test_proposition_conditions_are_cautiously_labeled(self):
        prop = self.audit["model"]["proposition_1"]
        self.assertIn(r"\frac{\delta\lambda}{1-\delta}",
                      prop["peace_and_eventual_proliferation_iff_latex"])
        self.assertIn(r"(p-p_n)", prop["peace_and_eventual_proliferation_iff_latex"])
        self.assertIn(r"(c_A+c_B)", prop["peace_and_eventual_proliferation_iff_latex"])
        self.assertTrue(prop["status"].endswith("proof_not_checked"))
        self.assertFalse(self.audit["verification"]["appendix_proofs_examined"])
        self.assertEqual(self.audit["verification"]["status"],
                         "partial_source_checked_not_proof_verified")

    def test_audit_does_not_republish_personalized_pdf(self):
        data = AUDIT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("73.132.", data)
        self.assertNotIn("/Users/", data)
        self.assertIn('"original_file_committed": false', data)

if __name__ == "__main__":
    unittest.main()

"""Deterministic, no-network tests for the signed repeated-bargaining adapter."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from research.factory import formal_workbench as fw
from research.factory import theory_fabricator as theory
from research.factory import review_workflow as gates


CANDIDATE = (Path(__file__).resolve().parents[1] / "examples" /
             "HOLY_DAYS_THEORY_BLUEPRINT_CANDIDATE.json")


class FormalWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "research"
        self.home.mkdir()
        self.inputs = Path(self.tmp.name) / "inputs"
        self.inputs.mkdir()
        self.project = "holy-days"
        gates.init(self.home, self.project, "Synthetic formal-bargaining test")
        for stage in ("puzzle", "diagnosis", "literature"):
            source = self.inputs / (stage + ".md")
            source.write_text("# " + stage + "\n\nThis is an artificial test fixture.\n")
            gates.submit(self.home, self.project, stage, [source],
                         "Synthetic source for isolated formal-workbench tests")
            gates.approve(self.home, self.project, stage, "Tester",
                          "Synthetic testing approval only")
        gates.activate_mvp(self.home, self.project)

    def signed(self):
        raw = json.loads(CANDIDATE.read_text(encoding="utf-8"))
        # Fixture must explicitly replicate the selected Holy Days game
        # protocol; do not silently treat the older 2x2 candidate as equivalent.
        raw["baseline"]["canonical_rules"] = (
            "Time is discrete. A chooses Attack or Propose x, B chooses "
            "Accept or Attack; there is no Reject action. Accepting is "
            "a one-period agreement and both retain the ability to attack "
            "in later periods. War is absorbing and costs both sides."
        )
        candidate_file = self.inputs / "corrected.json"
        candidate_file.write_text(json.dumps(raw))
        theory.propose(
            self.home, self.project,
            baseline="Repeated bilateral-war bargaining and one-period peace",
            candidate=candidate_file)
        theory.approve(self.home, self.project,
                       reviewer="Researcher", notes="Explicitly approve the corrected game as a test fixture.")
        return gates.file_sha(theory.folder(self.home, self.project) / "THEORY_BLUEPRINT.json")

    def scenario(self, sha):
        return {
            "schema": fw.CASE_SCHEMA, "blueprint_sha256": sha,
            "delta": 0.9, "p0": 0.5,
            "d_A": 0.0, "d_B": 0.0, "c_A": 0.2, "c_B": 0.3,
            "calendar_cycle": list(fw.STATES),
        }

    def test_cannot_prepare_before_actual_blueprint_approval(self):
        with self.assertRaisesRegex(ValueError, "APPROVE"):
            fw.prepare(self.home, self.project)
        self.assertFalse(fw.outdir(self.home, self.project).exists())

    def test_prepare_pins_approval_and_never_invents_parameters(self):
        sha = self.signed()
        report = fw.prepare(self.home, self.project)
        self.assertEqual(report["status"], "FORMAL_WORK_ORDER_PREPARED_NOT_SOLVED")
        self.assertEqual(report["network_or_paid_api_calls"], 0)
        template = json.loads(Path(report["parameter_template"]).read_text())
        self.assertEqual(template["blueprint_sha256"], sha)
        self.assertIsNone(template["delta"])
        self.assertEqual(template["calendar_cycle"], [])
        contract = json.loads(Path(report["contract"]).read_text())
        self.assertFalse(contract["equilibrium_proven"])
        self.assertFalse(contract["novelty_verified"])
        self.assertEqual(contract["approved_blueprint_sha256"], sha)
        self.assertIn("NOT", Path(report["review"]).read_text())
        self.assertEqual(gates.load(self.home, self.project)["stages"]
                         ["formal_model"]["status"], "not_started")

    def test_symbolic_constant_power_benchmark_existence_is_scope_limited(self):
        sha = self.signed()
        result = fw.constant_power_benchmark_proof()
        self.assertEqual(result["B_incentive_gap_if_binding"], "0")
        self.assertEqual(result["A_peace_minus_war_if_binding"], "c_A + c_B")
        self.assertFalse(result["holiday_equilibrium_proven"])
        self.assertFalse(result["other_SPE_classified"])
        prepared = fw.prepare(self.home, self.project)
        self.assertTrue(Path(prepared["constant_power_benchmark"]).exists())
        self.assertIn("NOT the solution", Path(prepared["constant_power_benchmark"]).read_text())
        self.assertEqual(
            json.loads((fw.outdir(self.home, self.project) /
                        "CONSTANT_POWER_BENCHMARK.json").read_text())["status"],
            "CONSTANT_POWER_STATIONARY_MPE_EXISTENCE_BENCHMARK_ONLY")

    def test_exact_stationary_baseline_offer_and_no_war(self):
        sha = self.signed()
        case = self.scenario(sha)
        result = fw.analyze(case, sha)
        self.assertEqual(result["checked_pure_stationary_policies"], 16)
        self.assertFalse(result["equilibrium_proven"])
        policies = [
            x for x in result["candidates"]
            if all(row["policy"] == "PEACE" for row in x["calendar_policy"])
        ]
        self.assertTrue(policies, "Constant military power should admit a peaceful MPE")
        # x_B = max(0, p-(1-delta)*c_B) = .5 - .1*.3 = .47
        for row in policies[0]["calendar_policy"]:
            self.assertAlmostEqual(row["minimal_acceptable_offer_to_B"], 0.47, places=9)
            self.assertAlmostEqual(row["offer_if_peace"], 0.47, places=9)
            self.assertLessEqual(row["A_deviation_gain"], 1e-9)
        self.assertEqual(result["status"], fw.STATUS)

    def test_all_four_states_and_cycle_values_are_explicit(self):
        sha = self.signed()
        case = self.scenario(sha)
        case["calendar_cycle"] = ["ordinary", "A_holiday", "ordinary", "B_holiday"]
        with self.assertRaisesRegex(ValueError, "each holiday state exactly once"):
            fw.analyze(case, sha)
        case = self.scenario(sha)
        case["blueprint_sha256"] = "not-approved"
        with self.assertRaisesRegex(ValueError, "different approved blueprint"):
            fw.analyze(case, sha)
        case = self.scenario(sha)
        case["delta"] = 1.0
        with self.assertRaisesRegex(ValueError, "strictly"):
            fw.analyze(case, sha)
        case = self.scenario(sha)
        case["d_B"] = 0.8
        with self.assertRaisesRegex(ValueError, "war probabilities"):
            fw.analyze(case, sha)

    def test_demo_is_synthetic_and_cannot_approve_model(self):
        sha = self.signed()
        result = fw.demo(self.home, self.project)
        self.assertEqual(result["status"], fw.STATUS)
        self.assertEqual(result["network_or_paid_api_calls"], 0)
        diagnostic = json.loads(Path(result["diagnostic"]).read_text())
        self.assertEqual(diagnostic["blueprint_sha256"], sha)
        self.assertEqual(diagnostic["case"]["status"],
                         "SYNTHETIC_ILLUSTRATION_NOT_EMPIRICAL")
        self.assertEqual(diagnostic["checked_pure_stationary_policies"], 16)
        self.assertFalse(diagnostic["equilibrium_proven"])
        self.assertFalse(diagnostic["empirical_hypotheses_derived"])
        self.assertFalse((theory.folder(self.home, self.project) /
                          "FORMAL_MODEL_APPROVAL.json").exists())
        self.assertEqual(gates.load(self.home, self.project)["stages"]
                         ["formal_model"]["status"], "not_started")

    def test_revising_architecture_makes_old_numerical_case_stale(self):
        sha = self.signed()
        case = self.scenario(sha)
        theory.reopen(self.home, self.project,
                      reason="Researcher demands a new game protocol")
        with self.assertRaisesRegex(ValueError, "APPROVE"):
            fw.prepare(self.home, self.project)
        with self.assertRaisesRegex(ValueError, "APPROVE"):
            fw.check(self.home, self.project, self.inputs / "nonexistent.json")


if __name__ == "__main__":
    unittest.main()

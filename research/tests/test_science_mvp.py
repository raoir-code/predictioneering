"""Integration checks for the human-gated scientific MVP pipeline.

All research content is explicitly synthetic; approval operations here occur
only within temporary test fixtures, never on a user's live project.
"""
import json
from pathlib import Path
import tempfile
import unittest

from research.factory import paper_sprint, review_workflow as g, science_mvp as mvp, theory_fabricator


class ScientificMVPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "research"
        self.home.mkdir()
        self.project = "holy-days"
        g.init(self.home, self.project, "Synthetic Paper Factory Integration")
        self.scratch = Path(self.temp.name) / "scratch"
        self.scratch.mkdir()

    def approved(self, stage):
        return g.approve(self.home, self.project, stage, "Integration Test",
                         "Synthetic fixture stage accepted for wiring tests only")

    def seed(self):
        for stage in ("puzzle", "diagnosis", "literature"):
            src = self.scratch / (stage + ".md")
            src.write_text("# Synthetic scientific test\n\nAssumptions and sources require review.\n")
            g.submit(self.home, self.project, stage, [src],
                     "Synthetic fixture: not scientific evidence for a publication")
            self.approved(stage)

    def toy_input(self):
        old = paper_sprint.ROOT
        try:
            paper_sprint.ROOT = self.home
            outputs = paper_sprint.demo()
        finally:
            paper_sprint.ROOT = old
        folder = Path(outputs["demo_dir"]) / "inputs"
        return folder / "formal_model.json", folder / "study.json"

    def approved_architecture(self, model_path):
        """Synthetic model architecture signoff is strictly local to this fixture."""
        candidate = {
            "schema": "theory_blueprint_v1", "status": "proposal_NOT_proven",
            "baseline": {
                "family": "complete_information_ultimatum",
                "canonical_rules": "One proposer offers a share to one responder with a stated outside option.",
                "proposer_protocol": "The same proposer moves first and makes the only proposed offer.",
                "rejection_transition": "Responder rejects and each player receives their stated outside option.",
                "discounting": "There is only one round, so intertemporal discounting is not used.",
                "information": "Both agents know the total surplus and responder outside option.",
                "baseline_source_status": "Synthetic textbook benchmark; not scientific novelty evidence."
            },
            "innovation": {
                "one_sentence_change": "Let the one observed responder outside option vary as a declared state, without new actors.",
                "state_variable": "outside_option_state",
                "added_state_variables": ["outside_option_state"],
                "state_values": ["low", "high"],
                "payoff_or_transition_affected": "The responder's reject payoff varies with the known outside option.",
                "added_players": [], "added_actions": []
            },
            "mechanism": {
                "candidate_literature_gap": "This is a synthetic toy example and has no original scholarly contribution.",
                "mechanism": "The responder's alternative opportunity determines their minimum acceptable offer.",
                "null_case": "If the outside option does not change, the equilibrium offer does not change.",
                "rival_explanation": "Any apparent relation could simply reflect how synthetic offers were generated."
            },
            "proof_plan": {
                "solution_concept": "Backward-induction subgame-perfect equilibrium in the single-stage bargaining game.",
                "equilibrium_conditions": "Verify proposer incentive and responder reservation utility with boundary conditions.",
                "off_path_requirements": "Responder actions at all offers and proposer deviations require independent scrutiny.",
                "benchmark_recovery": "Holding the state fixed reduces the game to the simple familiar ultimatum baseline."
            },
            "source_caveats": ["Synthetic fixture only; not a verified novel scientific mechanism."]
        }
        candidate_path = self.scratch / "blueprint_candidate.json"
        candidate_path.write_text(json.dumps(candidate))
        theory_fabricator.propose(self.home, self.project,
            baseline="Simple textbook ultimatum benchmark", candidate=candidate_path)
        theory_fabricator.approve(self.home, self.project,
            reviewer="Integration Test", notes="Approve synthetic game architecture only.")
        source = theory_fabricator.folder(self.home, self.project) / "THEORY_BLUEPRINT.json"
        obj = json.loads(model_path.read_text())
        obj.update({"theory_blueprint_sha256": g.file_sha(source),
                    "baseline_game_family": candidate["baseline"]["family"],
                    "one_change_summary": candidate["innovation"]["one_sentence_change"]})
        model_path.write_text(json.dumps(obj))

    def test_entire_human_gated_scientific_pipeline_produces_unreviewed_overleaf(self):
        self.seed()
        model, spec = self.toy_input()
        memo = self.scratch / "assessment.md"
        memo.write_text("# Synthetic novelty review\n\n" +
            "This deliberately simulated example offers no substantive novelty. " * 9)
        pending = mvp.produce(self.home, self.project, "novelty", assessment_path=memo)
        self.assertEqual(pending["status"], "awaiting_human_approval")
        with self.assertRaises(ValueError):
            mvp.produce(self.home, self.project, "formal_model", model_path=model)
        self.approved("novelty")
        pending = mvp.produce(self.home, self.project, "formal_model", model_path=model)
        self.assertEqual(pending["status"], "awaiting_human_approval")
        self.assertTrue((mvp.draft(self.home, self.project, "formal_model") /
                         "FORMAL_CHECKS.md").exists())
        self.approved("formal_model")
        pending = mvp.produce(self.home, self.project, "hypotheses")
        self.assertEqual(pending["status"], "awaiting_human_approval")
        self.approved("hypotheses")
        pending = mvp.produce(self.home, self.project, "data", spec_path=spec)
        self.assertEqual(pending["status"], "awaiting_human_approval")
        self.approved("data")
        pending = mvp.produce(self.home, self.project, "design", spec_path=spec)
        self.assertEqual(pending["status"], "awaiting_human_approval")
        private_study = mvp.draft(self.home, self.project, "design") / "study.json"
        self.assertTrue(Path(json.loads(private_study.read_text())["data"]["csv_path"]).is_absolute())
        self.approved("design")
        pending = mvp.produce(self.home, self.project, "analysis")
        self.assertEqual(pending["status"], "awaiting_human_approval")
        self.approved("analysis")
        pending = mvp.produce(self.home, self.project, "validation")
        self.assertEqual(pending["status"], "awaiting_human_approval")
        self.approved("validation")
        pending = mvp.produce(self.home, self.project, "manuscript")
        self.assertEqual(pending["status"], "awaiting_human_approval")
        self.assertTrue(Path(pending["archive"]).exists())
        self.approved("manuscript")
        pending = mvp.produce(self.home, self.project, "qc")
        self.assertEqual(pending["status"], "awaiting_human_approval")
        qc = json.loads((mvp.draft(self.home, self.project, "qc") /
                         "FINAL_QC_AUDIT.json").read_text())
        self.assertEqual(qc["status"], "PACKAGE_INTEGRITY_CHECKED_NOT_SCIENTIFIC_QC")
        self.assertTrue(qc["unmet_scientific_qc"])
        self.assertFalse(qc["independent_replication"])
        self.assertEqual(g.overview(self.home, self.project)["awaiting_human"], ["qc"])

    def test_mvp_profile_skips_redundant_gates_and_reorders_design_data(self):
        self.seed()
        old_literature_token = g.require_approved(self.home, self.project, "literature")
        profile = g.activate_mvp(self.home, self.project)
        self.assertEqual(profile["status"], "mvp_activated")
        self.assertEqual(profile["ready_stages"], ["formal_model"])
        self.assertEqual(g.require_approved(self.home, self.project, "literature"), old_literature_token)
        self.assertEqual(len(g.overview(self.home, self.project)["stages"]), 10)
        self.assertEqual(g.load(self.home, self.project)["stages"]["diagnosis"]["status"],
                         "approved")
        self.assertEqual(g.load(self.home, self.project)["stages"]["novelty"]["status"],
                         "not_started")
        model, spec = self.toy_input()
        with self.assertRaisesRegex(ValueError, "THEORY BLUEPRINT"):
            mvp.produce(self.home, self.project, "formal_model", model_path=model)
        self.approved_architecture(model)
        mvp.produce(self.home, self.project, "formal_model", model_path=model)
        self.assertTrue((mvp.draft(self.home, self.project, "formal_model") /
                         "THEORY_BLUEPRINT_APPROVAL.json").is_file())
        self.approved("formal_model")
        mvp.produce(self.home, self.project, "hypotheses")
        self.approved("hypotheses")
        self.assertEqual(g.overview(self.home, self.project)["ready_stages"], ["design"])
        design = mvp.produce(self.home, self.project, "design", spec_path=spec)
        self.assertEqual(design["status"], "awaiting_human_approval")
        approved_plan = mvp.draft(self.home, self.project, "design") / "study.json"
        self.assertTrue(Path(json.loads(approved_plan.read_text())["data"]["csv_path"]).is_absolute())
        self.approved("design")
        self.assertEqual(g.overview(self.home, self.project)["ready_stages"], ["data"])
        mvp.produce(self.home, self.project, "data")
        self.approved("data")
        mvp.produce(self.home, self.project, "analysis")
        self.approved("analysis")
        mvp.produce(self.home, self.project, "validation")
        self.approved("validation")
        paper = mvp.produce(self.home, self.project, "manuscript")
        self.assertTrue(Path(paper["archive"]).exists())
        qc = json.loads((Path(paper["archive"]).parent / "overleaf" / "PAPER_QC.json").read_text())
        self.assertFalse(qc["gates"]["human_novelty_review"])
        self.approved("manuscript")
        qc = mvp.produce(self.home, self.project, "qc")
        self.assertEqual(qc["status"], "awaiting_human_approval")
        self.assertEqual(g.overview(self.home, self.project)["awaiting_human"], ["qc"])

    def test_mvp_profile_preserves_snapshot_dependencies_when_literature_revised(self):
        self.seed()
        g.activate_mvp(self.home, self.project)
        model, _ = self.toy_input()
        self.approved_architecture(model)
        mvp.produce(self.home, self.project, "formal_model", model_path=model)
        self.approved("formal_model")
        g.revise(self.home, self.project, "literature",
                 "New directly relevant original paper alters the synthesis")
        state = g.load(self.home, self.project)
        self.assertEqual(state["stages"]["formal_model"]["status"], "stale")
        self.assertEqual(state["stages"]["diagnosis"]["status"], "approved")
        self.assertIn("literature", g.overview(self.home, self.project)["ready_stages"])

    def test_directed_dyad_panel_guards_reject_ambiguous_and_missing_days(self):
        import pandas as pd
        spec = {"design": {"unit": "dyad", "time": "date", "outcome": "attack"},
                "research_integrity_checks": {
                    "unique_unit_date": True, "complete_unit_daily_panel": True,
                    "require_directed_attack_attribution": True,
                    "direction_verified_column": "direction_verified"}}
        data = pd.DataFrame({
            "dyad": ["A-B", "A-B", "A-B"],
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "attack": [0, 1, 0], "direction_verified": [0, 1, 0]})
        checked = mvp.check_panel_integrity(spec, data)
        self.assertEqual(len(checked["checks"]), 3)
        self.assertFalse(checked["independent_direction_audit"])
        invalid = data.copy()
        invalid.loc[1, "direction_verified"] = 0
        with self.assertRaisesRegex(ValueError, "Unverified"):
            mvp.check_panel_integrity(spec, invalid)
        with self.assertRaisesRegex(ValueError, "Missing unit-day"):
            mvp.check_panel_integrity(spec, data.drop(index=1).assign(attack=[0, 1]))
        with self.assertRaisesRegex(ValueError, "Duplicate unit-date"):
            mvp.check_panel_integrity(spec, pd.concat([data, data.iloc[[0]]],
                                                        ignore_index=True))

    def test_no_autoapproval_and_missing_assessment_fails_closed(self):
        self.seed()
        with self.assertRaisesRegex(ValueError, "assessment"):
            mvp.produce(self.home, self.project, "novelty")
        self.assertEqual(g.load(self.home, self.project)["stages"]["novelty"]["status"],
                         "not_started")
        with self.assertRaises(ValueError):
            mvp.produce(self.home, self.project, "design")
        self.assertEqual(mvp.status(self.home, self.project)["ready_for_worker"], ["novelty"])

    def test_wrong_hypotheses_rejected_before_data_approval(self):
        self.seed()
        model, spec = self.toy_input()
        memo = self.scratch / "assessment.md"
        memo.write_text("A source-screening memo without any empirical novelty claim. " * 10)
        mvp.produce(self.home, self.project, "novelty", assessment_path=memo)
        self.approved("novelty")
        mvp.produce(self.home, self.project, "formal_model", model_path=model)
        self.approved("formal_model")
        mvp.produce(self.home, self.project, "hypotheses")
        self.approved("hypotheses")
        obj = json.loads(spec.read_text())
        obj["hypotheses"][0]["prediction"] = "Posthoc reversal of theory prediction"
        altered = self.scratch / "altered_study.json"
        # Keep the original dataset path absolute in altered fixture.
        obj["data"]["csv_path"] = str((spec.parent / obj["data"]["csv_path"]).resolve())
        altered.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, "approved formal-model derivatives"):
            mvp.produce(self.home, self.project, "data", spec_path=altered)
        self.assertEqual(g.load(self.home, self.project)["stages"]["data"]["status"],
                         "not_started")


if __name__ == "__main__":
    unittest.main()

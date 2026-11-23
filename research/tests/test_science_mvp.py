"""Integration checks for the human-gated scientific MVP pipeline.

All research content is explicitly synthetic; approval operations here occur
only within temporary test fixtures, never on a user's live project.
"""
import json
from pathlib import Path
import tempfile
import unittest

from research.factory import paper_sprint, review_workflow as g, science_mvp as mvp


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

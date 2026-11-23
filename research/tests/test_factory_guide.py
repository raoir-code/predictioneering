"""The next-step guide must be read-only, honest about scientific gates."""
import json
from pathlib import Path
import tempfile
import unittest

from research.factory import guide
from research.factory import review_workflow as gates
from research.factory import theory_fabricator as th

CANDIDATE = (Path(__file__).resolve().parents[1] / "examples" /
             "HOLY_DAYS_THEORY_BLUEPRINT_CANDIDATE.json")


class FactoryGuideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "research"
        self.home.mkdir()
        self.work = Path(self.tmp.name) / "source"
        self.work.mkdir()
        self.project = "holy-days"
        gates.init(self.home, self.project, "Fixture for science workflow guide")
        for stage in ("puzzle", "diagnosis", "literature"):
            path = self.work / (stage + ".md")
            path.write_text("# " + stage +
                            "\n\nSource screening is synthetic and unverified.\n")
            gates.submit(self.home, self.project, stage, [path],
                         "Source screen fixture, not a research result")
            gates.approve(self.home, self.project, stage, "Tester",
                          "Approve isolated fixture for guide testing")
        gates.activate_mvp(self.home, self.project)

    def test_guide_reports_no_blueprint_and_never_creates_one(self):
        report = guide.guide(self.home, self.project)
        self.assertEqual(report["stage"], "formal_model")
        self.assertIn("Create", report["next_action"])
        self.assertFalse(th.folder(self.home, self.project).exists())
        self.assertEqual(report["network_or_paid_api_calls"], 0)

    def test_guide_reports_next_review_after_claude_proposal(self):
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining with costly war",
                   candidate=CANDIDATE)
        report = guide.guide(self.home, self.project)
        self.assertEqual(report["stage"], "formal_model")
        self.assertEqual(report["blueprint_revision"], 0)
        self.assertIn("theory_fabricator review holy-days", report["command"])
        self.assertIn("human", " ".join(report["notes"]).lower())
        self.assertFalse((th.folder(self.home, self.project) /
                          "BLUEPRINT_APPROVAL.json").exists())

    def test_guide_does_not_claim_approved_architecture_is_solved(self):
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining with costly war",
                   candidate=CANDIDATE)
        th.approve(self.home, self.project, reviewer="Scientist",
                   notes="Architecture approved only; mathematical solution pending")
        report = guide.guide(self.home, self.project)
        self.assertEqual(report["stage"], "formal_model")
        self.assertIn("Prepare", report["next_action"])
        self.assertIn("formal_workbench prepare", report["command"])
        self.assertEqual(report["network_or_paid_api_calls"], 0)

    def test_guide_scaffolds_then_runs_numerical_diagnostics(self):
        from research.factory import formal_workbench as fw
        candidate = json.loads(CANDIDATE.read_text())
        candidate["baseline"]["canonical_rules"] = (
            "A chooses Attack or an offer; B chooses Accept or Attack; "
            "there is no Reject action. Accept is a one-period agreement."
        )
        source = self.work / "approved_game.json"
        source.write_text(json.dumps(candidate))
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining with bilateral war",
                   candidate=source)
        th.approve(self.home, self.project, reviewer="Scientist",
                   notes="Accepted numerical adapter fixture")
        before = guide.guide(self.home, self.project)
        self.assertIn("formal_workbench prepare", before["command"])
        fw.prepare(self.home, self.project)
        middle = guide.guide(self.home, self.project)
        self.assertIn("formal_workbench demo", middle["command"])
        fw.demo(self.home, self.project)
        after = guide.guide(self.home, self.project)
        self.assertIn("formal_model --model", after["command"])
        self.assertIn("independently verify", after["next_action"])
        self.assertFalse((th.folder(self.home, self.project) /
                          "FORMAL_MODEL_APPROVAL.json").exists())

    def test_guide_warns_about_unresolved_newer_claude_attempt(self):
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining with costly war",
                   candidate=CANDIDATE)
        dest = th.folder(self.home, self.project)
        path = dest / "attempts" / "CLAUDE_PARTIAL_test.diagnostic.json"
        th.write(path, {
            "status": "TRUNCATED_OR_INVALID_MODEL_OUTPUT",
            "prior_blueprint_sha256": gates.file_sha(dest / "THEORY_BLUEPRINT.json"),
        })
        report = guide.guide(self.home, self.project)
        self.assertIn("failed newer Claude", " ".join(report["notes"]))
        self.assertEqual(report["network_or_paid_api_calls"], 0)


if __name__ == "__main__":
    unittest.main()

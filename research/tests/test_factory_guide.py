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
        self.assertIn("Solve", report["next_action"])
        self.assertIn("formal_model --model", report["command"])
        self.assertEqual(report["network_or_paid_api_calls"], 0)

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

"""Offline tests: no paid calls or silent model approval."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from research.factory import review_workflow as gates, theory_fabricator as th

CANDIDATE = (Path(__file__).resolve().parents[1] / "examples" /
             "HOLY_DAYS_THEORY_BLUEPRINT_CANDIDATE.json")


class TheoryFabricatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "research"
        self.home.mkdir()
        self.work = Path(self.tmp.name) / "source"
        self.work.mkdir()
        self.project = "holy-days"
        gates.init(self.home, self.project, "Synthetic test of Holy Days theory architecture")
        for stage in ("puzzle", "diagnosis", "literature"):
            p = self.work / (stage + ".md")
            p.write_text("# Signed " + stage + "\n\nResearch question and primary sources not independently checked.\n")
            gates.submit(self.home, self.project, stage, [p],
                         "Synthetic approved source for theory-fabricator tests")
            gates.approve(self.home, self.project, stage, "Tester",
                          "Approve synthetic test source without scholarly claims")

    def candidate(self):
        return json.loads(CANDIDATE.read_text())

    def stage(self):
        return th.folder(self.home, self.project)

    def test_brief_uses_signed_sources_not_hypotheses_or_solver(self):
        bundle, folder = th.brief(
            self.home, self.project,
            baseline="Infinitely repeated ultimatum with calendar state")
        self.assertEqual(bundle["upstream"]["puzzle"]["token"],
                         gates.require_approved(self.home, self.project, "puzzle"))
        self.assertIn("literature_screen", bundle)
        self.assertIn("model", (folder / "THEORY_BRIEF.md").read_text().lower())
        self.assertFalse((folder / "BLUEPRINT_APPROVAL.json").exists())

    def test_single_calendar_change_and_full_proof_plan(self):
        c = th.validate(self.candidate())
        self.assertEqual(c["innovation"]["state_values"],
                         ["ordinary", "A_holiday", "B_holiday", "both_holiday"])
        altered = copy.deepcopy(c)
        altered["innovation"]["added_actions"] = ["Attack"]
        with self.assertRaisesRegex(ValueError, "players or actions"):
            th.validate(altered)
        altered = copy.deepcopy(c)
        altered["innovation"]["added_state_variables"] = ["holiday_state", "extra_state"]
        with self.assertRaisesRegex(ValueError, "Exactly one"):
            th.validate(altered)

    def test_human_blueprint_approval_provenance_and_change_guard(self):
        result = th.propose(self.home, self.project,
            baseline="Infinite repeated ultimatum bargaining",
            candidate=CANDIDATE)
        self.assertEqual(result["status"], "BLUEPRINT_PROPOSED_UNREVIEWED")
        model = {"baseline_game_family": "infinite_horizon_repeated_ultimatum_bargaining",
                 "one_change_summary": self.candidate()["innovation"]["one_sentence_change"],
                 "theory_blueprint_sha256": gates.file_sha(
                     self.stage() / "THEORY_BLUEPRINT.json")}
        with self.assertRaisesRegex(ValueError, "signed THEORY BLUEPRINT"):
            th.require_blueprint(self.home, self.project, model)
        th.approve(self.home, self.project, reviewer="Researcher",
                   notes="Approve only the repeated-ultimatum/calendar architecture.")
        self.assertEqual(th.require_blueprint(self.home, self.project, model)["schema"],
                         "theory_blueprint_v1")
        bad = dict(model)
        bad["baseline_game_family"] = "one_shot_inspection_game"
        with self.assertRaisesRegex(ValueError, "baseline"):
            th.require_blueprint(self.home, self.project, bad)
        source = self.stage() / "THEORY_BLUEPRINT.json"
        source.write_text(source.read_text().replace("A_holiday", "B_other_holiday"))
        with self.assertRaisesRegex(ValueError, "changed after"):
            th.require_blueprint(self.home, self.project, model)

    def test_revised_literature_invalidates_plan_without_erasing_signature(self):
        th.propose(self.home, self.project,
                   baseline="Infinite repeated ultimatum bargaining", candidate=CANDIDATE)
        th.approve(self.home, self.project, reviewer="Researcher",
                   notes="Provisional approval for testing input invalidation.")
        signed = self.stage() / "BLUEPRINT_APPROVAL.json"
        before = signed.read_bytes()
        gates.revise(self.home, self.project, "literature",
                     "Original scholarly sources change the mechanism and scope")
        with self.assertRaises(ValueError):
            th.require_blueprint(self.home, self.project,
                                  {"theory_blueprint_sha256": "fake"})
        self.assertEqual(before, signed.read_bytes())

    def test_paid_generation_refuses_without_explicit_permission(self):
        called = []
        def transport(*args):
            called.append(True)
            return self.candidate(), {"input_tokens": 100, "output_tokens": 200}, "test"
        offline = th.propose(self.home, self.project,
                             baseline="Infinite repeated ultimatum bargaining")
        self.assertEqual(offline["network_or_paid_api_calls"], 0)
        self.assertFalse(called)
        with self.assertRaisesRegex(ValueError, "confirm-share"):
            th.propose(self.home, self.project,
                       baseline="Infinite repeated ultimatum bargaining",
                       send=True, model="mock", key="secret",
                       input_rate=1, output_rate=1, max_usd=1,
                       transport=transport)
        self.assertFalse(called)
        with self.assertRaisesRegex(ValueError, "Budget guard"):
            th.propose(self.home, self.project,
                       baseline="Infinite repeated ultimatum bargaining",
                       send=True, share=True, model="mock", key="secret",
                       input_rate=200, output_rate=200, max_usd=0.0001,
                       transport=transport)
        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()

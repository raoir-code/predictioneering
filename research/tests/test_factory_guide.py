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
        self.assertIn("formal_reasoner draft", after["command"])
        self.assertIn("auditable equilibrium", after["next_action"])
        self.assertFalse((th.folder(self.home, self.project) /
                          "FORMAL_MODEL_APPROVAL.json").exists())

        from research.factory import formal_reasoner as fr
        from research.factory import formal_solver as solver
        from research.factory import formal_proof_brief as brief
        first_pass = {key: (
            "A provisional mathematical equation and equilibrium claim "
            "for independent algebraic and strategic verification."
        ) for key in fr.FIELDS}
        first_pass.update({
            "schema": fr.SCHEMA,
            "proof_steps": [
                {"claim": "B acceptance threshold",
                 "argument": "Compare the immediate attack payoff to expected continuation.",
                 "domain": "Finite deterministic cycle"},
                {"claim": "A choice",
                 "argument": "Compare peace obtained by offering the threshold to attacking.",
                 "domain": "Fixed bilateral-war game"},
            ],
            "unresolved_gaps": [
                "Independently verify existence, uniqueness and equilibrium selection."
            ]
        })
        local = self.work / "draft.json"
        local.write_text(json.dumps(first_pass))
        fr.draft(self.home, self.project, candidate_file=local)
        need_audit = guide.guide(self.home, self.project)
        self.assertIn("formal_solver audit", need_audit["command"])
        solver.audit(self.home, self.project, cases=2, max_phases=4)
        need_brief = guide.guide(self.home, self.project)
        self.assertIn("formal_proof_brief", need_brief["command"])
        brief.prepare(self.home, self.project)
        need_revision = guide.guide(self.home, self.project)
        self.assertIn("formal_reasoner review", need_revision["command"])
        self.assertIn("@", " ".join(need_revision["notes"]))
        self.assertEqual(need_revision["network_or_paid_api_calls"], 0)
        self.assertEqual(gates.load(self.home, self.project)["stages"]
                         ["formal_model"]["status"], "not_started")

    def test_guide_prioritizes_recovery_of_cutoff_formal_draft(self):
        from research.factory import formal_workbench as fw
        candidate = json.loads(CANDIDATE.read_text())
        candidate["baseline"]["canonical_rules"] = (
            "A chooses Attack or a new offer; B chooses Accept or Attack; "
            "there is no Reject action; acceptance is a one-period agreement."
        )
        source = self.work / "approved_game_for_recovery.json"
        source.write_text(json.dumps(candidate))
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining with bilateral war",
                   candidate=source)
        th.approve(self.home, self.project, reviewer="Scientist",
                   notes="Accepted numerical adapter fixture")
        fw.prepare(self.home, self.project)
        fw.demo(self.home, self.project)
        before = guide.guide(self.home, self.project)
        self.assertIn("formal_reasoner draft", before["command"])
        attempts = fw.outdir(self.home, self.project) / "derivations" / "attempts"
        attempts.mkdir(parents=True, exist_ok=True)
        (attempts / "CLAUDE_FORMAL_PARTIAL_test.txt").write_text(
            '{"schema":"formal_derivation_draft_v1",')
        after = guide.guide(self.home, self.project)
        self.assertIn("formal_reasoner recover", after["command"])
        self.assertIn("zero-cost recovery", after["next_action"])
        self.assertEqual(after["network_or_paid_api_calls"], 0)

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

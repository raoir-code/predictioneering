"""Formal reasoning drafts remain separate from theorem and workflow approval."""
import json
from pathlib import Path
import tempfile
import unittest

from research.factory import formal_reasoner as fr
from research.factory import formal_workbench as fw
from research.factory import theory_fabricator as th
from research.factory import review_workflow as gates

CANDIDATE = (Path(__file__).resolve().parents[1] / "examples" /
             "HOLY_DAYS_THEORY_BLUEPRINT_CANDIDATE.json")


class FormalReasonerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "research"
        self.home.mkdir()
        self.work = Path(self.tmp.name) / "inputs"
        self.work.mkdir()
        self.project = "holy-days"
        gates.init(self.home, self.project, "Formal proof draft test fixture")
        for stage in ("puzzle", "diagnosis", "literature"):
            source = self.work / (stage + ".md")
            source.write_text("# " + stage + "\n\nArtificial test input.\n")
            gates.submit(self.home, self.project, stage, [source],
                         "Synthetic source for formal-model worker tests")
            gates.approve(self.home, self.project, stage,
                          "Tester", "Artificial test evidence approved for checks")

    def signed_work_order(self):
        candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
        candidate["baseline"]["canonical_rules"] = (
            "A chooses Attack or one-period agreement; B chooses Accept "
            "or Attack; there is no Reject action. "
            "Accepting is a one-period agreement and both may attack next period."
        )
        path = self.work / "new_blueprint.json"
        path.write_text(json.dumps(candidate))
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining, bilateral attacks",
                   candidate=path)
        th.approve(self.home, self.project, reviewer="Scientist",
                   notes="Source-isolated mathematical draft test approval")
        return fw.prepare(self.home, self.project)

    def candidate(self):
        data = {key: (
            "An unverified analytical conjecture for the holiday bargaining "
            "game; requires independent checking of offers, incentives and "
            "state-contingent continuation equations."
        ) for key in fr.FIELDS}
        data.update({
            "schema": fr.SCHEMA,
            "proof_steps": [
                {"claim": "Stationary peace candidate",
                 "argument": "Compute the B threshold and A best response for each state.",
                 "domain": "delta lies in (0,1), war costs strictly positive"},
                {"claim": "Check war states",
                 "argument": "Compare both players' attack incentives to continuation payoffs.",
                 "domain": "the entire finite deterministic cycle"},
            ],
            "unresolved_gaps": [
                "Check non-Markov perfect equilibria and cycles of power shifts.",
                "Establish exact parameter regions and possible mixed equilibria.",
            ],
        })
        return data

    def test_never_draft_without_signed_blueprint_and_work_order(self):
        with self.assertRaisesRegex(ValueError, "APPROVE"):
            fr.source_bundle(self.home, self.project)
        self.assertFalse(fr.directory(self.home, self.project).exists())

    def test_offline_candidate_produces_unverified_report_only(self):
        record = self.signed_work_order()
        path = self.work / "proof_candidate.json"
        path.write_text(json.dumps(self.candidate()))
        result = fr.draft(self.home, self.project, candidate_file=path)
        self.assertEqual(result["network_or_paid_api_calls"], 0)
        self.assertFalse(result["formal_model_submitted"])
        saved = json.loads(Path(result["path"]).read_text())
        self.assertFalse(saved["general_equilibrium_proven"])
        self.assertFalse(saved["mathematically_certified"])
        self.assertFalse(saved["novelty_verified"])
        self.assertIn("UNVERIFIED", Path(result["review"]).read_text())
        self.assertEqual(gates.load(self.home, self.project)["stages"]
                         ["formal_model"]["status"], "not_started")

    def test_billable_generation_requires_consent_and_budget(self):
        self.signed_work_order()
        invocations = []
        def model_call(*args):
            invocations.append(args)
            return self.candidate(), {
                "input_tokens": 450, "output_tokens": 700
            }, "mock", ""
        with self.assertRaisesRegex(ValueError, "confirm-share"):
            fr.draft(self.home, self.project, model="mock", key="TEST",
                     input_rate=1, output_rate=1, max_usd=1,
                     transport=model_call)
        self.assertEqual(invocations, [])
        with self.assertRaisesRegex(ValueError, "Conservative API estimate"):
            fr.draft(self.home, self.project, share=True, model="mock",
                     key="TEST", input_rate=500, output_rate=500,
                     max_usd=.0001, transport=model_call)
        self.assertEqual(invocations, [])
        result = fr.draft(self.home, self.project, share=True, model="mock",
                          key="TEST", input_rate=1, output_rate=1,
                          max_usd=1, transport=model_call)
        self.assertEqual(len(invocations), 1)
        self.assertEqual(result["network_or_paid_api_calls"], 1)
        self.assertEqual(result["status"],
                         "UNVERIFIED_FORMAL_DRAFT_REQUIRES_HUMAN_PROOF_AUDIT")

    def test_multiple_revisions_archive_every_successful_draft(self):
        self.signed_work_order()
        first = self.work / "first.json"
        first.write_text(json.dumps(self.candidate()))
        fr.draft(self.home, self.project, candidate_file=first)
        changes = [
            "Correct A's incentive comparison when a costly war is available.",
            "Include non-Markov deviations and demonstrate benchmark recovery.",
        ]
        seen = []
        def transport(bundle, model, key, max_tokens):
            seen.append(bundle)
            data = self.candidate()
            data["candidate_equilibrium"] += "\nRevised draft " + str(len(seen))
            return data, {"input_tokens": 300, "output_tokens": 400}, model, ""
        old = fr.directory(self.home, self.project) / "PROOF_DRAFT.json"
        parent_sha = gates.file_sha(old)
        for feedback in changes:
            result = fr.draft(
                self.home, self.project, feedback=feedback,
                share=True, model="mock", key="TEST", input_rate=1,
                output_rate=1, max_usd=1, transport=transport)
            self.assertEqual(result["network_or_paid_api_calls"], 1)
            self.assertEqual(seen[-1]["previous_proof_sha256"], parent_sha)
            saved = json.loads(old.read_text())
            self.assertEqual(saved["generation"]["parent_draft_sha256"], parent_sha)
            self.assertEqual(saved["generation"]["researcher_feedback"], feedback)
            self.assertTrue((fr.directory(self.home, self.project) /
                             "history" / parent_sha[:16] /
                             "PROOF_DRAFT.json").exists())
            parent_sha = gates.file_sha(old)
        self.assertEqual(len(seen), 2)
        self.assertFalse(gates.load(self.home, self.project)["stages"]
                         ["formal_model"]["status"] == "approved")

    def test_interactive_approve_refuses_to_certify_proof(self):
        self.signed_work_order()
        first = self.work / "first.json"
        first.write_text(json.dumps(self.candidate()))
        fr.draft(self.home, self.project, candidate_file=first)
        answers = iter(["SHOW", "APPROVE", "QUIT"])
        output = []
        result = fr.review(self.home, self.project, share=False, model=None,
                           key=None, input_rate=None, output_rate=None,
                           max_usd=None,
                           ask=lambda _: next(answers), output=output.append)
        self.assertEqual(result["status"], "UNVERIFIED_DRAFT_AWAITING_PROOF_AUDIT")
        self.assertTrue(any("cannot be certified" in x for x in output))
        self.assertEqual(gates.load(self.home, self.project)["stages"]
                         ["formal_model"]["status"], "not_started")


if __name__ == "__main__":
    unittest.main()

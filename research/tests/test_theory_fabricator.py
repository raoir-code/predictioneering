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
        with self.assertRaisesRegex(ValueError, "Conflicting calendar state declarations"):
            th.validate(altered)

    def test_public_calendar_metadata_can_be_declared_exogenous(self):
        raw = self.candidate()
        raw["innovation"]["added_state_variables"] = []
        checked = th.validate(raw)
        self.assertEqual(
            checked["innovation"]["added_state_variables"], ["holiday_state"])
        self.assertEqual(raw["innovation"]["added_state_variables"], [])
        # No silent invention of separate 'country A holiday' and
        # 'country B holiday' variables is permitted.
        invalid = self.candidate()
        invalid["innovation"]["added_state_variables"] = ["A_holiday", "B_holiday"]
        with self.assertRaisesRegex(ValueError, "Conflicting calendar state"):
            th.validate(invalid)

    def test_draft_status_is_normalized_with_original_status_retained(self):
        raw = self.candidate()
        raw["status"] = "draft_pending_human_review"
        validated = th.validate(raw)
        self.assertEqual(validated["status"], "proposal_NOT_proven")
        self.assertEqual(validated["source_status_label"],
                         "draft_pending_human_review")
        self.assertEqual(raw["status"], "draft_pending_human_review")
        raw["status"] = "solved"
        with self.assertRaisesRegex(ValueError, "proof or approval"):
            th.validate(raw)

    def test_saved_claude_attempt_can_replay_without_network_or_loss_of_origin(self):
        input_dir = self.stage() / "attempts"
        input_dir.mkdir(parents=True, exist_ok=True)
        raw = self.candidate()
        raw["status"] = "unreviewed_candidate"
        path = input_dir / "CLAUDE_BLUEPRINT_replay_fixture.json"
        path.write_text(json.dumps(raw))
        result = th.propose(self.home, self.project,
            baseline="Infinitely repeated bargaining with costly war",
            candidate=path)
        self.assertEqual(result["network_or_paid_api_calls"], 0)
        self.assertEqual(result["origin"], "saved_claude_api_replay")
        self.assertIn("replayed saved Claude API proposal",
            (self.stage() / "BLUEPRINT_REVIEW.md").read_text())
        saved = json.loads((self.stage() / "THEORY_BLUEPRINT.json").read_text())
        self.assertEqual(saved["source_status_label"], "unreviewed_candidate")
        self.assertEqual(saved["status"], "proposal_NOT_proven")

    def test_rejected_paid_result_preserved_and_replayable_without_api(self):
        import re
        broken = self.candidate()
        broken["innovation"]["added_state_variables"] = [
            "A_holiday", "B_holiday"]
        calls = []
        def transport(bundle, model, key, max_tokens):
            calls.append(True)
            return broken, {"input_tokens": 40, "output_tokens": 120}, model
        with self.assertRaisesRegex(ValueError, "Raw response preserved"):
            th.propose(self.home, self.project,
                       baseline="Repeated ultimatum with one holiday calendar",
                       send=True, share=True, model="mock", key="TEST",
                       input_rate=1, output_rate=1, max_usd=1,
                       transport=transport)
        self.assertEqual(len(calls), 1)
        saved = list((self.stage() / "attempts").glob("CLAUDE_BLUEPRINT_*.json"))
        saved = [p for p in saved if not p.name.endswith(".diagnostic.json")]
        self.assertEqual(len(saved), 1)
        self.assertEqual(json.loads(saved[0].read_text()), broken)
        self.assertTrue(saved[0].with_suffix(".diagnostic.json").is_file())
        self.assertFalse((self.stage() / "THEORY_BLUEPRINT.json").exists())
        # A scientist reviews/corrects a copy of the raw response and replays
        # locally: this must not re-trigger Claude.
        corrected = self.work / "REVIEWED_CLAUDE_BLUEPRINT.json"
        broken["innovation"]["added_state_variables"] = ["holiday_state"]
        corrected.write_text(json.dumps(broken))
        result = th.propose(self.home, self.project,
                            baseline="Repeated ultimatum with one holiday calendar",
                            candidate=corrected)
        self.assertEqual(result["network_or_paid_api_calls"], 0)
        self.assertEqual(len(calls), 1)

    def test_human_blueprint_approval_provenance_and_change_guard(self):
        result = th.propose(self.home, self.project,
            baseline="Infinite repeated ultimatum bargaining",
            candidate=CANDIDATE)
        self.assertEqual(result["status"], "BLUEPRINT_PROPOSED_UNREVIEWED")
        packet = Path(result["review_packet"]).read_text()
        self.assertIn("Conventional baseline", packet)
        self.assertIn("Proposer protocol", packet)
        self.assertIn("One innovation", packet)
        self.assertIn("Could also be no effect", packet)
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

    def test_manual_stage_approval_cannot_bypass_theory_blueprint(self):
        gates.activate_mvp(self.home, self.project)
        file = self.work / "formal_model.json"
        file.write_text('{"title":"Unrelated, unsupported inspection game"}')
        gates.submit(self.home, self.project, "formal_model", [file],
                     "Manually supplied, unsupported model must fail architecture control")
        with self.assertRaisesRegex(ValueError, "signed THEORY BLUEPRINT"):
            gates.approve(self.home, self.project, "formal_model",
                          "Researcher", "Trying to approve without baseline screening")
        self.assertEqual(gates.load(self.home, self.project)["stages"]["formal_model"]["status"],
                         "awaiting_human_approval")

    def test_truncated_or_bad_claude_json_preserves_existing_blueprint(self):
        import io
        from unittest.mock import patch
        th.propose(self.home, self.project,
                   baseline="Infinite repeated ultimatum bargaining",
                   candidate=CANDIDATE)
        existing = (self.stage() / "THEORY_BLUEPRINT.json").read_bytes()
        for response, expected in [
            ({"stop_reason": "max_tokens", "content": [{"type": "text",
               "text": '{"schema":"theory_blueprint_v1","baseline":"cut'}]},
             "truncated"),
            ({"stop_reason": "end_turn", "content": [{"type": "text",
               "text": '{"schema":"theory_blueprint_v1","baseline":"cut'}]},
             "invalid JSON"),
        ]:
            with self.subTest(expected=expected):
                with patch("urllib.request.urlopen",
                           return_value=io.BytesIO(json.dumps(response).encode())):
                    with self.assertRaisesRegex(ValueError, expected):
                        th.propose(self.home, self.project,
                                   baseline="Infinite repeated ultimatum bargaining",
                                   send=True, share=True, model="test-model",
                                   key="TEST_KEY_NOT_A_REAL_SECRET", input_rate=1,
                                   output_rate=1, max_usd=1, max_tokens=6000)
                self.assertEqual(existing,
                                 (self.stage() / "THEORY_BLUEPRINT.json").read_bytes())
                self.assertFalse((self.stage() / "BLUEPRINT_APPROVAL.json").exists())

    def test_configurable_output_cap_transmitted_to_model(self):
        observed = []
        def transport(bundle, model, key, max_tokens):
            observed.append(max_tokens)
            return self.candidate(), {"input_tokens": 30,
                                      "output_tokens": 90}, model
        earlier = th.propose(self.home, self.project,
            baseline="Infinitely repeated ultimatum bargaining",
            candidate=CANDIDATE)
        before = (self.stage() / "THEORY_BLUEPRINT.json").read_bytes()
        original_sha = __import__("hashlib").sha256(before).hexdigest()[:16]
        result = th.propose(self.home, self.project,
            baseline="Infinitely repeated ultimatum bargaining",
            send=True, share=True, model="mock", key="TEST",
            input_rate=1, output_rate=1, max_usd=1,
            max_tokens=6000, transport=transport)
        self.assertEqual(observed, [6000])
        self.assertEqual(result["status"], "BLUEPRINT_PROPOSED_UNREVIEWED")
        self.assertEqual(result["network_or_paid_api_calls"], 1)
        self.assertEqual(result["origin"], "claude_api")
        self.assertIn("Claude API (mock)", (self.stage() / "BLUEPRINT_REVIEW.md").read_text())
        self.assertEqual(before, (self.stage() / "history" / original_sha /
                                  "THEORY_BLUEPRINT.json").read_bytes())

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

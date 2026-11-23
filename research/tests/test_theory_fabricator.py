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
        for harmless in ("unverified", "not_solved", "not_approved"):
            raw["status"] = harmless
            self.assertEqual(th.validate(raw)["status"], "proposal_NOT_proven")
        raw["status"] = (
            "blueprint_only_unsolved: no equilibrium derived, no hypotheses stated, "
            "novelty not assessed. Upstream puzzle approved only for Diagnosis. "
            "The literature screen is abstract-level only."
        )
        validated = th.validate(raw)
        self.assertEqual(validated["status"], "proposal_NOT_proven")
        self.assertEqual(validated["source_status_label"], raw["status"])
        self.assertEqual(raw["status"].count("approved"), 1)
        raw["status"] = "model_approved: equilibrium solved and proof verified"
        with self.assertRaisesRegex(ValueError, "proof or approval"):
            th.validate(raw)
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
        self.assertIn("Generator's original status note (unverified):",
                      (self.stage() / "BLUEPRINT_REVIEW.md").read_text())

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

    def test_reopen_archives_approval_without_rewriting_blueprint(self):
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining with war", candidate=CANDIDATE)
        before = gates.file_sha(self.stage() / "THEORY_BLUEPRINT.json")
        th.approve(self.home, self.project, reviewer="Scientist",
                   notes="Premature architecture approval for regression test.")
        result = th.reopen(self.home, self.project,
                           reason="Latest draft did not incorporate requested revision.")
        self.assertEqual(result["status"], "ARCHITECTURE_REOPENED_UNREVIEWED")
        self.assertEqual(before, gates.file_sha(self.stage() / "THEORY_BLUEPRINT.json"))
        self.assertFalse((self.stage() / "BLUEPRINT_APPROVAL.json").exists())
        saved = list((self.stage() / "approval_history").glob("*.json"))
        self.assertEqual(len(saved), 1)
        withdrawn = json.loads(saved[0].read_text())
        self.assertEqual(withdrawn["blueprint_sha256"], before)
        self.assertIn("Latest draft", withdrawn["withdrawal_reason"])
        with self.assertRaisesRegex(ValueError, "signed THEORY BLUEPRINT"):
            th.require_blueprint(self.home, self.project, {
                "theory_blueprint_sha256": before})

    def test_approval_guard_requires_explicit_stale_blueprint_acknowledgement(self):
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining with war", candidate=CANDIDATE)
        old_sha = gates.file_sha(self.stage() / "THEORY_BLUEPRINT.json")
        attempts = self.stage() / "attempts"
        attempts.mkdir(parents=True, exist_ok=True)
        th.write(attempts / "CLAUDE_PARTIAL_trial.diagnostic.json", {
            "status": "TRUNCATED_OR_INVALID_MODEL_OUTPUT",
            "prior_blueprint_sha256": old_sha,
        })
        with self.assertRaisesRegex(ValueError, "newer Claude revision FAILED"):
            th.approve(self.home, self.project, reviewer="Scientist",
                       notes="Attempt to approve an outdated draft")
        self.assertFalse((self.stage() / "BLUEPRINT_APPROVAL.json").exists())
        answers = iter(["APPROVE", "QUIT"])
        outputs = []
        result = th.review(
            self.home, self.project,
            ask=lambda _: next(answers), output=outputs.append)
        self.assertEqual(result["status"], "AWAITING_HUMAN_REVIEW")
        self.assertTrue(any("NOT APPROVED" in output for output in outputs))
        self.assertFalse((self.stage() / "BLUEPRINT_APPROVAL.json").exists())
        explicit = th.review(
            self.home, self.project,
            ask=lambda _: "APPROVE CURRENT", output=lambda _: None)
        self.assertEqual(explicit["status"], "ARCHITECTURE_APPROVED_NOT_SOLVED")
        approval = json.loads((self.stage() / "BLUEPRINT_APPROVAL.json").read_text())
        self.assertEqual(len(approval["explicitly_accepted_unresolved_attempts"]), 1)

    def test_reopen_blocks_if_formal_model_stage_is_approved(self):
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining with war", candidate=CANDIDATE)
        th.approve(self.home, self.project, reviewer="Scientist",
                   notes="Architecture accepted for this test.")
        # A downstream formal-model signature must never silently remain live.
        project_state = gates.load(self.home, self.project)
        project_state["stages"]["formal_model"]["status"] = "approved"
        gates.persist(self.home, self.project, project_state)
        with self.assertRaisesRegex(ValueError, "formal model is already approved"):
            th.reopen(self.home, self.project,
                      reason="Force re-examination of accepted architecture.")
        self.assertTrue((self.stage() / "BLUEPRINT_APPROVAL.json").exists())

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
             "exhausted"),
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
                partials = list((self.stage() / "attempts").glob("CLAUDE_PARTIAL_*.txt"))
                self.assertGreaterEqual(len(partials), 1)
                self.assertTrue(partials[-1].with_suffix(".diagnostic.json").exists())

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

    def test_human_feedback_revises_via_claude_and_archives_old_draft(self):
        import hashlib
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining, bilateral war outside option",
                   candidate=CANDIDATE)
        existing = (self.stage() / "THEORY_BLUEPRINT.json").read_bytes()
        previous_sha = hashlib.sha256(existing).hexdigest()
        observed = []
        def fake_claude(bundle, model, key, max_tokens):
            observed.append(bundle["revision_request"])
            revision = self.candidate()
            revision["baseline"]["rejection_transition"] = (
                "Either country may separately initiate war or continue "
                "discounted bargaining, and rejection alone does not start war."
            )
            return revision, {"input_tokens": 120, "output_tokens": 300}, model
        feedback = (
            "Both players must have a separate option to initiate war. "
            "A rejected offer should allow another bargaining round. "
            "Public holidays only change relative battlefield effectiveness."
        )
        result = th.revise(
            self.home, self.project, feedback=feedback, share=True,
            model="mock", key="TEST", input_rate=1, output_rate=1,
            max_usd=1, transport=fake_claude)
        self.assertEqual(result["status"], "BLUEPRINT_PROPOSED_UNREVIEWED")
        self.assertEqual(result["network_or_paid_api_calls"], 1)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["feedback"], feedback)
        self.assertEqual(observed[0]["prior_blueprint_sha256"], previous_sha)
        self.assertEqual(observed[0]["prior_blueprint"]["schema"],
                         "theory_blueprint_v1")
        revision = json.loads((self.stage() / "THEORY_BLUEPRINT.json").read_text())
        self.assertEqual(revision["generation"]["revision_of_sha256"], previous_sha)
        self.assertEqual(revision["generation"]["researcher_feedback"], feedback)
        self.assertEqual(revision["generation"]["revision_number"], 1)
        self.assertIn(feedback, (self.stage() / "BLUEPRINT_REVIEW.md").read_text())
        self.assertEqual(existing, (self.stage() / "history" / previous_sha[:16] /
                                    "THEORY_BLUEPRINT.json").read_bytes())
        self.assertFalse((self.stage() / "BLUEPRINT_APPROVAL.json").exists())

    def test_revisions_can_repeat_indefinitely_and_history_keeps_feedback(self):
        import hashlib
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining and costly war",
                   candidate=CANDIDATE)
        prior_sha = gates.file_sha(self.stage() / "THEORY_BLUEPRINT.json")
        feedbacks = [
            "Give both states a unilateral military option alongside bargains.",
            "Let either player reject and wait for a favorable holiday.",
            "Make readiness advantages symmetric when only one player has a holiday."
        ]
        observed = []
        def fake_claude(bundle, model, key, max_tokens):
            observed.append(bundle["revision_request"])
            candidate = self.candidate()
            candidate["baseline"]["rejection_transition"] = (
                "War and waiting are both options, subject to sequential "
                "rationality and explicit player moves. Revision " +
                str(len(observed))
            )
            return candidate, {"input_tokens": 200, "output_tokens": 300}, model
        for n, feedback in enumerate(feedbacks, 1):
            result = th.revise(
                self.home, self.project, feedback=feedback, share=True,
                model="mock", key="TEST", input_rate=1, output_rate=1,
                max_usd=1, max_tokens=12000, transport=fake_claude)
            self.assertEqual(result["network_or_paid_api_calls"], 1)
            self.assertEqual(observed[-1]["prior_blueprint_sha256"], prior_sha)
            current = json.loads((self.stage() / "THEORY_BLUEPRINT.json").read_text())
            self.assertEqual(current["generation"]["revision_number"], n)
            self.assertEqual(current["generation"]["researcher_feedback"], feedback)
            self.assertEqual(current["generation"]["revision_of_sha256"], prior_sha)
            prior_sha = gates.file_sha(self.stage() / "THEORY_BLUEPRINT.json")
        ledger = th.history(self.home, self.project)
        self.assertEqual(ledger["draft_count"], 4)
        self.assertEqual([x["revision_number"] for x in ledger["drafts"]],
                         [0, 1, 2, 3])
        self.assertEqual([x["researcher_feedback"] for x in ledger["drafts"][1:]],
                         feedbacks)
        self.assertTrue(ledger["drafts"][-1]["current"])
        self.assertEqual(ledger["drafts"][-1]["sha256"], prior_sha)
        for i in range(1, 4):
            self.assertEqual(ledger["drafts"][i]["parent_sha256"],
                             ledger["drafts"][i-1]["sha256"])

    def test_truncation_does_not_mutate_current_revision_or_history(self):
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining and costly war",
                   candidate=CANDIDATE)
        before = gates.file_sha(self.stage() / "THEORY_BLUEPRINT.json")
        import io
        from unittest.mock import patch
        simulated = {
            "stop_reason": "max_tokens", "model": "mock",
            "usage": {"input_tokens": 900, "output_tokens": 6000},
            "content": [{"type": "text", "text": '{"schema":"theory_blueprint_v1"'}],
        }
        with patch("urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(simulated).encode())):
            with self.assertRaisesRegex(ValueError, "Partial response preserved"):
                th.revise(self.home, self.project,
                    feedback="The rejected offer allows waiting and both players may fight.",
                    share=True, model="mock", key="TEST",
                    input_rate=1, output_rate=1, max_usd=1, max_tokens=12000)
        self.assertEqual(before, gates.file_sha(self.stage() / "THEORY_BLUEPRINT.json"))
        self.assertEqual(th.history(self.home, self.project)["draft_count"], 1)
        saved = list((self.stage() / "attempts").glob("CLAUDE_PARTIAL_*.txt"))
        self.assertEqual(len(saved), 1)
        diagnostic = json.loads(saved[0].with_suffix(".diagnostic.json").read_text())
        self.assertEqual(diagnostic["prior_blueprint_sha256"], before)
        self.assertEqual(diagnostic["stop_reason"], "max_tokens")
        self.assertIn("both players may fight", diagnostic["revision_feedback"])

    def test_offline_recovery_of_extra_data_retains_revision_lineage(self):
        import hashlib
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining and costly war",
                   candidate=CANDIDATE)
        parent_sha = gates.file_sha(self.stage() / "THEORY_BLUEPRINT.json")
        attempts = self.stage() / "attempts"
        attempts.mkdir(exist_ok=True)
        source = attempts / "CLAUDE_PARTIAL_20261123T182948258460Z.txt"
        raw = self.candidate()
        raw["innovation"]["one_sentence_change"] = (
            "Holidays shift war win chances but no other game primitive changes."
        )
        source.write_text(json.dumps(raw) + "\nSome trailing commentary about proof.")
        th.write(source.with_suffix(".diagnostic.json"), {
            "status": "TRUNCATED_OR_INVALID_MODEL_OUTPUT",
            "stop_reason": "end_turn", "reason": "Extra data",
            "model": "mock", "estimated_charge_usd": .12,
            "prior_blueprint_sha256": parent_sha,
            "revision_feedback": "Allow rejection to continue peace; both may attack.",
            "upstream": th.source_pins(th.source_inputs(self.home, self.project)),
        })
        result = th.recover(self.home, self.project)
        self.assertEqual(result["status"], "BLUEPRINT_PROPOSED_UNREVIEWED")
        self.assertEqual(result["network_or_paid_api_calls"], 0)
        self.assertEqual(result["origin"], "recovered_claude_api")
        self.assertGreater(result["ignored_trailing_characters"], 1)
        draft = json.loads((self.stage() / "THEORY_BLUEPRINT.json").read_text())
        self.assertEqual(draft["generation"]["revision_number"], 1)
        self.assertEqual(draft["generation"]["revision_of_sha256"], parent_sha)
        self.assertIn("Some trailing commentary",
                      draft["generation"]["ignored_trailing_text"])
        self.assertEqual(source.read_text(),
                         json.dumps(raw) + "\nSome trailing commentary about proof.")
        self.assertIn("Recovery note:",
            (self.stage() / "BLUEPRINT_REVIEW.md").read_text())
        self.assertEqual(th.history(self.home, self.project)["draft_count"], 2)

    def test_recovery_rejects_second_json_and_stale_parent(self):
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining and costly war",
                   candidate=CANDIDATE)
        attempts = self.stage() / "attempts"
        attempts.mkdir(exist_ok=True)
        source = attempts / "CLAUDE_PARTIAL_20261123T182948258461Z.txt"
        source.write_text(json.dumps(self.candidate()) + "\n" +
                          json.dumps(self.candidate()))
        sha = gates.file_sha(self.stage() / "THEORY_BLUEPRINT.json")
        diag = {
            "status": "TRUNCATED_OR_INVALID_MODEL_OUTPUT",
            "prior_blueprint_sha256": sha,
            "revision_feedback": "Allow both countries to initiate a costly war.",
            "upstream": th.source_pins(th.source_inputs(self.home, self.project))}
        th.write(source.with_suffix(".diagnostic.json"), diag)
        with self.assertRaisesRegex(ValueError, "more than one JSON"):
            th.recover(self.home, self.project, source=source)
        self.assertEqual(gates.file_sha(self.stage() / "THEORY_BLUEPRINT.json"), sha)
        diag["prior_blueprint_sha256"] = "badsha"
        th.write(source.with_suffix(".diagnostic.json"), diag)
        with self.assertRaisesRegex(ValueError, "differs from"):
            th.recover(self.home, self.project, source=source)

    def test_interactive_review_can_revise_then_approve(self):
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining and costly war",
                   candidate=CANDIDATE)
        received = []
        user_responses = iter([
            "SHOW",
            "Make it clear both countries may attack, and peace can persist.",
            "APPROVE",
        ])
        displayed = []
        def fake_claude(bundle, model, key, max_tokens):
            received.append(bundle["revision_request"]["feedback"])
            return self.candidate(), {"input_tokens": 100,
                                      "output_tokens": 200}, model
        result = th.review(
            self.home, self.project, share=True, model="mock", key="TEST",
            input_rate=1, output_rate=1, max_usd=1,
            ask=lambda prompt: next(user_responses), output=displayed.append,
            transport=fake_claude)
        self.assertEqual(result["status"], "ARCHITECTURE_APPROVED_NOT_SOLVED")
        self.assertEqual(received,
                         ["Make it clear both countries may attack, and peace can persist."])
        self.assertTrue((self.stage() / "BLUEPRINT_APPROVAL.json").exists())
        self.assertTrue(any("What should I change?" in x for x in displayed))
        self.assertTrue(any("One innovation" in x for x in displayed))
        self.assertTrue(any("Claude revised" in x for x in displayed))
        self.assertEqual(th.history(self.home, self.project)["draft_count"], 2)

    def test_interactive_review_does_not_send_without_consent(self):
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining and costly war",
                   candidate=CANDIDATE)
        with self.assertRaisesRegex(ValueError, "confirm-share"):
            th.review(
                self.home, self.project, share=False, model="mock", key="TEST",
                input_rate=1, output_rate=1, max_usd=1,
                ask=lambda prompt: "Make an attack option available to both sides.",
                output=lambda line: None,
                transport=lambda *a: self.fail("No API allowed"))
        self.assertFalse((self.stage() / "BLUEPRINT_APPROVAL.json").exists())

    def test_revision_requires_previous_draft_and_explicit_consent(self):
        feedback = "Make a separate attack option available to both countries."
        opts = dict(feedback=feedback, share=True, model="mock",
                    key="TEST", input_rate=1, output_rate=1, max_usd=1,
                    transport=lambda *a: self.fail("Unexpected API call"))
        with self.assertRaisesRegex(ValueError, "First generate"):
            th.revise(self.home, self.project, **opts)
        th.propose(self.home, self.project,
                   baseline="Repeated bargaining, bilateral war outside option",
                   candidate=CANDIDATE)
        old = (self.stage() / "THEORY_BLUEPRINT.json").read_bytes()
        opts["share"] = False
        with self.assertRaisesRegex(ValueError, "confirm-share"):
            th.revise(self.home, self.project, **opts)
        self.assertEqual(old, (self.stage() / "THEORY_BLUEPRINT.json").read_bytes())
        th.approve(self.home, self.project,
                   reviewer="Scientist", notes="Sign test draft")
        opts["share"] = True
        with self.assertRaisesRegex(ValueError, "reopen"):
            th.revise(self.home, self.project, **opts)

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

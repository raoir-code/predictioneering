"""Offline, no-API contract tests for human-gated scientific stage starters."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
from research import factory
import importlib.util

from research.factory import stage_starter as stage

MODEL = '''# Holy Days\n\nWith positive costs some peaceful bargain always exists.\nAt least one *explicit* friction is required for a repeated model.\nThis is a conditional strike-incentive result not equilibrium.\nThis is not an Israel->Hezbollah directed-dyad estimate.\nZero violence is *not* evidence of negotiated truce.\n'''


class StarterTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.home=Path(self.t.name)
        (self.home/'examples').mkdir()
        (self.home/'examples'/'holy_days_repeated_bargaining_model_v0.md').write_text(MODEL)
        (self.home/'HOLIDAY_FAST_START.md').write_text('The first H1 is observational and not a causal effect.\n')

    def tearDown(self):self.t.cleanup()

    def test_unchanged_puzzle_template_cannot_override_human_revision_request(self):
        from research.factory import review_workflow as g, stage_starter as starter
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)/"research";home.mkdir()
            (home/"examples").mkdir()
            (home/"examples"/"holy_days_repeated_bargaining_model_v0.md").write_text(MODEL)
            (home/"HOLIDAY_FAST_START.md").write_text("Exploratory H1 only")
            g.init(home,"holy-days","Holy Days and War")
            starter.run_puzzle(home,"holy-days",holy_days=True)
            g.revise(home,"holy-days","puzzle","Separate adversary and own holidays in the problem framing")
            with self.assertRaisesRegex(ValueError,"unchanged puzzle template"):
                starter.run_puzzle(home,"holy-days",holy_days=True)
            self.assertEqual(g.overview(home,"holy-days")["ready_stages"],["puzzle"])

    def test_holy_days_revision_preserves_prior_snapshot_and_stays_unapproved(self):
        from research.factory import review_workflow as g, stage_starter as starter
        g.init(self.home, "holy-days", "Holy Days and War")
        original_dir=self.home/"inbox"/"raw"/"scientific_stages"/"holy-days"/"puzzle"
        original_dir.mkdir(parents=True)
        proposal=original_dir/"PUZZLE_REVIEW.md"
        proposal.write_text("# Old puzzle review\\n\\nPremature H1 and ACLED details.\\n")
        provenance=original_dir/"LOCAL_SOURCE_PROVENANCE.json"
        provenance.write_text(json.dumps(starter.prepare_holy_days(self.home)))
        g.submit(self.home,"holy-days","puzzle",[proposal,provenance],
                 "Legacy Holy Days puzzle needing a strictly conceptual revision")
        snapshot=g.location(self.home,"holy-days")/"snapshots"/"puzzle"/"rev0001"/"PUZZLE_REVIEW.md"
        old=snapshot.read_text()
        self.assertIn("Premature H1",old)
        g.revise(self.home,"holy-days","puzzle",
                 "Keep only the strategic opportunity-versus-anticipation tension")
        revised=starter.revise_holy_days_puzzle(self.home,"holy-days")
        self.assertEqual(revised["revision"],2)
        self.assertEqual(revised["status"],"awaiting_human_approval")
        self.assertTrue(snapshot.is_file())
        self.assertEqual(snapshot.read_text(),old)
        self.assertEqual(g.load(self.home,"holy-days")["stages"]["diagnosis"]["status"],"not_started")
        new=g.location(self.home,"holy-days")/"snapshots"/"puzzle"/"rev0002"/"PUZZLE_REVIEW.md"
        self.assertTrue(new.is_file())
        self.assertIn("anticipate",new.read_text().lower())
        with self.assertRaisesRegex(ValueError,"not ready to produce work"):
            starter.revise_holy_days_puzzle(self.home,"holy-days")
        g.approve(self.home,"holy-days","puzzle","Researcher",
                  "I approve the conceptual puzzle for diagnosis only")
        diagnosis=starter.run_diagnosis(self.home,"holy-days")
        diagnosis_text=Path(diagnosis["report"]).read_text()
        self.assertIn("Competing strategic intuitions",diagnosis_text)
        self.assertIn("The potentially vulnerable side",diagnosis_text)
        self.assertNotIn("How, and under which bargaining frictions",diagnosis_text)

    def test_diagnosis_requires_approved_puzzle_and_keeps_decision_pending(self):
        from research.factory import review_workflow as g, stage_starter as starter
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)/"research"; home.mkdir()
            g.init(home,"holy-days","Holy Days and War")
            with self.assertRaisesRegex(ValueError,"not currently approved"):
                starter.run_diagnosis(home,"holy-days")
            source=home/"examples"/"holy_days_repeated_bargaining_model_v0.md"
            source.parent.mkdir(parents=True)
            source.write_text("An approved local theoretical research note.")
            registry=[{"id":"LOCAL-1","path":"examples/holy_days_repeated_bargaining_model_v0.md",
                       "sha256":starter.sha_file(source)}]
            info={"kind":"holy_days_puzzle","question":"Why do holidays matter for conflict?",
                  "source_registry":registry,"traceable_excerpts":[{"issue":"friction"}]}
            inputs=home/"inbox"/"raw"/"seed";inputs.mkdir(parents=True)
            proposal=inputs/"PUZZLE_REVIEW.md"; proposal.write_text("# Provisional puzzle")
            provenance=inputs/"LOCAL_SOURCE_PROVENANCE.json"; provenance.write_text(json.dumps(info))
            g.submit(home,"holy-days","puzzle",[proposal,provenance],
                     "A locally justified draft puzzle requiring formal diagnosis")
            g.approve(home,"holy-days","puzzle","Researcher",
                      "I approve this provisional framing for diagnostic inquiry, not novelty")
            result=starter.run_diagnosis(home,"holy-days")
            self.assertEqual(result["status"],"awaiting_human_approval")
            text=Path(result["report"]).read_text()
            self.assertIn("not a verified Israel",text)
            self.assertIn("APPROVE",text)
            with self.assertRaises(ValueError):
                starter.run_diagnosis(home,"holy-days")
            self.assertEqual(g.overview(home,"holy-days")["awaiting_human"],["diagnosis"])

    def test_puzzle_anchors_retain_real_markdown(self):
        doc=stage.prepare_holy_days(self.home)
        self.assertEqual(len(doc['traceable_excerpts']),5)
        self.assertEqual(doc['novelty_status'],'unassessed_original_papers_not_yet_screened')
        self.assertIn('equilibrium',stage.puzzle_report(doc))
        self.assertIn('not',stage.puzzle_report(doc).lower())

    def test_missing_or_changed_original_source_fail_closed(self):
        src=self.home/'examples'/'holy_days_repeated_bargaining_model_v0.md'
        src.write_text('Theoretical conclusion with no grounding\n')
        with self.assertRaisesRegex(ValueError,'expected measurement/model caveats'):
            stage.prepare_holy_days(self.home)

    def test_no_symlink_source(self):
        src=self.home/'examples'/'holy_days_repeated_bargaining_model_v0.md'
        link=self.home/'link.md';link.symlink_to(src)
        with self.assertRaisesRegex(ValueError,'symlink'):
            stage.read_document(link)

    def test_puzzle_submits_only_ready_unapproved(self):
        fake=types.ModuleType('research.factory.review_workflow')
        fake.require_ready=mock.Mock(return_value={'stages':{'puzzle':{'status':'not_started'}}})
        fake.submit=mock.Mock(return_value={'status':'awaiting_human_approval','stage':'puzzle'})
        with mock.patch.dict(sys.modules,{'research.factory.review_workflow':fake}), mock.patch.object(factory,'review_workflow',fake,create=True):
            output=stage.run_puzzle(self.home,'holy-days',holy_days=True)
        self.assertEqual(output['status'],'awaiting_human_approval')
        self.assertEqual(output['paid_api_calls'],0)
        self.assertNotIn('critic_request',output)
        fake.require_ready.assert_called_once_with(self.home,'holy-days','puzzle')
        fake.submit.assert_called_once()
        self.assertEqual(fake.submit.call_args.args[2],'puzzle')
        self.assertEqual(len(fake.submit.call_args.args[3]),2)

    def test_no_stage_submit_when_approval_missing(self):
        fake=types.ModuleType('research.factory.review_workflow')
        fake.require_ready=mock.Mock(side_effect=ValueError('Required stage diagnosis not approved'))
        fake.submit=mock.Mock()
        with mock.patch.dict(sys.modules,{'research.factory.review_workflow':fake}), mock.patch.object(factory,'review_workflow',fake,create=True):
            with self.assertRaisesRegex(ValueError,'not approved'):
                stage.run_puzzle(self.home,'holy-days',holy_days=True)
        fake.submit.assert_not_called()

    def test_literature_spec_validation(self):
        p=self.home/'queries.json';p.write_text(json.dumps({'search_queries':['holiday and conflict','religious observance bargaining']}))
        _,terms=stage.read_puzzle_spec(p)
        self.assertEqual(len(terms),2)
        p.write_text(json.dumps({'search_queries':[]}))
        with self.assertRaisesRegex(ValueError,'1–4 explicit'):
            stage.read_puzzle_spec(p)

    def test_literature_missing_db_halts_before_approved_packet(self):
        p=self.home/'queries.json';p.write_text(json.dumps({'search_queries':['religious holiday conflict']}))
        fake=types.ModuleType('research.factory.review_workflow');fake.require_ready=mock.Mock(return_value=True);fake.submit=mock.Mock()
        with mock.patch.dict(sys.modules,{'research.factory.review_workflow':fake}), mock.patch.object(factory,'review_workflow',fake,create=True):
            with self.assertRaisesRegex(ValueError,'Missing private indexed PDF'):
                stage.run_literature(self.home,'holy-days',p,self.home/'missing.db')
        fake.submit.assert_not_called()

    def test_literature_no_evidence_requires_more_sources(self):
        p=self.home/'queries.json';p.write_text(json.dumps({'search_queries':['religious holiday conflict']}))
        db=self.home/'index.db';db.write_bytes(b'not an actual database; assembler mocked')
        fake=types.ModuleType('research.factory.review_workflow');fake.require_ready=mock.Mock(return_value=True);fake.submit=mock.Mock()
        literature=types.ModuleType('research.factory.puzzle_evidence')
        literature.assemble=mock.Mock(return_value={'selected_evidence':[],'queries':[]})
        with mock.patch.dict(sys.modules,{'research.factory.review_workflow':fake,'research.factory.puzzle_evidence':literature}), mock.patch.object(factory,'review_workflow',fake,create=True), mock.patch.object(factory,'puzzle_evidence',literature,create=True):
            output=stage.run_literature(self.home,'holy-days',p,db)
        self.assertEqual(output['status'],'blocked_no_page_verified_sources')
        self.assertTrue(Path(output['details']).exists())
        fake.submit.assert_not_called()

    def test_literature_with_verified_page_candidate_goes_to_critique(self):
        p=self.home/'queries.json';p.write_text(json.dumps({'search_queries':['religious holiday conflict']}))
        db=self.home/'index.db';db.write_bytes(b'not an actual database; assembler mocked')
        fake=types.ModuleType('research.factory.review_workflow');fake.require_ready=mock.Mock(return_value=True)
        fake.submit=mock.Mock(return_value={'status':'awaiting_human_approval','stage':'literature'})
        literature=types.ModuleType('research.factory.puzzle_evidence')
        literature.assemble=mock.Mock(return_value={'selected_evidence':[
            {'title':'Paper A','source_id':'zot1','pdf_page':12,'evidence_id':'e1','human_review_status':'not_reviewed','pdf_sha256':'a'*64}],
            'queries':[{'query':'religious holiday conflict','retrieved_candidate_matches':1}]})
        with mock.patch.dict(sys.modules,{'research.factory.review_workflow':fake,'research.factory.puzzle_evidence':literature}), mock.patch.object(factory,'review_workflow',fake,create=True), mock.patch.object(factory,'puzzle_evidence',literature,create=True):
            output=stage.run_literature(self.home,'holy-days',p,db)
        self.assertEqual(output['status'],'awaiting_human_approval')
        self.assertEqual(output['source_count'],1)
        fake.submit.assert_called_once()
        self.assertNotIn('critic_request',output)
        self.assertFalse('approved' in output['status'])


    def test_real_gating_engine_puzzle_integration_when_installed(self):
        try:
            from research.factory import review_workflow as actual
        except ImportError:
            self.skipTest('Review workflow module not available in standalone fixture tree')
        actual.init(self.home,'holy-days','Holy Days and War')
        result=stage.run_puzzle(self.home,'holy-days',holy_days=True)
        self.assertEqual(result['status'],'awaiting_human_approval')
        state=actual.load(self.home,'holy-days')
        self.assertEqual(state['stages']['puzzle']['status'],'awaiting_human_approval')
        with self.assertRaisesRegex(ValueError,'Required stage puzzle'):
            actual.require_ready(self.home,'holy-days','diagnosis')
        self.assertEqual(state['stages']['diagnosis']['status'],'not_started')



if __name__=='__main__':unittest.main()

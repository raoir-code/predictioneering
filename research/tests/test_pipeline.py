"""Research orchestration integration tests; synthetic only, no network or Claude."""
from __future__ import annotations
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.factory import pipeline, prototype


class ResearchPipelineTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home=Path(temp.name)/"research"
        self.home.mkdir()
        self.card_id="a1b2c3d4e5f60123"
        self.card={
            "id":self.card_id,"status":"approved_for_literature_review",
            "title":"Why are repeat conflicts unexpectedly frequent?",
            "phenomenon":"Recurrent conflict appears despite expected peace",
            "expected_theory":"Costly fighting should reduce recurrence",
            "why_puzzling":"Why do disputes recur even when escalation is costly?",
            "candidate_mechanism":"Private information about commitment",
            "testable_prediction":"Disputes recur more after incomplete settlements",
        }
        (self.home/"projects").mkdir(parents=True)
        self.card_path=self.home/"projects"/(self.card_id+".json")
        pipeline.save(self.card_path,self.card)
        self.db=self.home/"dummy_library.sqlite3"
        self.db.write_text("synthetic index sentinel")
        self.bundle={"sources":[
            {"id":"zotero:S1","title":"Relevant Paper One","authors":"A. Author",
             "year":2020,"doi":"https://doi.org/10.1/example","abstract":"Metadata abstract",
             "full_text_verified":False},
            {"id":"zotero:S2","title":"Relevant Paper Two","authors":"B. Author",
             "year":2022,"full_text_verified":False}],
             "hazard_matches":[],"queries":["conflict recurrence"]}

    def setup_literature(self):
        with patch.object(pipeline,"retrieve_local",return_value=self.bundle) as found:
            result=pipeline.run_one(self.home,self.card_id,self.db)
        self.assertEqual(found.call_count,1)
        return result

    def test_unapproved_card_never_starts(self):
        self.card["status"]="pending_human_review"
        pipeline.save(self.card_path,self.card)
        with self.assertRaisesRegex(ValueError,"approval"):
            pipeline.run_one(self.home,self.card_id,self.db)
        self.assertFalse(pipeline.folder(self.home,self.card_id).exists())

    def test_only_safe_intake_id_and_no_path_traversal(self):
        for name in ("../secrets", "project-x", "f"*17,"../../production"):
            with self.assertRaises(ValueError):pipeline.folder(self.home,name)

    def test_initialization_preserves_provenance_and_requires_design(self):
        place,state,_=pipeline.initialize(self.home,self.card_id)
        self.assertEqual(state["network_or_paid_api_calls"],0)
        self.assertEqual(state["card_sha256"],pipeline.digest(self.card_path))
        spec=pipeline.read(place/"analysis_spec.json")
        self.assertIsNone(spec["design"]["method"])
        self.assertIsNone(spec["design"]["outcome"])
        self.assertEqual(spec["hypotheses"][0]["sign"],"unspecified")
        self.assertEqual(spec["novelty_review"]["status"],"pending")
        self.assertIn("Private information",(place/"theory_design_candidates.md").read_text())
        again,_,_=pipeline.initialize(self.home,self.card_id)
        self.assertEqual(again,place)

    def test_missing_library_blocks_safely(self):
        result=pipeline.run_one(self.home,self.card_id,self.home/"missing.sqlite3")
        self.assertEqual(result["status"],"blocked_missing_library")
        self.assertFalse(result["has_analysis_results"])

    def test_literature_to_review_gate_is_no_network(self):
        result=self.setup_literature()
        self.assertEqual(result["status"],"blocked_human_novelty_review")
        place=pipeline.folder(self.home,self.card_id)
        literature=pipeline.read(place/"literature_candidates.json")
        self.assertFalse(literature["full_text_verified"])
        self.assertEqual(literature["external_network_queries"],0)
        self.assertEqual(literature["source_count"],2)
        self.assertFalse((place/"output").exists())
        with patch.object(pipeline,"retrieve_local",side_effect=AssertionError("Should use cache")):
            repeated=pipeline.run_one(self.home,self.card_id,self.db)
        self.assertEqual(repeated["status"],"blocked_human_novelty_review")

    def test_approval_requires_human_attestation_and_source_ids(self):
        self.setup_literature()
        notes="I independently read the two original papers and compared their models and findings."
        with self.assertRaisesRegex(ValueError,"full-text"):
            pipeline.approve(self.home,self.card_id,"Researcher",notes,["zotero:S1"])
        with self.assertRaisesRegex(ValueError,"Source IDs"):
            pipeline.approve(self.home,self.card_id,"Researcher",notes,["invented"],confirmed=True)
        with self.assertRaisesRegex(ValueError,"substantive"):
            pipeline.approve(self.home,self.card_id,"Researcher","yes",["zotero:S1"],confirmed=True)
        result=pipeline.approve(self.home,self.card_id,"Researcher",notes,["zotero:S1"],confirmed=True)
        self.assertEqual(result["status"],"human_novelty_approved")
        place=pipeline.folder(self.home,self.card_id)
        spec=pipeline.read(place/"analysis_spec.json")
        self.assertEqual(spec["novelty_review"]["status"],"approved")
        self.assertEqual(len(spec["literature"]),1)
        self.assertNotIn("abstract",spec["literature"][0])
        with patch.object(pipeline,"retrieve_local",side_effect=AssertionError("cached")):
            state=pipeline.run_one(self.home,self.card_id,self.db)
        self.assertEqual(state["status"],"blocked_design_spec")

    def test_changed_intake_card_invalidates_approval(self):
        self.setup_literature()
        self.card["candidate_mechanism"]="An entirely different proposed mechanism"
        pipeline.save(self.card_path,self.card)
        with self.assertRaisesRegex(ValueError,"source card changed"):
            pipeline.run_one(self.home,self.card_id,self.db)

    def test_no_sources_cannot_be_approved(self):
        with patch.object(pipeline,"retrieve_local",return_value={"sources":[],"hazard_matches":[],"queries":[]}):
            state=pipeline.run_one(self.home,self.card_id,self.db)
        self.assertEqual(state["status"],"blocked_no_literature_candidates")
        with self.assertRaisesRegex(ValueError,"Source IDs"):
            pipeline.approve(self.home,self.card_id,"Researcher","I read the originals and carefully checked the novelty of this question.",["none"],confirmed=True)

    def test_after_approval_design_passes_into_statistical_and_manuscript_engine(self):
        self.setup_literature()
        notes="I read the original work in full and compared each model and reported finding."
        pipeline.approve(self.home,self.card_id,"Researcher",notes,["zotero:S1"],confirmed=True)
        place=pipeline.folder(self.home,self.card_id)
        sample_path=prototype.make_demo(place/"synthetic_fixture")
        sample=prototype.read_json(sample_path)
        spec_path=place/"analysis_spec.json"
        spec=pipeline.read(spec_path)
        spec["data"]={"csv_path":str(prototype.data_file(sample,sample_path)),
                      "redistribution_allowed":False,"synthetic":True}
        spec["design"]=sample["design"]
        pipeline.save(spec_path,spec)
        result=pipeline.run_one(self.home,self.card_id,self.db)
        self.assertEqual(result["status"],"draft_generated_not_publication_ready")
        self.assertEqual(result["analysis_status"],"prototype_complete")
        self.assertTrue((place/"output"/"results.json").exists())
        self.assertFalse(pipeline.read(place/"output"/"QC_REPORT.json")["passes"]["non_synthetic_data"])
        second=pipeline.run_one(self.home,self.card_id,self.db)
        self.assertEqual(second["analysis_status"],"reused_cached_run")
        self.assertEqual(second["network_or_paid_api_calls"],0)

    def test_synthetic_orchestrator_demo_without_external_review(self):
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code=pipeline.main(["--home",str(self.home),"demo"])
        self.assertEqual(code,0)
        result=json.loads(stdout.getvalue())
        self.assertEqual(result["status"],"synthetic_pipeline_demonstration_complete")
        self.assertTrue(result["synthetic_only"])
        self.assertFalse(result["quality"]["passes"]["human_novelty_review"])
        self.assertTrue((Path(result["project"])/"output"/"MANUSCRIPT_DRAFT.md").is_file())
        self.assertEqual(result["network_or_paid_api_calls"],0)


    def test_batch_advances_existing_approved_cards(self):
        with patch.object(pipeline,"retrieve_local",return_value=self.bundle):
            output=pipeline.batch(self.home,self.db)
        self.assertEqual(output["processed"],1)
        self.assertEqual(output["projects"][0]["status"],"blocked_human_novelty_review")
        self.assertEqual(output["network_or_paid_api_calls"],0)

    def test_material_hypothesis_revision_invalidates_novelty_review(self):
        self.setup_literature()
        pipeline.approve(self.home,self.card_id,"Researcher",
            "I independently read two originals and compared their models and claims.",
            ["zotero:S1"],confirmed=True)
        place=pipeline.folder(self.home,self.card_id)
        spec_path=place/"analysis_spec.json"
        spec=pipeline.read(spec_path)
        self.assertTrue(pipeline.review_ok(place,pipeline.read(place/"workflow.json"),spec))
        spec["hypotheses"][0]["prediction"]="Changed testable prediction"
        pipeline.save(spec_path,spec)
        result=pipeline.run_one(self.home,self.card_id,self.db)
        self.assertEqual(result["status"],"blocked_human_novelty_review")

    def test_literature_refresh_without_approved_reference_blocks(self):
        self.setup_literature()
        pipeline.approve(self.home,self.card_id,"Researcher",
            "I independently read two originals and compared their models and claims.",
            ["zotero:S1"],confirmed=True)
        updated={"sources":[self.bundle["sources"][1]],"hazard_matches":[],"queries":[]}
        with patch.object(pipeline,"retrieve_local",return_value=updated):
            result=pipeline.run_one(self.home,self.card_id,self.db,refresh_literature=True)
        self.assertEqual(result["status"],"blocked_human_novelty_review")


    def test_register_conceptual_puzzle_without_hypothesis(self):
        brief=self.home/"conceptual_puzzle.json"
        pipeline.save(brief,{
            "title":"Can predictable holidays alter military conflict?",
            "research_question":"Why would public holidays alter attacks when both sides anticipate the vulnerability?",
            "competing_intuitions":"Attackers might exploit reduced readiness, but defenders can prepare beforehand."
        })
        card_id=pipeline.register(self.home,brief)["card_id"]
        from research.factory.__main__ import main as intake
        self.assertEqual(intake(["--home",str(self.home),"approve",card_id]),0)
        path,_,card=pipeline.initialize(self.home,card_id)
        spec=pipeline.read(path/"analysis_spec.json")
        self.assertEqual(spec["mechanism"],"")
        self.assertEqual(spec["hypotheses"],[])
        self.assertIn("defenders",card["competing_intuitions"])

    def test_register_external_study_brief_requires_intake_review(self):
        brief=self.home/"researcher_puzzle.json"
        pipeline.save(brief,{"title":"A new bargaining puzzle",
          "research_question":"Why does conflict persist after bargaining?",
          "proposed_mechanism":"Informational frictions in repeated negotiation",
          "hypotheses":[{"id":"H1","prediction":"Higher uncertainty predicts renewed violence","sign":"positive"}]})
        result=pipeline.register(self.home,brief)
        self.assertEqual(result["status"],"pending_human_review")
        self.assertEqual(result["network_or_paid_api_calls"],0)
        with self.assertRaisesRegex(ValueError,"approval"):
            pipeline.run_one(self.home,result["card_id"],self.db)
        result2=pipeline.register(self.home,brief)
        self.assertEqual(result2["card_id"],result["card_id"])
        self.assertEqual(result2["status"],"pending_human_review")

if __name__=="__main__":unittest.main()

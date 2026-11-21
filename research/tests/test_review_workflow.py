"""Local, no-paid-API tests of mandatory stage-by-stage scientific signoffs."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research.factory import review_workflow as g


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.ctx = tempfile.TemporaryDirectory()
        self.addCleanup(self.ctx.cleanup)
        self.home = Path(self.ctx.name) / "research"
        self.home.mkdir()
        self.project = "holy-days"
        g.init(self.home,self.project,"Holy Days and War: Scientific Research Factory Pilot")
        self.artifacts = Path(self.ctx.name) / "artifacts"
        self.artifacts.mkdir()

    def source(self, name="puzzle.json", body=None):
        p = self.artifacts/name
        p.write_text(body or '{"question":"Why does conflict change during holy days?"}')
        return p

    def critic_file(self, name="review.json", recommendation="approve", issues=None, reviewer="Independent skeptic"):
        payload = {"reviewer":reviewer,"reviewer_kind":"independent_ai",
                   "recommendation":recommendation,
                   "summary":"Independent review of sources, assumptions and available evidence.",
                   "issues":issues if issues is not None else [],
                   "strengths":[],"open_questions":[]}
        p=self.source(name,json.dumps(payload))
        return p

    def submit(self, stage="puzzle", name=None):
        p=self.source(name or f"{stage}.json")
        return g.submit(self.home,self.project,stage,[p],
                        "Substantive scientific artifact ready for independent review")

    def approve(self, stage="puzzle", *, skip_critic=False):
        if not skip_critic:
            g.critique(self.home,self.project,stage,self.critic_file())
        return g.approve(self.home,self.project,stage,
                         "Researcher","Original literature, model, data and critique reviewed; evidence is sufficient")

    def advance(self, stage="puzzle"):
        self.submit(stage)
        return self.approve(stage)

    def test_init_default_closed(self):
        report=g.overview(self.home,self.project)
        self.assertEqual(report["ready_stages"],["puzzle"])
        self.assertEqual(len(report["stages"]),len(g.STAGES))
        self.assertEqual(report["network_or_paid_api_calls"],0)

    def test_cannot_skip_to_literature(self):
        with self.assertRaisesRegex(ValueError,"not currently approved"):
            self.submit("literature")

    def test_submit_creates_packet_and_does_not_auto_approve(self):
        result=self.submit()
        self.assertEqual(result["status"],"awaiting_critique")
        self.assertIn("Scientific decision checklist",Path(result["review_packet"]).read_text())
        self.assertEqual(g.overview(self.home,self.project)["awaiting_critique"],["puzzle"])
        with self.assertRaisesRegex(ValueError,"no independently critiqued"):
            g.approve(self.home,self.project,"puzzle","Researcher","I checked this decision carefully")

    def test_critique_then_human_approval_unlocks_next_stage(self):
        self.submit()
        g.critique(self.home,self.project,"puzzle",self.critic_file())
        self.assertEqual(g.overview(self.home,self.project)["awaiting_human"],["puzzle"])
        result=self.approve(skip_critic=True)
        self.assertEqual(result["ready_stages"],["diagnosis"])
        self.assertEqual(len(g.require_approved(self.home,self.project,"puzzle")),64)
        self.assertIn("Approved by",g.packet_path(self.home,self.project,"puzzle").read_text())

    def test_critiqued_revision_blocks_approval(self):
        self.submit()
        issue=[{"severity":"major","description":"No credible comparative theory found yet", 
                "suggested_fix":"Read original bargaining scholarship first"}]
        g.critique(self.home,self.project,"puzzle",self.critic_file(recommendation="revise", issues=issue))
        with self.assertRaisesRegex(ValueError,"Critic recommends"):
            g.approve(self.home,self.project,"puzzle","Researcher","I have reviewed the findings carefully")

    def test_critical_override_requires_explicit_reason(self):
        self.submit()
        g.critique(self.home,self.project,"puzzle",self.critic_file(recommendation="reject"))
        with self.assertRaisesRegex(ValueError,"60"):
            g.approve(self.home,self.project,"puzzle","Researcher","Waive",override=True)
        r=g.approve(self.home,self.project,"puzzle","Researcher",
                    "Despite the independent critique, I reviewed the substantive source evidence and explicitly accept the risk.",override=True)
        self.assertEqual(r["status"],"approved")
        self.assertTrue(g.load(self.home,self.project)["stages"]["puzzle"]["approval"]["override"])

    def test_same_reviewer_cannot_approve(self):
        self.submit()
        g.critique(self.home,self.project,"puzzle",self.critic_file(reviewer="Researcher"))
        with self.assertRaisesRegex(ValueError,"independent"):
            g.approve(self.home,self.project,"puzzle","Researcher","I approve after independent critique")

    def test_stale_after_earlier_revision_invalidates_only_descendants(self):
        self.advance("puzzle")
        self.advance("diagnosis")
        self.advance("literature")
        self.advance("novelty")
        g.revise(self.home,self.project,"literature","Original literature review omitted a crucial bargaining paper")
        st=g.load(self.home,self.project)["stages"]
        self.assertEqual(st["puzzle"]["status"],"approved")
        self.assertEqual(st["diagnosis"]["status"],"approved")
        self.assertEqual(st["literature"]["status"],"needs_revision")
        self.assertEqual(st["novelty"]["status"],"stale")
        self.assertEqual(g.overview(self.home,self.project)["ready_stages"],["literature"])
        with self.assertRaisesRegex(ValueError,"not currently approved"):
            g.require_ready(self.home,self.project,"formal_model")

    def test_revised_stage_increments_revision_without_deleting_old_snapshot(self):
        self.advance()
        first=g.load(self.home,self.project)["stages"]["puzzle"]["artifacts"][0]
        old=g.location(self.home,self.project)/first["snapshot"]
        g.revise(self.home,self.project,"puzzle","Mechanism changed after independent contradictory evidence was discovered")
        self.source("puzzle.json",'{"question":"New research puzzle and contrasting theory"}')
        r=self.submit()
        self.assertEqual(r["revision"],2)
        self.assertTrue(old.exists())
        self.assertIn("holy days",old.read_text().lower())

    def test_mutated_approved_artifact_blocks_downstream(self):
        self.advance()
        approved=g.load(self.home,self.project)["stages"]["puzzle"]["artifacts"][0]
        file=g.location(self.home,self.project)/approved["snapshot"]
        file.chmod(0o644)
        file.write_text("hindsight-fabricated change")
        with self.assertRaisesRegex(ValueError,"snapshot"):
            g.require_ready(self.home,self.project,"diagnosis")

    def test_modified_critique_snapshot_blocks_approval(self):
        self.submit()
        g.critique(self.home,self.project,"puzzle",self.critic_file())
        rec=g.load(self.home,self.project)["stages"]["puzzle"]
        path=g.location(self.home,self.project)/rec["critique"]["snapshot"]
        path.chmod(0o644)
        path.write_text('{"changed":"yes"}')
        with self.assertRaisesRegex(ValueError,"changed"):
            self.approve(skip_critic=True)

    def test_reject_keeps_history_and_prevents_downstream(self):
        self.submit()
        out=g.revise(self.home,self.project,"puzzle","No valid research puzzle after contract-rule audit",reject=True)
        self.assertEqual(out["status"],"rejected")
        with self.assertRaises(ValueError):
            self.submit("diagnosis")
        with self.assertRaises(ValueError):
            self.submit()
        g.revise(self.home,self.project,"puzzle","New verified evidence justifies reconsidering this rejected work")
        self.assertEqual(g.overview(self.home,self.project)["ready_stages"],["puzzle"])

    def test_no_duplicate_names_or_symlink(self):
        p=self.source()
        with self.assertRaisesRegex(ValueError,"unique"):
            g.submit(self.home,self.project,"puzzle",[p,p],"Sufficient summary about source document integrity")
        link=self.artifacts/"link.json"
        link.symlink_to(p)
        with self.assertRaisesRegex(ValueError,"symlink"):
            g.submit(self.home,self.project,"puzzle",[link],"Sufficient summary about source document integrity")

    def test_invalid_critic_schema_is_refused(self):
        self.submit()
        with self.assertRaisesRegex(ValueError,"reviewer_kind"):
            g.critique(self.home,self.project,"puzzle",self.source("invalid.json",'{"reviewer":"Bad","summary":"Something was wrong but no evidence here","reviewer_kind":"none","recommendation":"approve","issues":[]}'))

    def test_cannot_submit_untouched_critique_template(self):
        self.submit()
        template=Path(__file__).resolve().parents[1]/"examples"/"INDEPENDENT_CRITIQUE_TEMPLATE.json"
        with self.assertRaisesRegex(ValueError,"placeholder"):
            g.critique(self.home,self.project,"puzzle",template)

    def test_blocker_cannot_recommend_approval(self):
        self.submit()
        issues=[{"severity":"blocker","description":"Model has an invalid mathematical equilibrium", "suggested_fix":"Derive best responses again"}]
        with self.assertRaisesRegex(ValueError,"unresolved blockers"):
            g.critique(self.home,self.project,"puzzle",self.critic_file(issues=issues))

    def test_event_hash_chain_detects_tamper(self):
        self.submit()
        state=g.load(self.home,self.project)
        self.assertEqual(len(state["events"]),1)
        state["events"][0]["details"]["revision"]=99
        g.atomic(g.state_path(self.home,self.project),state)
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            g.require_ready(self.home,self.project,"diagnosis")

    def test_full_sequence_requires_signoff_at_every_stage(self):
        for index, stage in enumerate(g.STAGES):
            self.assertIn(stage,g.overview(self.home,self.project)["ready_stages"])
            self.submit(stage)
            with self.assertRaises(ValueError):
                g.require_ready(self.home,self.project,stage)
            self.approve(stage)
            self.assertEqual(sum(x["status"]=="approved" for x in g.overview(self.home,self.project)["stages"]),index+1)
        self.assertFalse(g.overview(self.home,self.project)["ready_stages"])
        self.assertIn("Approved by",g.packet_path(self.home,self.project,"qc").read_text())

    def test_cli_smoke(self):
        r=g.main(["--home",str(self.home),"status",self.project])
        self.assertEqual(r,0)
        r=g.main(["--home",str(self.home),"check",self.project,"analysis"])
        self.assertEqual(r,1)

    def test_source_hash_integrity_of_new_submission(self):
        r=self.submit()
        state=g.load(self.home,self.project)
        art=state["stages"]["puzzle"]["artifacts"][0]
        self.assertEqual(art["sha256"],g.file_sha(self.artifacts/art["name"]))
        self.assertEqual(r["network_or_paid_api_calls"],0)

    def test_tampered_approval_decision_blocks_next_stage(self):
        self.advance()
        f=g.location(self.home,self.project)/"decisions"/"puzzle"/"rev0001_approval.json"
        f.chmod(0o644)
        record=json.loads(f.read_text())
        record["notes"]="edited after human signoff"
        f.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,"decision.*altered"):
            g.require_ready(self.home,self.project,"diagnosis")

    def test_guarded_analysis_and_overleaf_adapter(self):
        from research.factory import paper_sprint as ps
        # The existing demo is explicitly synthetic and local (no paid API).
        original_root=ps.ROOT
        try:
            ps.ROOT=self.home
            demo=ps.demo()
        finally:
            ps.ROOT=original_root
        folder=Path(demo["demo_dir"])/"inputs"
        study=folder/"study.json"
        model=folder/"formal_model.json"
        data=folder/"SYNTHETIC_ultimatum.csv"
        self.advance("puzzle")
        self.advance("diagnosis")
        self.advance("literature")
        self.advance("novelty")
        g.submit(self.home,self.project,"formal_model",[model],
                 "Synthetic model with explicit assumptions and comparative static")
        self.approve("formal_model")
        self.advance("hypotheses")
        manifest=self.source("data_manifest.json",json.dumps({"data_sha256":g.file_sha(data),
            "synthetic":True,"access":"private","data_source":"synthetic demo"}))
        g.submit(self.home,self.project,"data",[manifest],
                 "Dataset inventory, provenance and hash available for review")
        self.approve("data")
        g.submit(self.home,self.project,"design",[study],
                 "Approved dataset, association design and forward holdout split")
        self.approve("design")
        result=g.produce(self.home,self.project,"analysis",spec_file=study)
        self.assertEqual(result["status"],"awaiting_critique")
        self.assertTrue(Path(result["output_directory"],"results.json").is_file())
        with self.assertRaises(ValueError):
            g.produce(self.home,self.project,"manuscript",spec_file=study,model_file=model)
        self.approve("analysis")
        self.advance("validation")
        paper=g.produce(self.home,self.project,"manuscript",spec_file=study,model_file=model)
        self.assertEqual(paper["status"],"awaiting_critique")
        self.assertTrue(Path(paper["archive"]).exists())
        self.assertEqual(g.overview(self.home,self.project)["awaiting_critique"],["manuscript"])

    def test_approved_data_hash_required_for_guarded_run(self):
        self.advance("puzzle")
        self.advance("diagnosis")
        self.advance("literature")
        self.advance("novelty")
        self.advance("formal_model")
        self.advance("hypotheses")
        self.advance("data")
        self.advance("design")
        with self.assertRaisesRegex(ValueError,"differs from approved design"):
            g.produce(self.home,self.project,"analysis",spec_file=self.source("other.json",'{"bad":"different"}'))


if __name__=="__main__":unittest.main()

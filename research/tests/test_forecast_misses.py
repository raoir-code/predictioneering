"""Synthetic, offline acceptance tests for the resolved-forecast miss adapter."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from research.factory import forecast_misses as m
from research.factory import pipeline, weekly


class ForecastMissTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base=Path(t.name)
        self.log=self.base/"production_like"/"predictions"/"brier_log.jsonl"
        self.log.parent.mkdir(parents=True)
        self.home=self.base/"research"
        self.out=self.home/"inbox"/"forecast_misses"
        self.inbox=self.base/"weekly"
        self.inbox.mkdir()

    def make(self,n=6, *,p=.02,market=.6,same_day=False):
        rows=[]
        for i in range(n):
            resolved=datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(days=0 if same_day else 7*i)
            rows.append({
                "market_id":str(i+1000),
                "market_label":"Will Iran target Jordan by September 30, 2026?",
                "dyad":"Iran-Jordan" if i%2==0 else "Iran-Kuwait",
                "first_prediction_ts":(resolved-timedelta(days=4)).isoformat(),
                "resolved_at":resolved.isoformat(),
                "outcome":1,
                "conditional_p":p,"market_p_at_first":market,
                "brier_conditional":0,"brier_market":0,
                "contract_type":"binary_onset","relation":"subset",
            })
        self.log.write_text("".join(json.dumps(x)+"\n" for x in rows))
        return rows

    def test_recomputes_log_brier_not_stored_values(self):
        self.make(1)
        rows,qc,sha=m.read_log(self.log)
        self.assertEqual(qc["valid_unique_resolved_contracts"],1)
        self.assertAlmostEqual(rows[0]["model_brier"],.9604)
        self.assertAlmostEqual(rows[0]["market_brier"],.16)
        self.assertEqual(len(sha),64)

    def test_prevents_contract_sibling_inflation(self):
        self.make(8,same_day=True)
        report=m.analyze(self.log,min_contracts=2,min_families=2)
        self.assertEqual(report["candidate_screen_count"],0)
        self.assertEqual(report["overall"]["possible_event_families"],2)
        self.assertEqual(report["overall"]["probable_duplicate_contracts"],6)

    def test_widespread_pattern_generates_diagnostic(self):
        self.make(8)
        report=m.analyze(self.log)
        self.assertGreater(report["candidate_screen_count"],0)
        brief=report["candidates"][0]["brief"]
        self.assertIn("UNKNOWN",brief["mechanism"])
        self.assertIn("not yet a scholarly puzzle",brief["expected_theory"])

    def test_defensible_model_beating_market_no_puzzle(self):
        self.make(8,p=.9,market=.1)
        self.assertEqual(m.analyze(self.log)["candidate_screen_count"],0)

    def test_invalid_and_unresolved_not_scored(self):
        records=self.make(5)
        records[0]["outcome"]=None
        records[1]["conditional_p"]="nan"
        records[2]["first_prediction_ts"]=records[2]["resolved_at"]
        self.log.write_text("".join(json.dumps(r)+"\n" for r in records))
        result=m.analyze(self.log)
        self.assertEqual(result["selected_resolved_contracts"],2)

    def test_duplicate_market_id_is_deduplicated(self):
        records=self.make(1)
        self.log.write_text(json.dumps(records[0])+"\n"+json.dumps(records[0])+"\n")
        self.assertEqual(m.analyze(self.log)["selected_resolved_contracts"],1)

    def test_conflicting_outcomes_are_excluded(self):
        records=self.make(1)
        altered={**records[0],"outcome":0}
        self.log.write_text(json.dumps(records[0])+"\n"+json.dumps(altered)+"\n")
        self.assertEqual(m.analyze(self.log)["selected_resolved_contracts"],0)

    def test_date_template_normalized(self):
        self.assertEqual(
            m.label_template("Will Iran target Jordan by August 31 2026?"),
            m.label_template("Will Iran target Jordan by September 15 2026?")
        )

    def test_analyze_is_pure_and_does_not_modify_source(self):
        self.make()
        before=self.log.read_bytes()
        m.analyze(self.log)
        self.assertEqual(before,self.log.read_bytes())
        self.assertFalse(self.out.exists())

    def test_register_only_pending_never_approves(self):
        self.make(8)
        before=self.log.read_bytes()
        report=m.execute(self.log,home=self.home,out=self.out,register=True)
        self.assertGreater(len(report["registered_pending_intake_cards"]),0)
        for r in report["registered_pending_intake_cards"]:
            card=pipeline.read(pipeline.card_path(self.home,r["card_id"]))
            self.assertEqual(card["status"],"pending_human_review")
            self.assertEqual(card["novelty"],"not_yet_checked")
        self.assertEqual(before,self.log.read_bytes())
        self.assertTrue(Path(report["readme_file"]).is_file())

    def test_repeat_is_idempotent(self):
        self.make(8)
        m.execute(self.log,home=self.home,out=self.out,register=True)
        old={p.stem for p in (self.home/"projects").glob("*.json")}
        m.execute(self.log,home=self.home,out=self.out,register=True)
        self.assertEqual(old,{p.stem for p in (self.home/"projects").glob("*.json")})

    def test_weekly_preview_no_file_changes(self):
        self.make(8)
        x=weekly.preview(self.home,self.inbox,forecast_log=self.log)
        self.assertEqual(x["forecast_misses"]["resolved_contracts"],8)
        self.assertFalse(self.home.exists())

    def test_weekly_opt_in_creates_pending_only(self):
        self.make(8)
        x=weekly.execute(self.home,self.inbox,forecast_log=self.log,register_misses=True)
        self.assertEqual(x["approved_projects_processed"],0)
        self.assertGreater(len(x["forecast_misses"]["registered_pending_intake_cards"]),0)
        self.assertTrue(all(c["intake_status"]=="pending_human_review"
                            for c in weekly.inventory(self.home)))

    def test_weekly_no_opt_in_has_no_cards(self):
        self.make(8)
        x=weekly.execute(self.home,self.inbox,forecast_log=self.log)
        self.assertEqual(x["forecast_misses"]["registered_pending_intake_cards"],[])
        self.assertEqual(weekly.inventory(self.home),[])

    def test_weekly_cli_must_supply_log_for_registration(self):
        self.assertEqual(weekly.main(["--home",str(self.home),"run",
            "--inbox",str(self.inbox),"--execute","--register-miss-candidates"]),1)


if __name__=="__main__":
    unittest.main()

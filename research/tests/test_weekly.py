"""Offline tests for weekly factory orchestration. Never use production data."""
from pathlib import Path
import json
import plistlib
import tempfile
import unittest
from unittest.mock import patch

from research.factory import weekly, pipeline


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)/"research"
        self.inbox=Path(self.temp.name)/"incoming"
        self.inbox.mkdir()
        self.home.mkdir()
        self.brief={"title":"Why does synthetic rivalry persist?",
                    "research_question":"Why does synthetic rivalry persist?",
                    "mechanism":"Uncertain restraint incentives",
                    "testable_prediction":"Observable incidents increase with crisis pressure"}

    def put(self,name="study.json"):
        p=self.inbox/name
        p.write_text(json.dumps(self.brief))
        return p

    def test_dry_run_never_registers(self):
        self.put()
        result=weekly.preview(self.home,self.inbox)
        self.assertEqual(result["status"],"dry_run_no_mutations")
        self.assertEqual(result["new_intake_candidates"],1)
        self.assertFalse((self.home/"projects").exists())

    def test_runs_registration_and_stops_at_intake_approval(self):
        self.put()
        result=weekly.execute(self.home,self.inbox)
        self.assertEqual(result["status"],"weekly_checkpoint_complete_with_human_gates")
        self.assertEqual(result["approved_projects_processed"],0)
        self.assertEqual(result["workflow_counts"],{"not_started":1})
        self.assertEqual(len(result["registration"]),1)
        self.assertTrue(Path(result["report_file"]).exists())
        self.assertEqual(result["paid_api_calls"],0)

    def test_repeated_execution_preserves_cards(self):
        self.put()
        a=weekly.execute(self.home,self.inbox)
        b=weekly.execute(self.home,self.inbox)
        self.assertEqual(a["registration"][0]["card_id"],b["registration"][0]["card_id"])
        self.assertEqual(len(list((self.home/"projects").glob("*.json"))),1)

    def test_approved_puzzle_reaches_missing_library_gate(self):
        self.put()
        a=weekly.execute(self.home,self.inbox)
        id=a["registration"][0]["card_id"]
        card=pipeline.card_path(self.home,id)
        val=pipeline.read(card)
        val["status"]="approved_for_literature_review"
        pipeline.save(card,val)
        result=weekly.execute(self.home,self.inbox,db=self.home/"missing_library.sqlite3")
        self.assertEqual(result["approved_projects_processed"],1)
        self.assertEqual(result["workflow_counts"],{"blocked_missing_library":1})

    def test_only_user_written_structured_json_is_accepted(self):
        (self.inbox/"worklog.md").write_text("Algorithm missed a crisis")
        (self.inbox/"bad.json").write_text('{"gibberish": 3}')
        result=weekly.execute(self.home,self.inbox)
        self.assertEqual(result["waiting_unstructured_log_count"],1)
        self.assertEqual(result["registration"],[])
        self.assertFalse((self.home/"projects"/"not-a-card.json").exists())

    def test_symlinks_never_followed(self):
        other=Path(self.temp.name)/"private.json"
        other.write_text(json.dumps(self.brief))
        (self.inbox/"link.json").symlink_to(other)
        self.assertEqual(weekly.incoming(self.inbox),[])

    def test_limit_validation(self):
        self.put()
        with self.assertRaises(ValueError):
            weekly.incoming(self.inbox,0)
        with self.assertRaises(ValueError):
            weekly.incoming(self.inbox,501)

    def test_large_file_not_read_or_registered(self):
        (self.inbox/"huge.json").write_bytes(b"x"*200001)
        scan=weekly.incoming(self.inbox)
        self.assertEqual(scan[0]["status"],"oversized_skipped")

    def test_launchd_only_generates_file(self):
        result=weekly.make_launchd(self.home,self.inbox,python=Path("/usr/bin/python3"))
        self.assertEqual(result["status"],"schedule_file_generated_not_installed")
        self.assertTrue(result["requires_user_review_and_manual_launchd_install"])
        definition=plistlib.loads(Path(result["plist_file"]).read_bytes())
        self.assertEqual(definition["StartCalendarInterval"],{"Weekday":1,"Hour":9,"Minute":0})
        self.assertIn("--execute",definition["ProgramArguments"])
        self.assertFalse(definition["RunAtLoad"])

    def test_launchd_does_not_invoke_launchctl(self):
        with patch("subprocess.run", side_effect=AssertionError("no launchctl")):
            weekly.make_launchd(self.home,self.inbox)

    def test_weekly_cli_plan_and_status(self):
        self.put()
        self.assertEqual(weekly.main(["--home",str(self.home),"plan","--inbox",str(self.inbox)]),0)
        self.assertEqual(weekly.main(["--home",str(self.home),"status"]),0)


if __name__=="__main__":
    unittest.main()

"""Offline tests for the end-to-end Holy Days H1 pilot: synthetic data only."""
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.factory.holiday_study import (
    months, major_holidays, is_israel_force, build_panel, estimate,
    acquire_months, load_months, month_entry, execute, write_summary,
)


def fake_event(day, actor="Military Forces of Israel (2022-)",
               subtype="Air/drone strike", precision=1, eid="LBN001"):
    return {
        "event_id_cnty":eid,"event_date":day,"time_precision":precision,
        "event_type":"Explosions/Remote violence","sub_event_type":subtype,
        "actor1":actor,"actor2":"Hezbollah",
        "notes":"SYNTHETIC TEST ONLY; NOT AN ACLED NOTE",
    }


class HolidayStudyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.out=Path(temp.name)/"private"/"study"

    def test_months_leap_year_and_bad_range(self):
        ms=list(months("2024-01","2024-03"))
        self.assertEqual([str(r[1]) for r in ms],
                         ["2024-01-31","2024-02-29","2024-03-31"])
        with self.assertRaises(ValueError):
            list(months("2024-13","2024-14"))
        with self.assertRaises(ValueError):
            list(months("2025-01","2024-12"))

    def test_israel_holiday_calendar_known_dates(self):
        calendar=major_holidays(2023,2025)
        self.assertIn("Yom Kippur",calendar[date(2024,10,12)])
        self.assertIn("Yom Kippur",calendar[date(2023,9,25)])
        self.assertIn("Rosh Hashanah I",calendar[date(2024,10,3)])
        self.assertIn("Rosh Hashanah II",calendar[date(2024,10,4)])
        self.assertNotIn(date(2024,10,11),calendar)

    def test_actor1_proxy_and_daily_zeros(self):
        self.assertTrue(is_israel_force("Military Forces of Israel (2022-)"))
        self.assertFalse(is_israel_force("Hezbollah"))
        records=[fake_event("2024-10-12",eid="1"),
                 fake_event("2024-10-12",eid="2"),
                 fake_event("2024-10-13",actor="Hezbollah",eid="3"),
                 fake_event("2024-10-14",precision=2,eid="4"),
                 fake_event("2024-10-15",subtype="Remote explosive/landmine/IED",eid="5")]
        rows,qc=build_panel(records,"2024-10","2024-10")
        lookup={r["date"]:r for r in rows}
        self.assertEqual(qc["included_israeli_remote_events"],2)
        self.assertEqual(lookup["2024-10-12"]["events"],2)
        self.assertEqual(lookup["2024-10-12"]["holiday"],1)
        self.assertEqual(lookup["2024-10-11"]["holiday_eve"],1)
        self.assertEqual(lookup["2024-10-13"]["events"],0)
        self.assertEqual(qc["days_in_panel"],31)
        self.assertEqual(qc["raw_acled_events"],5)

    def test_acquisition_without_fetch_no_auth(self):
        with patch("research.factory.holiday_study.get_token",
                   side_effect=AssertionError("No network expected")):
            result=acquire_months("2024-10","2024-10",out=self.out)
        self.assertEqual(result["newly_fetched_months"],0)
        self.assertEqual(len(result["missing_months"]),1)

    def test_verified_cached_month_does_not_reauth(self):
        self.out.mkdir(parents=True)
        key,p=month_entry(self.out,date(2024,10,1),date(2024,10,31))
        p.write_text(json.dumps(fake_event("2024-10-12"))+"\n")
        manifest={"queries":{key:{"file":str(p),"rows":1,
                                "sha256":hashlib.sha256(p.read_bytes()).hexdigest()}}}
        (self.out/"MANIFEST.json").write_text(json.dumps(manifest))
        with patch("research.factory.holiday_study.get_token",
                   side_effect=AssertionError("No network expected")):
            result=acquire_months("2024-10","2024-10",out=self.out,fetch=True)
        self.assertEqual(result["ready_months"],1)
        rows,meta=load_months("2024-10","2024-10",out=self.out)
        self.assertEqual(len(rows),1)
        self.assertEqual(meta[0]["rows"],1)
        with p.open("a") as f:
            f.write("{}\n")
        with self.assertRaisesRegex(ValueError,"Hash/path mismatch"):
            load_months("2024-10","2024-10",out=self.out)

    def test_ppml_with_controls(self):
        rows,_=build_panel([],"2024-01","2024-12")
        for i,row in enumerate(rows):
            row["events"]=(3 if row["holiday"] else 1)+(1 if i%3==0 else 0)
        fit=estimate(rows)
        self.assertEqual(fit["status"],"fit_exploratory")
        self.assertGreater(fit["irr"],1)
        self.assertIn("C(year_month)",fit["formula"])
        self.assertIn("C(weekday)",fit["formula"])

    def test_derived_results_have_no_raw_event_notes(self):
        rows,qc=build_panel([fake_event("2024-10-12")],"2024-10","2024-10")
        result=write_summary(rows,qc,{"major_holiday":{
            "status":"not_estimable","reason":"synthetic"}},
            out=self.out,start="2024-10",end="2024-10")
        p=self.out/"H1_DAILY_PANEL_PRIVATE.csv"
        self.assertTrue(p.is_file())
        self.assertNotIn("SYNTHETIC TEST ONLY",p.read_text())
        self.assertNotIn("SYNTHETIC TEST ONLY",json.dumps(result))

    def test_runner_refuses_to_fit_missing_cache(self):
        with patch("research.factory.holiday_study.estimate",
                   side_effect=AssertionError("No fitting expected")):
            result=execute(start="2024-10",end="2024-10",out=self.out)
        self.assertEqual(result["status"],"missing_data")


if __name__=="__main__":
    unittest.main()

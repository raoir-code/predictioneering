"""Offline ACLED audit checks; fabricated events only, no network."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research.factory.holiday_audit import (
    audit, load_verified, pick_review, safe_csv_value, write_private_review
)


class HolidayAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "inbox" / "acled" / "holy_days"
        self.folder.mkdir(parents=True)
        self.manifest = self.folder / "MANIFEST.json"

    def fixture(self):
        records = [
            {"event_id_cnty": "LBN1", "event_date": "2024-10-01",
             "time_precision": 1, "event_type": "Explosions/Remote violence",
             "sub_event_type": "Air/drone strike",
             "actor1": "Group A", "actor2": "Group B",
             "notes": "Source reports Group A attacked a position.",
             "source": "Local news", "direction_status": "undetermined_requires_notes_review"},
            {"event_id_cnty": "LBN2", "event_date": "2024-10-02",
             "time_precision": 2, "event_type": "Explosions/Remote violence",
             "sub_event_type": "Shelling/artillery/missile attack",
             "actor1": "Group B", "actor2": None,
             "notes": "", "source": "",
             "direction_status": "undetermined_requires_notes_review"},
            {"event_id_cnty": "LBN3", "event_date": "2024-10-03",
             "time_precision": 1, "event_type": "Explosions/Remote violence",
             "sub_event_type": "Shelling/artillery/missile attack",
             "actor1": "Group B", "actor2": None,
             "notes": "Unspecified explosion.", "source": "Local news",
             "direction_status": "undetermined_requires_notes_review"},
        ]
        filename = "lebanon_2024-10-01_2024-10-31_remote.jsonl"
        p = self.folder / filename
        p.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        self.manifest.write_text(json.dumps({
            "queries": {
                filename: {
                    "file": str(p), "event_type": "Explosions/Remote violence",
                    "rows": len(records),
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
            }
        }), encoding="utf-8")
        return p, records

    def test_quality_report_no_raw_notes_in_stdout_data(self):
        self.fixture()
        result = audit(self.manifest)
        self.assertEqual(result["total_rows"], 3)
        self.assertEqual(result["file_quality"][0]["exact_day_rows"], 2)
        self.assertEqual(result["file_quality"][0]["notes_present"], 2)
        self.assertEqual(result["file_quality"][0]["actor2_present"], 1)
        self.assertEqual(result["file_quality"][0]["direction_unknown"], 3)
        self.assertNotIn("Source reports Group A attacked", json.dumps(result))
        self.assertFalse(result["review_generated"])

    def test_reject_modified_raw_data(self):
        raw, _ = self.fixture()
        with raw.open("a", encoding="utf-8") as f:
            f.write("{}\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            load_verified(self.manifest)

    def test_deterministic_review_and_no_overwrite(self):
        _, records = self.fixture()
        selected = pick_review(records, per_type=2)
        self.assertEqual(selected, pick_review(records, per_type=2))
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(str(r["time_precision"]) == "1" for r in selected))
        result = audit(self.manifest, create_review=True, per_type=2)
        self.assertEqual(result["review_rows"], 2)
        p = Path(result["review_file"])
        with p.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["reviewer_initiator"], "")
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            audit(self.manifest, create_review=True, per_type=2)

    def test_spreadsheet_formula_injection_blocked(self):
        self.assertEqual(safe_csv_value("=HYPERLINK(bad)"), "'=HYPERLINK(bad)")
        self.assertEqual(safe_csv_value(" @call"), "' @call")
        self.assertEqual(safe_csv_value("ordinary notes"), "ordinary notes")

    def test_manifest_cannot_reference_external_folder(self):
        raw, records = self.fixture()
        manifest_data = json.loads(self.manifest.read_text())
        key = next(iter(manifest_data["queries"]))
        manifest_data["queries"][key]["file"] = str(self.folder.parent / key)
        self.manifest.write_text(json.dumps(manifest_data))
        with self.assertRaisesRegex(ValueError, "outside this private audit directory"):
            load_verified(self.manifest)


if __name__ == "__main__":
    unittest.main()

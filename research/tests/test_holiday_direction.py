"""Offline tests for the provisional direction assumption; no real ACLED data."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research.factory.holiday_direction import (
    provisional_direction, sample_rows, population_strata, direction_protocol,
    validate_annotations, wilson, SAMPLE_NAME, REVIEW_COLUMNS,
)


def event(eid, ty="Explosions/Remote violence", sub="Air/drone strike",
          a="Military Forces of X", b="Force Y", precision=1):
    return {
        "event_id_cnty": eid, "event_date": "2024-10-01",
        "time_precision": precision, "event_type": ty,
        "sub_event_type": sub, "actor1": a, "actor2": b,
        "notes": "Local report says army conducted an airstrike.",
        "source": "Example Source", "source_scale": "National",
        "country": "Exampleland", "admin1": "Example Region",
    }


class HolidayDirectionTests(unittest.TestCase):
    def test_actor1_is_only_provisional_remote_weapons_user(self):
        result = provisional_direction(event("x1"))
        self.assertEqual(result["provisional_weapons_user"], "Military Forces of X")
        self.assertEqual(result["provisional_target"], "Force Y")
        self.assertEqual(result["status"], "unverified_remote_proxy")

    def test_never_call_battle_or_landmine_directed(self):
        self.assertIsNone(provisional_direction(event("x", ty="Battles")))
        self.assertIsNone(provisional_direction(event("x", sub="Remote explosive/landmine/IED")))
        self.assertIsNone(provisional_direction(event("x", a="Unidentified Armed Group")))
        self.assertIsNone(provisional_direction(event("x", precision=2)))

    def test_missing_actor2_does_not_imply_target(self):
        result = provisional_direction(event("x", b=None))
        self.assertIsNone(result["provisional_target"])

    def test_reproducible_stratified_sample(self):
        rows = [event(f"x{i}", b=("Force Y" if i % 2 else None))
                for i in range(100)]
        rows += [event(f"s{i}", sub="Shelling/artillery/missile attack")
                 for i in range(100)]
        rows += [event("battle", ty="Battles")]
        s1 = sample_rows(rows, per_stratum=9)
        s2 = sample_rows(list(reversed(rows)), per_stratum=9)
        self.assertEqual([r["event_id_cnty"] for r in s1],
                         [r["event_id_cnty"] for r in s2])
        self.assertEqual(len(s1), 27)
        self.assertEqual(len(population_strata(rows)), 3)

    def test_wilson_interval_respects_no_observations(self):
        self.assertIsNone(wilson(0, 0))
        self.assertLess(wilson(10, 10)[0], 1)
        self.assertEqual(wilson(0, 10)[0], 0)

    def test_review_decisive_unknown_and_target_are_separate(self):
        original = [event("x1"), event("x2", b=None)]
        sample = []
        for i, r in enumerate(original):
            rr = {**r, **{k: "" for k in REVIEW_COLUMNS}}
            rr["review_actor1_weapon_user"] = "yes" if i == 0 else "unclear"
            rr["review_actor2_target"] = "no" if i == 0 else "not_applicable"
            sample.append(rr)
        report = validate_annotations(sample, original)
        self.assertEqual(report["gate"], "review_incomplete_or_ambiguous")
        strata = {x["actor2_stratum"]: x for x in report["strata"]}
        self.assertEqual(strata["with_actor2"]["actor1_weapon_user_confirmed"], 1)
        self.assertEqual(strata["with_actor2"]["actor2_target_confirmed"], 0)
        self.assertEqual(strata["without_actor2"]["weapon_user_unclear_or_unreviewed"], 1)

    def test_refuse_yes_target_when_actor2_absent(self):
        r = event("x", b=None)
        annotated = [{**r, "review_actor1_weapon_user": "yes",
                      "review_actor2_target": "yes"}]
        with self.assertRaisesRegex(ValueError, "Actor2 is missing"):
            validate_annotations(annotated, [r])

    def test_refuse_stale_or_nonproxy_review(self):
        r = event("x")
        edited = {**r, "actor1": "Fictional other actor",
                  "review_actor1_weapon_user": "yes"}
        with self.assertRaisesRegex(ValueError, "does not match verified"):
            validate_annotations([edited], [r])
        with self.assertRaisesRegex(ValueError, "non-proxy"):
            validate_annotations([event("battle", ty="Battles")], [r])

    def test_local_manifest_review_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            row = event("x")
            name = "fixture_remote.jsonl"
            raw = folder / name
            raw.write_text(json.dumps(row) + "\n", encoding="utf-8")
            manifest = folder / "MANIFEST.json"
            manifest.write_text(json.dumps({
                "queries": {name: {
                    "file": str(raw), "event_type": "Explosions/Remote violence",
                    "rows": 1,
                    "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                }}
            }), encoding="utf-8")
            first = direction_protocol(manifest, make_review=True)
            self.assertEqual(first["sample_events"], 1)
            csv_path = folder / SAMPLE_NAME
            self.assertTrue(csv_path.is_file())
            with csv_path.open(newline="", encoding="utf-8") as fp:
                rec = list(csv.DictReader(fp))[0]
            self.assertEqual(rec["review_actor1_weapon_user"], "")
            self.assertEqual(rec["notes"], row["notes"])
            self.assertNotIn("Local report", json.dumps(first))
            with self.assertRaisesRegex(ValueError, "must not be overwritten"):
                direction_protocol(manifest, make_review=True)
            assessed = direction_protocol(manifest, evaluate=True)
            self.assertEqual(assessed["evaluation"]["gate"], "review_incomplete_or_ambiguous")

    def test_review_file_must_remain_private(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            manifest = folder / "MANIFEST.json"
            manifest.write_text(json.dumps({"queries": {}}))
            with self.assertRaisesRegex(ValueError, "must remain beside"):
                direction_protocol(manifest, make_review=True,
                                   review_file=folder.parent / "public.csv")


if __name__ == "__main__":
    unittest.main()

"""Offline ACLED pilot tests; no API, OAuth, or real credentials."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from research.factory.holiday_acled import (
    classify_direction, credentials, file_for, fetch_one, fetch_page,
    get_token, pilot, validate_window,
)


def event(event_id="LBN1", event_type="Battles", day="2024-10-11", prec=1):
    return {
        "event_id_cnty": event_id, "event_date": day, "time_precision": prec,
        "event_type": event_type, "actor1": "Group A", "actor2": "Group B",
        "notes": "Reported shelling but attribution remains uncertain.",
        "source": "Example Local Source", "source_scale": "National",
        "fatalities": 0, "country": "Lebanon",
    }


class HolidayAcledTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.out = Path(td.name) / "research" / "inbox" / "acled" / "holy_days"

    def test_dry_run_never_requests_api_or_reads_credentials(self):
        with patch("research.factory.holiday_acled.credentials", side_effect=AssertionError("credentials accessed")):
            with patch("research.factory.holiday_acled.fetch_page", side_effect=AssertionError("network accessed")):
                output = pilot("Lebanon", "2024-10-01", "2024-10-31", out=self.out)
        self.assertEqual(output["status"], "dry_run_no_network")
        self.assertEqual(len(output["queries"]), 3)
        self.assertFalse(self.out.exists())

    def test_battles_and_remote_are_not_inferred_directed(self):
        for ty in ("Battles", "Explosions/Remote violence"):
            self.assertEqual(classify_direction(event(event_type=ty)),
                             "undetermined_requires_notes_review")
        self.assertEqual(classify_direction(event(event_type="Violence against civilians")),
                         "actor1_targets_civilians_coding_rule")

    def test_window_limits_and_reporting_lag(self):
        with self.assertRaises(ValueError):
            validate_window("2024-11-01", "2024-10-01")
        with self.assertRaises(ValueError):
            validate_window("2024-01-01", "2024-12-31")
        with self.assertRaises(ValueError):
            validate_window("2026-11-14", "2026-11-20", today=__import__("datetime").date(2026, 11, 20))
        self.assertIsNotNone(validate_window("2024-10-01", "2024-10-31"))

    def test_two_cursor_pages_keep_notes_and_provenance(self):
        replies = [
            {"status": 200, "data": [event("LBN1")], "next_cursor": "next-2",
             "data_query_restrictions": {}},
            {"status": 200, "data": [
                event("LBN2", "Battles", prec=2),
                event("LBN3", "Battles"),
            ], "next_cursor": None, "data_query_restrictions": {}},
        ]
        calls = []
        def fake_page(params, state, username, password):
            calls.append(dict(params))
            return replies[len(calls)-1]
        with patch("research.factory.holiday_acled.fetch_page", fake_page):
            outcome = fetch_one("Lebanon", "2024-10-01", "2024-10-31",
                                "Battles", out=self.out,
                                state=["token"], username="u", password="p")
        data = [json.loads(x) for x in Path(outcome["file"]).read_text().splitlines()]
        self.assertEqual(len(data), 3)
        self.assertEqual(outcome["pages"], 2)
        self.assertEqual(outcome["exact_day_rows"], 2)
        self.assertEqual(outcome["direction_unknown_rows"], 3)
        self.assertEqual(data[0]["notes"], event()["notes"])
        self.assertEqual(data[0]["source"], "Example Local Source")
        self.assertNotIn("page", calls[0])
        self.assertNotIn("cursor", calls[0])
        self.assertEqual(calls[1]["cursor"], "next-2")
        self.assertFalse(outcome["has_account_query_restrictions"])

    def test_repeated_cursor_fails_without_publishing_partial_output(self):
        with patch("research.factory.holiday_acled.fetch_page",
                   return_value={"data": [event()], "next_cursor": "same",
                                 "data_query_restrictions": {}}):
            with self.assertRaisesRegex(RuntimeError, "Repeated ACLED cursor"):
                fetch_one("Lebanon", "2024-10-01", "2024-10-31",
                          "Battles", out=self.out,
                          state=["token"], username="u", password="p")
        self.assertFalse(file_for("Lebanon", "2024-10-01", "2024-10-31",
                                  "Battles", self.out).exists())

    def test_full_page_without_cursor_refuses_truncation(self):
        with patch("research.factory.holiday_acled.fetch_page",
                   return_value={"data": [event("LBN1"), event("LBN2")],
                                 "data_query_restrictions": {}}):
            with self.assertRaisesRegex(ValueError, "Missing next_cursor"):
                fetch_one("Lebanon", "2024-10-01", "2024-10-31", "Battles",
                          out=self.out, limit=2,
                          state=["token"], username="u", password="p")

    def test_cached_files_do_not_reauthenticate(self):
        with patch("research.factory.holiday_acled.credentials", return_value=("u", "p")) as cred:
            with patch("research.factory.holiday_acled.get_token", return_value="token") as auth:
                with patch("research.factory.holiday_acled.fetch_page",
                           return_value={"data": [event()], "next_cursor": None,
                                         "data_query_restrictions": {}}) as data:
                    first = pilot("Lebanon", "2024-10-01", "2024-10-31",
                                  fetch=True, out=self.out)
                    second = pilot("Lebanon", "2024-10-01", "2024-10-31",
                                   fetch=True, out=self.out)
        self.assertEqual(data.call_count, 3)
        self.assertEqual(auth.call_count, 1)
        self.assertEqual(cred.call_count, 1)
        self.assertEqual(len(first["queries"]), 3)
        self.assertEqual({x["cache_status"] for x in second["queries"]},
                         {"cached"})

    def test_reauth_after_expired_access_token(self):
        state = ["old"]
        expired = HTTPError(url="https://acleddata.com/api/acled/read", code=401,
                            msg="Unauthorized", hdrs=None, fp=None)
        with patch("research.factory.holiday_acled.request_json",
                   side_effect=[expired, {"data": [], "status": 200}]) as request:
            with patch("research.factory.holiday_acled.get_token",
                       return_value="new") as auth:
                j = fetch_page({"country": "Lebanon"}, state, "u", "p",
                               sleep=lambda _: None)
        self.assertEqual(j["data"], [])
        self.assertEqual(state[0], "new")
        self.assertEqual(request.call_count, 2)
        auth.assert_called_once_with("u", "p")

    def test_no_token_leak_on_bad_login(self):
        expired = HTTPError(url="https://acleddata.com/oauth/token", code=400,
                            msg="Invalid credentials", hdrs=None, fp=None)
        with patch("research.factory.holiday_acled.request_json", side_effect=expired):
            with self.assertRaisesRegex(RuntimeError, "HTTP 400") as err:
                get_token("user@example.org", "SECRET_PASSWORD")
        self.assertNotIn("SECRET_PASSWORD", str(err.exception))

    def test_no_fulltext_llm_processing(self):
        with patch("research.factory.holiday_acled.fetch_page",
                   return_value={"data": [event(event_type="Violence against civilians")],
                                 "next_cursor": None, "data_query_restrictions": {}}):
            result = fetch_one("Lebanon", "2024-10-01", "2024-10-31",
                               "Violence against civilians", out=self.out,
                               state=["t"], username="u", password="p")
        self.assertEqual(result["coded_perpetrator_to_civilians_rows"], 1)
        self.assertEqual(result["direction_unknown_rows"], 0)


if __name__ == "__main__":
    unittest.main()

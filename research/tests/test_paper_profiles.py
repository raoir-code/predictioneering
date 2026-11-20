"""Offline evidence-profiling tests. Mock Claude; never upload scholarly PDFs."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from research.factory.pdf_inventory import SCHEMA as INVENTORY
from research.factory.pdf_text import SCHEMA as TEXT_SCHEMA
from research.factory.paper_profiles import (
    chunks_for, main, plan, run, show, validated, prepare, search_profiles
)


class PaperProfilesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / "Conflict"
        self.folder.mkdir()
        # macOS /var is often a symlink to /private/var. Match production canonical roots.
        self.folder = self.folder.resolve(strict=True)
        self.db = Path(temp.name) / "library.sqlite3"
        self.sample = ("War occurs when credible commitments cannot be made. "
                       "Leaders must consider audience costs and alternative bargains.")
        with closing(sqlite3.connect(self.db)) as conn:
            conn.executescript(INVENTORY)
            conn.executescript(TEXT_SCHEMA)
            conn.execute(
                """INSERT INTO pdf_files(root,relpath,size_bytes,mtime_ns,sha256,
                text_status,zotero_uid,zotero_title,match_method,match_confidence,
                bibliography_version,error,last_scanned)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(self.folder), "theory.pdf", 150, 10, "abc123", "text_available",
                 "zotero-item", "Bargaining Theory", "filename_title", "high",
                 "zotero-v1", None, "now"),
            )
            conn.execute(
                """INSERT INTO pdf_text_documents(root,relpath,sha256,version,
                status,error,pages_total,pages_with_text,extracted_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (str(self.folder), "theory.pdf", "abc123", "pdftotext-page-v1",
                 "ok", None, 2, 2, "now"),
            )
            conn.executemany(
                "INSERT INTO pdf_text_pages(root,relpath,page_num,text) VALUES(?,?,?,?)",
                [(str(self.folder), "theory.pdf", 1, self.sample),
                 (str(self.folder), "theory.pdf", 2, "We derive a formal equilibrium in which signaling is costly.")],
            )
            conn.commit()

    def fake_model(self, payload, model, key):
        return {"evidence": [{
            "page": 1, "kind": "theory",
            "claim": "Commitment problems can cause war.",
            "quote": "War occurs when credible commitments cannot be made.",
        }]}, 115, 48

    def test_plan_is_local_and_counts_calls(self):
        with patch("research.factory.paper_profiles.claude_extract") as model:
            report = plan(self.db, self.folder, 1, "test-model")
        model.assert_not_called()
        self.assertEqual(report["selected_papers"], 1)
        self.assertEqual(report["api_calls_needed"], 1)
        self.assertEqual(report["status"], "dry_run_no_api_calls")

    def test_run_writes_only_verified_evidence_and_reuses_cache(self):
        first = run(self.db, self.folder, 1, 2, "test-model", "fake-key",
                    extractor=self.fake_model)
        self.assertEqual(first["actual_api_calls"], 1)
        self.assertEqual(first["results"][0]["status"], "profile_saved")
        details = show(self.db, "theory.pdf")[0]
        self.assertEqual(details["categories"]["theory"][0]["page"], 1)
        self.assertEqual(details["evidence"][0]["quote_verified"], True)
        self.assertEqual(details["status"], "model_extracted_not_scientifically_reviewed")
        second = run(self.db, self.folder, 1, 2, "test-model", "fake-key",
                     extractor=lambda *args: self.fail("Cached call must not repeat"))
        self.assertEqual(second["actual_api_calls"], 0)
        self.assertEqual(second["results"][0]["previously_cached_chunks"], 1)

    def test_invented_quote_and_wrong_page_rejected(self):
        chunk = [(1, self.sample)]
        evidence, rejected = validated({"evidence": [
            {"page": 1, "kind": "theory", "claim": "Proposition", "quote": "Never appeared anywhere in this paper."},
            {"page": 12, "kind": "theory", "claim": "Proposition", "quote": self.sample[:55]},
            {"page": 1, "kind": "theory", "claim": "Proposition", "quote": self.sample[:55]},
        ]}, chunk)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(rejected, 2)

    def test_chunking_covers_long_documents(self):
        doc = "w" * 30000
        parts = chunks_for([(2, doc)])
        self.assertGreater(len(parts), 2)
        self.assertEqual("".join(text for group in parts for _, text in group), doc)

    def test_budget_defers_without_api_charges(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE pdf_text_pages SET text=? WHERE page_num=1",
                         ("This long source text " * 900,))
            conn.commit()
        with patch("research.factory.paper_profiles.claude_extract") as model:
            report = run(self.db, self.folder, 1, 1, "test-model", "fake-key")
        model.assert_not_called()
        self.assertEqual(report["actual_api_calls"], 0)
        self.assertEqual(report["results"][0]["status"], "deferred_by_max_calls")

    def test_failure_keeps_completed_chunk_and_resumes(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE pdf_text_pages SET text=? WHERE page_num=1",
                         (self.sample * 170,))
            conn.commit()
        calls = 0
        def flaky(payload, model, key):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("temporary Anthropic failure")
            return {"evidence": []}, 100, 30
        one = run(self.db, self.folder, 1, 5, "test-model", "fake-key",
                  extractor=flaky)
        self.assertEqual(one["results"][0]["status"], "failed_retryable")
        self.assertEqual(one["actual_api_calls"], 2)
        two = run(self.db, self.folder, 1, 5, "test-model", "fake-key",
                  extractor=lambda *args: ({"evidence": []}, 100, 30))
        self.assertEqual(two["results"][0]["status"], "profile_saved")
        self.assertEqual(two["results"][0]["previously_cached_chunks"], 1)
        self.assertEqual(two["actual_api_calls"], 1)

    def test_stale_profile_not_exposed_after_reinventory(self):
        run(self.db, self.folder, 1, 1, "test-model", "fake-key",
            extractor=self.fake_model)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE pdf_text_documents SET sha256='newhash'")
            conn.commit()
        with self.assertRaisesRegex(ValueError, "No current profile"):
            show(self.db, "theory")

    def test_paid_run_rejected_without_explicit_flag(self):
        with patch("research.factory.paper_profiles.claude_extract") as model:
            ret = main(["--db", str(self.db), "run",
                        "--folder", str(self.folder),
                        "--model", "test-model"])
        self.assertEqual(ret, 1)
        model.assert_not_called()

    def test_no_evidence_not_dressed_up_as_findings(self):
        run(self.db, self.folder, 1, 1, "test-model", "fake-key",
            extractor=lambda *args: ({"evidence": []}, 0, 0))
        details = show(self.db, "theory")[0]
        self.assertEqual(details["evidence"], [])
        self.assertEqual(details["categories"]["empirical_finding"], [])


    def test_profile_search_returns_page_referenced_quotes(self):
        run(self.db, self.folder, 1, 2, "test-model", "fake-key",
            extractor=self.fake_model)
        result = search_profiles(self.db, "credible commitments")
        self.assertEqual(result["profiles_matched"], 1)
        evidence = result["results"][0]["evidence"][0]
        self.assertEqual(evidence["pdf_page"], 1)
        self.assertIn("War occurs", evidence["verified_quote"])
        self.assertEqual(search_profiles(self.db, "completely unrelated")["profiles_matched"], 0)

    def test_select_paper_by_filename_without_charges(self):
        selected = plan(self.db, self.folder, 1, "test-model", "THEORY")
        missing = plan(self.db, self.folder, 1, "test-model", "no-such-paper")
        self.assertEqual(selected["selected_papers"], 1)
        self.assertEqual(missing["selected_papers"], 0)

if __name__ == "__main__":
    unittest.main()

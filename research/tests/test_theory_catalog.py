"""Offline tests for cross-paper catalog quote provenance and human review gates."""
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from research.factory.pdf_inventory import SCHEMA as INVENTORY
from research.factory.pdf_text import SCHEMA as TEXT
from research.factory.paper_profiles import SCHEMA as PROFILES, VERSION
from research.factory.profile_audit import mark
from research.factory.theory_catalog import search, main


class TheoryCatalogTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "Conflict"
        self.root.mkdir()
        self.root = self.root.resolve(strict=True)
        self.db = Path(temp.name) / "library.sqlite3"
        self.quote = "Credible commitment problems can cause preventive war."
        self.profile = {
            "title": "Preventive War and Bargaining",
            "file": "preventive.pdf", "model": "test-model",
            "zotero_uid": "zotero:item:001",
            "evidence": [{
                "evidence_id": "p2-test", "page": 2, "kind": "mechanism",
                "claim": "A credible commitment problem may cause preventive war.",
                "quote": self.quote, "quote_verified": True,
                "interpretation_reviewed": False,
            }]
        }
        with closing(sqlite3.connect(self.db)) as db:
            db.executescript(INVENTORY)
            db.executescript(TEXT)
            db.executescript(PROFILES)
            db.execute("""INSERT INTO pdf_files
                (root,relpath,size_bytes,mtime_ns,sha256,text_status,zotero_uid,
                 zotero_title,match_method,match_confidence,bibliography_version,
                 error,last_scanned) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(self.root), "preventive.pdf", 100, 1, "sha1", "text_available",
                 "zotero:item:001", self.profile["title"], "filename_title", "high",
                 "v1", None, "now"))
            db.execute("""INSERT INTO pdf_text_documents
                (root,relpath,sha256,version,status,error,pages_total,pages_with_text,
                 extracted_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (str(self.root), "preventive.pdf", "sha1", "pdftotext-page-v1",
                 "ok", None, 2, 1, "now"))
            db.execute("""INSERT INTO pdf_text_pages
                (root,relpath,page_num,text) VALUES(?,?,?,?)""",
                (str(self.root), "preventive.pdf", 2,
                 "The text concludes: " + self.quote + " Further discussion."))
            db.execute("""INSERT INTO paper_profiles
                (root,relpath,pdf_sha256,version,model,title,zotero_uid,
                 zotero_match_confidence,profile_json,completed_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (str(self.root), "preventive.pdf", "sha1", VERSION, "test-model",
                 self.profile["title"], "zotero:item:001", "high",
                 json.dumps(self.profile), "now"))
            db.commit()

    def test_finds_quoted_but_not_yet_reviewed_source(self):
        result = search(self.db, "credible commitment war")
        self.assertEqual(result["evidence_hits"], 1)
        self.assertFalse(result["novelty_verified"])
        evidence = result["results"][0]
        self.assertEqual(evidence["pdf_page"], 2)
        self.assertEqual(evidence["source_id"], "zotero:item:001")
        self.assertEqual(evidence["human_review_status"], "not_reviewed")
        self.assertFalse(evidence["interpretation_independently_checked"])
        self.assertEqual(evidence["verified_quote"], self.quote)

    def test_approved_only_needs_human_gate(self):
        self.assertEqual(search(self.db, "preventive war", approved_only=True)
                         ["evidence_hits"], 0)
        with self.assertRaisesRegex(ValueError, "confirm-source-reviewed"):
            mark(self.db, "preventive", "p2-test", "approved", "Unchecked")
        mark(self.db, "preventive", "p2-test", "approved", "Read source", confirmed=True)
        result = search(self.db, "preventive war", approved_only=True)
        self.assertEqual(result["evidence_hits"], 1)
        self.assertTrue(result["results"][0]["interpretation_independently_checked"])

    def test_rejected_does_not_flow_into_default_catalog(self):
        mark(self.db, "preventive", "p2-test", "rejected", "Unsupported inference")
        self.assertEqual(search(self.db, "preventive war")["evidence_hits"], 0)
        rejected = search(self.db, "preventive war", include_rejected=True)
        self.assertEqual(rejected["results"][0]["human_review_status"], "rejected")

    def test_current_source_hash_required(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE pdf_files SET sha256='newsha'")
            db.commit()
        self.assertEqual(search(self.db, "preventive")["evidence_hits"], 0)

    def test_quote_is_rechecked_against_indexed_page(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE pdf_text_pages SET text='Completely unrelated contents'")
            db.commit()
        self.assertEqual(search(self.db, "preventive war")["evidence_hits"], 0)

    def test_cli_never_invokes_model_and_clearly_qualifies_evidence(self):
        with patch("research.factory.paper_profiles.claude_extract") as model:
            with redirect_stdout(io.StringIO()) as output:
                code = main(["--db", str(self.db), "search",
                             "preventive war", "--limit", "2"])
        self.assertEqual(code, 0)
        model.assert_not_called()
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["evidence_hits"], 1)
        self.assertIn("does not prove", parsed["caution"])

    def test_rejects_empty_query_and_invalid_limit(self):
        with self.assertRaisesRegex(ValueError, "substantive"):
            search(self.db, "and the")
        with self.assertRaisesRegex(ValueError, "1-100"):
            search(self.db, "war", limit=0)


if __name__ == "__main__":
    unittest.main()

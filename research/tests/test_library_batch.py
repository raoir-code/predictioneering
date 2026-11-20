"""No-API tests of the safe, source-versioned multi-paper pilot planner."""
import hashlib
import io
import json
import shlex
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from research.factory.pdf_inventory import SCHEMA as INVENTORY
from research.factory.pdf_text import SCHEMA as TEXT
from research.factory.paper_profiles import (
    SCHEMA as PROFILES, VERSION, chunks_for, serialize_chunk,
)
from research.factory.library_batch import preview, scan, shell_command, main


class LibraryBatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "Conflict"
        self.root.mkdir()
        self.root = self.root.resolve(strict=True)
        self.db = Path(temp.name) / "library.sqlite3"
        self.paper = {
            "done.pdf": ("Bargaining Theory of Preventive War",
                         "A short article about war and bargaining."),
            "partial.pdf": ("Formal Models of Crisis Bargaining",
                            "This model considers war and strategic bargaining. " * 340),
            "new.pdf": ("Historical Country Data",
                        "The dataset describes an historical case study."),
        }
        with closing(sqlite3.connect(self.db)) as db:
            db.executescript(INVENTORY)
            db.executescript(TEXT)
            db.executescript(PROFILES)
            for name, (title, text) in self.paper.items():
                db.execute(
                    """INSERT INTO pdf_files
                    (root,relpath,size_bytes,mtime_ns,sha256,text_status,zotero_uid,
                     zotero_title,match_method,match_confidence,bibliography_version,
                     error,last_scanned) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(self.root), name, 100, 1, "sha-" + name, "text_available",
                     "uid-"+name, title, "filename_title", "high", "v1", None, "now"),
                )
                db.execute(
                    """INSERT INTO pdf_text_documents
                    (root,relpath,sha256,version,status,error,pages_total,
                     pages_with_text,extracted_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (str(self.root), name, "sha-"+name, "pdftotext-page-v1",
                     "ok", None, 1, 1, "now"),
                )
                db.execute(
                    """INSERT INTO pdf_text_pages(root,relpath,page_num,text)
                       VALUES(?,?,?,?)""",
                    (str(self.root), name, 1, text)
                )
            db.execute(
                """INSERT INTO paper_profiles(root,relpath,pdf_sha256,version,model,
                   title,zotero_uid,zotero_match_confidence,profile_json,completed_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (str(self.root), "done.pdf", "sha-done.pdf", VERSION, "test-model",
                 self.paper["done.pdf"][0], "uid-done.pdf", "high",
                 json.dumps({"status":"model_extracted_not_scientifically_reviewed"}),
                 "now")
            )
            split = chunks_for([(1, self.paper["partial.pdf"][1])])
            self.assertEqual(len(split), 2)
            payload = serialize_chunk(split[0])
            fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            db.execute(
                """INSERT INTO paper_profile_chunks
                (root,relpath,pdf_sha256,version,model,chunk_index,chunk_sha256,
                 response_json,evidence_json,valid_evidence,rejected_evidence,
                 input_tokens,output_tokens,completed_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(self.root), "partial.pdf", "sha-partial.pdf", VERSION,
                 "test-model", 0, fingerprint, '{"evidence":[]}', '[]',
                 0, 0, 100, 10, "now")
            )
            db.commit()

    def test_skips_finished_and_uses_cached_chunks(self):
        rows = {x["file"]: x for x in scan(self.db, self.root, "test-model")}
        self.assertEqual(rows["done.pdf"]["profile_status"], "profiled_unreviewed")
        self.assertEqual(rows["partial.pdf"]["chunks_total"], 2)
        self.assertEqual(rows["partial.pdf"]["chunks_cached"], 1)
        self.assertEqual(rows["partial.pdf"]["api_calls_needed"], 1)
        self.assertEqual(rows["new.pdf"]["api_calls_needed"], 1)

    def test_prioritizes_partial_and_respects_total_budget(self):
        result = preview(self.db, self.root, "test-model", max_papers=2, max_calls=2)
        self.assertEqual(result["status"], "dry_run_no_api_calls")
        self.assertEqual(result["indexed_papers_matching_filter"], 3)
        self.assertEqual(result["profile_counts"]["profiled_unreviewed"], 1)
        self.assertEqual(result["selected_papers"], 2)
        self.assertEqual(result["selected_api_calls_needed"], 2)
        self.assertEqual(result["remaining_call_budget"], 0)
        self.assertEqual([e["file"] for e in result["selected"]],
                         ["partial.pdf", "new.pdf"])
        self.assertTrue(all("--send-to-claude" in e["command_if_explicitly_approved"]
                            for e in result["selected"]))

    def test_small_call_budget_never_forces_overrun(self):
        result = preview(self.db, self.root, "test-model", max_papers=2, max_calls=1)
        self.assertEqual(result["selected_papers"], 1)
        self.assertEqual(result["selected_api_calls_needed"], 1)
        self.assertEqual(result["remaining_call_budget"], 0)
        self.assertTrue(result["deferred_by_budget"])

    def test_new_model_prevents_misusing_old_profile_and_cache(self):
        original = scan(self.db, self.root, "test-model")
        switched = scan(self.db, self.root, "new-model")
        self.assertEqual(len(original), len(switched))
        by_name = {item["file"]: item for item in switched}
        self.assertEqual(by_name["done.pdf"]["profile_status"], "not_profiled")
        self.assertTrue(by_name["done.pdf"]["existing_other_model_or_stale_profile"])
        self.assertEqual(by_name["partial.pdf"]["chunks_cached"], 0)
        self.assertEqual(by_name["partial.pdf"]["api_calls_needed"], 2)

    def test_changed_pdf_is_not_considered_already_profiled(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE pdf_text_documents SET sha256='next' WHERE relpath='done.pdf'")
            db.execute("UPDATE pdf_files SET sha256='next' WHERE relpath='done.pdf'")
            db.commit()
        row = next(x for x in scan(self.db, self.root, "test-model")
                   if x["file"] == "done.pdf")
        self.assertEqual(row["profile_status"], "not_profiled")
        self.assertTrue(row["existing_other_model_or_stale_profile"])

    def test_title_matching_does_not_invent_novelty(self):
        result = preview(self.db, self.root, "test-model", max_papers=3,
                         max_calls=10, match="Formal Models")
        self.assertEqual(result["indexed_papers_matching_filter"], 1)
        self.assertEqual(result["selected"][0]["file"], "partial.pdf")
        self.assertIn("heuristic", result["relevance_note"])
        self.assertEqual(preview(self.db, self.root, "test-model", match="missing")
                         ["selected_papers"], 0)

    def test_shell_commands_quote_untrusted_filenames(self):
        path = "a.pdf; echo PWNED"
        command = shell_command(str(self.root), path, "test-model", 1)
        parts = shlex.split(command)
        self.assertEqual(parts[parts.index("--file")+1], path)
        self.assertEqual(parts[parts.index("--model")+1], "test-model")
        self.assertEqual(parts[parts.index("--max-calls")+1], "1")
        self.assertEqual(parts.count("--send-to-claude"), 1)

    def test_cli_never_calls_claude(self):
        with patch("research.factory.paper_profiles.claude_extract") as model:
            with redirect_stdout(io.StringIO()) as output:
                code = main(["--db", str(self.db), "plan",
                             "--folder", str(self.root), "--model", "test-model",
                             "--max-papers", "2", "--max-calls", "2"])
        self.assertEqual(code, 0)
        model.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["selected_api_calls_needed"], 2)

    def test_rejects_invalid_budget_or_missing_model(self):
        with self.assertRaisesRegex(ValueError, "must be >= 1"):
            preview(self.db, self.root, "test-model", max_calls=0)
        with self.assertRaisesRegex(ValueError, "cache safety"):
            preview(self.db, self.root, "", max_calls=3)
        with self.assertRaisesRegex(ValueError, "Safety bounds"):
            preview(self.db, self.root, "test-model", max_calls=1000)


if __name__ == "__main__":
    unittest.main()

"""Offline tests for read-only PDF text extraction and page-level retrieval."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from research.factory.pdf_inventory import SCHEMA as INVENTORY_SCHEMA
from research.factory.pdf_text import extract, search

class PDFTextTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "Conflict"
        self.root.mkdir()
        # macOS /var is often a symlink to /private/var. Match production canonical roots.
        self.root = self.root.resolve(strict=True)
        self.db = Path(tmp.name) / "library.sqlite3"
        with closing(sqlite3.connect(self.db)) as db:
            db.executescript(INVENTORY_SCHEMA)
            db.commit()

    def pdf(self, name="study.pdf", title=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\nFake-PDF-mock-only")
        stat = path.stat()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute(
                """INSERT INTO pdf_files
                (root,relpath,size_bytes,mtime_ns,sha256,text_status,zotero_uid,
                 zotero_title,match_method,match_confidence,bibliography_version,error,last_scanned)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(self.root), name, stat.st_size, stat.st_mtime_ns, "sha1", "text_available",
                 "zotero1", title, "filename_title", "high", "v1", None, "now"))
            db.commit()
        return path

    def extracted(self, contents=b"Page one ceasefire\n\f\fPage three strategic bargaining\n\f"):
        fake = type("Completed", (), {
            "stdout": contents, "stderr": b"", "returncode": 0
        })()
        return patch("research.factory.pdf_text.subprocess.run", return_value=fake)

    def test_pages_are_real_pdf_page_numbers(self):
        path = self.pdf("ceasefire.pdf", title="Ceasefire Research")
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"), self.extracted():
            stats = extract(self.root, self.db)
        self.assertEqual(stats["page_records_added"], 2)
        self.assertEqual(search(self.db, "strategic bargaining")["results"][0]["pdf_page"], 3)
        self.assertEqual(search(self.db, "ceasefire")["results"][0]["title"], "Ceasefire Research")
        self.assertEqual(path.read_bytes(), b"%PDF-1.4\nFake-PDF-mock-only")

    def test_unmatched_pdf_remains_searchable(self):
        self.pdf("orphan.pdf")
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"), self.extracted():
            extract(self.root, self.db)
        self.assertEqual(search(self.db, "ceasefire")["results"][0]["title"], "orphan")

    def test_second_extraction_is_cached(self):
        self.pdf()
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"), self.extracted():
            extract(self.root, self.db)
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"), \
             patch("research.factory.pdf_text.subprocess.run") as run:
            self.assertEqual(extract(self.root, self.db)["cached_unchanged"], 1)
            run.assert_not_called()

    def test_pilot_limit_then_resume(self):
        self.pdf("a.pdf")
        self.pdf("b.pdf")
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"), self.extracted():
            first = extract(self.root, self.db, limit=1)
            second = extract(self.root, self.db)
        self.assertEqual(first["files_processed"], 1)
        self.assertEqual(first["remaining_to_extract"], 1)
        self.assertEqual(second["files_processed"], 1)

    def test_missing_extractor_gives_install_instructions(self):
        self.pdf()
        with patch("research.factory.pdf_text.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "brew install poppler"):
                extract(self.root, self.db)

    def test_scanned_pdf_without_text_reported(self):
        self.pdf()
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"), self.extracted(b"\f"):
            self.assertEqual(extract(self.root, self.db)["no_extractable_text"], 1)
        self.assertEqual(search(self.db, "ceasefire")["results"], [])

    def test_symlinked_file_cannot_be_read(self):
        self.pdf()
        outside = self.root.parent / "outside.pdf"
        outside.write_bytes(b"%PDF-1.4\nSecret")
        (self.root / "study.pdf").unlink()
        (self.root / "study.pdf").symlink_to(outside)
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"):
            result = extract(self.root, self.db)
        self.assertEqual(result["extraction_errors"], 1)
        self.assertEqual(search(self.db, "ceasefire")["results"], [])

    def test_stale_file_content_not_returned(self):
        self.pdf()
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"), self.extracted():
            extract(self.root, self.db)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE pdf_files SET sha256='other' WHERE relpath='study.pdf'")
            db.commit()
        self.assertEqual(search(self.db, "ceasefire")["results"], [])

    def test_failed_reextraction_removes_stale_text_and_can_retry(self):
        self.pdf()
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"), self.extracted():
            extract(self.root, self.db)
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"), \
             patch("research.factory.pdf_text.subprocess.run", side_effect=OSError("bad")):
            failure = extract(self.root, self.db, force=True)
        self.assertEqual(failure["extraction_errors"], 1)
        self.assertEqual(search(self.db, "ceasefire")["results"], [])
        with patch("research.factory.pdf_text.shutil.which", return_value="pdftotext"), self.extracted():
            self.assertEqual(extract(self.root, self.db)["files_processed"], 1)

if __name__ == "__main__":
    unittest.main()

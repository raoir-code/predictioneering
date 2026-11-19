"""Read-only inventory tests; no source PDFs or network touched outside test temp dir."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.factory.pdf_inventory import scan


class PDFInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.folder = self.base / "Conflict"
        self.folder.mkdir()
        self.db = self.base / "research.sqlite3"
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("""CREATE TABLE documents (
                         source TEXT,uid TEXT,title TEXT,doi TEXT)""")
            conn.execute("INSERT INTO documents VALUES (?,?,?,?)", (
                "zotero", "zotero1", "Rationalist Explanations for War",
                "10.1017/s0020818300033324"))
            conn.execute("INSERT INTO documents VALUES (?,?,?,?)", (
                "zotero", "zotero2", "Strategic Bargaining in Civil Wars",
                "10.1234/abc"))
            conn.commit()

    def add_pdf(self, name, content=b"%PDF-1.4\nTEST\n"):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_scan_title_match_and_incremental_cache(self):
        self.add_pdf("Fearon-1995-Rationalist-Explanations-for-War.pdf")
        with patch("research.factory.pdf_inventory.first_pages",
                   return_value=("", "no_extractable_text")):
            result = scan(self.folder, self.db)
            self.assertEqual(result["pdfs"], 1)
            self.assertEqual(result["high_confidence_zotero_matches"], 1)
            self.assertEqual(result["new_or_changed"], 1)
            repeat = scan(self.folder, self.db)
            self.assertEqual(repeat["cached_unchanged"], 1)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("select zotero_uid from pdf_files").fetchone()[0], "zotero1")

    def test_doi_match_uses_first_page_when_filename_uninformative(self):
        self.add_pdf("0001_unknown.pdf")
        with patch("research.factory.pdf_inventory.first_pages", return_value=(
            "Article published. DOI: 10.1234/ABC)\nFull text here." * 4, "text_available")):
            result = scan(self.folder, self.db)
        self.assertEqual(result["high_confidence_zotero_matches"], 1)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("select zotero_uid from pdf_files").fetchone()[0], "zotero2")

    def test_ignores_symlink_targets_outside_root(self):
        outside = self.base / "external.pdf"
        outside.write_bytes(b"%PDF-1.4\nOUTSIDE")
        (self.folder / "linked.pdf").symlink_to(outside)
        outside_folder = self.base / "outside"
        outside_folder.mkdir()
        (outside_folder / "more.pdf").write_bytes(b"%PDF-1.4\nOUTSIDE")
        (self.folder / "linked-dir").symlink_to(outside_folder, target_is_directory=True)
        self.assertEqual(scan(self.folder, self.db)["pdfs"], 0)

    def test_stale_entries_are_removed_without_touching_pdfs(self):
        file = self.add_pdf("Rationalist Explanations for War.pdf")
        with patch("research.factory.pdf_inventory.first_pages", return_value=("", "no_extractable_text")):
            scan(self.folder, self.db)
            old = file.read_bytes()
            self.assertEqual(file.read_bytes(), old)
            file.unlink()
            self.assertEqual(scan(self.folder, self.db)["pdfs"], 0)

    def test_weak_matches_not_guessed(self):
        self.add_pdf("new-paper-about-ceasefires.pdf")
        with patch("research.factory.pdf_inventory.first_pages",
                   return_value=("", "no_extractable_text")):
            result = scan(self.folder, self.db)
        self.assertEqual(result["unmatched_or_ambiguous"], 1)
        self.assertEqual(result["high_confidence_zotero_matches"], 0)

    def test_duplicate_pdfs_recognized_by_content(self):
        self.add_pdf("a.pdf")
        self.add_pdf("b.pdf")
        with patch("research.factory.pdf_inventory.first_pages", return_value=("", "no_extractable_text")):
            result = scan(self.folder, self.db)
        self.assertEqual(result["exact_duplicate_files"], 1)

    def test_no_database_fails_without_writing_source(self):
        self.add_pdf("sample.pdf")
        with self.assertRaisesRegex(ValueError, "index missing"):
            scan(self.folder, self.base / "not_present.sqlite3")
        self.assertTrue((self.folder / "sample.pdf").exists())


if __name__ == "__main__":
    unittest.main()

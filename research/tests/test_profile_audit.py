"""Zero-network tests of profile provenance, scientific review flags and human gate."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from research.factory.pdf_inventory import SCHEMA as INVENTORY
from research.factory.pdf_text import SCHEMA as TEXT
from research.factory.paper_profiles import SCHEMA as PROFILES, VERSION
from research.factory.profile_audit import (
    assessment, context_for, load_profile, main, mark, model_packet,
    open_audit_db, report
)


class ProfileAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "Conflict"
        self.root.mkdir()
        self.root = self.root.resolve(strict=True)  # macOS /var -> /private/var
        self.db = Path(tmp.name) / "private.sqlite3"
        self.text = (
            "Proposition 1. Assume two states A and B bargain over a stake. "
            "A attacks when war is cheaper than expected future concessions. "
            "The proof establishes the equilibrium threshold. "
            "Table 2 lists eighteen episodes and numerical values. "
            "In a simulation, the equilibrium predicts more war under lower costs."
        )
        self.evidence = [
            {
                "page": 7, "kind": "formal_model",
                "claim": "Proposition 1 states that A attacks when future concessions are more costly.",
                "quote": "A attacks when war is cheaper than expected future concessions.",
                "evidence_id": "p7-formal", "quote_verified": True,
                "interpretation_reviewed": False,
            },
            {
                "page": 7, "kind": "empirical_finding",
                "claim": "The model implies more war when preventive attack is cheaper.",
                "quote": "In a simulation, the equilibrium predicts more war under lower costs.",
                "evidence_id": "p7-model-not-empirical", "quote_verified": True,
                "interpretation_reviewed": False,
            },
            {
                "page": 7, "kind": "empirical_finding",
                "claim": "Table 2 shows that 200 cases involved war.",
                "quote": "Table 2 lists eighteen episodes and numerical values.",
                "evidence_id": "p7-table", "quote_verified": True,
                "interpretation_reviewed": False,
            },
        ]
        profile = {
            "title": "Credible Commitments in Bargaining",
            "root": str(self.root), "file": "sample.pdf",
            "pdf_sha256": "sha123", "model": "test-model",
            "extractor_version": VERSION, "status": "model_extracted_not_scientifically_reviewed",
            "evidence": self.evidence,
        }
        self.profile = profile
        with closing(sqlite3.connect(self.db)) as db:
            db.executescript(INVENTORY)
            db.executescript(TEXT)
            db.executescript(PROFILES)
            db.execute(
                """INSERT INTO pdf_files
                (root,relpath,size_bytes,mtime_ns,sha256,text_status,zotero_uid,
                 zotero_title,match_method,match_confidence,bibliography_version,error,last_scanned)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(self.root), "sample.pdf", 10, 11, "sha123", "text_available",
                 "uid", profile["title"], "filename_title", "high", "v1", None, "now")
            )
            db.execute(
                """INSERT INTO pdf_text_documents
                (root,relpath,sha256,version,status,error,pages_total,pages_with_text,
                 extracted_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (str(self.root), "sample.pdf", "sha123", "pdftotext-page-v1",
                 "ok", None, 7, 1, "now")
            )
            db.execute(
                "INSERT INTO pdf_text_pages(root,relpath,page_num,text) VALUES(?,?,?,?)",
                (str(self.root), "sample.pdf", 7, self.text)
            )
            db.execute(
                """INSERT INTO paper_profiles
                (root,relpath,pdf_sha256,version,model,title,zotero_uid,
                 zotero_match_confidence,profile_json,completed_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (str(self.root), "sample.pdf", "sha123", VERSION, "test-model",
                 profile["title"], "uid", "high", json.dumps(profile), "now")
            )
            db.commit()

    def test_reports_risk_but_never_labels_claim_scientifically_verified(self):
        with patch("research.factory.profile_audit.urllib", create=True) as transport:
            output = report(self.db, "sample")
        self.assertEqual(output["evidence_total"], 3)
        self.assertEqual(output["source_quote_mismatches"], 0)
        self.assertEqual(output["scientific_verdict"], "not_verified")
        self.assertEqual(output["human_reviews"]["not_reviewed"], 3)
        self.assertEqual(output["queue_total"], 3)
        transport.assert_not_called()

    def test_flags_theoretical_finding_and_table_missing_number(self):
        data = {e["evidence_id"]: assessment(e, self.text) for e in self.evidence}
        self.assertIn("formal_result_requires_equation_payoff_and_proof_check",
                      data["p7-formal"]["warnings"])
        self.assertIn("possible_theory_or_simulation_mislabeled_empirical",
                      data["p7-model-not-empirical"]["warnings"])
        self.assertIn("table_or_figure_requires_original_pdf_inspection",
                      data["p7-table"]["warnings"])
        self.assertIn("numeric_detail_not_shown_in_local_quote_context",
                      data["p7-table"]["warnings"])

    def test_quotes_must_match_claimed_pdf_page(self):
        data = assessment(dict(self.evidence[0], quote="A fabricated citation " * 3),
                          self.text)
        self.assertFalse(data["quote_found_on_original_indexed_page"])
        self.assertIn("quote_not_found_on_claimed_pdf_page", data["warnings"])
        self.assertEqual(data["priority"], 100)

    def test_review_requires_explicit_human_confirmation(self):
        with self.assertRaisesRegex(ValueError, "confirm-source-reviewed"):
            mark(self.db, "sample", "p7-formal", "approved", "I read it")
        result = mark(self.db, "sample", "p7-formal", "approved",
                      "Checked proposition in original PDF", confirmed=True)
        self.assertEqual(result["decision"], "approved")
        output = report(self.db, "sample")
        self.assertEqual(output["human_reviews"]["approved"], 1)
        self.assertEqual(output["queue_total"], 2)
        self.assertNotIn("p7-formal", [r["evidence_id"] for r in output["queue"]])

    def test_review_reject_is_local_and_does_not_change_profile(self):
        mark(self.db, "sample", "p7-model-not-empirical", "needs_revision",
             "Misclassified theoretical implication")
        with closing(open_audit_db(self.db)) as db:
            row, profile = load_profile(db, "sample")
            self.assertEqual(profile, self.profile)
        self.assertEqual(report(self.db, "sample")["human_reviews"]["needs_revision"], 1)

    def test_ambiguous_filename_refused(self):
        with closing(open_audit_db(self.db)) as db:
            with db:
                old = json.loads(db.execute("SELECT profile_json FROM paper_profiles").fetchone()[0])
                old["file"] = "sample-additional.pdf"
                db.execute(
                    """INSERT INTO pdf_files
                    (root,relpath,size_bytes,mtime_ns,sha256,text_status,zotero_uid,
                     zotero_title,match_method,match_confidence,bibliography_version,error,last_scanned)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(self.root), old["file"], 10, 11, "second", "text_available",
                     "uid2", "Second Sample", "filename_title", "high", "v1", None, "now")
                )
                db.execute("""INSERT INTO pdf_text_documents
                    (root,relpath,sha256,version,status,error,pages_total,pages_with_text,
                     extracted_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (str(self.root), old["file"], "second", "pdftotext-page-v1",
                     "ok", None, 2, 1, "now"))
                db.execute("""INSERT INTO paper_profiles
                    (root,relpath,pdf_sha256,version,model,title,zotero_uid,
                     zotero_match_confidence,profile_json,completed_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (str(self.root), old["file"], "second", VERSION, "test-model",
                     "Second Sample", "uid2", "high", json.dumps(old), "now"))
            with self.assertRaisesRegex(ValueError, "Ambiguous"):
                load_profile(db, "sample")

    def test_old_profile_and_approval_not_carried_to_new_pdf_hash(self):
        mark(self.db, "sample", "p7-formal", "approved", confirmed=True)
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("UPDATE pdf_files SET sha256='new-source-hash'")
            db.commit()
        with self.assertRaisesRegex(ValueError, "No current profile"):
            report(self.db, "sample")
        with self.assertRaisesRegex(ValueError, "No current profile"):
            mark(self.db, "sample", "p7-formal", "approved", confirmed=True)

    def test_model_packet_never_invents_equations(self):
        packet = model_packet(self.db, "sample")
        self.assertEqual(packet["candidate_source_cards"][0]["pdf_page"], 7)
        self.assertEqual(packet["review_fields"]["payoff_functions"],
                         "NOT YET VERIFIED AGAINST ORIGINAL TYPESET PDF")
        self.assertIn("Proposition 1", packet["candidate_source_cards"][0]["source_context"])

    def test_cli_outputs_without_remote_requests(self):
        self.assertEqual(main(["--db", str(self.db), "audit", "--file", "sample",
                               "--limit", "1"]), 0)
        self.assertEqual(main(["--db", str(self.db), "model-packet",
                               "--file", "sample", "--limit", "1"]), 0)

    def test_bad_evidence_id_cannot_be_approved(self):
        with self.assertRaisesRegex(ValueError, "does not uniquely match"):
            mark(self.db, "sample", "made-up", "approved", confirmed=True)



    def test_stratified_sample_covers_different_claim_types(self):
        data = report(self.db, "sample", limit=3, stratified=True)
        self.assertEqual(len(data["queue"]), 3)
        self.assertEqual(
            {item["kind"] for item in data["queue"]},
            {"formal_model", "empirical_finding"},
        )
        self.assertEqual(data["scientific_verdict"], "not_verified")

    def test_quote_reappearance_on_wrong_page_does_not_count(self):
        mismatched = dict(self.evidence[0], page=6)
        info = assessment(mismatched, None)
        self.assertFalse(info["quote_found_on_original_indexed_page"])
        self.assertEqual(info["priority"], 100)


if __name__ == "__main__":
    unittest.main()

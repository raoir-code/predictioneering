"""Network-free tests for Puzzle Finder -> scientific citation retrieval."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.factory.puzzle_evidence import assemble, diversified, main


def hit(paper, number, score):
    return {
        "file": paper + ".pdf", "pdf_sha256": "hash-" + paper,
        "evidence_id": "p1-" + str(number), "pdf_page": number,
        "score": score, "title": paper, "kind": "mechanism",
        "claim_unreviewed_or_annotated": "A provisional claim about interstate war.",
        "verified_quote": "A source quotation.",
        "human_review_status": "not_reviewed",
        "interpretation_independently_checked": False,
    }


class PuzzleEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "research"
        (self.home / "projects").mkdir(parents=True)
        self.puzzle = "a0123456789abcde"
        (self.home / "projects" / (self.puzzle + ".json")).write_text(
            json.dumps({
                "id": self.puzzle,
                "title": "Why does war escalation persist?",
                "candidate_mechanism": "Rivalry commitment problem",
                "status": "approved_for_literature_review",
            }), encoding="utf-8"
        )

    def test_round_robin_prevents_single_paper_monopoly(self):
        hits = [hit("dominant", i, 50-i) for i in range(8)]
        hits += [hit("second", 20, 35), hit("third", 30, 27)]
        result = diversified(hits, limit=6, max_per_paper=2)
        self.assertEqual(len(result), 4)
        self.assertEqual([r["file"] for r in result[:3]],
                         ["dominant.pdf", "second.pdf", "third.pdf"])
        self.assertEqual([r["file"] for r in result].count("dominant.pdf"), 2)

    def test_deduplicates_and_ranks_across_multiple_searches(self):
        def fake_search(database, query, limit, approved_only):
            rows = ([hit("A", 1, 20), hit("A", 2, 18), hit("B", 1, 11)]
                    if "war" in query else
                    [hit("A", 1, 17), hit("C", 1, 12)])
            return {"results": rows, "evidence_hits": len(rows),
                    "profiles_matching": len(set(row["file"] for row in rows))}
        with patch("research.factory.puzzle_evidence.search", fake_search):
            output = assemble(self.home / "missing-db", queries=["war", "rivalry"],
                              max_per_paper=1)
        self.assertEqual(output["total_unique_candidates_in_retrieved_pool"], 4)
        self.assertEqual(output["papers_in_selected"], 3)
        self.assertEqual(output["selected_evidence"][0]["matched_queries"],
                         ["war", "rivalry"])
        self.assertFalse(output["novelty_verified"])

    def test_approved_puzzle_status_does_not_imply_verified_literature(self):
        with patch("research.factory.puzzle_evidence.search", return_value={
            "results": [hit("One", 1, 10)], "evidence_hits": 1,
            "profiles_matching": 1
        }) as search_mock:
            output = assemble(home=self.home, puzzle_id=self.puzzle)
        self.assertEqual(len(output["queries"]), 2)
        self.assertTrue(output["subject"]["human_approved"])
        self.assertFalse(output["novelty_verified"])
        self.assertEqual(output["scientific_verdict"], "not_verified")
        self.assertEqual(search_mock.call_count, 2)

    def test_approved_only_is_forwarded_to_catalog(self):
        with patch("research.factory.puzzle_evidence.search", return_value={
            "results": [], "evidence_hits": 0, "profiles_matching": 0
        }) as search_mock:
            output = assemble(queries=["war escalation"], approved_only=True)
        self.assertEqual(output["selected_evidence"], [])
        self.assertTrue(search_mock.call_args.kwargs["approved_only"])

    def test_file_path_cannot_be_traversed_as_puzzle_id(self):
        with self.assertRaisesRegex(ValueError, "16 lowercase hex"):
            assemble(home=self.home, puzzle_id="../some-secret")
        with self.assertRaisesRegex(ValueError, "Choose a puzzle ID or"):
            assemble(home=self.home, puzzle_id=self.puzzle,
                     spec_path=Path("test.json"))

    def test_json_spec_uses_search_queries(self):
        spec = Path(self.temp.name) / "spec.json"
        spec.write_text(json.dumps({
            "id": "new_puzzle", "research_question": "Why do wars recur?",
            "search_queries": ["power transition", "rivalry escalation"]
        }), encoding="utf-8")
        with patch("research.factory.puzzle_evidence.search", return_value={
            "results": [], "evidence_hits": 0, "profiles_matching": 0
        }):
            output = assemble(spec_path=spec)
        self.assertEqual(len(output["queries"]), 2)
        self.assertEqual(output["subject"]["spec_id"], "new_puzzle")

    def test_optional_save_stays_private_and_does_not_call_claude(self):
        with patch("research.factory.puzzle_evidence.search", return_value={
            "results": [hit("One", 1, 5)], "evidence_hits": 1,
            "profiles_matching": 1
        }):
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                code = main(["--home", str(self.home), "--query",
                             "war escalation", "--save"])
        self.assertEqual(code, 0)
        parsed = json.loads(capture.getvalue())
        path = Path(parsed["saved_private_record"])
        self.assertTrue(path.is_file())
        self.assertIn("inbox/records", path.as_posix())
        self.assertEqual(len(json.loads(path.read_text())["selected_evidence"]), 1)


if __name__ == "__main__":
    unittest.main()

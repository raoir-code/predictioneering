import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.factory.literature import abstract_text, search_openalex, verify_map, run


def work(i, query="q"):
    return {"id": f"https://openalex.org/W{i}", "display_name": f"Paper {i}",
            "publication_year": 2022, "authorships": [], "query_hits": [query],
            "abstract_inverted_index": {"A": [0], "ceasefire": [1]}}


def review(sid):
    return {
        "camps": [{"name": "strategic violations", "argument": "Potentially relevant",
                   "source_ids": [sid]}],
        "closest_work": [{"source_id": sid, "overlap": "Related",
                          "limitations_to_verify": "Need full text"}],
        "candidate_gap": "Possibly missing conditions for asymmetric restraint",
        "alternative_explanations": ["Measurement"], "questions_for_full_text": ["Check theory"],
        "priority_source_ids": [sid], "provisional_verdict": "investigate",
    }


class LiteratureTests(unittest.TestCase):
    def test_inverted_abstract(self):
        self.assertEqual(abstract_text({"ceasefire": [1], "A": [0]}), "A ceasefire")

    def test_dedupes_metadata(self):
        sample = {"results": [work(123)]}
        with patch("research.factory.literature._request_json", return_value=sample):
            result = search_openalex(["one", "two"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["query_hits"], ["one", "two"])

    def test_rejects_invented_citation(self):
        with self.assertRaisesRegex(ValueError, "unknown source"):
            verify_map(review("https://openalex.org/W999"), [work(123)])

    def test_review_remains_unverified(self):
        valid = verify_map(review("https://openalex.org/W123"), [work(123)])
        self.assertFalse(valid["novelty_verified"])
        self.assertEqual(valid["status"], "needs_full_text_and_human_review")

    def test_cached_sources_after_model_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / "research"
            spec_path = Path(folder) / "spec.json"
            spec_path.write_text(json.dumps({
                "id": "test_puzzle", "research_question": "Why do some truces persist?",
                "search_queries": ["ceasefire durability"]
            }))
            with patch("research.factory.literature.search_openalex", return_value=[work(123)]) as finder, \
                 patch("research.factory.literature.ask_claude", side_effect=RuntimeError("transient")):
                with self.assertRaisesRegex(RuntimeError, "transient"):
                    run(spec_path, home)
            record_path = next((home / "inbox" / "records").glob("*.json"))
            self.assertEqual(json.loads(record_path.read_text())["status"], "failed")
            with patch("research.factory.literature.search_openalex") as finder, \
                 patch("research.factory.literature.ask_claude", return_value=review("https://openalex.org/W123")):
                run(spec_path, home)
                finder.assert_not_called()
            self.assertEqual(json.loads(record_path.read_text())["status"], "complete")
            with patch("research.factory.literature.search_openalex") as finder, \
                 patch("research.factory.literature.ask_claude") as writer:
                run(spec_path, home)
                finder.assert_not_called()
                writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()

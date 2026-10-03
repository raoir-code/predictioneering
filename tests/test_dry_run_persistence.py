import hashlib
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("GNEWS_API_KEY", "test-key")

from pipeline import engine
from pipeline import predict


ROOT = Path(__file__).resolve().parents[1]

PERSISTENT_STATE = [
    ROOT / "pipeline" / ".context_cooldown_state.json",
    ROOT / "pipeline" / "agglomeration_configs.json",
    ROOT / "pipeline" / "classified_feed.json",
    ROOT / "pipeline" / "context_changelog.jsonl",
    ROOT / "pipeline" / "dyad_configs.json",
    ROOT / "pipeline" / "live_feed.json",
    ROOT / "pipeline" / "node_memory_state.json",
    ROOT / "pipeline" / "node_score_history.jsonl",
    ROOT / "pipeline" / "theater_state.json",
    ROOT / "pipeline" / "translator_cache.json",
    ROOT / "predictions" / "log.jsonl",
    ROOT / "predictions" / "brier_log.jsonl",
    ROOT / "predictions" / "brier_summary.json",
]


def digest(path):
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DryRunPersistenceTests(unittest.TestCase):

    def test_predict_dry_run_does_not_mutate_persistent_state(self):
        before = {str(p): digest(p) for p in PERSISTENT_STATE}

        # No network calls are needed for this invariant test.
        # Empty evidence causes both node-scoring functions to return zeros.
        with patch.object(predict, "fetch_gnews", return_value=[]):
            predict.run(dry_run=True)

        after = {str(p): digest(p) for p in PERSISTENT_STATE}

        changed = {
            p: (before[p], after[p])
            for p in before
            if before[p] != after[p]
        }

        self.assertEqual(
            changed,
            {},
            msg=f"dry_run mutated persistent state: {changed}",
        )

    def test_fetch_gnews_can_disable_cache_write(self):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "articles": [
                        {
                            "title": "Test headline",
                            "description": "Test description",
                            "publishedAt": "2026-10-03T12:00:00Z",
                        }
                    ]
                }

        with tempfile.TemporaryDirectory() as td:
            cache_dir = Path(td)

            with (
                patch.object(engine, "GNEWS_CACHE", cache_dir),
                patch.object(engine.requests, "get", return_value=FakeResponse()),
                patch.object(engine.time, "sleep", return_value=None),
            ):
                result = engine.fetch_gnews(
                    "US-Iran",
                    date(2026, 10, 3),
                    write_cache=False,
                )

            self.assertEqual(len(result), 1)
            self.assertEqual(list(cache_dir.iterdir()), [])

    def test_node_scoring_failure_can_disable_log_write(self):
        with tempfile.TemporaryDirectory() as td:
            failure_log = Path(td) / "node_scoring_failures.jsonl"

            with (
                patch.object(engine, "NODE_SCORING_FAILURES_LOG", failure_log),
                patch.object(
                    engine.requests,
                    "post",
                    side_effect=engine.requests.exceptions.ConnectionError(
                        "synthetic failure"
                    ),
                ),
                patch.object(engine.time, "sleep", return_value=None),
            ):
                result = engine._call_claude_json(
                    "test",
                    ["x"],
                    max_tokens=10,
                    retries=0,
                    dyad="US-Iran",
                    as_of_date=date(2026, 10, 3),
                    persist_failures=False,
                )

            self.assertEqual(result, {"x": 0.0})
            self.assertFalse(failure_log.exists())


if __name__ == "__main__":
    unittest.main()

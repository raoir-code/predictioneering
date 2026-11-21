import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research.factory.__main__ import ingest, main, validate


def sample():
    return {'puzzles': [{
        'title': 'Do elections change crisis escalation?',
        'phenomenon': 'A forecast miss during election periods.',
        'expected_theory': 'Expected little escalation.',
        'why_puzzling': 'Could indicate missing bargaining incentives.',
        'candidate_mechanism': 'Electoral audience costs.',
        'testable_prediction': 'Elections affect conflict risk conditional on rivalry.',
        'potential_data': 'Election dates and ACLED events.',
        'forecasting_benefit': 'Test prospective escalation gains.',
        'source_excerpt': 'forecast miss'
    }]}


class ResearchIntakeTests(unittest.TestCase):
    def test_complete_idempotent_and_human_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'research'
            log = Path(temp) / 'log.md'
            log.write_text('forecast miss near a midterm election')
            with patch('research.factory.__main__.claude', return_value=sample()) as model:
                with contextlib.redirect_stdout(io.StringIO()):
                    ingest(log, 'worklog', home)
                    ingest(log, 'worklog', home)
                self.assertEqual(model.call_count, 1)
            files = list((home / 'projects').glob('*.json'))
            self.assertEqual(len(files), 1)
            item = json.loads(files[0].read_text())
            self.assertEqual(item['novelty'], 'not_yet_checked')
            self.assertEqual(item['status'], 'pending_human_review')
            self.assertTrue(item['source_quote_verified'])
            with contextlib.redirect_stdout(io.StringIO()):
                status = main(['--home', str(home), 'approve', item['id']])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(files[0].read_text())['status'],
                             'approved_for_literature_review')

    def test_conceptual_puzzle_needs_no_hypothesis_or_dataset(self):
        candidate={"puzzles":[{
            "title":"Can predictable holidays change attack incentives?",
            "phenomenon":"Predictable public holidays may affect military readiness.",
            "competing_intuitions":"Attacker sees an opportunity; defender anticipates it and prepares.",
            "why_puzzling":"If both anticipate each other, why should attack timing change?",
            "why_worth_investigating":"Strategic predictability may neutralize short-term opportunities.",
            "source_excerpt":"holidays"
        }]}
        result=validate(candidate,"Working notes about holidays and anticipation")
        self.assertEqual(result[0]["testable_prediction"],"")
        self.assertEqual(result[0]["candidate_mechanism"],"")
        self.assertTrue(result[0]["source_quote_verified"])
        self.assertEqual(result[0]["status"],"pending_human_review")

    def test_fabricated_quote_is_not_accepted(self):
        puzzle = sample()
        puzzle['puzzles'][0]['source_excerpt'] = 'not in the input'
        result = validate(puzzle, 'forecast miss')
        self.assertEqual(result[0]['source_excerpt'], '')
        self.assertFalse(result[0]['source_quote_verified'])

    def test_failed_call_is_saved_and_retryable(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'research'
            log = Path(temp) / 'log.md'
            log.write_text('forecast miss during elections')
            with patch('research.factory.__main__.claude', side_effect=RuntimeError('temporary failure')):
                with self.assertRaises(RuntimeError):
                    ingest(log, 'diagnostic', home)
            record_path = next((home / 'inbox' / 'records').glob('*.json'))
            self.assertEqual(json.loads(record_path.read_text())['status'], 'failed')
            with patch('research.factory.__main__.claude', return_value=sample()):
                with contextlib.redirect_stdout(io.StringIO()):
                    ingest(log, 'diagnostic', home)
            self.assertEqual(json.loads(record_path.read_text())['status'], 'complete')

    def test_retry_does_not_duplicate_or_overwrite_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'research'
            log = Path(temp) / 'log.md'
            log.write_text('forecast miss during elections')
            with patch('research.factory.__main__.claude', return_value=sample()):
                with contextlib.redirect_stdout(io.StringIO()):
                    ingest(log, 'worklog', home)
            card = next((home / 'projects').glob('*.json'))
            approved = json.loads(card.read_text())
            approved['status'] = 'approved_for_literature_review'
            card.write_text(json.dumps(approved))
            record = next((home / 'inbox' / 'records').glob('*.json'))
            intake = json.loads(record.read_text())
            intake['status'] = 'failed'
            record.write_text(json.dumps(intake))
            with patch('research.factory.__main__.claude', return_value=sample()):
                with contextlib.redirect_stdout(io.StringIO()):
                    ingest(log, 'worklog', home)
            self.assertEqual(len(list((home / 'projects').glob('*.json'))), 1)
            self.assertEqual(json.loads(card.read_text())['status'], 'approved_for_literature_review')

    def test_no_puzzles_is_valid(self):
        self.assertEqual(validate({'puzzles': []}, 'ordinary maintenance log'), [])

    def test_show_does_not_change_status(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / 'research'
            log = Path(temp) / 'log.md'
            log.write_text('forecast miss during elections')
            with patch('research.factory.__main__.claude', return_value=sample()):
                with contextlib.redirect_stdout(io.StringIO()):
                    ingest(log, 'worklog', home)
            card = next((home / 'projects').glob('*.json'))
            item = json.loads(card.read_text())
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = main(['--home', str(home), 'show', item['id']])
            self.assertEqual(status, 0)
            self.assertIn('Literature novelty', output.getvalue())
            self.assertEqual(json.loads(card.read_text())['status'], 'pending_human_review')


if __name__ == '__main__':
    unittest.main()

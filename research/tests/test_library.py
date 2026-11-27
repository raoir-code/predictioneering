import csv
import json
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from research.factory.library import (connect, import_zotero, import_hazards,
                                      search_documents, search_hazards, stats)
from research.factory.library_review import run, local_sources


class ResearchLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.dbpath = self.home / 'private' / 'library.sqlite3'
        self.zpath = self.home / 'Zotero.json'
        self.zpath.write_text(json.dumps([
            {'id': 'http://zotero.org/users/1/items/A',
             'title': 'Why Some Ceasefires Survive',
             'DOI': 'https://doi.org/10.1234/ABC',
             'abstract': 'A ceasefire can survive violence.',
             'type': 'article-journal',
             'issued': {'date-parts': [[2022, 4, 1]]}},
            {'id': 'http://zotero.org/users/1/items/B',
             'title': 'Civil War Causes', 'abstract': '', 'type': 'book'}
        ]))
        self.hpath = self.home / 'hazards.csv'
        self.headers = ['study', 'variable', 'coefficient', 'se', 'p_value',
                        'model_type', 'outcome_class', 'conflict_type', 'family',
                        'in_analysis_sample']
        with self.hpath.open('w', newline='') as fp:
            writer = csv.DictWriter(fp, self.headers)
            writer.writeheader()
            writer.writerow({'study': 'Sample Study 2020', 'variable': 'Contiguity',
                             'coefficient': '2.0', 'se': '0.4', 'p_value': '0.01',
                             'model_type': 'logit', 'outcome_class': 'interstate_onset',
                             'conflict_type': 'MID', 'family': 'contiguity',
                             'in_analysis_sample': 'True'})

    def init(self):
        conn = connect(self.dbpath)
        import_zotero(conn, self.zpath)
        import_hazards(conn, self.hpath)
        return conn

    def test_import_idempotence_and_preserves_raw(self):
        with closing(self.init()) as conn:
            self.assertEqual(stats(conn)['zotero_references'], 2)
            self.assertEqual(stats(conn)['hazard_estimates'], 1)
            self.assertEqual(import_zotero(conn, self.zpath), (2, 'unchanged'))
            self.assertEqual(import_hazards(conn, self.hpath), (1, 'unchanged'))
            self.assertEqual(stats(conn)['hazard_estimates'], 1)
            record = conn.execute('select metadata_json from hazard_estimates').fetchone()[0]
            self.assertEqual(json.loads(record)['coefficient'], '2.0')
            self.assertEqual(search_documents(conn, 'ceasefire')[0]['doi'], '10.1234/abc')
            self.assertEqual(search_hazards(conn, 'contiguity')[0]['coefficient'], '2.0')

    def test_invalid_csv_cannot_destroy_previous_import(self):
        with closing(self.init()) as conn:
            self.hpath.write_text('invalid,headers\n1,2\n')
            with self.assertRaisesRegex(ValueError, 'missing required columns'):
                import_hazards(conn, self.hpath)
            self.assertEqual(stats(conn)['hazard_estimates'], 1)

    def test_import_changed_file_replaces_not_duplicates(self):
        with closing(self.init()) as conn:
            items = json.loads(self.zpath.read_text())
            items.pop()
            self.zpath.write_text(json.dumps(items))
            self.assertEqual(import_zotero(conn, self.zpath), (1, 'imported'))
            self.assertEqual(stats(conn)['zotero_references'], 1)

    def test_literature_can_retrieve_without_external_api(self):
        with closing(self.init()):
            pass
        spec = self.home / 'spec.json'
        spec.write_text(json.dumps({'id': 'test_ceasefire',
                                    'research_question': 'Why do ceasefires persist?',
                                    'search_queries': ['ceasefire violence', 'ceasefire violations']}))
        bundle = run(spec, db_path=self.dbpath, home=self.home / 'research',
                     external=False, retrieve_only=True)
        self.assertGreaterEqual(bundle['local_count'], 1)
        self.assertEqual(bundle['external_count'], 0)
        self.assertEqual(bundle['hazard_matches'], [])
        self.assertFalse(bundle['sources'][0]['full_text_verified'])
        self.assertIn('Ceasefires', bundle['sources'][0]['title'])

    def test_api_failure_falls_back_to_local_without_fake_novelty(self):
        with closing(self.init()):
            pass
        spec = self.home / 'spec.json'
        spec.write_text(json.dumps({'id': 'failure_case',
                                    'research_question': 'Why do ceasefires persist?',
                                    'search_queries': ['ceasefire violence']}))
        report_dir = self.home / 'research'
        with patch('research.factory.library_review.openalex', side_effect=RuntimeError('no API')):
            bundle = run(spec, db_path=self.dbpath, home=report_dir,
                         external=True, retrieve_only=True)
        self.assertIn('no API', bundle['external_search_error'])
        with patch('research.factory.library_review.synthesize', return_value={
            'provisional_verdict': 'insufficient_evidence',
            'candidate_gap': 'Cannot establish novelty',
            'novelty_verified': False,
        }) as model:
            result = run(spec, db_path=self.dbpath, home=report_dir, external=True)
            self.assertEqual(model.call_count, 1)
            self.assertTrue(result['assessment']['external_discovery_incomplete'])
            self.assertFalse(result['assessment']['novelty_verified'])
        with patch('research.factory.library_review.synthesize') as model:
            rerun = run(spec, db_path=self.dbpath, home=report_dir, external=True)
            model.assert_not_called()
            self.assertEqual(rerun['status'], 'complete')


if __name__ == '__main__':
    unittest.main()

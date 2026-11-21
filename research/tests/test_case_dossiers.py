"""Offline forecast-dossier tests with authentic resolver field names."""
import json
from pathlib import Path
import tempfile
import unittest
from research.factory import case_dossiers as d


class CaseDossierTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.brier=self.root/'brier.jsonl'
        self.pred=self.root/'pred.jsonl'
        self.nodes=self.root/'nodes.jsonl'
        self.meta=self.root/'meta.json'
        self.news=self.root/'news.json'
        self.context=self.root/'context.json'
        self.out=self.root/'private.json'
        self.data={'market_id':'42','market_label':'Will Iran strike Iraq by Dec 31?',
                   'dyad':'Iran-Iraq','first_prediction_ts':'2026-11-01T12:00:00+00:00',
                   'resolved_at':'2026-11-10T12:00:00+00:00',
                   'outcome':1,'conditional_p':0.01,'market_p_at_first':0.4,
                   'contract_type':'binary_onset','relation':'equivalent'}
        self.write_lines(self.brier,[self.data])
        self.write_lines(self.pred,[
            {'market_id':'42','timestamp':'2026-11-01T11:55:00+00:00','conditional_p':0.01,'market_p':0.4},
            {'market_id':'42','timestamp':'2026-11-02T11:55:00+00:00','conditional_p':0.8,'market_p':0.9}])
        self.write_lines(self.nodes,[
            {'dyad':'Iran-Iraq','logged_at':'2026-10-31T00:00:00+00:00','TriggerType':0.2},
            {'dyad':'Iran-Iraq','logged_at':'2026-11-02T00:00:00+00:00','TriggerType':0.9}])
        self.meta.write_text(json.dumps({'42':{'question':self.data['market_label'],
                                               'endDate':'2026-12-31T00:00:00+00:00',
                                               'fetched_at':'2026-11-06T00:00:00+00:00'}}))
        self.news.write_text(json.dumps([
            {'id':'n1','title':'Pre-forecast news','url':'https://example.org/pre',
             'published_at':'2026-10-31T00:00:00+00:00'},
            {'id':'n2','title':'Post-forecast news','url':'https://example.org/post',
             'published_at':'2026-11-05T00:00:00+00:00'},
            {'id':'n3','title':'Undated','url':'https://example.org/undated'}]))
        self.context.write_text(json.dumps([
            {'id':'pre-code','captured_at':'2026-10-30T00:00:00+00:00','code_sha':'a'*40,'summary':'Game model'},
            {'id':'future-code','captured_at':'2026-11-02T00:00:00+00:00','code_sha':'b'*40,'summary':'Retrospective'}]))

    def write_lines(self,path,items):
        path.write_text(''.join(json.dumps(r)+'\n' for r in items))

    def run_build(self,**kwargs):
        opts=dict(brier=self.brier,predictions=self.pred,nodes=self.nodes,
                  metadata=self.meta,news=self.news,model_context=self.context,out=self.out)
        opts.update(kwargs)
        return d.build(**opts)

    def test_only_as_of_data_used(self):
        result=self.run_build();c=result['cases'][0]
        self.assertEqual(result['dossier_count'],1)
        self.assertEqual(len(c['individual_forecasts_as_of']),1)
        self.assertEqual(c['future_or_undated_forecasts_excluded'],1)
        self.assertEqual(c['node_traces_as_of'][0]['values']['TriggerType'],0.2)
        self.assertEqual([x['source_id'] for x in c['news_published_by_forecast']],['NEWS:n1'])
        self.assertEqual([x['source_id'] for x in c['news_published_after_forecast']],['NEWS:n2'])
        self.assertEqual(len(c['news_without_valid_publication_time_excluded']),1)
        self.assertEqual(len(c['historical_models_as_of']),1)
        self.assertEqual(c['rejected_unproven_model_context'][0]['id'],'future-code')
        self.assertFalse(c['market_metadata']['as_of_snapshot_proven'])
        self.assertAlmostEqual(c['outcome_after']['model_brier'],0.9801)

    def test_missing_prediction_log_fails_closed(self):
        self.pred.unlink()
        c=self.run_build()['cases'][0]
        self.assertEqual(c['individual_forecasts_matched_count'],0)
        self.assertFalse(c['model_reasoning_verified'])
        self.assertIn('missing or empty', ' '.join(c['missing_evidence_or_warnings']))

    def test_post_resolution_forecast_excluded(self):
        self.data['first_prediction_ts']='2026-11-11T00:00:00+00:00'
        self.write_lines(self.brier,[self.data])
        with self.assertRaises(ValueError):
            self.run_build(market_ids=['42'])

    def test_false_historical_model_unproven(self):
        self.context.write_text(json.dumps([{'id':'unverified','code_sha':'c'*40}]))
        c=self.run_build()['cases'][0]
        self.assertFalse(c['historical_models_as_of'])
        self.assertFalse(c['model_reasoning_verified'])

    def test_source_checksum_and_immutability(self):
        old=self.brier.read_bytes()
        r=self.run_build()
        self.assertEqual(self.brier.read_bytes(),old)
        self.assertEqual(r['source_provenance']['brier']['sha256'],d.hashlib.sha256(old).hexdigest())
        self.assertTrue(self.out.exists())

    def test_reject_overwriting_production(self):
        with self.assertRaises(ValueError):
            self.run_build(out=self.brier)

    def test_unknown_market_rejected(self):
        with self.assertRaises(ValueError):
            self.run_build(market_ids=['not-real'])

    def test_corrupt_and_conflicting_resolutions_excluded(self):
        self.write_lines(self.brier,[self.data,{**self.data,'outcome':0}])
        with self.assertRaises(ValueError):
            self.run_build(market_ids=['42'])

    def test_top_ranked_deduplicates_near_contracts(self):
        self.write_lines(self.brier,[self.data,
                         {**self.data,'market_id':'43','market_label':'Will Iran strike Iraq by Nov 30?'}])
        self.assertEqual(self.run_build(top=10)['dossier_count'],1)


if __name__=='__main__':unittest.main()

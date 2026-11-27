import json
from pathlib import Path
import tempfile
import unittest
from research.factory import diagnostic_critic as c

class DiagnosticCriticTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.dossiers=self.root/'cases.json'
        self.output=self.root/'critic.json'
        self.dossiers.write_text(json.dumps({'cases':[
            {'market_id':'42','market_label':'A','source_registry':{'FILE:brier':{'kind':'local_file'}},
             'model_reasoning_verified':False,'dossier_version':'v1',
             'forecast_cutoff_utc':'2026-11-01T00:00:00+00:00'}]}))
        self.good={'case_ids':['42'],'diagnosis_categories':['INSUFFICIENT_EVIDENCE'],
                   'ranked_hypotheses':[{'explanation':'Could be contract coding error',
                    'supporting_source_ids':['FILE:brier'],'contradicting_source_ids':[],
                    'tests_to_discriminate':['Read the market rules contemporaneous to forecast']}],
                   'existing_theory_comparison':'No verified original theoretical passages',
                   'candidate_puzzle_or_null':None,'uncertainty':'High',
                   'missing_evidence':['Forecast snapshots'],'recommended_action':'monitor'}
    def test_offline_plan_no_network(self):
        x=c.run(self.dossiers,out=self.output)
        self.assertEqual(x['status'],'offline_plan_no_api_call')
        self.assertFalse(self.output.exists())
    def test_requires_permission_and_budget(self):
        with self.assertRaises(ValueError):
            c.run(self.dossiers,out=self.output,send=True)
        with self.assertRaises(ValueError):
            c.run(self.dossiers,out=self.output,send=True,confirm_share=True,model='test',key='dummy')
        with self.assertRaises(ValueError):
            c.run(self.dossiers,out=self.output,send=True,confirm_share=True,model='test',key='dummy',
                  input_rate=100,output_rate=100,max_usd=0.00001)
    def test_stub_transport_and_cached_response(self):
        calls=[]
        def mock(payload,model,key,max_tokens):
            calls.append(1)
            return self.good,{'input_tokens':400,'output_tokens':100},model
        args=dict(out=self.output,send=True,confirm_share=True,model='test-model',key='dummy',
                  input_rate=1,output_rate=5,max_usd=1,transport=mock)
        res=c.run(self.dossiers,**args)
        self.assertEqual(res['status'],'diagnosis_saved_unreviewed')
        self.assertEqual(res['recommended_action'],'monitor')
        self.assertEqual(c.run(self.dossiers,**args)['status'],'reused_cached_diagnosis_no_api_call')
        self.assertEqual(len(calls),1)
        self.assertTrue(json.loads(self.output.read_text())['no_auto_approval'])
    def test_unknown_citation_rejected(self):
        payload,_=c.prepare(self.dossiers)
        bad=json.loads(json.dumps(self.good))
        bad['ranked_hypotheses'][0]['supporting_source_ids']=['NEWS:invented']
        with self.assertRaises(ValueError):c.validate_answer(bad,payload)
    def test_cannot_advance_without_model_history(self):
        payload,_=c.prepare(self.dossiers)
        bad={**self.good,'recommended_action':'advance_for_human_review',
             'diagnosis_categories':['PLAUSIBLE_MISSING_MECHANISM'],
             'candidate_puzzle_or_null':'Might there be missing coercion?'}
        with self.assertRaises(ValueError):c.validate_answer(bad,payload)
    def test_case_mismatch_rejected(self):
        payload,_=c.prepare(self.dossiers)
        with self.assertRaises(ValueError):
            c.validate_answer({**self.good,'case_ids':['99']},payload)
    def test_puzzle_cannot_coexist_insufficient_evidence(self):
        payload,_=c.prepare(self.dossiers)
        with self.assertRaises(ValueError):
            c.validate_answer({**self.good,'candidate_puzzle_or_null':'Fake novelty'},payload)
    def test_private_source_paths_not_in_payload(self):
        cases=json.loads(self.dossiers.read_text())
        cases['cases'][0]['source_registry']['FILE:brier']['filename']='/Users/private/secret'
        self.dossiers.write_text(json.dumps(cases))
        payload,_=c.prepare(self.dossiers)
        self.assertNotIn('/Users/private',json.dumps(payload))

if __name__=='__main__':unittest.main()

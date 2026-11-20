"""Offline, fully synthetic tests of the reusable research factory."""
import contextlib
import csv
from datetime import date, timedelta
import io
import json
from pathlib import Path
import random
import tempfile
import unittest

from research.factory.prototype import (
    analysis, data_file, digest, gate_report, make_demo, main, plan, read_data,
    read_json, run, validate_spec, write_json, temporal_validation
)


class FactoryPrototypeTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.dir=Path(td.name)
        self.spec=make_demo(self.dir)

    def test_validate_and_plan_zero_network(self):
        p=plan(self.spec)
        self.assertTrue(p['ready_to_run'])
        self.assertEqual(p['network_or_paid_api_calls'],0)
        self.assertTrue(p['data_exists'])

    def test_full_demo_creates_all_artifacts(self):
        res=run(self.spec,destination=self.dir/'out')
        self.assertEqual(res['status'],'prototype_complete')
        self.assertEqual(res['analysis_rows'],1200)
        self.assertEqual(res['estimate']['status'],'estimated_association_not_causal')
        self.assertGreater(res['estimate']['coefficient'],0)
        self.assertEqual(res['predictive_validation']['status'],'holdout_scored')
        self.assertTrue((self.dir/'out'/'MANUSCRIPT_DRAFT.md').exists())
        self.assertTrue((self.dir/'out'/'replication_manifest.json').exists())
        self.assertFalse((self.dir/'out'/'SYNTHETIC_data.csv').exists())
        manuscript=(self.dir/'out'/'MANUSCRIPT_DRAFT.md').read_text()
        self.assertIn('NOT A SUBMISSION-READY',manuscript)
        self.assertIn('Results (exploratory)',manuscript)
        quality=res['quality']['passes']
        self.assertFalse(quality['human_novelty_review'])
        self.assertFalse(quality['causal_identification_independently_approved'])
        self.assertFalse(quality['formal_theory_derivation_verified'])
        self.assertFalse(quality['non_synthetic_data'])

    def test_cache_is_idempotent_and_revised_data_invalidates(self):
        path=self.dir/'out'
        first=run(self.spec,destination=path)
        second=run(self.spec,destination=path)
        self.assertEqual(second['status'],'reused_cached_run')
        data=self.dir/'SYNTHETIC_data.csv'
        with data.open('a') as fp:
            fp.write('2024-04-11,unit_03,1,0.3,1\n')
        new=run(self.spec,destination=path)
        self.assertEqual(new['status'],'prototype_complete')
        self.assertEqual(new['analysis_rows'],1201)
        self.assertNotEqual(first['analysis_rows'],new['analysis_rows'])

    def test_novelty_gate_blocks_and_does_not_fit_or_write_draft(self):
        content=read_json(self.spec)
        content['novelty_review']={'status':'pending'}
        write_json(self.spec,content)
        result=run(self.spec,destination=self.dir/'out')
        self.assertEqual(result['status'],'blocked_before_analysis')
        self.assertFalse((self.dir/'out'/'MANUSCRIPT_DRAFT.md').exists())
        self.assertTrue(result['plan']['novelty_review_pending'])

    def test_missing_data_gate(self):
        content=read_json(self.spec)
        content['data']['csv_path']='missing_private.csv'
        write_json(self.spec,content)
        self.assertFalse(plan(self.spec)['ready_to_run'])
        self.assertEqual(run(self.spec)['status'],'blocked_before_analysis')

    def test_no_demogate_with_real_data(self):
        content=read_json(self.spec)
        content['data']['synthetic']=False
        with self.assertRaisesRegex(ValueError,'demo_only'):
            validate_spec(content)

    def test_invalid_column_formula_is_rejected(self):
        content=read_json(self.spec)
        content['design']['outcome']='y + import os'
        with self.assertRaisesRegex(ValueError,'safe column'):
            validate_spec(content)

    def test_binomial_nonbinary_outcome_fails_safely(self):
        with (self.dir/'SYNTHETIC_data.csv').open('a') as fp:
            fp.write('2024-01-01,unit_10,1,0.2,7\n')
        with self.assertRaisesRegex(ValueError,'0/1'):
            read_data(read_json(self.spec),self.dir/'SYNTHETIC_data.csv')

    def test_real_status_requires_human_review_identity(self):
        spec=read_json(self.spec)
        spec['data']['synthetic']=False
        spec['novelty_review']={'status':'approved'}
        with self.assertRaisesRegex(ValueError,'reviewer'):
            validate_spec(spec)
        spec['novelty_review']={'status':'approved','reviewer':'Researcher','notes':'Original papers manually reviewed'}
        self.assertEqual(validate_spec(spec)['novelty_review']['status'],'approved')

    def test_synthetic_did_estimation_and_no_fake_oos(self):
        rng=random.Random(7)
        p=self.dir/'did.csv'
        with p.open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['date','unit','treated','post','outcome'])
            for day in range(60):
                for unit in range(10):
                    t=int(unit>=5); post=int(day>=30)
                    outcome=1.3 + .4*t +.5*post+2.1*t*post + rng.gauss(0,.35)
                    w.writerow([(date(2024,1,1)+timedelta(days=day)).isoformat(), f'u{unit}',t,post,outcome])
        spec=read_json(self.spec)
        spec['data']['csv_path']=p.name
        spec['design']={'method':'did','family':'gaussian','outcome':'outcome','treatment':'treated',
                        'post':'post','time':'date','unit':'unit','controls':[], 'cluster':'unit'}
        frame,qc=read_data(spec,p)
        m=analysis(spec,frame,qc)
        self.assertEqual(m['status'],'estimated_association_not_causal')
        self.assertGreater(m['coefficient'],1.7)
        self.assertEqual(temporal_validation(spec,frame)['status'],'not_implemented_for_design')

    def test_synthetic_rdd_estimation_and_nonsharp_block(self):
        rng=random.Random(9)
        p=self.dir/'rdd.csv'
        with p.open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['date','running','treated','outcome'])
            for i in range(400):
                x=-1+2*i/399
                t=int(x>=0)
                y=1+2.5*t+0.4*x + rng.gauss(0,.2)
                w.writerow([(date(2024,1,1)+timedelta(days=i%70)).isoformat(),x,t,y])
        spec=read_json(self.spec)
        spec['data']['csv_path']=p.name
        spec['design']={'method':'rdd','family':'gaussian','outcome':'outcome','treatment':'treated',
                        'running':'running','time':'date','cutoff':0,'bandwidth':0.5,'controls':[]}
        frame,qc=read_data(spec,p)
        fit=analysis(spec,frame,qc)
        self.assertEqual(fit['status'],'estimated_association_not_causal')
        self.assertGreater(fit['coefficient'],2)
        spec['design']['cutoff']=0.1
        with self.assertRaisesRegex(ValueError,'sharp RDD'):
            read_data(spec,p)

    def test_cli_demo_and_plan(self):
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            code=main(['demo','--out',str(self.dir/'cli_demo')])
        self.assertEqual(code,0)
        summary=json.loads(stream.getvalue())
        self.assertTrue(summary['synthetic_demo_only'])
        self.assertEqual(summary['status'],'prototype_complete')
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            code=main(['plan',str(self.spec)])
        self.assertEqual(code,0)
        self.assertIn('ready_to_run',stream.getvalue())


if __name__=='__main__':
    unittest.main()

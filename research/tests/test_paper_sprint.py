"""Offline tests for manuscript/figure/formal-derivative packaging."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from research.factory import paper_sprint as ps


class PaperSprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_root=ps.ROOT
        cls.tmp=tempfile.TemporaryDirectory()
        ps.ROOT=Path(cls.tmp.name)/'research'
        ps.ROOT.mkdir(parents=True)
        cls.demo=ps.demo()
        cls.workspace=Path(cls.demo['demo_dir'])
        cls.spec_path=cls.workspace/'inputs'/'study.json'
        cls.model_path=cls.workspace/'inputs'/'formal_model.json'
        cls.analysis=cls.workspace/'analysis'

    @classmethod
    def tearDownClass(cls):
        ps.ROOT=cls.original_root
        cls.tmp.cleanup()

    def spec(self):return json.loads(self.spec_path.read_text())
    def model(self):return json.loads(self.model_path.read_text())

    def test_full_demo_zip_contains_tex_figures_no_private_csv(self):
        archive=Path(self.demo['archive'])
        with zipfile.ZipFile(archive) as z:
            files=z.namelist()
            self.assertIn('main.tex',files)
            self.assertIn('references.bib',files)
            self.assertIn('REVIEW_REQUIRED.md',files)
            self.assertIn('figures/estimate.pdf',files)
            self.assertIn('figures/holdout.pdf',files)
            self.assertNotIn('SYNTHETIC_ultimatum.csv',files)
            self.assertFalse(any(x.endswith('.csv') for x in files))
            self.assertFalse(any(x.endswith(('.log','.aux','.out','.pdf')) and x.startswith('main.') for x in files))

    def test_synthetic_and_review_gates_always_unapproved(self):
        qc=json.loads((Path(self.demo['package_dir'])/'PAPER_QC.json').read_text())
        self.assertTrue(qc['gates']['symbolic_derivative_signs_verified'])
        for k in ('equilibrium_proof_independently_verified','non_synthetic_data',
                  'human_final_manuscript_review','claim_to_source_citations_independently_checked'):
            self.assertFalse(qc['gates'][k])
        self.assertEqual(qc['status'],'UNREVIEWED_NOT_SUBMISSION_READY')

    def test_derivation_and_empirical_mapping_match(self):
        checked=ps.check_model(self.model(),self.spec())
        self.assertEqual(checked['derivatives'][0]['derivative_sympy'],'1')
        self.assertEqual(checked['derivatives'][0]['hypothesis_id'],'H1')
        self.assertFalse(checked['equilibrium_optimality_verified'])

    def test_hypotheses_generated_from_theory_first(self):
        h=ps.hypotheses_from_model(self.model())
        self.assertEqual(h['hypotheses'][0]['prediction'],self.spec()['hypotheses'][0]['prediction'])
        self.assertTrue(h['review_required'])

    def test_conflicting_empirical_hypothesis_fails(self):
        s=self.spec();s['hypotheses'][0]['prediction']='Opposite outcome!'
        with self.assertRaisesRegex(ValueError,'exactly match'):
            ps.check_model(self.model(),s)

    def test_conflicting_sign_fails(self):
        s=self.spec();s['hypotheses'][0]['sign']='negative'
        with self.assertRaisesRegex(ValueError,'contradicts'):
            ps.check_model(self.model(),s)

    def test_wrong_explanatory_or_outcome_mapping_fails(self):
        m=self.model();m['comparative_statics'][0]['empirical_mapping']['outcome']='unobserved'
        with self.assertRaisesRegex(ValueError,'map to'):
            ps.check_model(m,self.spec())

    def test_unverified_sign_does_not_claim_proof(self):
        m=self.model();m['equilibrium']['expression']='u*V'
        check=ps.check_model(m,self.spec())
        self.assertTrue(check['all_derivative_signs_verified'])  # V>0 explicitly
        m['parameters']['V']='real'
        check=ps.check_model(m,self.spec())
        self.assertFalse(check['all_derivative_signs_verified'])

    def test_injected_python_and_function_calls_fail_closed(self):
        m=self.model()
        for s in ('__import__("os").system("true")', 'open("file")','u.__class__','u+z','u**999'):
            m['equilibrium']['expression']=s
            with self.subTest(expr=s),self.assertRaises(ValueError):
                ps.check_model(m,self.spec())

    def test_typed_reference_malformed_doi_not_cited(self):
        bib,refs,warn=ps.bibliography([{'title':'A fake synthetic title','authors':'Test, T.',
                                      'year':2026,'doi':'bad doi'}])
        self.assertFalse(refs)
        self.assertTrue(warn)
        self.assertNotIn('fake synthetic',bib)

    def test_citation_claims_require_source_key_page_and_attestation(self):
        data=[{'title':'Bibliographic test entry','authors':'Test, T.',
               'year':2025,'doi':'10.1111/example.2025'}]
        _,refs,warnings=ps.bibliography(data)
        self.assertFalse(warnings)
        self.assertEqual(refs[0]['key'],'provided001')
        spec={'literature_claims':[{'source_key':'provided001','page':13,
                'claim':'An original claim is present.','verbatim_quote':'Quoted example original passage',
                'human_quote_checked':False},
                {'source_key':'phantom','page':13,'claim':'Untraceable',
                 'verbatim_quote':'Bad source claim','human_quote_checked':True}]}
        accepted,warnings=ps.evidence_claims(spec,refs)
        self.assertFalse(accepted)
        self.assertEqual(len(warnings),2)
        spec['literature_claims'][0]['human_quote_checked']=True
        accepted,warnings=ps.evidence_claims(spec,refs)
        self.assertEqual(len(accepted),1)
        output=ps.manuscript(self.spec(),self.model(),ps.check_model(self.model(),self.spec()),
                             json.loads((self.analysis/'results.json').read_text()),refs,[],accepted)
        self.assertIn(r'\cite[p.~13]{provided001}',output)
        self.assertNotIn('phantom',output)

    def test_stale_analysis_must_fail_even_with_valid_result_json(self):
        with tempfile.TemporaryDirectory() as td:
            inp=Path(td)/'input';inp.mkdir()
            spath=inp/'study.json';m=inp/'formal_model.json'
            s=self.spec();s['title']='Changed without analysis rerun';s['data']['csv_path']=str(self.workspace/'inputs'/'SYNTHETIC_ultimatum.csv')
            spath.write_text(json.dumps(s));m.write_text(json.dumps(self.model()))
            with self.assertRaisesRegex(ValueError,'fingerprint mismatch'):
                ps.run(spath,m,out=Path(td)/'output',analysis_dir=self.analysis)

    def test_output_contains_no_false_actual_citations(self):
        main=(Path(self.demo['package_dir'])/'main.tex').read_text()
        self.assertIn('No complete attributable bibliographic records',main)
        self.assertNotIn(r'\cite{provided001}',main)
        self.assertIn('not independently proved',main)

    def test_result_charts_are_computed_from_analysis_not_invented(self):
        self.assertEqual(self.demo['figures'],['estimate','holdout'])
        result=json.loads((Path(self.demo['package_dir'])/'statistical_results.json').read_text())
        self.assertEqual(result['model']['status'],'estimated_association_not_causal')
        self.assertEqual(result['predictive_validation']['status'],'holdout_scored')

    def test_model_missing_players_or_payoffs_rejected(self):
        m=self.model();m['payoffs'].pop('Responder')
        with self.assertRaisesRegex(ValueError,'payoff'):
            ps.check_model(m,self.spec())

    def test_no_hypotheses_rejected(self):
        m=self.model();m['comparative_statics']=[]
        with self.assertRaisesRegex(ValueError,'Every prespecified'):
            ps.check_model(m,self.spec())

    @unittest.skipUnless(shutil.which('pdflatex'),'LaTeX not installed on this host')
    def test_latex_compiles_with_figures(self):
        import subprocess
        package=Path(self.demo['package_dir'])
        proc=subprocess.run(['pdflatex','-interaction=nonstopmode','-halt-on-error','main.tex'],
                            cwd=package,capture_output=True,timeout=45)
        self.assertEqual(proc.returncode,0,proc.stdout.decode('utf-8',errors='replace')[-2500:])
        self.assertGreater((package/'main.pdf').stat().st_size,10000)


if __name__=='__main__':unittest.main()

# Separate integration check: source-linked text and bibliography compile together.
class BibliographyIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('pdflatex') and shutil.which('bibtex'),
                         'LaTeX/BibTeX tools not installed')
    def test_attested_page_citation_compiles_with_bibtex(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            spec_path=ps.ROOT/'projects'/'factory_runs'/'paper_sprint_synthetic_demo'/'inputs'/'study.json'
            model_path=ps.ROOT/'projects'/'factory_runs'/'paper_sprint_synthetic_demo'/'inputs'/'formal_model.json'
            # Generate an independent toy dataset rather than using any private research data.
            source=ps.prototype.make_demo(root/'base')
            sp=ps.prototype.read_json(source)
            mod={
                'title':'Two-player toy decision problem',
                'players':['P','R'],
                'information':'Both know u',
                'timing':'P moves before R',
                'strategies':['P offers','R accepts'],
                'payoffs':{'P':'residual','R':'offer or outside option'},
                'solution_concept':'Asserted toy subgame perfect equilibrium',
                'equilibrium_argument':'Synthetic game notation for a formatting check only',
                'parameters':{'u':'positive'},'equilibrium':{'choice':'x','expression':'u'},
                'comparative_statics':[{'id':'CS1','parameter':'u','sign':'positive',
                 'hypothesis_id':'H1','hypothesis_text':sp['hypotheses'][0]['prediction'],
                 'interpretation':'Toy mapping only',
                 'empirical_mapping':{'predictor':sp['design']['treatment'],
                                      'outcome':sp['design']['outcome']}}],
            }
            sp['data']['csv_path']=str((root/'base'/'SYNTHETIC_data.csv').resolve())
            sp['literature']=[{'title':'Synthetic bibliography placeholder',
                              'authors':'Test, Example','year':2025,
                              'doi':'10.1000/example.2025'}]
            sp['literature_claims']=[{'source_key':'provided001','page':13,
                                     'claim':'Toy source description, not factual evidence.',
                                     'verbatim_quote':'A hypothetical quote.',
                                     'human_quote_checked':True}]
            study=root/'study.json';formal=root/'formal.json'
            study.write_text(json.dumps(sp));formal.write_text(json.dumps(mod))
            result=ps.run(study,formal,out=root/'paper')
            package=Path(result['package_dir'])
            self.assertIn(r'\cite[p.~13]{provided001}',(package/'main.tex').read_text())
            for cmd in (['pdflatex','-interaction=nonstopmode','-halt-on-error','main.tex'],
                        ['bibtex','main'],
                        ['pdflatex','-interaction=nonstopmode','-halt-on-error','main.tex']):
                p=subprocess.run(cmd,cwd=package,capture_output=True,timeout=45)
                self.assertEqual(p.returncode,0,p.stdout.decode('utf-8',errors='replace')[-1800:])

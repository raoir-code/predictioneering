"""Formal comparative statics -> existing empirical runner -> Overleaf-ready draft.

All outputs are RESEARCH DRAFTS, with no novelty, equilibrium, causal,
source-claim, external-replication or human-signoff assertion. No network, paid
models, forecasting writes or publication. Python stdlib + SymPy/matplotlib.
"""
from __future__ import annotations

import argparse
import ast
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import sys
import zipfile

from . import prototype

ROOT = Path(__file__).resolve().parents[1]
VERSION = "research-factory-paper-sprint-0.1"
VALID_SIGN = {"positive", "negative", "zero", "nonzero"}
NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,49}$")
DOI = re.compile(r"^10\.\d{4,9}/[^\s]+$", re.I)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def required(obj, key, maximum=8000):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Required nonempty {key} (max {maximum} characters)")
    return value.strip()


def safe_expr(source, symbols):
    """Convert a strictly arithmetic AST to SymPy, without eval or function calls."""
    import sympy as sp
    if not isinstance(source, str) or len(source) > 200:
        raise ValueError("Equilibrium expression must be short arithmetic text")
    try:
        root = ast.parse(source, mode="eval").body
    except SyntaxError as exc:
        raise ValueError("Invalid equilibrium expression") from exc
    ops={ast.Add:lambda a,b:a+b,ast.Sub:lambda a,b:a-b,
         ast.Mult:lambda a,b:a*b,ast.Div:lambda a,b:a/b,ast.Pow:lambda a,b:a**b}
    def walk(node, depth=0):
        if depth > 16:raise ValueError("Expression too deeply nested")
        if isinstance(node, ast.Constant) and type(node.value) in (int,float):
            if not math.isfinite(node.value) or abs(node.value)>1e8:
                raise ValueError("Unsafe numeric constant")
            return sp.Rational(str(node.value))
        if isinstance(node, ast.Name) and node.id in symbols:
            return symbols[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            x=walk(node.operand,depth+1)
            return x if isinstance(node.op,ast.UAdd) else -x
        if isinstance(node,ast.BinOp) and type(node.op) in ops:
            if isinstance(node.op,ast.Pow):
                if not isinstance(node.right,ast.Constant) or type(node.right.value) not in (int,float) or abs(node.right.value)>6:
                    raise ValueError("Exponent must be a small numeric constant")
            return ops[type(node.op)](walk(node.left,depth+1),walk(node.right,depth+1))
        raise ValueError("Only arithmetic involving declared parameters is allowed")
    out=walk(root)
    if len(str(out))>1000:raise ValueError("Symbolic expression too long")
    return out


def check_model(model, spec):
    """Check derivative algebra and mappings, not equilibrium optimality or novelty."""
    import sympy as sp
    if not isinstance(model,dict):raise ValueError("Formal model must be a JSON object")
    for key in ("title","information","timing","solution_concept","equilibrium_argument"):
        required(model,key)
    actors=model.get('players')
    if not isinstance(actors,list) or len(actors)<2 or len(actors)>10 or not all(isinstance(x,str) and 2<=len(x)<=100 for x in actors):
        raise ValueError("Model must name two or more players")
    if not isinstance(model.get('strategies'),list) or not model['strategies']:
        raise ValueError("Model must describe strategies")
    payoffs=model.get('payoffs')
    if not isinstance(payoffs,dict) or not all(p in payoffs and isinstance(payoffs[p],str) and payoffs[p].strip() for p in actors):
        raise ValueError("Each player's payoff must be supplied")
    params=model.get('parameters')
    if not isinstance(params,dict) or not 1<=len(params)<=12 or any(not NAME.fullmatch(k) or v not in ('real','positive','nonnegative') for k,v in params.items()):
        raise ValueError("Model parameters require safe names and real/positive/nonnegative assumptions")
    sym={k:sp.Symbol(k,real=True,**({'positive':True} if v=='positive' else {'nonnegative':True} if v=='nonnegative' else {})) for k,v in params.items()}
    eq=model.get('equilibrium')
    if not isinstance(eq,dict):raise ValueError("equilibrium object required")
    var=required(eq,'choice')
    if not NAME.fullmatch(var) or var in sym:raise ValueError("Invalid equilibrium choice")
    expression=safe_expr(required(eq,'expression',200),sym)
    derivatives=[]
    specs={h['id']:h for h in spec['hypotheses']}
    used=set()
    for cs in model.get('comparative_statics',[]):
        if not isinstance(cs,dict):raise ValueError("Comparative static must be an object")
        ident=required(cs,'id'); param=required(cs,'parameter')
        hypothesis=required(cs,'hypothesis_id')
        sign=required(cs,'sign'); interpretation=required(cs,'interpretation')
        hypothesis_text=required(cs,'hypothesis_text')
        if not NAME.fullmatch(ident) or param not in sym or hypothesis not in specs or hypothesis in used or sign not in VALID_SIGN:
            raise ValueError("Invalid comparative-static ID, parameter, sign or hypothesis mapping")
        used.add(hypothesis)
        mapping=cs.get('empirical_mapping')
        if not isinstance(mapping,dict) or mapping.get('predictor') != spec['design']['treatment'] or mapping.get('outcome') != spec['design']['outcome']:
            raise ValueError("Comparative static must map to prespecified predictor and outcome")
        if sign!=specs[hypothesis]['sign']:
            raise ValueError("Formal prediction sign contradicts empirical hypothesis sign")
        if hypothesis_text != specs[hypothesis]['prediction'].strip():
            raise ValueError("Empirical hypothesis must exactly match formal comparative-static hypothesis_text")
        derivative=sp.simplify(sp.diff(expression,sym[param]))
        truth={'positive':derivative.is_positive,'negative':derivative.is_negative,
               'zero':derivative.is_zero,'nonzero':derivative.is_nonzero}[sign]
        derivatives.append({'id':ident,'parameter':param,'hypothesis_id':hypothesis,
                            'expected_sign':sign,'derivative_sympy':str(derivative),
                            'derivative_latex':sp.latex(derivative),
                            'sign_algebra_verified':bool(truth is True),
                            'interpretation':interpretation, 'hypothesis_text':hypothesis_text})
    if not derivatives or used!=set(specs):
        raise ValueError("Every prespecified hypothesis needs exactly one comparative static")
    return {'equilibrium_expression':str(expression),
            'equilibrium_latex':sp.latex(expression), 'choice':var,
            'derivatives':derivatives,
            'all_derivative_signs_verified':all(x['sign_algebra_verified'] for x in derivatives),
            'equilibrium_optimality_verified':False,
            'caution':'Derivatives are checked conditional on an asserted equilibrium; strategies, best responses and equilibrium optimality still need independent review.'}


def hypotheses_from_model(model):
    """Treat comparative statics, not post-hoc regression signs, as source of H1/H2."""
    seen=set();out=[]
    for row in model.get('comparative_statics',[]):
        if not isinstance(row,dict):raise ValueError('Invalid comparative static')
        hid=required(row,'hypothesis_id');txt=required(row,'hypothesis_text')
        sign=required(row,'sign');mapping=row.get('empirical_mapping')
        if hid in seen or sign not in VALID_SIGN or not isinstance(mapping,dict):
            raise ValueError('Invalid/duplicate hypothesis or empirical mapping')
        seen.add(hid)
        out.append({'id':hid,'prediction':txt,'sign':sign,
                    'predictor':required(mapping,'predictor'),
                    'outcome':required(mapping,'outcome'),
                    'source_comparative_static':required(row,'id'),
                    'status':'proposed_from_formal_model_NOT_empirically_verified'})
    if not out:raise ValueError('Formal model lacks comparative statics')
    return {'hypotheses':out,'review_required':True,
            'warning':'Comparative statics and empirical variable mapping are author-supplied, not independent theory proof'}


def evidence_claims(spec,refs):
    """Require explicit researcher attestation, page, quote, and actual bib key."""
    records=spec.get('literature_claims',[])
    if not isinstance(records,list):raise ValueError('literature_claims must be a list')
    allowed={x['key'] for x in refs}
    ready=[];warnings=[]
    for i,c in enumerate(records,1):
        if not isinstance(c,dict):raise ValueError('literature claim must be a JSON object')
        key=c.get('source_key');page=c.get('page');checked=c.get('human_quote_checked')
        if key not in allowed or not isinstance(page,int) or isinstance(page,bool) or page<1 or page>10000:
            warnings.append(f'Claim {i}: invalid bibliography key or source page; not printed')
            continue
        try:
            quote=required(c,'verbatim_quote',900);claim=required(c,'claim',900)
        except ValueError:
            warnings.append(f'Claim {i}: missing quote/claim; not printed');continue
        if not checked:
            warnings.append(f'Claim {i}: original-source quote not human-attested; not printed');continue
        ready.append({'claim':claim,'quote':quote,'page':page,'source_key':key,
                      'status':'human_attested_not_machine_verified'})
    return ready,warnings


def tex(text):
    """Escape arbitrary researcher text, never treat it as LaTeX code."""
    escapes={'\\':r'\textbackslash{}','{':r'\{','}':r'\}',
             '%':r'\%','$':r'\$','&':r'\&','#':r'\#','_':r'\_',
             '^':r'\textasciicircum{}','~':r'\textasciitilde{}'}
    return ''.join(escapes.get(ch,ch) for ch in str(text).replace('\n',' '))


def bibliography(records):
    """Only supplied verifiable bibliography IDs; no invented source metadata."""
    out=[]; warnings=[]; bib=[]
    for i,record in enumerate(records,1):
        title=required(record,'title')
        authors=record.get('authors');year=record.get('year');doi=record.get('doi');url=record.get('url')
        if not isinstance(authors,str) or not authors.strip() or not isinstance(year,(int,str)) or not str(year).isdigit() or len(str(year))!=4:
            warnings.append(f"Reference {i}: incomplete author/year; omitted from .bib")
            continue
        if doi and not DOI.fullmatch(str(doi)):
            warnings.append(f"Reference {i}: invalid DOI; omitted from .bib")
            continue
        if url and (not isinstance(url,str) or not url.startswith('https://') or any(x in url for x in ['\\','{','}','\n'])):
            warnings.append(f"Reference {i}: unsafe/non-HTTPS URL; omitted from .bib")
            continue
        if not doi and not url:
            warnings.append(f"Reference {i}: no DOI or HTTPS URL; omitted from .bib")
            continue
        key=f'provided{i:03d}'
        def safe_bib(s):return str(s).replace('\\','').replace('{','').replace('}','').replace('\n',' ').replace('%',r'\%')
        fields=[f'  title = {{{safe_bib(title)}}}',f'  author = {{{safe_bib(authors)}}}',f'  year = {{{year}}}']
        if doi:fields.append(f'  doi = {{{safe_bib(doi)}}}')
        if url:fields.append(f'  url = {{{safe_bib(url)}}}')
        bib.append('@misc{'+key+',\n'+',\n'.join(fields)+'\n}')
        out.append({'key':key,'title':title,'status':'metadata_only_NOT_claim_verified',
                    'reviewer_attested':record.get('review_status')=='human_verified_full_text'})
    return '\n\n'.join(bib)+'\n',out,warnings


def plot_results(results,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out.mkdir(parents=True,exist_ok=True)
    figs=[]
    fit=results.get('model',{})
    if fit.get('status')=='estimated_association_not_causal':
        ci=fit.get('confidence_interval_95')
        b=fit.get('coefficient')
        if b is not None and ci and all(isinstance(x,(int,float)) and math.isfinite(x) for x in [b,*ci]):
            fig,ax=plt.subplots(figsize=(6.0,2.7))
            ax.errorbar([b],[0],xerr=[[max(0,b-ci[0])],[max(0,ci[1]-b)]],fmt='o',capsize=4)
            ax.axvline(0,color='gray',linestyle='--',linewidth=1)
            ax.set_yticks([0],[str(fit.get('contrast','estimate'))]);ax.set_xlabel('Coefficient (95% model-based CI)')
            ax.set_title('Exploratory estimate; not causal evidence')
            fig.tight_layout();fig.savefig(out/'estimate.pdf',bbox_inches='tight');plt.close(fig)
            figs.append(('estimate',r'Estimated association and model-based 95\% confidence interval'))
    pred=results.get('predictive_validation',{})
    if pred.get('status')=='holdout_scored':
        labels=['Model','Train-mean baseline']
        values=[pred.get('model_score'),pred.get('train_mean_baseline_score')]
        if all(isinstance(x,(int,float)) and math.isfinite(x) for x in values):
            fig,ax=plt.subplots(figsize=(5.8,3.2))
            ax.bar(labels,values)
            ax.set_ylabel(str(pred.get('metric','holdout score'))+' (lower is better)')
            ax.set_title('Strictly chronological holdout; not external replication')
            fig.tight_layout();fig.savefig(out/'holdout.pdf',bbox_inches='tight');plt.close(fig)
            figs.append(('holdout','Temporal holdout score and training-mean baseline'))
    return figs


def manuscript(spec,model,mathcheck,results,refs,figs,claims):
    fit=results.get('model',{});out=results.get('predictive_validation',{})
    lines=[r'\documentclass[11pt]{article}',r'\usepackage[margin=1in]{geometry}',
           r'\usepackage[T1]{fontenc}',r'\usepackage[utf8]{inputenc}',
           r'\usepackage{amsmath,amssymb,graphicx,booktabs,hyperref}',
           r'\usepackage[numbers]{natbib}',r'\hypersetup{hidelinks}',
           r'\title{'+tex(spec['title'])+'}',
           r'\author{Research Factory --- unreviewed automated working draft}',
           r'\date{Draft only: no scientific or publication approval}',
           r'\begin{document}',r'\maketitle',
           r'\begin{abstract}',
           tex('Unreviewed draft. '+spec['research_question']+' The empirical association is exploratory. Formal equilibrium, novelty, identification and all substantive claims require independent verification.'),
           r'\end{abstract}',
           r'\section{Research question}',tex(spec['research_question']),
           r'\section{Literature and contribution (requires verification)}']
    if refs:
        lines += ['These are supplied bibliographic records, not verified support for any claims: '+', '.join(r'\cite{'+r['key']+'}' for r in refs)+'.']
    else:lines.append(r'\textbf{No complete attributable bibliographic records provided. Do not claim novelty.}')
    if claims:
        lines.append(r'\paragraph{Source-linked, reviewer-attested claims (original PDFs not machine-verified).}')
        for c in claims:
            lines.append(tex(c['claim'])+' '+r'\cite[p.~'+str(c['page'])+']{'+c['source_key']+'}.')
    lines += [r'\section{Formal model: proposed, not independently proved}',
              r'\textbf{The model and equilibrium expression were supplied; only symbolic derivative algebra was machine-checked.}',
              r'\paragraph{Players.} '+tex('; '.join(model['players'])),
              r'\paragraph{Information.} '+tex(model['information']),
              r'\paragraph{Timing.} '+tex(model['timing']),
              r'\paragraph{Strategies.} '+tex('; '.join(model['strategies'])),
              r'\paragraph{Payoffs.} '+tex('; '.join(p+': '+model['payoffs'][p] for p in model['players'])),
              r'\paragraph{Solution concept.} '+tex(model['solution_concept']),
              r'\paragraph{Proposed equilibrium argument.} '+tex(model['equilibrium_argument']),
              r'\[ '+tex(mathcheck['choice'])+'^{*} = '+mathcheck['equilibrium_latex']+r' \] ']
    if model.get('normal_form_2x2') and mathcheck.get('normal_form_2x2_audit'):
        audit = mathcheck['normal_form_2x2_audit']
        lines += [r'\paragraph{Payoff-matrix indifference audit.} ',
                  tex('The following exact mixing identities follow from the supplied two-by-two payoff matrix, conditional on both probabilities lying strictly between zero and one. This is not a complete equilibrium-domain proof.'),
                  r'\[ p^{*} = '+audit['row_player_first_action_probability_latex']+r',\qquad q^{*} = '+audit['column_player_first_action_probability_latex']+r' \]']
    if model.get('note'):
        lines += [r'\paragraph{Research scope caveat.} '+tex(model['note'])]
    lines += [r'\section{Comparative statics and falsifiable hypotheses}']
    for d in mathcheck['derivatives']:
        h=next(x for x in spec['hypotheses'] if x['id']==d['hypothesis_id'])
        lines += [r'\paragraph{'+tex(d['id'])+' / '+tex(h['id'])+'} '+tex(d['interpretation']),
                  r'\[ \frac{\partial '+tex(mathcheck['choice'])+r'^*}{\partial '+tex(d['parameter'])+'} = '+d['derivative_latex']+r' \]',
                  tex('Sign check conditional on asserted equilibrium: '+('PASS' if d['sign_algebra_verified'] else 'UNRESOLVED')+'.')+' '+tex('Empirical hypothesis: '+h['prediction'])]
    lines += [r'\section{Data and empirical design}',
              tex('Design: '+spec['design']['method']+'; family: '+spec['design']['family']+'. Predictor: '+spec['design']['treatment']+'; outcome: '+spec['design']['outcome']+'.'),
              r'\textbf{No causal identification is established by the association estimate.}',
              r'\section{Exploratory results}']
    if fit.get('status')=='estimated_association_not_causal':
        def fmt(x):return 'NA' if x is None else str(x)
        ci=fit['confidence_interval_95']
        lines += [r'\begin{table}[ht]',r'\centering',r'\begin{tabular}{lr}',r'\toprule',r'Quantity & Value \\',r'\midrule',
                  r'Coefficient & '+tex(fmt(fit.get('coefficient')))+r' \\',
                  r'Standard error & '+tex(fmt(fit.get('standard_error')))+r' \\',
                  r'95\% CI & '+tex(fmt(ci))+r' \\',
                  r'Exploratory $p$-value & '+tex(fmt(fit.get('p_value_exploratory')))+r' \\',
                  r'Observations & '+tex(fmt(fit.get('sample_n')))+r' \\',
                  r'\bottomrule',r'\end{tabular}',
                  r'\caption{Computed estimates; do not interpret as causal or independently replicated.}',r'\end{table}']
    else:lines.append(tex('Estimation unavailable: '+str(fit.get('reason','unknown error'))))
    if out.get('status')=='holdout_scored':
        lines.append(tex('Temporal holdout: '+str(out.get('metric'))+' model '+str(out.get('model_score'))+' versus train-only baseline '+str(out.get('train_mean_baseline_score'))+'.'))
    else:lines.append(tex('Temporal predictive validation unavailable: '+str(out.get('status'))+'.'))
    for name,caption in figs:
        lines += [r'\begin{figure}[ht]',r'\centering',r'\includegraphics[width=0.80\textwidth]{figures/'+name+'.pdf}',
                  r'\caption{'+caption+'}',r'\end{figure}']
    lines += [r'\section{Robustness, scope and limitations}',
              tex('Independent equilibrium proof, novelty search, source-to-claim citations, empirical identification, alternate specifications, multiple-testing control, independent replication, and human review have not been automatically passed.')]
    if spec.get('study_limitations'):
        lines.append(tex(spec['study_limitations']))
    lines += [r'\section{Conclusion}',
              tex('This is a machine-assembled working-paper shell, not a scientific finding. Conclusions remain open pending independent review.'),
              r'\section*{Research integrity and replication}',
              tex('See REVIEW_REQUIRED.md and replication_manifest.json. No protected source data were copied into the manuscript package.')]
    if refs:lines += [r'\bibliographystyle{plainnat}',r'\bibliography{references}']
    lines += [r'\end{document}']
    return '\n'.join(lines)+'\n'


def run(spec_path,model_path,*,out=None,analysis_dir=None):
    spec_path=Path(spec_path).expanduser().resolve();model_path=Path(model_path).expanduser().resolve()
    spec=prototype.validate_spec(prototype.read_json(spec_path))
    model=load(model_path)
    mathcheck=check_model(model,spec)
    if model.get('normal_form_2x2') is not None:
        from . import two_by_two_game
        mathcheck['normal_form_2x2_audit'] = two_by_two_game.verify(model)
    out=Path(out).expanduser().resolve() if out else ROOT/'projects'/'factory_runs'/spec['id']/'paper_sprint'
    if out in (spec_path,model_path) or any(x in out.parents for x in [spec_path,model_path]):
        raise ValueError('Invalid output directory')
    out.mkdir(parents=True,exist_ok=True)
    source_dir=Path(analysis_dir).expanduser().resolve() if analysis_dir else out.parent/'analysis'
    # An existing cached results.json does not prove it came from the current spec/data.
    # Always invoke the prototype's fingerprinted run if no explicitly supplied analysis_dir.
    if analysis_dir is None:
        completed=prototype.run(spec_path,destination=source_dir)
        if completed.get('status') not in ('prototype_complete','reused_cached_run'):
            raise ValueError('Estimation blocked: '+str(completed.get('plan',{}).get('blockers',[])))
    manifest=source_dir/'replication_manifest.json'
    if not manifest.is_file():raise ValueError('Missing analysis replication_manifest.json')
    provenance=load(manifest)
    source=prototype.data_file(spec,spec_path)
    if not source.is_file() or source.stat().st_size>200_000_000:
        raise ValueError('Source data missing or exceeds 200MB')
    if provenance.get('data_sha256')!=prototype.digest(source.read_bytes()):
        raise ValueError('Analysis/data hash mismatch: rerun analysis')
    results_path=source_dir/'results.json'
    if not results_path.is_file():raise ValueError('No real analysis results.json')
    results=load(results_path)
    if results.get('study_id')!=spec['id']:
        raise ValueError('Results study ID does not match requested specification')
    # Caller-supplied analysis directory is only acceptable with a valid state fingerprint.
    state_file=source_dir/'state.json'
    if not state_file.is_file():raise ValueError('Missing analysis state.json')
    state=load(state_file)
    signature=prototype.digest((prototype.VERSION+prototype.digest(spec_path.read_bytes())+prototype.digest(source.read_bytes())).encode('utf-8'))
    if state.get('signature')!=signature or state.get('status')!='prototype_complete':
        raise ValueError('Analysis fingerprint mismatch or run incomplete')
    package=out/'overleaf'
    package.mkdir(parents=True,exist_ok=True)
    bib,refs,citation_warnings=bibliography(spec.get('literature',[]))
    claims,claim_warnings=evidence_claims(spec,refs)
    citation_warnings += claim_warnings
    figs=plot_results(results,package/'figures')
    prototype.atomic_text(package/'main.tex',manuscript(spec,model,mathcheck,results,refs,figs,claims))
    prototype.atomic_text(package/'references.bib',bib)
    prototype.write_json(package/'statistical_results.json',results)
    # Redacted replication record: never copy private local dataset or user path.
    prototype.write_json(package/'replication_manifest.json',{
        'research_factory_version':VERSION,
        'study_id':spec['id'],
        'data_sha256':prototype.digest(source.read_bytes()),
        'private_data_included':False,
        'source_code': 'research/factory/prototype.py and research/factory/paper_sprint.py',
        'instructions':'Recreate private study.json, formal_model.json and CSV locally; install research/requirements.txt, then rerun paper_sprint run.',
        'review_status':'UNREVIEWED_DRAFT'})
    original_qc=load(source_dir/'QC_REPORT.json')
    gates={'symbolic_derivative_signs_verified':mathcheck['all_derivative_signs_verified'],
           'mixed_indifference_from_payoff_matrix_verified':bool(
               mathcheck.get('normal_form_2x2_audit',{}).get('algebraic_indifference_identically_zero')),
           'equilibrium_proof_independently_verified':False,
           'empirical_mapping_independently_verified':False,
           'human_novelty_review':spec['novelty_review']['status']=='approved',
           'non_synthetic_data':not spec['data']['synthetic'],
           'statistical_estimation_completed':results.get('model',{}).get('status')=='estimated_association_not_causal',
           'temporal_oos_completed':results.get('predictive_validation',{}).get('status')=='holdout_scored',
           'complete_bibliography_metadata':bool(refs) and len(refs)==len(spec.get('literature',[])),
           'claim_to_source_citations_independently_checked':False,
           'causal_identification_reviewed':False,
           'independent_replication_verified':False,
           'human_final_manuscript_review':False}
    qc={'status':'UNREVIEWED_NOT_SUBMISSION_READY','gates':gates,'unmet':[k for k,v in gates.items() if not v],
        'derivative_checks':mathcheck,'citation_warnings':citation_warnings,
        'reference_metadata':refs,'human_attested_claims_rendered':len(claims),
        'underlying_analysis_gates':original_qc,
        'caution':'Derivative sign conditional on supplied equilibrium expression is not equilibrium proof; citation metadata is not claim verification.'}
    prototype.write_json(package/'PAPER_QC.json',qc)
    review=['# HUMAN SCIENTIFIC REVIEW REQUIRED','',
      '- [ ] Read original papers and verify substantive claims against page-level passages',
      '- [ ] Confirm actual contribution and novelty against closest game-theoretic models',
      '- [ ] Independently verify equilibrium existence, best responses, conditions and comparative statics',
      '- [ ] Verify that each comparative static implies its exact empirical hypothesis and estimand',
      '- [ ] Confirm causal identification / limitations, cluster robustness and preanalysis decisions',
      '- [ ] Audit all source dates and covariates for train/test temporal leakage',
      '- [ ] Replicate all Python analyses and figures on a clean machine',
      '- [ ] Confirm all in-text citations and bibliography entries against original sources',
      '- [ ] Check title, abstract, tables, plots and text for exaggerated claims or AI errors',
      '- [ ] Approve revised manuscript before any submission or public distribution','',
      '**Do not treat any autogenerated checklist item as completed.**','',
      'Automated algebra derivative status: '+str(gates['symbolic_derivative_signs_verified']),
      'Formal game-theory proof reviewed: False',
      'Source metadata warnings: '+('; '.join(citation_warnings) if citation_warnings else 'None recorded'),
      '']
    prototype.atomic_text(package/'REVIEW_REQUIRED.md','\n'.join(review))
    # Avoid source CSV, API keys, private notes or licensed source text in the archive.
    docs={name:(package/name).read_bytes() for name in ('main.tex','references.bib','statistical_results.json','replication_manifest.json','PAPER_QC.json','REVIEW_REQUIRED.md')}
    sha={'spec_sha256':prototype.digest(spec_path.read_bytes()),'model_sha256':prototype.digest(model_path.read_bytes()),
         'results_sha256':prototype.digest(results_path.read_bytes()),'input_data_sha256':prototype.digest(source.read_bytes()),
         'included_sha256':{p:prototype.digest(b) for p,b in docs.items()}}
    prototype.write_json(package/'PACKAGE_MANIFEST.json',sha)
    archive=out/(spec['id']+'_OVERLEAF_DRAFT.zip')
    included = ['main.tex','references.bib','statistical_results.json',
                'replication_manifest.json','PAPER_QC.json',
                'REVIEW_REQUIRED.md','PACKAGE_MANIFEST.json']
    included += ['figures/'+name+'.pdf' for name,_ in figs]
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for filename in included:
            z.write(package/filename,filename)
    return {'status':'overleaf_draft_created_NOT_submission_ready',
            'archive':str(archive),'package_dir':str(package),'figures':[f[0] for f in figs],
            'source_data_included':False,'derived_hypotheses':len(mathcheck['derivatives']),
            'mathematical_derivatives_checked':mathcheck['all_derivative_signs_verified'],
            'bibliography_entries':len(refs),'unmet_qc':qc['unmet'],'network_or_paid_calls':0}


def demo():
    folder=ROOT/'projects'/'factory_runs'/'paper_sprint_synthetic_demo'
    input_dir=folder/'inputs';input_dir.mkdir(parents=True,exist_ok=True)
    rng=random.Random(10151)
    import csv
    data=input_dir/'SYNTHETIC_ultimatum.csv'
    with data.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['day','unit','outside_option','offer'])
        start=date(2024,1,1)
        for day in range(100):
            for unit in range(12):
                u=rng.uniform(.2,.9)
                x=u+rng.gauss(0,.085)
                w.writerow([(start+timedelta(days=day)).isoformat(),f'unit{unit:02d}',round(u,5),round(x,5)])
    spec={'id':'ultimatum-demo','title':'Synthetic ultimatum bargaining: formal-to-empirical demonstration',
          'research_question':'Does a higher responder outside option increase the offered concession in a synthetic ultimatum game?',
          'mechanism':'A proposer makes a minimum acceptable offer to a responder with outside option u.',
          'hypotheses':[{'id':'H1','prediction':'Increasing the outside option raises the offered concession.','sign':'positive'}],
          'data':{'csv_path':data.name,'redistribution_allowed':False,'synthetic':True},
          'design':{'method':'association','family':'gaussian','outcome':'offer','treatment':'outside_option',
                    'time':'day','unit':'unit','controls':[],'fixed_effects':[],'cluster':'unit','holdout_fraction':.25},
          'literature':[],'novelty_review':{'status':'demo_only'}}
    model={'title':'Complete-information ultimatum with a fixed responder outside option',
           'players':['Proposer','Responder'],
           'information':'Both players know the proposer surplus V and responder outside option u. Assume 0 <= u < V.',
           'timing':'First proposer offers x in [0,V]; then responder accepts or rejects.',
           'strategies':['Proposer chooses x','Responder accepts if and only if x >= u'],
           'payoffs':{'Proposer':'If accepted, V-x; otherwise 0.',
                      'Responder':'If accepted, x; otherwise u.'},
           'solution_concept':'Subgame-perfect equilibrium with acceptance at indifference.',
           'equilibrium_argument':'Backward induction: the responder accepts x >= u. Given 0 <= u < V and rejection payoff zero, the proposer minimizes an accepted offer, so x* = u. This argument requires independent verification for substantive work.',
           'parameters':{'u':'nonnegative','V':'positive'},
           'equilibrium':{'choice':'x','expression':'u'},
           'comparative_statics':[{'id':'CS1','parameter':'u','sign':'positive','hypothesis_id':'H1',
                                   'interpretation':'The minimum accepted offer rises one-for-one with the responder outside option.',
                                   'hypothesis_text':'Increasing the outside option raises the offered concession.',
                                   'empirical_mapping':{'predictor':'outside_option','outcome':'offer'}}]}
    spec_path=input_dir/'study.json';model_path=input_dir/'formal_model.json'
    prototype.write_json(spec_path,spec);prototype.write_json(model_path,model)
    result=run(spec_path,model_path,out=folder/'package')
    result.update({'synthetic_only':True,'demo_dir':str(folder)})
    return result


def holiday_demo():
    """Actual Holy Days factory wiring using FAKE data and conditional game."""
    import csv
    folder=ROOT/'projects'/'factory_runs'/'holy_days_synthetic_demo'
    inputs=folder/'inputs'
    inputs.mkdir(parents=True,exist_ok=True)
    source_model=ROOT/'examples'/'HOLY_DAYS_2X2_MODEL_CANDIDATE.json'
    source_spec=ROOT/'examples'/'HOLY_DAYS_STUDY_CANDIDATE.json'
    model=load(source_model)
    spec=load(source_spec)
    # Dates below are intentionally NOT religious or national calendars.
    # This tests software only; no historical data or identified treatment.
    rng=random.Random(20261123)
    data=inputs/'SYNTHETIC_holiday_dyad_days.csv'
    with data.open('w',newline='',encoding='utf-8') as handle:
        writer=csv.writer(handle)
        writer.writerow(['event_date','directed_dyad','defender_holiday',
                         'attack_attempt','direction_verified'])
        base=date(2024,1,1)
        for day in range(150):
            h=int(day%19 in (0,1))
            for unit in range(12):
                p_attack=(0.12+0.12*h)/0.8
                attack=int(rng.random()<p_attack)
                writer.writerow([(base+timedelta(days=day)).isoformat(),
                                 f'actor{unit:02d}-opponent',h,attack,attack])
    spec['id']='holy-days-synthetic-demo'
    spec['title']='SYNTHETIC — holiday inspection-game software demonstration'
    spec['research_question']='Can the software estimate an artificial attack signal generated from a stipulated mixed-strategy game?'
    spec['data']['csv_path']=data.name
    spec['data']['synthetic']=True
    spec['novelty_review']={'status':'demo_only'}
    spec['study_limitations']=(
        'Every observation is simulated; the holiday indicator is an artificial repeating pattern, not a genuine religious calendar. '
        'The model and its assumed game structure have not been validated for real conflict. '
        'No causal identification, scholarly novelty, or empirical interstate result is established.')
    spec_path=inputs/'study.json'
    prototype.write_json(spec_path,spec)
    output=run(spec_path,source_model,out=folder/'package')
    output.update({'synthetic_only':True,'data_source':'GENERATED_FAKE_DYAD_DAYS',
                   'research_paper_claim':False,
                   'demo_dir':str(folder)})
    return output


def main(argv=None):
    p=argparse.ArgumentParser(description='Formal-model hypothesis -> Python -> figures -> Overleaf unreviewed draft')
    subs=p.add_subparsers(dest='command',required=True)
    subs.add_parser('demo',help='Safe synthetic end-to-end demo; no paid APIs or real scientific claims')
    subs.add_parser('holy-days-demo',help='Synthetic holiday 2x2 inspection game -> estimation -> Overleaf (NOT a real paper)')
    h=subs.add_parser('hypotheses',help='Extract prespecified empirical hypotheses from formal comparative statics')
    h.add_argument('formal_model',type=Path)
    r=subs.add_parser('run',help='Prepare Overleaf draft from supplied theory and a reviewed empirical specification')
    r.add_argument('spec',type=Path);r.add_argument('--formal-model',required=True,type=Path)
    r.add_argument('--out',type=Path);r.add_argument('--analysis-dir',type=Path)
    a=p.parse_args(argv)
    try:
        output=(demo() if a.command=='demo' else
                holiday_demo() if a.command=='holy-days-demo' else
                hypotheses_from_model(load(a.formal_model)) if a.command=='hypotheses' else
                run(a.spec,a.formal_model,out=a.out,analysis_dir=a.analysis_dir))
        print(json.dumps(output,indent=2));return 0
    except (OSError,ValueError,KeyError,TypeError,RuntimeError) as e:
        print('Paper sprint stopped safely: '+str(e),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())

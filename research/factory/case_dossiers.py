"""Read-only, point-in-time case dossiers for Predictioneering forecast errors.

No forecasting code imports, network traffic, retroactive node attribution or LLM calls.
Unknown historical facts are recorded as missing, never reconstructed by hindsight.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from . import forecast_misses as fm
from . import prototype

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / 'research'
VERSION = 'research-forecast-forensics-v0.1'


def load_json(path, maximum=6_000_000):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('JSON source absent or exceeds size cap: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def rows(path, maximum=60_000_000):
    path = Path(path).expanduser().resolve()
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('JSONL file exceeds size cap or is not regular file: ' + str(path))
    result = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                result.append(item)
        except ValueError:
            continue
    return result


def stamp(value):
    return fm.iso_time(value)


def canonical_date(value):
    value = stamp(value)
    return value.isoformat() if value else None


def source_info(path):
    path = Path(path).expanduser().resolve()
    if path.is_file() and path.stat().st_size>60_000_000:
        raise ValueError('Input exceeds 60 MB safety cap: '+str(path))
    return {'file': str(path), 'exists': path.is_file(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
            'bytes': path.stat().st_size if path.is_file() else 0}


def read_resolved(brier):
    """Minimal stable resolver-schema parser, independent of scanner implementation."""
    indexed, conflicted, qc = {}, set(), defaultdict(int)
    for rec in rows(brier,maximum=50_000_000) or []:
        mid=str(rec.get('market_id') or '').strip()
        if not mid or mid in conflicted:
            continue
        y=rec.get('outcome')
        p=fm.probability(rec.get('conditional_p'))
        m=fm.probability(rec.get('market_p_at_first'))
        at=stamp(rec.get('first_prediction_ts'))
        resolved=stamp(rec.get('resolved_at'))
        if type(y) is not int or y not in (0,1) or p is None or m is None or not at or not resolved or at>=resolved:
            qc['invalid_or_missing_outcome_time_or_probability']+=1
            continue
        curr={'market_id':mid,'label':str(rec.get('market_label') or '')[:250],
              'dyad':str(rec.get('dyad') or ''),'contract_type':rec.get('contract_type'),
              'relation':rec.get('relation'),'outcome':y,'forecast_at':at.isoformat(),
              'resolved_at':resolved.isoformat(),'forecast_p':p,'market_p':m,
              'model_brier':(p-y)**2,'market_brier':(m-y)**2,
              'excess_brier':(p-y)**2-(m-y)**2}
        if mid in indexed:
            old=indexed[mid]
            if old['outcome']!=y or old['resolved_at']!=curr['resolved_at']:
                indexed.pop(mid);conflicted.add(mid)
                qc['conflicting_resolution_ids']+=1
            else:qc['duplicate_resolution_lines']+=1
            continue
        indexed[mid]=curr
    qc['valid_unique_resolved_contracts']=len(indexed)
    return list(indexed.values()),dict(qc)


def pick_cases(brier, ids, top):
    valid, discarded = read_resolved(brier)
    if ids:
        missing = sorted(set(ids)-{r['market_id'] for r in valid})
        if missing:
            raise ValueError('Market IDs absent or invalid in resolved log: ' + ', '.join(missing))
        byid = {r['market_id']: r for r in valid}
        return [byid[id] for id in dict.fromkeys(ids)], discarded
    # Earliest logged p, at most one item per approximate event family, not
    # independence proof. Default limits API costs and investigative workload.
    chosen, seen = [], set()
    for r in sorted(valid, key=lambda x: (-x['excess_brier'], x['market_id'])):
        key = (r.get('dyad'), fm.label_template(r.get('label')))
        if key in seen:
            continue
        chosen.append(r)
        seen.add(key)
        if len(chosen) >= top:
            break
    return chosen, discarded


def forecast_history(predictions, market_id, cutoff):
    matching = []
    skipped = 0
    for r in predictions or []:
        if str(r.get('market_id', '')) != market_id:
            continue
        time = stamp(r.get('timestamp') or r.get('prediction_ts') or r.get('forecast_ts'))
        if time is None or time > cutoff:
            skipped += 1
            continue
        matching.append((time, r))
    matching.sort(key=lambda x: x[0])
    safe = []
    for when, r in matching[-100:]:
        safe.append({'source_id': 'PRED:'+market_id+':'+when.isoformat(),
                     'timestamp': when.isoformat(),
                     'conditional_p':fm.probability(r.get('conditional_p')),
                     'engine_p':fm.probability(r.get('engine_p')),
                     'market_p':fm.probability(r.get('market_p')),
                     'pricing_component':r.get('pricing_component'),
                     'contract_type':r.get('contract_type'),
                     'dyad':r.get('dyad'),
                     'code_commit':r.get('code_commit') or r.get('git_sha')})
    return safe, skipped, len(matching)


def node_history(nodes, dyad, cutoff, max_days=14):
    matching = []
    for r in nodes or []:
        if str(r.get('dyad', '')) != dyad:
            continue
        when = stamp(r.get('logged_at'))
        if when is None or when > cutoff:
            continue
        if (cutoff-when).total_seconds() > max_days*86400:
            continue
        matching.append((when,r))
    matching.sort(key=lambda x: x[0])
    # Values are traces only, not proof of model feature use or causal influence.
    return [{ 'source_id': 'NODE:'+dyad+':'+when.isoformat(),
              'timestamp':when.isoformat(), 'dyad':dyad,
              'values':{k:v for k,v in rec.items() if k not in ('dyad','date','logged_at')
                        and isinstance(v,(float,int,bool,str)) and len(k)<90}}
            for when,rec in matching[-3:]]


def news_evidence(news, cutoff, market_id, dyad):
    seen = set()
    pre, post, unknown = [], [], []
    for n in news or []:
        if not isinstance(n,dict):
            continue
        if n.get('market_id') is not None and str(n['market_id']) != market_id:
            continue
        if n.get('dyad') is not None and str(n['dyad']) != dyad:
            continue
        name, url, sid = n.get('title'),n.get('url'),n.get('id')
        if not isinstance(sid,str) or not sid or sid in seen or not isinstance(name,str) or not isinstance(url,str) or not url.startswith('https://'):
            continue
        seen.add(sid)
        published=stamp(n.get('published_at'))
        entry={'source_id':'NEWS:'+sid,'title':name[:200],'url':url[:1000],
               'published_at':published.isoformat() if published else None,
               'event_at':canonical_date(n.get('event_at')),
               'retrieved_at':canonical_date(n.get('retrieved_at')),
               'source_kind':n.get('source_kind','news_metadata'),
               'license':n.get('license','unverified')}
        if not published:
            unknown.append(entry)
        elif published <= cutoff:
            entry['available_before_forecast_not_proven_consumed'] = True
            pre.append(entry)
        else:
            post.append(entry)
    return pre[:30],post[:30],unknown[:30]


def model_evidence(context, cutoff):
    # Historian supplied provenance only. The current working tree is NEVER
    # counted as a historical model revision.
    accepted, rejected=[],[]
    for item in context or []:
        if not isinstance(item,dict):continue
        captured=stamp(item.get('captured_at'))
        sid=str(item.get('id') or '')
        sha=str(item.get('code_sha') or '')
        if not sid or not captured or not (7<=len(sha)<=64) or not all(c in '0123456789abcdef' for c in sha.lower()):
            rejected.append({'id':sid,'reason':'no timestamped code revision evidence'})
        elif captured > cutoff:
            rejected.append({'id':sid,'reason':'code context captured after forecast'})
        else:
            accepted.append({'source_id':'MODEL:'+sid,'captured_at':captured.isoformat(),
                             'code_sha':sha,'summary':str(item.get('summary',''))[:3000],
                             'assumptions':item.get('assumptions',[])[:20] if isinstance(item.get('assumptions',[]),list) else []})
    return accepted[:8],rejected


def reconstruct(resolved, predictions, nodes, meta, news, contexts, provenance):
    market_id=resolved['market_id']
    cutoff=stamp(resolved['forecast_at'])
    # fm.read_log has already verified the timestamp against resolution time.
    history, late, total=forecast_history(predictions,market_id,cutoff)
    traces=node_history(nodes,resolved.get('dyad',''),cutoff)
    before,after,undated=news_evidence(news,cutoff,market_id,resolved.get('dyad',''))
    historical_models,rejected_models=model_evidence(contexts,cutoff)
    md=meta.get(market_id,{}) if isinstance(meta,dict) else {}
    if not isinstance(md,dict): md={}
    fetched=stamp(md.get('fetched_at'))
    metadata_contemporaneous=bool(fetched and fetched<=cutoff)
    # Metadata fetched after forecast can be shown only as retrospective context.
    timestamps=[stamp(md.get('startDate')),stamp(md.get('endDate'))]
    warnings=[]
    if predictions is None or not predictions:
        warnings.append('Individual forecast log missing or empty; recorded first-prediction row cannot be independently verified')
    elif not history:
        warnings.append('No timestamped individual forecast found at or before first_prediction_ts')
    if not traces:
        warnings.append('No exact-dyad historical node snapshot within 14 days before first prediction')
    if not historical_models:
        warnings.append('Historical model code/weights not established: cannot attribute prediction to particular game-theoretic assumption')
    if not metadata_contemporaneous:
        warnings.append('Market metadata fetched after forecast or timestamp unknown: rules not verified as-of')
    if timestamps[1] and cutoff>timestamps[1]:
        warnings.append('First prediction timestamp is later than recorded contract endDate; possible post-event leakage')
    if late:
        warnings.append(f'{late} individual forecast entries excluded as later than first prediction or lacking comparable timestamp')
    if not before:
        warnings.append('No sourced news demonstrably published by forecast time in provided news manifest')
    sources={}
    for key,v in provenance.items():
        if v['exists']:
            sources['FILE:'+key]={'kind':'local_file','sha256':v['sha256'],'filename':v['file']}
    for rec in history+traces+before+after+undated+historical_models:
        sources[rec['source_id']]={'kind':rec['source_id'].split(':')[0],
                                    'timestamp':rec.get('timestamp') or rec.get('published_at') or rec.get('captured_at'),
                                    'url':rec.get('url')}
    observed=resolved['outcome']
    return {'dossier_version':VERSION,'market_id':market_id,
            'market_label':resolved.get('label'),'dyad':resolved.get('dyad'),
            'contract_type':resolved.get('contract_type'),'relation':resolved.get('relation'),
            'forecast_cutoff_utc':cutoff.isoformat(),
            'forecast_at_first':{'conditional_p':resolved['forecast_p'],
                                 'market_p_logged':resolved['market_p'],
                                 'source_id':'FILE:brier',
                                 'verified_in_individual_log':any(h.get('conditional_p') is not None and abs(h['conditional_p']-resolved['forecast_p'])<1e-6 and abs((stamp(h['timestamp'])-cutoff).total_seconds())<=10 for h in history)},
            'outcome_after':{'outcome':observed,'resolved_at':resolved['resolved_at'],
                             'source_id':'FILE:brier','model_brier':resolved['model_brier'],
                             'market_brier_logged':resolved['market_brier'],
                             'excess_brier':resolved['excess_brier']},
            'individual_forecasts_as_of':history,
            'individual_forecasts_matched_count':total,
            'future_or_undated_forecasts_excluded':late,
            'node_traces_as_of':traces,
            'historical_models_as_of':historical_models,
            'rejected_unproven_model_context':rejected_models,
            'market_metadata':{'question':md.get('question'),'startDate':md.get('startDate'),
                               'endDate':md.get('endDate'),'fetched_at':md.get('fetched_at'),
                               'as_of_snapshot_proven':metadata_contemporaneous},
            'news_published_by_forecast':before,
            'news_published_after_forecast':after,
            'news_without_valid_publication_time_excluded':undated,
            'source_registry':sources,
            'missing_evidence_or_warnings':warnings,
            'model_reasoning_verified':False,
            'historical_input_trace_partial':bool(history and historical_models and traces),
            'research_status':'diagnostic_only_no_novelty_or_causal_inference'}


def build(*, brier=None, predictions=None, nodes=None, metadata=None, news=None,
          model_context=None, market_ids=(), top=4, out=None):
    paths={'brier':Path(brier or ROOT/'predictions/brier_log.jsonl'),
           'predictions':Path(predictions or ROOT/'predictions/log.jsonl'),
           'node_history':Path(nodes or ROOT/'pipeline/node_score_history.jsonl'),
           'market_metadata':Path(metadata or ROOT/'pipeline/market_meta.json')}
    if news: paths['news_manifest']=Path(news)
    if model_context: paths['model_context']=Path(model_context)
    if not 1<=top<=12 or len(market_ids)>12:
        raise ValueError('At most 12 dossiers per batch')
    provenance={k:source_info(v) for k,v in paths.items()}
    if not provenance['brier']['exists']:
        raise ValueError('Resolved Brier log required')
    picks,qc=pick_cases(paths['brier'], market_ids, top)
    p=rows(paths['predictions']); n=rows(paths['node_history'])
    meta=load_json(paths['market_metadata']) if paths['market_metadata'].is_file() else {}
    news_rows=load_json(paths['news_manifest']) if news else []
    model_rows=load_json(paths['model_context']) if model_context else []
    if not isinstance(news_rows,list) or not isinstance(model_rows,list):
        raise ValueError('News and model-context manifests must be JSON arrays')
    dossiers=[reconstruct(r,p,n,meta,news_rows,model_rows,provenance) for r in picks]
    report={'version':VERSION,'status':'case_dossiers_created_no_llm',
            'source_provenance':provenance,'resolver_qc':dict(qc),
            'cases':dossiers,'dossier_count':len(dossiers),
            'limitations':['Brier resolution time is not necessarily event time',
                           'Sibling contracts may share the same event; do not infer independence',
                           'Contemporaneous news publication is not proof the engine consumed it',
                           'Current model code is not historical code; do not infer old game-theoretic logic',
                           'Market prices may not be simultaneous or contract-comparable',
                           'No automatically retrieved news, scholarly papers or model revision history'],
            'paid_api_calls':0,'network_calls':0}
    if out is not None:
        target=Path(out).expanduser().resolve()
        if target==paths['brier'].expanduser().resolve() or target in [x.expanduser().resolve() for x in paths.values()]:
            raise ValueError('Refusing to overwrite any input file')
        prototype.write_json(target,report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Time-safe forensic dossiers for forecasting misses (offline)')
    parser.add_argument('--brier-log',type=Path)
    parser.add_argument('--predictions-log',type=Path)
    parser.add_argument('--node-history',type=Path)
    parser.add_argument('--market-meta',type=Path)
    parser.add_argument('--news-manifest',type=Path,help='Optional list of dated, sourced news links; no fetching')
    parser.add_argument('--model-context',type=Path,help='Optional historical model manifest, with timestamped code SHA')
    parser.add_argument('--market-id',action='append',default=[])
    parser.add_argument('--top',type=int,default=4)
    parser.add_argument('--out',type=Path,default=RESEARCH/'inbox/forecast_misses/CASE_DOSSIERS_PRIVATE.json')
    args=parser.parse_args(argv)
    try:
        result=build(brier=args.brier_log,predictions=args.predictions_log,
                     nodes=args.node_history,metadata=args.market_meta,
                     news=args.news_manifest,model_context=args.model_context,
                     market_ids=args.market_id,top=args.top,out=args.out)
        print(json.dumps({'status':result['status'],'dossiers':result['dossier_count'],
                          'out':str(args.out),'coverage':[
                              {'market_id':c['market_id'],
                               'forecast_history':c['individual_forecasts_matched_count'],
                               'nodes':len(c['node_traces_as_of']),
                               'historical_model_proven':bool(c['historical_models_as_of']),
                               'warnings':len(c['missing_evidence_or_warnings'])}
                              for c in result['cases']],
                          'network_or_paid_api_calls':0},indent=2))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print('Forensic dossier build stopped safely: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())

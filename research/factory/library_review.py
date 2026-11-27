"""Bridge the private Zotero/hazard library to the existing literature agent.

No new vendor API required for retrieval-only mode. Literature synthesis remains
preliminary until the researcher reads actual papers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path

from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from .library import HOME, DEFAULT_DB, connect, search_documents, search_hazards, terms


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as file:
        tmp = Path(file.name)
        json.dump(record, file, indent=2, ensure_ascii=False)
        file.write('\n')
    tmp.replace(path)


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def openalex(queries):
    from .literature import search_openalex
    return search_openalex(queries)


def synthesize(spec, sources):
    from .literature import ask_claude, verify_map
    return verify_map(ask_claude(spec, sources), sources)


def local_sources(conn, queries, limit=18):
    pool = []
    seen = set()
    for query in queries:
        for row in search_documents(conn, query, limit=20):
            doi = row['doi']
            stable = f'doi:{doi}' if doi else row['source_id']
            if stable in seen:
                continue
            seen.add(stable)
            pool.append({
                'id': row['source_id'], 'title': row['title'], 'authors': row['authors'],
                'year': row['year'], 'venue': row['venue'],
                'doi': ('https://doi.org/' + doi if doi else None),
                'abstract': (row['abstract'] or '')[:1400],
                'query_hits': [query], 'source': 'local_zotero_metadata',
                'full_text_verified': False,
                '_rank': row['score'],
            })
    counts = Counter(word for query in queries for word in set(terms(query)))
    repeated = [word for word, count in counts.most_common() if count >= 2]
    anchor = repeated[0] if repeated else None
    pool.sort(key=lambda r: (
        int(bool(anchor and anchor in r['title'].lower())),
        int(bool(anchor and anchor in r['abstract'].lower())),
        r['_rank'],
    ), reverse=True)
    for row in pool:
        row.pop('_rank', None)
    return pool[:limit]


def local_hazards(conn, queries, limit=12):
    # A term repeated across searches usually identifies the actual phenomenon.
    # Require it for hazard matches, preventing a generic term such as
    # "strategic" from being mistaken for evidence about ceasefires.
    counts = Counter(word for query in queries for word in set(terms(query)))
    repeated = [word for word, count in counts.most_common() if count >= 2]
    anchor = repeated[0] if repeated else None
    records = []
    seen = set()
    for query in queries:
        for record in search_hazards(conn, query, limit=12):
            if record['source_id'] in seen:
                continue
            searchable = ' '.join(str(record.get(field) or '') for field in
                                  ('study', 'variable', 'outcome_class', 'conflict_type', 'family')).lower()
            if anchor and anchor not in searchable:
                continue
            seen.add(record['source_id'])
            records.append(record)
            if len(records) >= limit:
                return records
    return records


def run(spec_path, db_path=DEFAULT_DB, home=HOME, external=True, retrieve_only=False):
    db_path = Path(db_path).expanduser()
    if not db_path.is_file():
        raise ValueError('No local index. First run python3 -m research.factory.library import ...')
    spec = load(Path(spec_path).expanduser())
    key = spec.get('id')
    if not isinstance(key, str) or not 3 <= len(key) <= 64 or not key.isascii() or not key.replace('_', '').replace('-', '').isalnum():
        raise ValueError('A project id containing letters/numbers/_/- is required')
    if not isinstance(spec.get('research_question'), str) or not spec['research_question'].strip():
        raise ValueError('Missing research question')
    queries = spec.get('search_queries')
    if not isinstance(queries, list) or not 1 <= len(queries) <= 4 or any(
        not isinstance(q, str) or not 3 <= len(q) <= 120 for q in queries
    ):
        raise ValueError('Provide 1 to 4 literature search queries')
    with closing(connect(db_path)) as conn:
        files = conn.execute('SELECT kind,sha256 FROM source_files ORDER BY kind').fetchall()
        fingerprint = '|'.join(f'{r[0]}:{r[1]}' for r in files)
        local = local_sources(conn, queries)
        hazards = local_hazards(conn, queries)
    scope = json.dumps([spec, fingerprint, external], sort_keys=True)
    stamp = hashlib.sha256(scope.encode('utf-8')).hexdigest()[:16]
    basename = f'library_review_{key}_{stamp}'
    source_path = Path(home) / 'inbox' / 'raw' / f'{basename}_sources.json'
    record_path = Path(home) / 'inbox' / 'records' / f'{basename}.json'
    if record_path.exists() and load(record_path).get('status') == 'complete':
        report = load(record_path)
        print('Cached assessment:', record_path)
        print('Verdict:', report['assessment']['provisional_verdict'])
        return report
    if source_path.exists():
        bundle = load(source_path)
    else:
        external_sources, external_error = [], None
        if external:
            try:
                external_sources = openalex(queries)[:24]
            except Exception as exc:
                # Local library remains usable, but warn that novelty screening is incomplete.
                external_error = f'{type(exc).__name__}: {exc}'
        by_doi = {str(x.get('doi') or '').lower() for x in local if x.get('doi')}
        external_sources = [dict(x, source='openalex_abstract_metadata',
                                 full_text_verified=False)
                            for x in external_sources
                            if not x.get('doi') or x['doi'].lower() not in by_doi]
        bundle = {'queries': queries, 'local_count': len(local),
                  'external_count': len(external_sources), 'sources': local + external_sources,
                  'hazard_matches': hazards,
                  'external_search_error': external_error,
                  'retrieved_at': timestamp(),
                  'provenance': 'Bibliographic metadata and hazard coefficients, not verified full text'}
        save(source_path, bundle)
    if not bundle['sources']:
        raise ValueError('No relevant source records were discovered')
    if retrieve_only:
        print(f"Found {bundle['local_count']} Zotero candidates; {bundle['external_count']} OpenAlex candidates; "
              f"{len(bundle['hazard_matches'])} relevant hazard estimates")
        print('Candidate papers:')
        for item in bundle['sources'][:15]:
            print('-', str(item.get('title') or 'Untitled')[:120])
        print('Saved source list:', source_path)
        return bundle
    record = {'project_id': key, 'source_path': str(source_path),
              'status': 'synthesizing', 'updated': timestamp()}
    save(record_path, record)
    try:
        assessment = synthesize(spec, bundle['sources'])
        if bundle.get('external_search_error'):
            assessment['external_discovery_incomplete'] = True
        assessment['source_scope'] = 'Metadata/abstracts only; does not establish novelty'
        record.update(status='complete', assessment=assessment, updated=timestamp())
        save(record_path, record)
        print('Provisional verdict:', assessment['provisional_verdict'])
        print('Candidate gap:', assessment['candidate_gap'])
        print('STOP: Read the closest original papers and approve novelty manually.')
        print('Saved assessment:', record_path)
        return record
    except Exception as exc:
        record.update(status='failed', error=str(exc), updated=timestamp())
        save(record_path, record)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description='Zotero-first literature screening (pilot)')
    parser.add_argument('spec', type=Path)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--home', type=Path, default=HOME)
    parser.add_argument('--local-only', action='store_true')
    parser.add_argument('--retrieve-only', action='store_true', help='No Claude API call')
    args = parser.parse_args(argv)
    try:
        run(args.spec, args.db, args.home, external=not args.local_only,
            retrieve_only=args.retrieve_only)
        return 0
    except Exception as exc:
        print(f'Literature review stopped safely: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

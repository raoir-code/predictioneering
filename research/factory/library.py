"""Local, reproducible source index for CSL-JSON Zotero and hazard-estimate CSV.

Pure Python standard library. Local data only; never modifies forecasting components.
"""
from __future__ import annotations

import argparse
import csv
from contextlib import closing
import hashlib
import html
import json
import math
import re
import sqlite3
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
DEFAULT_DB = HOME / 'datasets' / 'private' / 'research_library.sqlite3'

SCHEMA = '''
CREATE TABLE IF NOT EXISTS documents (
  source TEXT NOT NULL, uid TEXT NOT NULL, title TEXT NOT NULL,
  year INTEGER, authors TEXT NOT NULL, venue TEXT,
  doi TEXT, abstract TEXT, url TEXT, kind TEXT,
  metadata_json TEXT NOT NULL,
  PRIMARY KEY(source,uid)
);
CREATE INDEX IF NOT EXISTS documents_doi ON documents(doi);
CREATE TABLE IF NOT EXISTS hazard_estimates (
  source TEXT NOT NULL, row_num INTEGER NOT NULL,
  study TEXT NOT NULL, variable TEXT NOT NULL,
  coefficient TEXT, se TEXT, p_value TEXT, model_type TEXT,
  outcome_class TEXT, conflict_type TEXT, family TEXT,
  in_analysis_sample INTEGER NOT NULL, metadata_json TEXT NOT NULL,
  PRIMARY KEY(source,row_num)
);
CREATE TABLE IF NOT EXISTS source_files (
  kind TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
  source_filename TEXT NOT NULL, imported_rows INTEGER NOT NULL
);
'''
STOP = {'the','and','for','with','that','this','from','have','when','does','some','into',
        'over','under','were','are','can','why','what','whose','which','their','than','about'}


def connect(path=DEFAULT_DB):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def digest(path):
    hash_ = hashlib.sha256()
    with Path(path).open('rb') as fp:
        for block in iter(lambda: fp.read(1024 * 1024), b''):
            hash_.update(block)
    return hash_.hexdigest()


def year_of(item):
    issued = item.get('issued') or {}
    try:
        year = int(issued['date-parts'][0][0])
        return year if 1000 <= year <= 2200 else None
    except (KeyError, ValueError, TypeError, IndexError):
        return None


def clean(value):
    return html.unescape(re.sub(r'<[^>]*>', '', str(value or ''))).strip()


def normalize_doi(value):
    doi = str(value or '').strip().lower()
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)
    return doi.removeprefix('doi:').strip()


def import_zotero(conn, filename):
    path = Path(filename).expanduser()
    sha = digest(path)
    saved = conn.execute('SELECT sha256, imported_rows FROM source_files WHERE kind=?',
                         ('zotero_csl_json',)).fetchone()
    if saved and saved['sha256'] == sha:
        return saved['imported_rows'], 'unchanged'
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, list) or not data:
        raise ValueError('Zotero export must be a nonempty CSL JSON list')
    docs = []
    seen = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f'Invalid Zotero item at {i}')
        uid = str(item.get('id') or '').strip() or f'entry:{i}'
        if uid in seen:
            raise ValueError(f'Duplicate Zotero item ID: {uid}')
        seen.add(uid)
        authors = '; '.join(clean((a.get('family') or a.get('literal') or '') +
                                  (', ' + a.get('given', '') if a.get('given') else ''))
                            for a in (item.get('author') or []) if isinstance(a, dict))
        docs.append(('zotero', uid, clean(item.get('title')) or '[Untitled]', year_of(item),
                     authors, clean(item.get('container-title')), normalize_doi(item.get('DOI')),
                     str(item.get('abstract') or ''), str(item.get('URL') or ''),
                     str(item.get('type') or ''), json.dumps(item, ensure_ascii=False)))
    with conn:
        conn.execute('DELETE FROM documents WHERE source=?', ('zotero',))
        conn.executemany('''INSERT INTO documents(source,uid,title,year,authors,venue,doi,
                             abstract,url,kind,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)''', docs)
        conn.execute('''INSERT OR REPLACE INTO source_files(kind,sha256,source_filename,imported_rows)
                        VALUES (?,?,?,?)''', ('zotero_csl_json', sha, path.name, len(docs)))
    return len(docs), 'imported'


def import_hazards(conn, filename):
    path = Path(filename).expanduser()
    sha = digest(path)
    saved = conn.execute('SELECT sha256, imported_rows FROM source_files WHERE kind=?',
                         ('hazard_csv',)).fetchone()
    if saved and saved['sha256'] == sha:
        return saved['imported_rows'], 'unchanged'
    with path.open('r', encoding='utf-8-sig', newline='') as fp:
        reader = csv.DictReader(fp)
        required = {'study','variable','coefficient','se','p_value','model_type',
                    'outcome_class','conflict_type','in_analysis_sample'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError('Hazard CSV missing required columns: ' +
                             ', '.join(sorted(required - set(reader.fieldnames or []))))
        data = list(reader)
    if not data:
        raise ValueError('Hazard CSV has no records')
    records = []
    for i, row in enumerate(data, start=1):
        if any(val is None for val in row.values()):
            raise ValueError(f'CSV row {i}: malformed number of columns')
        flag = str(row['in_analysis_sample']).strip().lower()
        if flag not in ('true','false','1','0'):
            raise ValueError(f'CSV row {i}: unrecognized analysis-sample flag')
        records.append(('conflict_hazards', i, row['study'], row['variable'],
                        row.get('coefficient'), row.get('se'), row.get('p_value'),
                        row.get('model_type'), row.get('outcome_class'),
                        row.get('conflict_type'), row.get('family'),
                        int(flag in ('true','1')), json.dumps(row, ensure_ascii=False)))
    with conn:
        conn.execute('DELETE FROM hazard_estimates WHERE source=?', ('conflict_hazards',))
        conn.executemany('''INSERT INTO hazard_estimates(source,row_num,study,variable,
            coefficient,se,p_value,model_type,outcome_class,conflict_type,family,
            in_analysis_sample,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', records)
        conn.execute('''INSERT OR REPLACE INTO source_files(kind,sha256,source_filename,imported_rows)
                        VALUES (?,?,?,?)''', ('hazard_csv', sha, path.name, len(records)))
    return len(records), 'imported'


def terms(query):
    return [term for term in re.findall(r'[a-z0-9]+', query.lower())
            if len(term) > 2 and term not in STOP][:12]


def score(text, words):
    val = text.lower()
    return sum(val.count(word) for word in words)


def search_documents(conn, query, limit=15):
    words = list(dict.fromkeys(terms(query)))
    if not words:
        return []
    docs = conn.execute("SELECT uid,title,year,authors,venue,doi,abstract,url,kind FROM documents").fetchall()
    # In a small library, IDF-weighted lexical matching is transparent and inexpensive.
    frequency = {word: sum(word in (r['title'] + ' ' + (r['abstract'] or '')).lower()
                           for r in docs) for word in words}
    weight = {word: 1 + math.log((len(docs) + 1) / (frequency[word] + 1))
              for word in words}
    found = []
    for row in docs:
        r = dict(row)
        matched = []
        rank = 0.0
        for word in words:
            title_hits = min(score(r['title'], [word]), 3)
            abstract_hits = min(score(r['abstract'] or '', [word]), 4)
            author_hits = min(score(r['authors'], [word]), 2)
            if title_hits or abstract_hits or author_hits:
                matched.append(word)
                rank += weight[word] * (10 * title_hits + 2 * abstract_hits + author_hits)
        if not matched:
            continue
        rank += 8 * max(0, len(matched) - 1)
        r['source_id'] = r.pop('uid')
        r['source_library'] = 'zotero_csl_json'
        r['full_text_verified'] = False
        r['score'] = round(rank, 2)
        found.append(r)
    found.sort(key=lambda r: (-r['score'], -(r['year'] or 0), r['title']))
    unique, seen = [], set()
    for r in found:
        dedupe = r['doi'] or re.sub(r'\W+', '', r['title'].lower())
        if dedupe in seen:
            continue
        seen.add(dedupe)
        unique.append(r)
        if len(unique) >= limit:
            break
    return unique


def search_hazards(conn, query, limit=12):
    words = terms(query)
    if not words:
        return []
    rows = conn.execute('''SELECT row_num,study,variable,coefficient,se,p_value,model_type,
                                 outcome_class,conflict_type,family,in_analysis_sample
                          FROM hazard_estimates''').fetchall()
    found = []
    for row in rows:
        r = dict(row)
        rank = 4 * score(r['variable'], words) + 2 * score(r['study'] or '', words)
        rank += score(' '.join((r['outcome_class'] or '', r['family'] or '',
                                r['conflict_type'] or '')), words)
        if rank > 0:
            r['score'] = rank
            r['source_id'] = f"hazard_csv_row:{r.pop('row_num')}"
            r['interpretation_checked'] = False
            found.append(r)
    return sorted(found, key=lambda r: -r['score'])[:limit]


def context(conn, query, paper_limit=15, hazard_limit=12):
    return {
        'query': query,
        'source_level': 'Zotero bibliographic metadata/abstracts and raw published hazard estimates',
        'novelty_verified': False,
        'full_text_verified': False,
        'papers': search_documents(conn, query, paper_limit),
        'hazard_estimates': search_hazards(conn, query, hazard_limit),
    }


def stats(conn):
    return {
        'zotero_references': conn.execute('SELECT count(*) FROM documents').fetchone()[0],
        'with_abstract': conn.execute("SELECT count(*) FROM documents WHERE abstract IS NOT NULL AND abstract != ''").fetchone()[0],
        'with_doi': conn.execute("SELECT count(*) FROM documents WHERE doi IS NOT NULL AND doi != ''").fetchone()[0],
        'hazard_estimates': conn.execute('SELECT count(*) FROM hazard_estimates').fetchone()[0],
        'hazard_studies': conn.execute('SELECT count(DISTINCT study) FROM hazard_estimates').fetchone()[0],
        'hazard_analysis_sample': conn.execute('SELECT count(*) FROM hazard_estimates WHERE in_analysis_sample=1').fetchone()[0],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local scholarly library (never uploaded to GitHub)')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    commands = parser.add_subparsers(dest='cmd', required=True)
    load = commands.add_parser('import')
    load.add_argument('--zotero', type=Path)
    load.add_argument('--hazards', type=Path)
    commands.add_parser('stats')
    find = commands.add_parser('search')
    find.add_argument('query')
    find.add_argument('--limit', type=int, default=10)
    args = parser.parse_args(argv)
    if args.cmd == 'import' and not (args.zotero or args.hazards):
        parser.error('import needs --zotero and/or --hazards')
    with closing(connect(args.db)) as conn:
        if args.cmd == 'import':
            if args.zotero:
                print('Zotero:', *import_zotero(conn, args.zotero))
            if args.hazards:
                print('Hazards:', *import_hazards(conn, args.hazards))
            print(json.dumps(stats(conn), indent=2))
        elif args.cmd == 'stats':
            print(json.dumps(stats(conn), indent=2))
        else:
            if not 1 <= args.limit <= 50:
                parser.error('--limit must be between 1 and 50')
            print(json.dumps(context(conn, args.query, args.limit, args.limit), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Offline, citation-bearing search across currently indexed scientific profiles.

Exposes provisional claims distinctly from human-reviewed evidence. Never
creates a paper, proves a proposition, calls a model or claims novelty.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import sys

from .paper_profiles import VERSION, prepare, cleaned
from .profile_audit import SCHEMA as REVIEW_SCHEMA
from .pdf_text import DEFAULT_DB

STOP = {"the", "and", "for", "that", "with", "from", "which", "this",
        "those", "their", "about", "when", "would", "could", "there",
        "have", "were", "been"}


def terms(query):
    return list(dict.fromkeys(
        t for t in re.findall(r"[a-z0-9]{3,}", query.casefold())
        if t not in STOP
    ))[:10]


def search(database, query, limit=12, approved_only=False,
           include_rejected=False):
    if not 1 <= limit <= 100:
        raise ValueError("--limit must be 1-100")
    words = terms(query)
    if not words:
        raise ValueError("Provide at least one substantive search term")
    with closing(prepare(database)) as db:
        db.executescript(REVIEW_SCHEMA)
        current = db.execute(
            """SELECT p.root,p.relpath,p.pdf_sha256,p.model,p.version,
                      p.profile_json
               FROM paper_profiles p
               JOIN pdf_files i ON i.root=p.root AND i.relpath=p.relpath
               JOIN pdf_text_documents d ON d.root=p.root AND d.relpath=p.relpath
               WHERE p.version=? AND p.pdf_sha256=d.sha256
                 AND i.sha256=d.sha256 AND d.status='ok'
               ORDER BY p.root,p.relpath""", (VERSION,)
        ).fetchall()
        hits = []
        for row in current:
            profile = json.loads(row["profile_json"])
            review = {r["evidence_id"]: r["decision"]
                      for r in db.execute(
                          """SELECT evidence_id,decision FROM profile_evidence_reviews
                             WHERE root=? AND relpath=? AND pdf_sha256=?
                               AND profile_version=? AND model=?""",
                          (row["root"], row["relpath"], row["pdf_sha256"],
                           row["version"], row["model"])
                      )}
            for e in profile.get("evidence", []):
                status = review.get(e["evidence_id"], "not_reviewed")
                if approved_only and status != "approved":
                    continue
                if not include_rejected and status == "rejected":
                    continue
                # Check original local page text as well as the stored evidence.
                original = db.execute(
                    """SELECT text FROM pdf_text_pages
                       WHERE root=? AND relpath=? AND page_num=?""",
                    (row["root"], row["relpath"], e["page"])
                ).fetchone()
                quote = e.get("quote", "")
                if not original or not quote or cleaned(quote) not in cleaned(original["text"]):
                    continue
                claim = e.get("claim", "")
                title = profile.get("title", "")
                kind = e.get("kind", "")
                c = claim.casefold()
                q = quote.casefold()
                t = title.casefold()
                k = kind.casefold()
                # A paper title match alone does not support an individual
                # evidence card; require claim, verbatim quote or kind match.
                if not any(w in c or w in q or w in k for w in words):
                    continue
                score = sum(5*(w in c)+3*(w in q)+(w in k)+(w in t)
                            for w in words)
                hits.append((score, {
                    "source_id": profile.get("zotero_uid"),
                    "title": title, "file": row["relpath"],
                    "pdf_sha256": row["pdf_sha256"],
                    "pdf_page": e["page"], "kind": kind,
                    "claim_unreviewed_or_annotated": claim,
                    "verified_quote": quote,
                    "evidence_id": e["evidence_id"],
                    "human_review_status": status,
                    "interpretation_independently_checked": status == "approved",
                    "model": row["model"],
                    "score": score,
                }))
    hits.sort(key=lambda pair: (-pair[0], pair[1]["title"], pair[1]["pdf_page"]))
    papers = len(set((x[1]["file"], x[1]["pdf_sha256"]) for x in hits))
    return {
        "query": query,
        "profiles_matching": papers,
        "evidence_hits": len(hits),
        "results": [r for _, r in hits[:limit]],
        "approved_only": approved_only,
        "novelty_verified": False,
        "caution": ("Verbatim quote was rechecked against current indexed PDF page. "
                    "Matching a quote to a page does not prove the associated "
                    "interpretation; even human-approved entries are not proofs "
                    "of a complete paper or model. PDF page indexes depend "
                    "on the specific edition."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local cross-paper theory/evidence search")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("search")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=12)
    find.add_argument("--approved-only", action="store_true")
    find.add_argument("--include-rejected", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = search(args.db, args.query, args.limit,
                        args.approved_only, args.include_rejected)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        print("Theory catalog failed safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

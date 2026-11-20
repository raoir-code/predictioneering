"""Portfolio-wide, zero-API scientific extraction diagnostics.

This is a QC dashboard, not verification of the truth of extracted claims.
All source passages remain in the user's local private SQLite database.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

from .paper_profiles import VERSION
from .profile_audit import open_audit_db, audits
from .pdf_text import DEFAULT_DB


def summary(database, *, include_papers=True):
    with closing(open_audit_db(database)) as db:
        library_count = db.execute("SELECT COUNT(*) FROM pdf_files").fetchone()[0]
        current = db.execute(
            """SELECT p.root,p.relpath,p.pdf_sha256,p.version,p.model,
                      p.title,p.profile_json
               FROM paper_profiles p
               JOIN pdf_files i ON i.root=p.root AND i.relpath=p.relpath
               JOIN pdf_text_documents d ON d.root=p.root AND d.relpath=p.relpath
               WHERE p.version=? AND d.status='ok'
                 AND i.sha256=p.pdf_sha256 AND d.sha256=p.pdf_sha256
               ORDER BY p.title,p.relpath""",
            (VERSION,)
        ).fetchall()
        all_kinds, all_flags, all_origins, all_reviews = (
            Counter(), Counter(), Counter(), Counter()
        )
        sources_checked, evidence_count, papers = 0, 0, []
        for row in current:
            profile = json.loads(row["profile_json"])
            entries = audits(db, row, profile)
            flags = Counter(flag for entry in entries for flag in entry["warnings"])
            origins = Counter(e["source_type_hint"] for e in entries
                              if e["kind"] == "empirical_finding")
            reviews = Counter(e["review_status"] for e in entries)
            kinds = Counter(e["kind"] for e in entries)
            mismatch = sum(not e["quote_found_on_original_indexed_page"]
                           for e in entries)
            total = len(entries)
            evidence_count += total
            sources_checked += total - mismatch
            all_kinds.update(kinds)
            all_flags.update(flags)
            all_origins.update(origins)
            all_reviews.update(reviews)
            if include_papers:
                papers.append({
                    "paper": row["title"], "file": row["relpath"],
                    "model": row["model"], "evidence_total": total,
                    "quote_mismatches": mismatch,
                    "warning_counts": dict(flags),
                    "evidence_kinds": dict(kinds),
                    "empirical_source_type_hints": dict(origins),
                    "human_reviews": dict(reviews),
                })
    return {
        "status": "offline_source_audit_only",
        "indexed_pdf_count": library_count,
        "current_profiles": len(current),
        "unprofiled_or_stale": max(0, library_count - len(current)),
        "extracted_evidence_total": evidence_count,
        "matched_quote_total": sources_checked,
        "quote_mismatches": evidence_count - sources_checked,
        "warning_counts": dict(all_flags),
        "evidence_kinds": dict(all_kinds),
        "empirical_source_type_hints": dict(all_origins),
        "human_reviews": dict(all_reviews),
        "papers": papers if include_papers else [],
        "source_notes": (
            "Flags may overlap per evidence entry. Type hints are tentative, not "
            "corrections: simulation outputs and prior literature reports should "
            "not be counted as observational empirical confirmations. A matched "
            "quotation does not validate the claim, equation, or causal inference."
        ),
        "scientific_verdict": "not_verified",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Offline cross-paper profile QA dashboard")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--summary-only", action="store_true",
                   help="Hide per-paper detail")
    args = p.parse_args(argv)
    try:
        print(json.dumps(summary(args.db, include_papers=not args.summary_only),
                         indent=2, ensure_ascii=False))
        return 0
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        print("Portfolio quality audit failed safely: " + str(exc),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

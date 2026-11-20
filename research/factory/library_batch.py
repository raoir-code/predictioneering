"""Offline batch planner for scaling scientific paper profiles deliberately.

No API calls. Planning may expose filenames/metadata locally but does not
upload PDFs, invoke Claude or alter source files. User must execute each
generated paid command themselves.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import sys

from .paper_profiles import (
    VERSION, chunks_cached, chunks_for, indexed, prepare,
    sections, serialize_chunk,
)
from .pdf_text import DEFAULT_DB

THEORY_SIGNALS = (
    (r"\b(?:theory|theories|theoretical)\b", 6),
    (r"\b(?:game|games|model|models|modeling|modelling)\b", 5),
    (r"\b(?:bargaining|bargain|commitment|equilibrium|strategic)\b", 4),
    (r"\b(?:war|conflict|crisis|deterrence|escalation)\b", 2),
)
UNCERTIFIED = "model_extracted_not_scientifically_reviewed"


def title_priority(title):
    """Heuristic relevance hint, not a publication-quality or novelty judgment."""
    return sum(weight for pattern, weight in THEORY_SIGNALS
               if re.search(pattern, title, re.IGNORECASE))


def shell_command(root, relpath, model, remaining_calls):
    """Exact filename targets one paper; quote shell arguments against injection."""
    args = [
        "python3", "-m", "research.factory.paper_profiles", "run",
        "--folder", root, "--file", relpath, "--model", model,
        "--limit", "1", "--max-calls", str(max(1, remaining_calls)),
        "--send-to-claude",
    ]
    return " ".join(shlex.quote(str(x)) for x in args)


def scan(database, folder, model, match=None):
    """Return current PDF inventory/status using existing versioned caches."""
    if not model:
        raise ValueError("Set CLAUDE_MODEL or pass --model for cache safety")
    with closing(prepare(database)) as db:
        rows = indexed(db, folder)
        records = []
        for row in rows:
            title = row["zotero_title"] or Path(row["relpath"]).stem
            if match and match.casefold() not in (title + " " + row["relpath"]).casefold():
                continue
            cached_profile = db.execute(
                """SELECT pdf_sha256,version,model,profile_json
                   FROM paper_profiles
                   WHERE root=? AND relpath=?""",
                (row["root"], row["relpath"])
            ).fetchone()
            current = bool(
                cached_profile
                and cached_profile["pdf_sha256"] == row["sha256"]
                and cached_profile["version"] == VERSION
                and cached_profile["model"] == model
            )
            chunks = chunks_for(sections(db, row))
            saved = chunks_cached(db, row, model, chunks)
            needs = len(chunks) - len(saved)
            records.append({
                "title": title, "file": row["relpath"], "root": row["root"],
                "pdf_sha256": row["sha256"],
                "pages_with_text": row["pages_with_text"],
                "chunks_total": len(chunks),
                "chunks_cached": len(saved), "api_calls_needed": needs,
                "characters_to_send": sum(
                    len(serialize_chunk(chunk))
                    for i, chunk in enumerate(chunks) if i not in saved
                ),
                "profile_status": (
                    "profiled_unreviewed" if current
                    else "cached_chunks_awaiting_profile" if saved
                    else "not_profiled"
                ),
                "existing_other_model_or_stale_profile": bool(
                    cached_profile and not current
                ),
                "theory_title_score": title_priority(title),
            })
        return records


def preview(database, folder, model, max_papers=3, max_calls=20,
            match=None, ordering="theory"):
    if max_papers < 1 or max_calls < 1:
        raise ValueError("--max-papers and --max-calls must be >= 1")
    if max_papers > 100 or max_calls > 200:
        raise ValueError("Safety bounds: --max-papers <= 100, --max-calls <= 200")
    if ordering not in ("theory", "smallest", "filename"):
        raise ValueError("Unknown --order")
    records = scan(database, folder, model, match)
    counts = Counter(row["profile_status"] for row in records)
    pending = [row for row in records if row["profile_status"] != "profiled_unreviewed"]
    if ordering == "theory":
        pending.sort(key=lambda row: (-int(row["chunks_cached"] > 0),
                                     -row["theory_title_score"],
                                     row["api_calls_needed"], row["file"].casefold()))
    elif ordering == "smallest":
        pending.sort(key=lambda row: (-int(row["chunks_cached"] > 0),
                                     row["api_calls_needed"], row["file"].casefold()))
    else:
        pending.sort(key=lambda row: row["file"].casefold())
    remaining, chosen, deferred = max_calls, [], []
    for row in pending:
        if len(chosen) >= max_papers:
            break
        needed = row["api_calls_needed"]
        if needed > remaining:
            deferred.append({
                "file": row["file"], "needed_calls": needed,
                "remaining_call_budget": remaining,
                "reason": "does_not_fit_call_budget",
            })
            continue
        item = {k: v for k, v in row.items() if k not in ("pdf_sha256",)}
        item["command_if_explicitly_approved"] = shell_command(
            row["root"], row["file"], model, needed
        )
        chosen.append(item)
        remaining -= needed
    return {
        "status": "dry_run_no_api_calls",
        "model": model, "order": ordering, "match": match,
        "indexed_papers_matching_filter": len(records),
        "profile_counts": dict(counts),
        "selected": chosen,
        "selected_papers": len(chosen),
        "selected_api_calls_needed": max_calls-remaining,
        "selected_characters_to_send": sum(x["characters_to_send"] for x in chosen),
        "max_papers": max_papers,
        "max_calls": max_calls,
        "remaining_call_budget": remaining,
        "deferred_by_budget": deferred[:20],
        "pending_not_selected": len(pending)-len(chosen),
        "relevance_note": ("Title keywords are only a prioritization heuristic. "
                           "No novelty, relevance or scientific validity is inferred."),
        "cost_note": ("This previews the number of *billable attempts*, not dollar cost. "
                      "Actual token usage and model pricing may vary. Commands are "
                      "never executed by this planner."),
        "quality_gate": ("All generated profiles remain model-extracted and "
                         "unreviewed; run profile_audit before scientific reuse."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline queue and budget preview for the indexed PDF library")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="Plan capped multi-paper pilot without API calls")
    p.add_argument("--folder", type=Path, required=True)
    p.add_argument("--model", default=os.getenv("CLAUDE_MODEL", ""))
    p.add_argument("--match", help="Restrict paper title/filename to substring")
    p.add_argument("--max-papers", type=int, default=3)
    p.add_argument("--max-calls", type=int, default=20)
    p.add_argument("--order", choices=("theory", "smallest", "filename"),
                   default="theory")
    args = parser.parse_args(argv)
    try:
        output = preview(args.db, args.folder, args.model, args.max_papers,
                         args.max_calls, args.match, args.order)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print("Library batch plan failed safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Page-referenced local PDF text index. No cloud calls; originals are read-only."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys

from .pdf_inventory import DEFAULT_DB

VERSION = "pdftotext-page-v1"
MAX_TEXT_BYTES = 24_000_000
SCHEMA = """
CREATE TABLE IF NOT EXISTS pdf_text_documents (
 root TEXT NOT NULL, relpath TEXT NOT NULL, sha256 TEXT NOT NULL,
 version TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
 pages_total INTEGER NOT NULL, pages_with_text INTEGER NOT NULL,
 extracted_at TEXT NOT NULL, PRIMARY KEY(root,relpath)
);
CREATE TABLE IF NOT EXISTS pdf_text_pages (
 root TEXT NOT NULL, relpath TEXT NOT NULL, page_num INTEGER NOT NULL,
 text TEXT NOT NULL, PRIMARY KEY(root,relpath,page_num)
);
CREATE INDEX IF NOT EXISTS pdf_text_pages_file
 ON pdf_text_pages(root,relpath);
"""

def connect_existing(database: Path):
    database = Path(database).expanduser()
    if not database.is_file():
        raise ValueError("Private research database missing. Import Zotero and run the PDF inventory first.")
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pdf_files'"
    ).fetchone():
        conn.close()
        raise ValueError("Run python3 -m research.factory.pdf_inventory FOLDER first.")
    conn.executescript(SCHEMA)
    return conn

def pdf_pages(path: Path, executable: str):
    """Use form feeds for *PDF* pages (not the journal's printed page numbers)."""
    try:
        proc = subprocess.run(
            [executable, "-enc", "UTF-8", str(path), "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("pdftotext timed out") from exc
    except OSError as exc:
        raise RuntimeError("pdftotext could not start") from exc
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"pdftotext failed ({proc.returncode}): {detail}")
    if len(proc.stdout) > MAX_TEXT_BYTES:
        raise RuntimeError("PDF text exceeded per-file safety limit")
    raw = proc.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    parts = raw.split("\f")
    if len(parts) > 1 and not parts[-1].strip():
        parts.pop()
    pages = [(n, p.strip()) for n, p in enumerate(parts, 1) if p.strip()]
    return ("ok" if pages else "no_extractable_text"), pages, len(parts)

def extract(folder: Path, database: Path = DEFAULT_DB,
            limit: int | None = None, force: bool = False):
    """Extract inventoried PDFs only. Store everything in ignored private SQLite."""
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    executable = shutil.which("pdftotext")
    if not executable:
        raise ValueError("pdftotext not found. On macOS run: brew install poppler")
    if limit is not None and limit < 1:
        raise ValueError("--limit must be >= 1")
    report = {
        "root": str(root), "files_processed": 0,
        "cached_unchanged": 0, "remaining_to_extract": 0,
        "no_extractable_text": 0, "extraction_errors": 0,
        "page_records_added": 0, "examples_of_errors": [],
    }
    with closing(connect_existing(database)) as db:
        files = db.execute(
            "SELECT relpath,sha256,size_bytes,mtime_ns FROM pdf_files "
            "WHERE root=? ORDER BY relpath", (str(root),)
        ).fetchall()
        if not files:
            raise ValueError("No PDFs inventoried for this folder; rerun pdf_inventory first.")
        processed = 0
        for file in files:
            name = file["relpath"]
            if not file["sha256"]:
                report["extraction_errors"] += 1
                continue
            saved = db.execute(
                "SELECT sha256,version,status FROM pdf_text_documents "
                "WHERE root=? AND relpath=?", (str(root), name)
            ).fetchone()
            if (not force and saved and saved["sha256"] == file["sha256"]
                    and saved["version"] == VERSION and saved["status"] != "failed"):
                report["cached_unchanged"] += 1
                continue
            if limit is not None and processed >= limit:
                report["remaining_to_extract"] += 1
                continue
            processed += 1
            path = root / name
            try:
                # A path may have changed since inventory. Refuse symlink escapes.
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError("PDF now resolves outside selected folder")
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != (file["size_bytes"], file["mtime_ns"]):
                    raise ValueError("PDF changed since inventory; rerun pdf_inventory")
                status, pages, page_count = pdf_pages(path, executable)
                error = None
            except (OSError, ValueError, RuntimeError) as exc:
                status, pages, page_count, error = "failed", [], 0, str(exc)
                report["extraction_errors"] += 1
                if len(report["examples_of_errors"]) < 5:
                    report["examples_of_errors"].append({"file": name, "error": error})
            if status == "no_extractable_text":
                report["no_extractable_text"] += 1
            stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with db:
                # Never serve stale content from changed or failed PDF sources.
                db.execute(
                    "DELETE FROM pdf_text_pages WHERE root=? AND relpath=?",
                    (str(root), name),
                )
                db.executemany(
                    "INSERT INTO pdf_text_pages(root,relpath,page_num,text) VALUES(?,?,?,?)",
                    ((str(root), name, num, content) for num, content in pages),
                )
                db.execute(
                    """INSERT OR REPLACE INTO pdf_text_documents
                    (root,relpath,sha256,version,status,error,pages_total,
                     pages_with_text,extracted_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (str(root), name, file["sha256"], VERSION, status, error,
                     page_count, len(pages), stamp),
                )
            report["files_processed"] += 1
            report["page_records_added"] += len(pages)
        report["pdfs_in_inventory"] = len(files)
    return report

def search(database: Path, query: str, limit: int = 10):
    """Search raw page text; return local filenames, PDF pages, and literal excerpts."""
    if not 1 <= limit <= 50:
        raise ValueError("--limit must be 1-50")
    terms = list(dict.fromkeys(re.findall(r"[a-z0-9]{3,}", query.lower())))[:8]
    if not terms:
        raise ValueError("Provide a query containing at least one 3-letter word")
    conditions = " OR ".join("instr(lower(p.text),?)>0" for _ in terms)
    with closing(connect_existing(database)) as db:
        rows = db.execute(
            f"""SELECT p.root,p.relpath,p.page_num,p.text,
                        i.zotero_title,i.match_confidence
                  FROM pdf_text_pages p
                  JOIN pdf_files i ON i.root=p.root AND i.relpath=p.relpath
                  JOIN pdf_text_documents d ON d.root=p.root AND d.relpath=p.relpath
                  WHERE d.status='ok' AND d.sha256=i.sha256 AND ({conditions})""",
            terms,
        ).fetchall()
    ranked = []
    for row in rows:
        raw, lower = row["text"], row["text"].lower()
        frequency = sum(min(8, lower.count(term)) for term in terms)
        score = 10 * sum(term in lower for term in terms) + frequency
        pos = min(lower.index(term) for term in terms if term in lower)
        start = max(0, pos - 110)
        excerpt = re.sub(r"\s+", " ", raw[start:pos + 240]).strip()
        ranked.append((score, {
            "title": row["zotero_title"] or Path(row["relpath"]).stem,
            "root": row["root"], "file": row["relpath"],
            "pdf_page": row["page_num"],
            "zotero_match_confidence": row["match_confidence"],
            "excerpt": ("…" if start else "") + excerpt +
                       ("…" if pos + 240 < len(raw) else ""),
            "score": score,
        }))
    ranked.sort(key=lambda item: (-item[0], item[1]["file"], item[1]["pdf_page"]))
    return {
        "query": query, "pages_matched": len(rows),
        "results": [item for _, item in ranked[:limit]],
        "caution": "Raw extracted text; PDF pages are 1-based, not verified journal pagination.",
    }

def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only local PDF full-text indexing/search")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    commands = parser.add_subparsers(dest="command", required=True)
    indexing = commands.add_parser("extract")
    indexing.add_argument("folder", type=Path)
    indexing.add_argument("--limit", type=int)
    indexing.add_argument("--force", action="store_true")
    lookup = commands.add_parser("search")
    lookup.add_argument("query")
    lookup.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        output = (extract(args.folder, args.db, args.limit, args.force)
                  if args.command == "extract" else search(args.db, args.query, args.limit))
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"PDF text operation failed safely: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())

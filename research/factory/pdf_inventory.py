"""Read-only inventory of local PDFs, linked conservatively to Zotero metadata.

Writes only to the private SQLite index, never to the source PDF folders.
No network or LLM calls. Uses pdftotext if installed, otherwise scans filenames.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from difflib import SequenceMatcher
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

HOME = Path(__file__).resolve().parents[1]
DEFAULT_DB = HOME / "datasets" / "private" / "research_library.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pdf_files (
 root TEXT NOT NULL,
 relpath TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL,
 sha256 TEXT,
 text_status TEXT NOT NULL,
 zotero_uid TEXT,
 zotero_title TEXT,
 match_method TEXT NOT NULL,
 match_confidence TEXT NOT NULL,
 bibliography_version TEXT NOT NULL,
 error TEXT,
 last_scanned TEXT NOT NULL,
 PRIMARY KEY (root, relpath)
);
CREATE INDEX IF NOT EXISTS pdf_files_by_sha ON pdf_files(sha256);
CREATE INDEX IF NOT EXISTS pdf_files_by_zotero ON pdf_files(zotero_uid);
"""
DOI_RE = re.compile(r"(?i)\b10\.\d{4,9}/[-._;()/:A-Z0-9]+")


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_pages(path: Path, *, executable: str | None) -> tuple[str, str]:
    """Best-effort text for matching only; a failed extraction is not fabricated content."""
    if not executable:
        return "", "extractor_not_installed"
    try:
        result = subprocess.run(
            [executable, "-f", "1", "-l", "2", "-enc", "UTF-8", str(path), "-"],
            check=False, capture_output=True, text=True, errors="replace", timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "", "extraction_failed"
    if result.returncode != 0:
        return "", "extraction_failed"
    if len(result.stdout.strip()) < 40:
        return "", "no_extractable_text"
    return result.stdout[:12000], "text_available"


def read_references(conn: sqlite3.Connection) -> list[dict]:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone():
        raise ValueError("First import the Zotero JSON with python3 -m research.factory.library import ...")
    rows = conn.execute("SELECT uid, title, doi FROM documents WHERE source='zotero'").fetchall()
    if not rows:
        raise ValueError("Zotero bibliography is empty. First run the Zotero JSON import.")
    return [{"uid": uid, "title": title, "doi": str(doi or "").lower(),
             "norm": normalize(title)} for uid, title, doi in rows]


def bibliography_version(conn: sqlite3.Connection) -> str:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_files'").fetchone():
        row = conn.execute("SELECT sha256 FROM source_files WHERE kind='zotero_csl_json'").fetchone()
        if row:
            return row[0]
    return "unversioned"


def match_pdf(path: Path, preview: str, references: list[dict]) -> tuple[str | None, str | None, str, str]:
    """Require reliable DOI or clear title; ambiguous matches remain unverified."""
    doi_map: dict[str, list[dict]] = {}
    for record in references:
        if record["doi"]:
            doi_map.setdefault(record["doi"], []).append(record)
    for doi in DOI_RE.findall(preview[:12000]):
        doi = doi.lower().rstrip(".,;:)]}")
        entries = doi_map.get(doi)
        if entries:
            return entries[0]["uid"], entries[0]["title"], "first_pages_doi", "high"

    filename = normalize(path.stem)
    page_text = normalize(preview[:1700])
    scores = []
    for record in references:
        title = record["norm"]
        if len(title) < 18 or len(title.split()) < 3:
            continue
        if title in filename:
            score, method = 1.0, "filename_title"
        elif title in page_text:
            score, method = 0.98, "first_pages_title"
        else:
            similarity = SequenceMatcher(None, title, filename, autojunk=False).ratio()
            score, method = similarity, "filename_similarity"
        if score >= 0.68:
            scores.append((score, record, method))
    if not scores:
        return None, None, "unmatched", "none"
    scores.sort(key=lambda item: item[0], reverse=True)
    highest, record, method = scores[0]
    runner_up = scores[1][0] if len(scores) > 1 else 0.0
    if highest >= 0.9 and highest - runner_up >= 0.07:
        return record["uid"], record["title"], method, "high"
    if highest >= 0.78 and highest - runner_up >= 0.08:
        return record["uid"], record["title"], method, "possible"
    return None, None, "ambiguous_or_weak", "none"


def iter_pdfs(root: Path):
    """Never follow symbolic links to PDFs or directories outside the selected root."""
    for parent, subdirs, files in os.walk(root, followlinks=False,
                                           onerror=lambda error: (_ for _ in ()).throw(error)):
        subdirs[:] = sorted(d for d in subdirs if not (Path(parent) / d).is_symlink()
                            and d not in {".git", "__pycache__"})
        for name in sorted(files):
            if name.lower().endswith(".pdf"):
                path = Path(parent) / name
                if not path.is_symlink():
                    yield path


def scan(folder: Path, database: Path = DEFAULT_DB) -> dict:
    """Inventory and match PDFs; all writes are confined to the local DB."""
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"PDF location is not a directory: {root}")
    database = Path(database).expanduser()
    if not database.is_file():
        raise ValueError("Research SQLite index missing; first run research.factory.library import.")
    extractor = shutil.which("pdftotext")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(sqlite3.connect(database)) as conn:
        conn.executescript(SCHEMA)
        refs = read_references(conn)
        bib_version = bibliography_version(conn)
        seen = set()
        scanned = cached = errors = 0
        for path in iter_pdfs(root):
            relative = path.relative_to(root).as_posix()
            seen.add(relative)
            try:
                stat = path.stat()
                prior = conn.execute(
                    "SELECT size_bytes,mtime_ns,bibliography_version,text_status FROM pdf_files "
                    "WHERE root=? AND relpath=?", (str(root), relative)
                ).fetchone()
                if (prior and prior[:3] == (stat.st_size, stat.st_mtime_ns, bib_version)
                        and not (extractor and prior[3] == "extractor_not_installed")):
                    cached += 1
                    continue
                with path.open("rb") as file:
                    if file.read(5) != b"%PDF-":
                        raise ValueError("File has .pdf extension but lacks PDF header")
                fingerprint = sha256_file(path)
                preview, text_status = first_pages(path, executable=extractor)
                uid, title, method, confidence = match_pdf(path, preview, refs)
                error = None if text_status not in ("extraction_failed",) else "pdftotext could not extract text"
                conn.execute(
                    """INSERT OR REPLACE INTO pdf_files
                       (root,relpath,size_bytes,mtime_ns,sha256,text_status,zotero_uid,
                        zotero_title,match_method,match_confidence,bibliography_version,
                        error,last_scanned) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(root), relative, stat.st_size, stat.st_mtime_ns, fingerprint,
                     text_status, uid, title, method, confidence, bib_version, error, now),
                )
                scanned += 1
            except (OSError, ValueError) as exc:
                errors += 1
                conn.execute(
                    """INSERT OR REPLACE INTO pdf_files
                       (root,relpath,size_bytes,mtime_ns,sha256,text_status,zotero_uid,
                        zotero_title,match_method,match_confidence,bibliography_version,
                        error,last_scanned) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (str(root), relative, 0, 0, None, "failed", None, None,
                     "unreadable", "none", bib_version, str(exc), now),
                )
            conn.commit()
        existing = [r[0] for r in conn.execute("SELECT relpath FROM pdf_files WHERE root=?", (str(root),))]
        for relpath in existing:
            if relpath not in seen:
                conn.execute("DELETE FROM pdf_files WHERE root=? AND relpath=?", (str(root), relpath))
        conn.commit()
        data = conn.execute(
            "SELECT match_confidence,text_status,COUNT(*) FROM pdf_files WHERE root=? "
            "GROUP BY match_confidence,text_status", (str(root),)
        ).fetchall()
        total = sum(r[2] for r in data)
        unique_hashes = conn.execute(
            "SELECT COUNT(DISTINCT sha256) FROM pdf_files WHERE root=? AND sha256 IS NOT NULL",
            (str(root),),
        ).fetchone()[0]
        duplicates = conn.execute(
            "SELECT COUNT(*) FROM pdf_files WHERE root=? AND sha256 IS NOT NULL", (str(root),)
        ).fetchone()[0] - unique_hashes
        missing = conn.execute(
            "SELECT relpath FROM pdf_files WHERE root=? AND match_confidence='none' "
            "ORDER BY relpath LIMIT 8", (str(root),)
        ).fetchall()
        return {
            "root": str(root), "database": str(database), "pdfs": total,
            "new_or_changed": scanned, "cached_unchanged": cached, "scan_errors": errors,
            "high_confidence_zotero_matches": sum(r[2] for r in data if r[0] == "high"),
            "possible_zotero_matches_need_review": sum(r[2] for r in data if r[0] == "possible"),
            "unmatched_or_ambiguous": sum(r[2] for r in data if r[0] == "none"),
            "pdfs_with_extractable_text": sum(r[2] for r in data if r[1] == "text_available"),
            "exact_duplicate_files": duplicates,
            "pdftotext_installed": bool(extractor),
            "unmatched_examples": [r[0] for r in missing],
            "note": "Matches based on metadata, not full-text scientific verification",
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only local PDF inventory + Zotero matching")
    parser.add_argument("folder", type=Path, help="Directory to recursively scan")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)
    try:
        result = scan(args.folder, args.db)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"PDF inventory failed safely: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

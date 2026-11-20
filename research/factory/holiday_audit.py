"""Offline ACLED data-quality and directed-event audit for the holiday paper.

Reads only the private hash-verified JSONL pilot. Prints aggregate summaries,
and writes a local private annotation worksheet with source notes for human
direction coding. It NEVER decides that Actor1 is the aggressor or sends notes
to a model, GitHub, or the network.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

from .holiday_acled import ATTRIBUTION, OUT, checksum

PRIVATE_COLUMNS = (
    "event_id_cnty", "event_date", "time_precision", "event_type",
    "sub_event_type", "actor1", "actor2", "country", "admin1",
    "direction_status", "notes", "source",
    "reviewer_initiator", "reviewer_target", "reviewer_confidence",
    "reviewer_reason",
)


def nonempty(v):
    return v is not None and str(v).strip() != ""


def load_verified(manifest_path):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("queries", {})
    if not isinstance(entries, dict) or not entries:
        raise ValueError("No ACLED pilot query entries in manifest")
    reports, rows = [], []
    for key in sorted(entries):
        entry = entries[key]
        file = Path(entry["file"])
        # Prevent a misleading summary if the data were moved or changed.
        if file.parent.resolve() != manifest_path.parent.resolve():
            raise ValueError("Manifest points outside this private audit directory")
        if file.name != key or not file.is_file():
            raise ValueError("Missing or unexpected ACLED JSONL: " + key)
        if checksum(file) != entry.get("sha256"):
            raise ValueError("ACLED JSONL hash mismatch: " + key)
        from_file = []
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("ACLED row is not a dictionary: " + key)
                from_file.append(item)
        if len(from_file) != entry.get("rows"):
            raise ValueError("ACLED row count mismatch: " + key)
        rows.extend(from_file)
        reports.append({
            "file": key, "event_type": entry.get("event_type"),
            "rows": len(from_file),
            "exact_day_rows": sum(str(r.get("time_precision")) == "1" for r in from_file),
            "notes_present": sum(nonempty(r.get("notes")) for r in from_file),
            "source_present": sum(nonempty(r.get("source")) for r in from_file),
            "actor2_present": sum(nonempty(r.get("actor2")) for r in from_file),
            "direction_unknown": sum(r.get("direction_status") == "undetermined_requires_notes_review" for r in from_file),
            "subevents_top": Counter(str(r.get("sub_event_type") or "Missing")
                                     for r in from_file).most_common(8),
        })
    return reports, rows


def pick_review(rows, per_type=25):
    """Deterministic sample balanced by actor2 presence within each event type."""
    if not 1 <= per_type <= 200:
        raise ValueError("per-type must be between 1 and 200")
    buckets = defaultdict(list)
    for row in rows:
        if str(row.get("time_precision")) != "1":
            continue
        ty = str(row.get("event_type") or "")
        has_actor2 = nonempty(row.get("actor2"))
        buckets[(ty, has_actor2)].append(row)
    def rank(row):
        identifier = str(row.get("event_id_cnty") or "") + "|" + str(row.get("event_date") or "")
        return hashlib.sha256(identifier.encode("utf-8")).hexdigest()

    picked = []
    for ty in sorted({k[0] for k in buckets}):
        with_target = sorted(buckets.get((ty, True), []), key=rank)
        without_target = sorted(buckets.get((ty, False), []), key=rank)
        # Always reserve samples from both observed strata; fill remaining slots
        # with the global best-ranked leftovers (deterministic reproducibility).
        quota_target = min(len(with_target), per_type // 2)
        quota_without = min(len(without_target), per_type // 2)
        chosen = with_target[:quota_target] + without_target[:quota_without]
        extras = sorted(with_target[quota_target:] + without_target[quota_without:], key=rank)
        chosen += extras[:max(0, per_type - len(chosen))]
        picked.extend(chosen)
    return picked


def safe_csv_value(value):
    """Prevent spreadsheet formula injection from source-authored fields."""
    value = "" if value is None else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")):
        value = "'" + value
    return value


def write_private_review(path, selected, *, overwrite=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise ValueError("Review worksheet exists; refusing to overwrite human labels")
    import os
    import tempfile
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8",
                                         dir=path.parent, delete=False) as f:
            temp = Path(f.name)
            writer = csv.DictWriter(f, fieldnames=PRIVATE_COLUMNS)
            writer.writeheader()
            for row in selected:
                writer.writerow({
                    field: safe_csv_value(row.get(field, ""))
                    for field in PRIVATE_COLUMNS
                })
        os.chmod(temp, 0o600)
        temp.replace(path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def audit(manifest_path=OUT / "MANIFEST.json", *, per_type=25,
          create_review=False, review_path=None, overwrite=False):
    reports, rows = load_verified(manifest_path)
    pair_counts = Counter(
        (str(r.get("actor1") or "Missing"), str(r.get("actor2") or "Missing"))
        for r in rows
    )
    summary = {
        "status": "local_acled_direction_audit",
        "attribution": ATTRIBUTION,
        "manifest": str(manifest_path),
        "total_rows": len(rows),
        "file_quality": reports,
        "direction_coding_rule": (
            "Actor1 is not generally an initiator. Directed attacker-target "
            "assignments require notes/source verification."
        ),
        "actor_pairs_top": [
            {"actor1": a, "actor2": b, "events": count}
            for (a, b), count in pair_counts.most_common(15)
        ],
        "review_generated": False,
    }
    if create_review:
        path = Path(review_path) if review_path else Path(manifest_path).parent / "DIRECTION_REVIEW_PRIVATE.csv"
        selected = pick_review(rows, per_type=per_type)
        write_private_review(path, selected, overwrite=overwrite)
        summary["review_generated"] = True
        summary["review_file"] = str(path)
        summary["review_rows"] = len(selected)
        summary["instructions"] = (
            "Review notes/source locally, manually fill reviewer_initiator/target/"
            "confidence/reason. Never infer from actor order alone. Do not paste "
            "source notes or raw worksheet into ChatGPT/Claude without permission."
        )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline ACLED actor-direction quality audit")
    parser.add_argument("--manifest", type=Path, default=OUT / "MANIFEST.json")
    parser.add_argument("--review", action="store_true",
                        help="Create local private CSV for coding sampled source notes")
    parser.add_argument("--per-type", type=int, default=25)
    parser.add_argument("--review-path", type=Path)
    parser.add_argument("--overwrite-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = audit(args.manifest, per_type=args.per_type,
                       create_review=args.review, review_path=args.review_path,
                       overwrite=args.overwrite_review)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("ACLED audit stopped safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

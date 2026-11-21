"""Mandatory per-stage human review gates for the isolated Research Factory.

All actions are local, offline, and confined to research/projects/factory_runs.
Artifacts are copied into immutable-by-convention versioned snapshots; approval
is bound to their SHA256 and to upstream approval tokens. This is scientific
workflow governance, not a substitute for independent scientific verification.

Legacy stand-alone scripts remain callable; orchestrated work MUST call
require_ready() before producing a new stage and require_approved() for consuming
approved upstream artifacts. The guarded workflow never silently runs them.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import functools
import fcntl
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "research-factory-human-gates-v0.1"
PROJECT_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
STAGES = (
    "puzzle", "diagnosis", "literature", "novelty", "formal_model",
    "hypotheses", "data", "design", "analysis", "validation", "manuscript", "qc",
)
DEPS = {
    "puzzle": (),
    "diagnosis": ("puzzle",),
    "literature": ("diagnosis",),
    "novelty": ("literature",),
    "formal_model": ("novelty",),
    "hypotheses": ("formal_model",),
    "data": ("hypotheses",),
    "design": ("data", "hypotheses"),
    "analysis": ("design",),
    "validation": ("analysis",),
    "manuscript": ("validation", "literature", "formal_model"),
    "qc": ("manuscript",),
}
CHECKS = {
    "puzzle": "What is genuinely surprising? Are repeated cases independent? Could this be a coding or measurement error?",
    "diagnosis": "Are forecast-time sources actually historical? Were news and model assumptions knowable then? Have ordinary bugs been eliminated?",
    "literature": "Were original papers read and page-cited? Are competing explanations and contrary findings fairly represented?",
    "novelty": "Does the contribution survive an adversarial existing-theory comparison? Is the claimed gap specific and defensible?",
    "formal_model": "Are timing, information, payoffs, equilibrium existence, best responses, and derivations mathematically valid?",
    "hypotheses": "Are hypotheses derived from proved comparative statics rather than fitted to observed data? What would falsify them?",
    "data": "Are source access, units, dates, selection, license, missingness and measurements suitable? What data remain unavailable?",
    "design": "Are estimator, estimand, DAG/confounders, alternatives, leakage defenses and identification claims prespecified?",
    "analysis": "Do results reproduce from recorded inputs? Are diagnostics, robustness, nulls and uncertainty faithfully reported?",
    "validation": "Is the holdout genuinely future and unexamined? Are baselines fair and predictive improvements statistically defensible?",
    "manuscript": "Do text, tables, figures and citations match approved evidence, data and formal results? Does Overleaf compile?",
    "qc": "Has an independent reviewer checked claims, proofs, estimation, replication, citations and all remaining concerns?",
}
VALID_STATUS = {"not_started", "awaiting_critique", "awaiting_human_approval",
                "needs_revision", "approved", "rejected", "stale"}
RECOMMENDATIONS = {"approve", "revise", "reject"}
SEVERITIES = {"blocker", "major", "minor", "info"}
MAX_FILE_BYTES = 20_000_000
MAX_PROJECT_ARTIFACTS = 16


def time_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    hash_obj = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for data in iter(lambda: handle.read(1024 * 1024), b""):
            hash_obj.update(data)
    return hash_obj.hexdigest()


def atomic(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    fd, temp = tempfile.mkstemp(prefix=".workflow-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".workflow-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def safe_project(value):
    if not PROJECT_NAME.fullmatch(str(value)):
        raise ValueError("Project ID must be lowercase alphanumerics, dashes or underscores (1–64 chars)")
    return str(value)


def safe_stage(value):
    if value not in DEPS:
        raise ValueError("Unknown research stage: " + str(value))
    return value


def location(home, project):
    return (Path(home).expanduser().resolve() / "projects" / "factory_runs" /
            safe_project(project) / "human_gates")


def state_path(home, project):
    return location(home, project) / "state.json"


def load(home, project):
    path = state_path(home, project)
    if not path.is_file():
        raise ValueError(f"Unknown project: {project}. First run init.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("version") != VERSION or data.get("project") != project or
        set(data.get("stages", {})) != set(STAGES)):
        raise ValueError("Workflow state schema mismatch; refusing to continue")
    return data


def ensure_text(value, label, minimum=5, maximum=16000):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(f"{label} must be {minimum}–{maximum} non-whitespace characters")
    return value.strip()


@contextmanager
def mutation_lock(home, project):
    """Serialize state mutations across independent CLI invocations (macOS/Linux)."""
    directory = location(home, project)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".review_workflow.lock").open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def serialized(fn):
    @functools.wraps(fn)
    def call(home, project, *args, **kwargs):
        with mutation_lock(home, project):
            return fn(home, project, *args, **kwargs)
    return call


@serialized
def init(home, project, title):
    project = safe_project(project)
    title = ensure_text(title, "Title", 5, 220)
    file = state_path(home, project)
    if file.exists():
        state = load(home, project)
        return {"status": "existing_project_preserved", "project": project,
                "title": state["title"], "state_file": str(file)}
    state = {"version": VERSION, "project": project, "title": title,
             "created_utc": time_now(),
             "stages": {stage: {"status": "not_started", "revision": 0}
                        for stage in STAGES},
             "events": []}
    atomic(file, state)
    dashboard(home, project, state)
    return {"status": "initialized", "project": project, "state_file": str(file),
            "next_ready_stages": ["puzzle"], "network_or_paid_api_calls": 0}


def event(state, kind, stage, details):
    prev = state["events"][-1]["event_sha256"] if state["events"] else "GENESIS"
    rec = {"seq": len(state["events"]) + 1, "type": kind,
           "stage": stage, "at_utc": time_now(), "previous": prev, "details": details}
    rec["event_sha256"] = sha_bytes(canonical(rec).encode("utf-8"))
    state["events"].append(rec)


def validate_events(state):
    previous = "GENESIS"
    for i, e in enumerate(state["events"], 1):
        if e.get("seq") != i or e.get("previous") != previous:
            raise ValueError("Approval event history is inconsistent")
        d = dict(e)
        sha = d.pop("event_sha256", None)
        if sha != sha_bytes(canonical(d).encode("utf-8")):
            raise ValueError("Approval event hash mismatch")
        previous = sha


def artifacts_valid(home, project, record):
    base = location(home, project).resolve()
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return False
    for entry in artifacts:
        rel = entry.get("snapshot")
        if not isinstance(rel, str):
            return False
        file = base / rel
        if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(base):
            return False
        if file.stat().st_size != entry.get("bytes") or file_sha(file) != entry.get("sha256"):
            return False
    return True


def approved_token(home, state, stage):
    record = state["stages"][stage]
    if record["status"] != "approved":
        raise ValueError(f"Required stage {stage} is not currently approved")
    if not artifacts_valid(home, state["project"], record):
        raise ValueError(f"Approved snapshot for {stage} changed or is missing")
    approval = record.get("approval")
    if not isinstance(approval, dict) or not approval.get("token"):
        raise ValueError(f"Approval record missing for {stage}")
    if not critique_valid(home, state["project"], record):
        raise ValueError(f"Independently reviewed evidence for {stage} changed or is missing")
    decision = (location(home, state["project"]) / "decisions" / stage /
                f"rev{record['revision']:04d}_approval.json")
    if decision.is_symlink() or not decision.is_file():
        raise ValueError(f"Immutable human approval decision missing for {stage}")
    signed = json.loads(decision.read_text(encoding="utf-8"))
    signed_token = signed.pop("token", None)
    if (signed_token != approval["token"] or
        sha_bytes(canonical(signed).encode("utf-8")) != approval["token"] or
        signed["critic_sha256"] != approval["critic_sha256"] or
        signed["artifact_sha256"] != approval["artifact_sha256"] or
        signed["dependency_tokens"] != approval["dependencies"]):
        raise ValueError(f"Human approval decision for {stage} was altered")
    for upstream, expected in approval["dependencies"].items():
        if approved_token(home, state, upstream) != expected:
            raise ValueError(f"Approved stage {stage} is stale after {upstream} changed")
    return approval["token"]


def require_ready(home, project, stage):
    """Call this from any orchestrated stage runner BEFORE invoking an expensive worker."""
    stage = safe_stage(stage)
    state = load(home, safe_project(project))
    validate_events(state)
    entry = state["stages"][stage]
    if entry["status"] not in ("not_started", "needs_revision", "stale"):
        raise ValueError(f"Stage {stage} is {entry['status']}, not ready to produce work")
    for upstream in DEPS[stage]:
        approved_token(home, state, upstream)
    return state


def require_approved(home, project, stage):
    """Call this when a worker consumes an approved scientific upstream artifact."""
    state = load(home, safe_project(project))
    validate_events(state)
    return approved_token(home, state, safe_stage(stage))


def downstream(stage):
    todo = [stage]
    found = set()
    while todo:
        cur = todo.pop()
        for name, parents in DEPS.items():
            if cur in parents and name not in found:
                found.add(name)
                todo.append(name)
    return [s for s in STAGES if s in found]


def invalidate(state, changed):
    invalidated = []
    for stage in downstream(changed):
        record = state["stages"][stage]
        if record["status"] == "not_started":
            continue
        if record["status"] != "stale":
            record["status"] = "stale"
            record["stale_due_to"] = changed
            invalidated.append(stage)
    return invalidated


def persist(home, project, state):
    atomic(state_path(home, project), state)
    dashboard(home, project, state)


def ensure_regular_small(path):
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Artifact is not a regular file (or is symlink): {path}")
    size = path.stat().st_size
    if size <= 0 or size > MAX_FILE_BYTES:
        raise ValueError(f"Artifact must be 1–{MAX_FILE_BYTES} bytes: {path}")
    return path, size


@serialized
def submit(home, project, stage, files, summary):
    state = require_ready(home, project, stage)
    summary = ensure_text(summary, "Stage summary", 15, 16000)
    if not isinstance(files, (list, tuple)) or not 1 <= len(files) <= MAX_PROJECT_ARTIFACTS:
        raise ValueError("Provide 1–16 actual stage artifacts")
    names, prepared = set(), []
    stage_root = location(home, project)
    for source in files:
        p, size = ensure_regular_small(source)
        if p.name in names or p.name == "review.json":
            raise ValueError("Artifact filenames must be unique and not state.json or review.json")
        names.add(p.name)
        if stage_root in p.resolve().parents:
            raise ValueError("Do not submit a workflow snapshot as new source evidence")
        prepared.append((p, size, file_sha(p)))
    record = state["stages"][stage]
    rev = record.get("revision", 0) + 1
    target = stage_root / "snapshots" / stage / f"rev{rev:04d}"
    if target.exists():
        raise ValueError("Revision snapshot already exists; refusing to overwrite")
    upstream = {key: approved_token(home, state, key) for key in DEPS[stage]}
    target.mkdir(parents=True)
    snapshots = []
    for p, size, sha in prepared:
        copied = target / p.name
        shutil.copyfile(p, copied)
        if copied.stat().st_size != size or file_sha(copied) != sha:
            raise ValueError("Artifact changed during copy; stop and retry")
        copied.chmod(0o444)
        snapshots.append({"name": p.name,
                          "snapshot": str(copied.relative_to(stage_root)),
                          "sha256": sha, "bytes": size,
                          "original_source": str(p.resolve())})
    changed = invalidate(state, stage) if record.get("revision", 0) > 0 else []
    state["stages"][stage] = {"status": "awaiting_critique", "revision": rev,
                               "submitted_utc": time_now(), "summary": summary,
                               "artifacts": snapshots, "upstream_approval_tokens": upstream}
    event(state, "submitted", stage, {"revision": rev, "sha256": [e["sha256"] for e in snapshots],
                                      "invalidated": changed})
    persist(home, project, state)
    write_packet(home, project, stage, state)
    return {"status": "awaiting_critique", "project": project, "stage": stage,
            "revision": rev, "review_packet": str(packet_path(home, project, stage)),
            "invalidated_downstream": changed, "network_or_paid_api_calls": 0}


def check_critique(payload):
    if not isinstance(payload, dict):
        raise ValueError("Critique must be JSON object")
    for key, minimum in (("reviewer", 2), ("summary", 20)):
        value = ensure_text(payload.get(key), "Critique "+key, minimum, 16000)
        if "REPLACE" in value.upper() or "PLACEHOLDER" in value.upper():
            raise ValueError("Replace every independent-review template placeholder before submission")
    if payload.get("reviewer_kind") not in ("independent_ai", "independent_human"):
        raise ValueError("Critique reviewer_kind must be independent_ai or independent_human")
    if payload.get("recommendation") not in RECOMMENDATIONS:
        raise ValueError("Critique recommendation must be approve, revise or reject")
    issues = payload.get("issues")
    if not isinstance(issues, list) or len(issues) > 80:
        raise ValueError("Critique issues must be a list (0–80 entries)")
    for issue in issues:
        if not isinstance(issue, dict) or issue.get("severity") not in SEVERITIES:
            raise ValueError("Issue severity must be blocker, major, minor or info")
        for field, minimum in (("description", 10), ("suggested_fix", 5)):
            value = ensure_text(issue.get(field), "Issue " + field, minimum, 5000)
            if "REPLACE" in value.upper() or "PLACEHOLDER" in value.upper():
                raise ValueError("Replace independent-review issue template placeholders")
    if payload.get("recommendation") == "approve" and any(x["severity"] == "blocker" for x in issues):
        raise ValueError("Critique cannot recommend approve with unresolved blockers")
    return payload


@serialized
def critique(home, project, stage, report_path):
    stage = safe_stage(stage)
    state = load(home, safe_project(project))
    validate_events(state)
    rec = state["stages"][stage]
    if rec["status"] != "awaiting_critique":
        raise ValueError("Stage must be submitted and awaiting critique")
    if not artifacts_valid(home, project, rec):
        raise ValueError("Submitted artifact has changed or disappeared")
    p, _ = ensure_regular_small(report_path)
    supplied = check_critique(json.loads(p.read_text(encoding="utf-8")))
    sha = file_sha(p)
    record = {"reviewer": supplied["reviewer"].strip(),
              "reviewer_kind": supplied["reviewer_kind"],
              "recommendation": supplied["recommendation"],
              "summary": supplied["summary"].strip(),
              "issues": supplied["issues"], "strengths": supplied.get("strengths", []),
              "open_questions": supplied.get("open_questions", []),
              "estimated_cost_usd": supplied.get("estimated_cost_usd", None),
              "original_review_sha256": sha, "at_utc": time_now(),
              "reviewed_revision": rec["revision"],
              "reviewed_artifact_hashes": [x["sha256"] for x in rec["artifacts"]]}
    dest = location(home, project) / "reviews" / stage / f"rev{rec['revision']:04d}.json"
    if dest.exists():
        raise ValueError("Review snapshot already exists")
    atomic(dest, record)
    dest.chmod(0o444)
    rec["critique"] = {**record, "snapshot": str(dest.relative_to(location(home, project))),
                       "snapshot_sha256": file_sha(dest)}
    rec["status"] = "awaiting_human_approval"
    event(state, "independent_critique_received", stage,
          {"revision": rec["revision"], "recommendation": record["recommendation"],
           "critique_sha256": rec["critique"]["snapshot_sha256"]})
    persist(home, project, state)
    write_packet(home, project, stage, state)
    return {"status": "awaiting_human_approval", "stage": stage,
            "recommendation": record["recommendation"],
            "review_packet": str(packet_path(home, project, stage))}


def critique_valid(home, project, rec):
    c = rec.get("critique")
    if not isinstance(c, dict):
        return False
    dest = location(home, project) / c.get("snapshot", "")
    if dest.is_symlink() or not dest.is_file():
        return False
    return (file_sha(dest) == c.get("snapshot_sha256") and
            c.get("reviewed_revision") == rec.get("revision") and
            c.get("reviewed_artifact_hashes") == [x["sha256"] for x in rec["artifacts"]])


@serialized
def approve(home, project, stage, reviewer, notes, *, override=False):
    stage = safe_stage(stage)
    reviewer = ensure_text(reviewer, "Human signatory", 2, 200)
    notes = ensure_text(notes, "Human decision notes", 20, 16000)
    state = load(home, safe_project(project))
    validate_events(state)
    rec = state["stages"][stage]
    if rec["status"] != "awaiting_human_approval":
        raise ValueError("Stage has no independently critiqued work awaiting human approval")
    if not artifacts_valid(home, project, rec) or not critique_valid(home, project, rec):
        raise ValueError("Submitted evidence or independent review changed")
    c = rec["critique"]
    if reviewer.casefold() == c["reviewer"].casefold():
        raise ValueError("Human approval must be independent of critique authorship")
    blocked = (c["recommendation"] != "approve" or
               any(x["severity"] in ("blocker", "major") for x in c["issues"]))
    if blocked and not override:
        raise ValueError("Critic recommends revision/rejection or flags major concerns. Use revise, or explicit --override-critic with reason.")
    if blocked and (not override or len(notes) < 60):
        raise ValueError("Overriding scientific concerns requires 60+ characters explaining why")
    deps = {key: approved_token(home, state, key) for key in DEPS[stage]}
    if deps != rec.get("upstream_approval_tokens"):
        raise ValueError("Upstream scientific decisions changed since submission")
    hashes = [a["sha256"] for a in rec["artifacts"]]
    data = {"project": project, "stage": stage, "revision": rec["revision"],
            "artifact_sha256": hashes, "dependency_tokens": deps,
            "critic_sha256": c["snapshot_sha256"], "reviewer": reviewer,
            "notes": notes, "override": bool(override), "approved_utc": time_now()}
    token = sha_bytes(canonical(data).encode("utf-8"))
    rec["approval"] = {"token": token, "reviewer": reviewer, "notes": notes,
                       "approved_utc": data["approved_utc"],
                       "dependencies": deps, "critic_sha256": c["snapshot_sha256"],
                       "override": bool(override), "artifact_sha256": hashes}
    rec["status"] = "approved"
    event(state, "human_approved", stage,
          {"revision": rec["revision"], "approval_token": token, "reviewer": reviewer,
           "critic_override": bool(override)})
    decision_dir = location(home, project) / "decisions" / stage
    decision_dir.mkdir(parents=True, exist_ok=True)
    destination = decision_dir / f"rev{rec['revision']:04d}_approval.json"
    if destination.exists():
        raise ValueError("Immutable approval decision already exists")
    atomic(destination, data | {"token": token})
    destination.chmod(0o444)
    persist(home, project, state)
    write_packet(home, project, stage, state)
    return {"status": "approved", "stage": stage, "revision": rec["revision"],
            "approval_token": token, "ready_stages": ready_stages(home, project, state),
            "network_or_paid_api_calls": 0}


@serialized
def revise(home, project, stage, notes, *, reject=False):
    stage = safe_stage(stage)
    notes = ensure_text(notes, "Human revision/rejection reason", 20, 16000)
    state = load(home, safe_project(project))
    validate_events(state)
    rec = state["stages"][stage]
    if rec["status"] == "not_started":
        raise ValueError("No work at this stage to revise or reject")
    if rec["status"] == "rejected" and reject:
        raise ValueError("Already rejected")
    rec["status"] = "rejected" if reject else "needs_revision"
    rec["human_revision_notes"] = notes
    changed = invalidate(state, stage)
    event(state, "human_rejected" if reject else "human_requested_revision", stage,
          {"reason": notes, "invalidated": changed})
    persist(home, project, state)
    write_packet(home, project, stage, state)
    return {"status": rec["status"], "stage": stage,
            "invalidated_downstream": changed,
            "network_or_paid_api_calls": 0}


def ready_stages(home, project, state=None):
    state = state or load(home, project)
    ready = []
    for stage in STAGES:
        if state["stages"][stage]["status"] not in ("not_started", "needs_revision", "stale"):
            continue
        try:
            for parent in DEPS[stage]:
                approved_token(home, state, parent)
        except ValueError:
            continue
        ready.append(stage)
    return ready


def overview(home, project):
    state = load(home, safe_project(project))
    validate_events(state)
    steps = []
    for stage in STAGES:
        rec = state["stages"][stage]
        details = {"stage": stage, "status": rec["status"], "revision": rec["revision"],
                   "dependencies": DEPS[stage]}
        if rec["status"] == "approved":
            try:
                approved_token(home, state, stage)
                details["snapshot_integrity"] = "verified"
            except ValueError as exc:
                details["snapshot_integrity"] = "INVALID: " + str(exc)
        steps.append(details)
    return {"project": project, "title": state["title"],
            "ready_stages": ready_stages(home, project, state),
            "awaiting_human": [s["stage"] for s in steps if s["status"]=="awaiting_human_approval"],
            "awaiting_critique": [s["stage"] for s in steps if s["status"]=="awaiting_critique"],
            "stages": steps, "events": len(state["events"]),
            "network_or_paid_api_calls": 0}


def packet_path(home, project, stage):
    return location(home, project) / "review_packets" / (stage + ".md")


def write_packet(home, project, stage, state):
    rec = state["stages"][stage]
    c = rec.get("critique") or {}
    lines = [f"# Human review: {stage}", "",
             f"Project: **{state['title']}** (`{project}`)",
             f"Stage status: **{rec['status']}**, revision **{rec['revision']}**", "",
             "## Scientific decision checklist", "", CHECKS[stage], "",
             "## Submitted work", "", rec.get("summary", "No submitted artifacts yet"), ""]
    for a in rec.get("artifacts", []):
        lines.append(f"- `{a['name']}` — SHA256 `{a['sha256']}` ({a['bytes']} bytes)")
    lines += ["", "## Independent critic", "",
              c.get("summary", "**PENDING.** Independent critique required before human approval."),
              f"Recommendation: **{c.get('recommendation', 'not supplied')}**", ""]
    for issue in c.get("issues", []):
        lines.append(f"- **{issue['severity']}**: {issue['description']} → {issue['suggested_fix']}")
    if rec.get("human_revision_notes"):
        lines += ["", "## Requested changes", "", rec["human_revision_notes"]]
    if rec.get("approval"):
        lines += ["", "## Human sign-off", "",
                  f"Approved by {rec['approval']['reviewer']} on {rec['approval']['approved_utc']}.",
                  "Approval bound to this revision and its upstream SHA256 tokens."]
    lines += ["", "## Decision", "",
              "**APPROVE:** Only after independent review and satisfactory evidence.",
              "**REVISE:** Explain required changes, repair this stage, then resubmit.",
              "**REJECT:** Stop the branch; retain evidence and decision history.",
              "No downstream stage is released without this stage's valid human approval.", ""]
    atomic_text(packet_path(home, project, stage), "\n".join(lines))


def dashboard(home, project, state):
    folder = location(home, project)
    lines = [f"# Research Factory approval dashboard — {state['title']}", "",
             "Human sign-off is mandatory after every stage; nothing below authorizes auto-advancement.", "",
             "| Stage | Status | Revision | Depends on |", "|---|---|---:|---|"]
    for s in STAGES:
        r = state["stages"][s]
        lines.append(f"| {s} | {r['status']} | {r['revision']} | {', '.join(DEPS[s]) or '—'} |")
    lines += ["", "## Current actions", ""]
    awaiting = [s for s in STAGES if state["stages"][s]["status"] == "awaiting_human_approval"]
    if awaiting:
        lines.append("Awaiting your explicit approval, revision, or rejection: " + ", ".join(awaiting))
    for s in STAGES:
        if state["stages"][s]["status"] == "awaiting_critique":
            lines.append(f"- {s}: independent critic must submit a review report before your sign-off")
    lines.append("\nUse `python -m research.factory.review_workflow --help` to inspect and act.\n")
    atomic_text(folder / "PROJECT_DASHBOARD.md", "\n".join(lines))


def approved_sha_matches(home, project, stage, source):
    """Require an exact byte-for-byte match with frozen, approved stage artifacts."""
    state = load(home, safe_project(project))
    approved_token(home, state, safe_stage(stage))
    sha = file_sha(source)
    if sha not in {x["sha256"] for x in state["stages"][stage]["artifacts"]}:
        raise ValueError(f"Supplied {source} differs from approved {stage} artifact")
    return sha


def data_hash_from_approved_manifest(home, project):
    """A data approval freezes dataset bytes by hash, without copying licensed CSVs."""
    state = load(home, project)
    approved_token(home, state, "data")
    base = location(home, project)
    matching = []
    for a in state["stages"]["data"]["artifacts"]:
        if a["name"] != "data_manifest.json":
            continue
        manifest = json.loads((base / a["snapshot"]).read_text(encoding="utf-8"))
        value = manifest.get("data_sha256")
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
            raise ValueError("Approved data_manifest.json must contain data_sha256")
        matching.append(value)
    if len(matching) != 1:
        raise ValueError("Exactly one approved data_manifest.json is required")
    return matching[0]


def produce(home, project, stage, *, spec_file=None, model_file=None):
    """Guarded analysis or manuscript worker: run, then STOP at critique gate.

    Existing standalone CLIs remain accessible by design; use this guarded
    orchestrator for projects where human approval at each step is mandatory.
    No network, paid Claude or publishing operations are invoked.
    """
    if stage not in ("analysis", "manuscript"):
        raise ValueError("Only analysis and manuscript have guarded automated adapters")
    require_ready(home, project, stage)
    if spec_file is None:
        raise ValueError("--spec is required for guarded workers")
    spec_file = Path(spec_file).expanduser().resolve()
    approved_sha_matches(home, project, "design", spec_file)
    from . import prototype
    spec = prototype.validate_spec(prototype.read_json(spec_file))
    data_file = prototype.data_file(spec, spec_file)
    expected = data_hash_from_approved_manifest(home, project)
    if not data_file.is_file() or file_sha(data_file) != expected:
        raise ValueError("Dataset differs from human-approved data manifest; rerun data review")
    outputs = location(home, project).parent / "stage_outputs"
    if stage == "analysis":
        out = outputs / "analysis"
        result = prototype.run(spec_file, destination=out)
        if result.get("status") not in ("prototype_complete", "reused_cached_run"):
            raise ValueError("Empirical analysis stopped or failed: " + str(result.get("status")))
        files = [out / name for name in ("results.json", "QC_REPORT.json",
                                                "replication_manifest.json", "state.json")]
        submission = submit(home, project, stage, files,
                            "Python estimation and temporal validation results (exploratory); independent QC still required")
        return {**submission, "worker_status": result["status"], "output_directory": str(out)}
    if model_file is None:
        raise ValueError("--formal-model is required for manuscript generation")
    model_file = Path(model_file).expanduser().resolve()
    approved_sha_matches(home, project, "formal_model", model_file)
    # Frozen analysis outputs must agree with what the reviewer approved.
    analysis_dir = outputs / "analysis"
    state = load(home, project)
    approved_token(home, state, "analysis")
    frozen = {x["name"]: x["sha256"] for x in state["stages"]["analysis"]["artifacts"]}
    for name in ("results.json", "replication_manifest.json", "state.json", "QC_REPORT.json"):
        file = analysis_dir / name
        if not file.is_file() or file_sha(file) != frozen.get(name):
            raise ValueError(f"Analysis file {name} no longer matches approved results")
    from . import paper_sprint
    result = paper_sprint.run(spec_file, model_file, out=outputs / "manuscript", analysis_dir=analysis_dir)
    if result.get("status") != "overleaf_draft_created_NOT_submission_ready":
        raise ValueError("Paper packaging failed or did not produce an unreviewed draft")
    submission = submit(home, project, stage,
                        [Path(result["archive"]), Path(result["package_dir"]) / "PAPER_QC.json"],
                        "Overleaf draft, figures, bibliography and QA checklist; requires independent scientific and human review")
    return {**submission, "worker_status": result["status"], "archive": result["archive"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Research Factory immutable scientific review gates")
    parser.add_argument("--home", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    i = sub.add_parser("init"); i.add_argument("project"); i.add_argument("--title", required=True)
    s = sub.add_parser("status"); s.add_argument("project")
    r = sub.add_parser("submit"); r.add_argument("project"); r.add_argument("stage", choices=STAGES)
    r.add_argument("--artifact", action="append", type=Path, required=True)
    r.add_argument("--summary", required=True)
    c = sub.add_parser("critique"); c.add_argument("project"); c.add_argument("stage", choices=STAGES)
    c.add_argument("--report", type=Path, required=True)
    a = sub.add_parser("approve"); a.add_argument("project"); a.add_argument("stage", choices=STAGES)
    a.add_argument("--reviewer", required=True); a.add_argument("--notes", required=True)
    a.add_argument("--override-critic", action="store_true")
    for op in ("revise", "reject"):
        sp = sub.add_parser(op); sp.add_argument("project"); sp.add_argument("stage", choices=STAGES)
        sp.add_argument("--reason", required=True)
    pr = sub.add_parser("produce", help="Run guarded analysis/manuscript adapter, then stop at critique")
    pr.add_argument("project"); pr.add_argument("stage", choices=("analysis", "manuscript"))
    pr.add_argument("--spec", type=Path, required=True)
    pr.add_argument("--formal-model", type=Path)
    g = sub.add_parser("check"); g.add_argument("project"); g.add_argument("stage", choices=STAGES)
    g.add_argument("--approved", action="store_true", help="Validate completed approval instead of readiness")
    args = parser.parse_args(argv)
    try:
        if args.command == "init": output = init(args.home, args.project, args.title)
        elif args.command == "status": output = overview(args.home, args.project)
        elif args.command == "submit": output = submit(args.home, args.project, args.stage, args.artifact, args.summary)
        elif args.command == "critique": output = critique(args.home, args.project, args.stage, args.report)
        elif args.command == "approve": output = approve(args.home, args.project, args.stage,args.reviewer,args.notes,override=args.override_critic)
        elif args.command == "revise": output = revise(args.home, args.project, args.stage,args.reason)
        elif args.command == "reject": output = revise(args.home, args.project, args.stage,args.reason,reject=True)
        elif args.command == "produce": output = produce(args.home,args.project,args.stage,
                                                           spec_file=args.spec,model_file=args.formal_model)
        elif args.command == "check":
            val = require_approved(args.home,args.project,args.stage) if args.approved else require_ready(args.home,args.project,args.stage)
            output = {"status":"approved" if args.approved else "ready", "stage":args.stage,
                      "approval_token": val if args.approved else None}
        else: raise ValueError("Unknown command")
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("Human review gate stopped safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

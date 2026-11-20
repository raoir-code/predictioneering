"""Local research factory weekly runner and schedule generator.

Strictly research-only. The supplied inbox contains user-authored puzzle briefs,
not automatically interpreted work logs. Zero network or paid model calls.
Neither launchd installation nor live background scheduling is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import sys

from . import pipeline, prototype

ROOT = Path(__file__).resolve().parents[1]
VERSION = "research-factory-weekly-v0.1"


def timestamp():
    return datetime.now(timezone.utc)


def incoming(inbox, limit=100):
    """Inspect one explicitly supplied directory, never follow symlinks or recurse."""
    inbox = Path(inbox).expanduser().resolve()
    if not inbox.is_dir():
        raise ValueError(f"Inbox does not exist: {inbox}")
    if not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("--limit must be an integer between 1 and 500")
    items = []
    for p in sorted(inbox.iterdir(), key=lambda q: q.name):
        if len(items) >= limit:
            break
        if p.is_symlink() or not p.is_file():
            continue
        suffix = p.suffix.lower()
        if suffix not in (".json", ".md", ".txt"):
            continue
        stat = p.stat()
        if stat.st_size > 200000:
            items.append({"name": p.name, "status": "oversized_skipped"})
            continue
        raw = p.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if suffix == ".json":
            try:
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError("Expected a JSON object")
                fields = [obj.get("title") or obj.get("research_question"),
                          obj.get("research_question") or obj.get("why_puzzling"),
                          obj.get("mechanism") or obj.get("proposed_mechanism") or obj.get("candidate_mechanism"),
                          obj.get("testable_prediction")]
                if not fields[3] and isinstance(obj.get("hypotheses"), list) and obj["hypotheses"]:
                    item = obj["hypotheses"][0]
                    fields[3] = item.get("prediction") if isinstance(item, dict) else None
                ok = all(isinstance(f, str) and 3 <= len(f.strip()) <= 5000 for f in fields)
                status = "registerable_brief" if ok else "invalid_brief_requires_researcher"
            except (UnicodeDecodeError, ValueError, TypeError, KeyError):
                status = "invalid_json_requires_researcher"
        else:
            status = "unstructured_log_requires_researcher_or_opted_in_ai_intake"
        items.append({"name": p.name, "sha256": digest,
                      "bytes": len(raw), "status": status})
    return items


def inventory(home):
    home = Path(home).expanduser().resolve()
    cards = home / "projects"
    values = []
    for p in sorted(cards.glob("*.json")):
        if not pipeline.CARD_RE.fullmatch(p.stem) or p.is_symlink():
            continue
        try:
            c = pipeline.read(p)
            if c.get("id") != p.stem:
                continue
            s = pipeline.status(home, p.stem)
            values.append({"card_id": p.stem,"intake_status": c.get("status"),
                           "workflow_status": s.get("status")})
        except (ValueError, OSError, TypeError, KeyError):
            values.append({"card_id": p.stem, "intake_status":"invalid_card",
                           "workflow_status":"not_processed"})
    return values


def summarize(rows):
    counts={}
    for row in rows:
        key=row["workflow_status"]
        counts[key]=counts.get(key, 0)+1
    return dict(sorted(counts.items()))


def preview(home,inbox,limit=100):
    items=incoming(inbox,limit)
    current=inventory(home)
    return {"status":"dry_run_no_mutations","inbox":str(Path(inbox).expanduser().resolve()),
            "new_intake_candidates":sum(i["status"]=="registerable_brief" for i in items),
            "inbox_inventory":items,
            "projects":current,
            "workflow_counts":summarize(current),
            "paid_api_calls":0,"external_network_calls":0,
            "warning":"Unstructured worklogs cannot be converted into puzzles without a separate, explicitly authorized intake process."}


def execute(home,inbox,limit=100,db=None):
    """Register valid user-authored briefs, run local literature/analysis batch."""
    home=Path(home).expanduser().resolve()
    inbox=Path(inbox).expanduser().resolve()
    scan=incoming(inbox,limit)
    registration=[]
    for item in scan:
        if item["status"]!="registerable_brief":
            continue
        source=inbox/item["name"]
        try:
            result=pipeline.register(home,source)
            registration.append({"name":item["name"],"card_id":result["card_id"],
                                 "status":result["status"]})
        except (ValueError,OSError,KeyError,TypeError) as exc:
            registration.append({"name":item["name"],"status":"registration_failed_safe",
                                 "reason":type(exc).__name__})
    batch_result=pipeline.batch(home,db=db,limit=limit)
    current=inventory(home)
    stamp=timestamp()
    report={"status":"weekly_checkpoint_complete_with_human_gates",
            "version":VERSION,"generated_utc":stamp.isoformat(timespec="seconds"),
            "week":stamp.strftime("%G-W%V"),
            "inbox_file_count":len(scan),"registration":registration,
            "approved_projects_processed":batch_result["processed"],
            "project_advances":batch_result["projects"],
            "workflow_counts":summarize(current),
            "waiting_unstructured_log_count":sum(x["status"].startswith("unstructured") for x in scan),
            "paid_api_calls":0,"external_network_calls":0,
            "note":"Intake cards require explicit human approval; novelty and real data/model design gates are enforced by pipeline.run_one."}
    report_dir=home/"projects"/"factory_runs"/"weekly"
    report_dir.mkdir(parents=True,exist_ok=True)
    file=report_dir/("weekly_"+stamp.strftime("%G-W%V")+".json")
    prototype.write_json(file,report)
    report["report_file"]=str(file)
    return report


def make_launchd(home,inbox,*,python=None,weekday=1,hour=9,minute=0,db=None):
    """Generate launchd definition only. Do NOT install, load, or execute it."""
    home=Path(home).expanduser().resolve()
    inbox=Path(inbox).expanduser().resolve()
    if not inbox.is_dir():
        raise ValueError("Inbox must already exist")
    if not (1 <= weekday <= 7 and 0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Invalid weekday/hour/minute")
    exe=Path(python or sys.executable).expanduser().resolve()
    args=[str(exe),"-m","research.factory.weekly","--home",str(home),
          "run","--inbox",str(inbox),"--execute"]
    if db is not None:
        args.extend(["--db",str(Path(db).expanduser().resolve())])
    folder=home/"projects"/"factory_runs"/"weekly"
    folder.mkdir(parents=True,exist_ok=True)
    definition={"Label":"org.predictioneering.research-factory-weekly",
                "ProgramArguments":args,
                "WorkingDirectory":str(home.parent),
                "StartCalendarInterval":{"Weekday":weekday,"Hour":hour,"Minute":minute},
                "StandardOutPath":str(folder/"launchd_stdout.log"),
                "StandardErrorPath":str(folder/"launchd_stderr.log"),
                "RunAtLoad":False}
    target=folder/"org.predictioneering.research-factory-weekly.plist"
    target.write_bytes(plistlib.dumps(definition))
    return {"status":"schedule_file_generated_not_installed",
            "plist_file":str(target),"schedule":"Mon 09:00 local" if (weekday,hour,minute)==(1,9,0) else f"weekday={weekday} {hour:02d}:{minute:02d} local",
            "requires_user_review_and_manual_launchd_install":True,
            "paid_api_calls":0,"network_calls":0}


def main(argv=None):
    p=argparse.ArgumentParser(description="Local weekly Research Factory operations")
    p.add_argument("--home",type=Path,default=ROOT)
    subs=p.add_subparsers(dest="command",required=True)
    for name in ("plan","run","make-launchd"):
        sp=subs.add_parser(name)
        sp.add_argument("--inbox",type=Path,required=True)
        if name!="make-launchd":
            sp.add_argument("--limit",type=int,default=100)
        if name in ("run","make-launchd"):
            sp.add_argument("--db",type=Path)
        if name=="run":
            sp.add_argument("--execute",action="store_true")
        if name=="make-launchd":
            sp.add_argument("--python",type=Path)
            sp.add_argument("--weekday",type=int,default=1)
            sp.add_argument("--hour",type=int,default=9)
            sp.add_argument("--minute",type=int,default=0)
    subs.add_parser("status")
    args=p.parse_args(argv)
    try:
        if args.command=="status":
            cards=inventory(args.home)
            result={"status":"local_factory_status","projects":cards,
                    "workflow_counts":summarize(cards),"network_or_paid_api_calls":0}
        elif args.command=="plan" or (args.command=="run" and not args.execute):
            result=preview(args.home,args.inbox,args.limit)
        elif args.command=="run":
            result=execute(args.home,args.inbox,args.limit,args.db)
        else:
            result=make_launchd(args.home,args.inbox,python=args.python,
                                weekday=args.weekday,hour=args.hour,minute=args.minute,db=args.db)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print("Weekly factory stopped safely: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())

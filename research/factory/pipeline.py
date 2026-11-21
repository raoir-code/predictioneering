"""One-command research-only orchestration: approved puzzle -> guarded paper draft.

Uses the existing puzzle intake card, LOCAL literature metadata index, and
prototype statistical/manuscript runner. No Anthropic, OpenAlex, ACLED or other
external calls. No source content is silently sent to any third party.

Human approvals and real data/analysis decisions are NEVER synthesized. The
pipeline stops at explicit gates rather than inventing citations or methods.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from . import prototype

HOME = Path(__file__).resolve().parents[1]
CARD_RE = re.compile(r"^[0-9a-f]{16}$")
VERSION = "research-factory-orchestrator-0.1"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_card_id(value):
    if not CARD_RE.fullmatch(str(value)):
        raise ValueError("Use a 16-character ID produced by puzzle intake")
    return str(value)


def folder(home, card_id):
    return Path(home).expanduser().resolve()/"projects"/"factory_runs"/("p"+safe_card_id(card_id))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, obj):
    prototype.write_json(Path(path),obj)


def card_path(home, card_id):
    return Path(home).expanduser().resolve()/"projects"/(safe_card_id(card_id)+".json")


def register(home,source_path):
    """Import a researcher-written puzzle without an AI API call or automatic approval."""
    home=Path(home).expanduser().resolve()
    source=Path(source_path).expanduser().resolve()
    raw=source.read_bytes()
    if len(raw)>200_000:
        raise ValueError("Puzzle input exceeds 200 KB; summarize it in a JSON study brief")
    value=json.loads(raw)
    if not isinstance(value,dict):
        raise ValueError("Puzzle study brief must be a JSON object")
    title=value.get("title") or value.get("research_question")
    question=value.get("research_question") or value.get("why_puzzling")
    competing=value.get("competing_intuitions")
    mechanism=(value.get("candidate_mechanism") or value.get("proposed_mechanism")
               or value.get("mechanism"))
    hypotheses=value.get("hypotheses")
    first=(hypotheses[0].get("prediction") if isinstance(hypotheses,list)
           and hypotheses and isinstance(hypotheses[0],dict) else None)
    prediction=value.get("testable_prediction") or first
    # Conceptual puzzles can be registered before a mechanism/H1/data exist.
    # Older researcher-authored study briefs remain valid for compatibility.
    if not all(isinstance(x,str) and 3<=len(x.strip())<=5000
               for x in (title,question)):
        raise ValueError("Supply a title and research_question")
    if not (isinstance(competing,str) and len(competing.strip())>=10
            or (isinstance(mechanism,str) and len(mechanism.strip())>=3
                and isinstance(prediction,str) and len(prediction.strip())>=3)):
        raise ValueError("Supply competing_intuitions for a conceptual puzzle, or a legacy mechanism and testable prediction")
    ident=hashlib.sha256(raw).hexdigest()[:16]
    card={"id":ident,"title":title.strip(),"phenomenon":str(value.get("phenomenon") or question).strip(),
          "expected_theory":str(value.get("expected_theory") or ""),
          "why_puzzling":question.strip(),
          "competing_intuitions":str(competing or "").strip() or (
              "Prior proposed mechanism: "+str(mechanism)),
          "why_worth_investigating":str(value.get("why_worth_investigating") or "For subsequent diagnosis"),
          "candidate_mechanism":str(mechanism or "").strip(),
          "testable_prediction":str(prediction or "").strip(),
          "potential_data":str(value.get("potential_data") or ""),
          "forecasting_benefit":str(value.get("forecasting_benefit") or ""),
          "source_excerpt":"","source_quote_verified":False,
          "status":"pending_human_review","novelty":"not_yet_checked",
          "evidence":"candidate_not_finding","source_kind":"researcher_supplied_study_brief",
          "source_hash":hashlib.sha256(raw).hexdigest(),"created":now()}
    dest=card_path(home,ident)
    if dest.is_file():
        existing=read(dest)
        if existing.get("source_hash")!=card["source_hash"]:
            raise ValueError("Hash collision with different existing intake card")
        return {"status":existing.get("status"),"card_id":ident,
                "next_action":"Existing card preserved. Use existing intake show/approve as appropriate."}
    save(dest,card)
    return {"status":"pending_human_review","card_id":ident,
            "card_file":str(dest),
            "next_action":f"Review and approve: python -m research.factory approve {ident}",
            "network_or_paid_api_calls":0}


def approved_card(home, card_id):
    path=card_path(home, card_id)
    if not path.is_file():
        raise ValueError("No intake card with this ID: "+str(path))
    card=read(path)
    if card.get("id")!=card_id or card.get("status")!="approved_for_literature_review":
        raise ValueError("Puzzle must first pass existing human intake approval")
    if not all(isinstance(card.get(k),str) and card[k].strip() for k in
               ("title","phenomenon","why_puzzling")):
        raise ValueError("Approved puzzle is missing required original fields")
    return card,digest(path)


def project_title(card):
    return card["title"].strip()[:180]


def research_question(card):
    return card.get("why_puzzling") or card.get("title")


def query_suggestions(card):
    # Exact user-approved source language, not invented literature claims.
    phrases=[card.get("title",""),card.get("phenomenon",""),
             card.get("expected_theory",""),card.get("candidate_mechanism","")]
    queries=[]
    for phrase in phrases:
        phrase=re.sub(r"\s+"," ",str(phrase)).strip()[:120]
        if len(phrase)>=3 and phrase not in queries:
            queries.append(phrase)
        if len(queries)==4:
            break
    return queries


def initial_spec(card, card_id):
    # Invalid analysis columns intentionally force real researcher design choices.
    return {
        "id":"p"+card_id,
        "title":project_title(card),
        "research_question":research_question(card),
        "mechanism":card.get("candidate_mechanism") or "",
        "hypotheses":([{"id":"H1","prediction":card.get("testable_prediction") or "Not yet formulated",
                       "sign":"unspecified"}] if card.get("testable_prediction") else []),
        "data":{"csv_path":"SET_PRIVATE_DATA_CSV_PATH.csv",
                "redistribution_allowed":False,"synthetic":False},
        "design":{"method":None,"family":None,"outcome":None,
                  "treatment":None,"time":None,"unit":None,
                  "controls":[],"fixed_effects":[],"cluster":None,
                  "holdout_fraction":0.25},
        "literature":[],"novelty_review":{"status":"pending"},
    }


def theory_design_worksheet(card):
    lines=["# Theory and design candidates (NOT a solved or approved model)","",
        "This is a deterministic first draft extracted from a human-approved puzzle card.",
        "No empirical sign, causal design, or equilibrium has been established.","",
        "## Research puzzle", research_question(card),"",
        "## What existing theory led us to expect",card.get("expected_theory") or "Unspecified", "",
        "## Proposed mechanism",card.get("candidate_mechanism") or "Not yet formulated","",
        "## Hypotheses (not required at Puzzle stage)",card.get("testable_prediction") or "Not yet formulated","",
        "## Formalization obligations","",
        "- Define players, action sets, timing, observable state, and information sets.",
        "- Write coherent payoffs/outside options; solve or state why solution is not yet obtained.",
        "- Derive comparative statics and counterexamples; distinguish equilibrium from intuition.",
        "- Specify falsifiers and rival mechanisms; do not infer novelty from metadata.","",
        "## Research-design choice (requires researcher input)","",
        "- Association: specify treatment/outcome/time, measurement, confounders and clusters.",
        "- DiD: additionally provide treated unit and post indicator; assess anticipation/parallel trends.",
        "- RDD: provide running variable, cutoff and bandwidth; assess manipulation/continuity.",
        "- Choose outcome family (gaussian, binomial, poisson), validate dataset columns.",
        "- Define the estimation sample, predictive target, leakage risks and OOS split.",
        "- State which interventions are plausibly exogenous and which remain correlational.","",
        "Edit analysis_spec.json only after reading the literature candidate file.",
        "The pipeline never converts this worksheet into an approved causal design automatically.",""]
    return "\n".join(lines)


def literature_spec(card, card_id):
    return {"id":"p"+card_id,"research_question":research_question(card),
            "proposed_mechanism":card.get("candidate_mechanism") or "",
            "search_queries":query_suggestions(card)}


def initialize(home,card_id):
    home=Path(home).expanduser().resolve()
    card,sha=approved_card(home,card_id)
    place=folder(home,card_id)
    record=place/"workflow.json"
    if record.exists():
        existing=read(record)
        if existing.get("card_sha256")!=sha:
            raise ValueError("Approved source card changed. Archive this run and start a new puzzle card; prior novelty review cannot be inherited.")
        return place,existing,card
    place.mkdir(parents=True,exist_ok=True)
    save(place/"analysis_spec.json",initial_spec(card,card_id))
    save(place/"literature_spec.json",literature_spec(card,card_id))
    prototype.atomic_text(place/"theory_design_candidates.md",theory_design_worksheet(card))
    state={"version":VERSION,"card_id":card_id,"study_id":"p"+card_id,
           "card_sha256":sha,"created_utc":now(),"status":"initialized",
           "history":[{"stage":"initialized","at":now()}],
           "network_or_paid_api_calls":0,
           "sources_are_metadata_candidates_only":True}
    save(record,state)
    return place,state,card


def mark(place,state,status,reason=None,**fields):
    new={**state,"status":status,"updated_utc":now(),**fields}
    if reason:
        new["next_action"]=reason
    if state.get("status")!=status or state.get("next_action")!=reason:
        new["history"]=(state.get("history",[])+[{"stage":status,"at":now()}])[-50:]
    save(place/"workflow.json",new)
    return new


def retrieve_local(db,spec_path,home):
    """Same local Zotero/hazard index as existing library_review; no web, no LLM."""
    from .library_review import run as run_library_review
    return run_library_review(spec_path,db_path=db,home=home,
                              external=False,retrieve_only=True)


def ensure_literature(place,home,db,refresh=False):
    path=place/"literature_candidates.json"
    if path.is_file() and not refresh:
        return read(path)
    if not Path(db).expanduser().is_file():
        return None
    bundle=retrieve_local(Path(db).expanduser(),place/"literature_spec.json",home)
    # Never store abstracts or raw quoted source notes in public Github.
    result={"status":"unverified_metadata_not_novelty",
            "sources":bundle.get("sources",[]),
            "hazard_matches":bundle.get("hazard_matches",[]),
            "queries":bundle.get("queries",[]),
            "source_count":len(bundle.get("sources",[])),
            "full_text_verified":False,
            "external_network_queries":0,"created_utc":now()}
    save(path,result)
    return result


def review_ok(place,state,spec):
    review_path=place/"novelty_approval.json"
    if not review_path.is_file():return False
    review=read(review_path)
    if review.get("card_sha256")!=state["card_sha256"]:return False
    if review.get("status")!="human_approved_full_text":return False
    r=spec.get("novelty_review",{})
    if r.get("status")!="approved" or r.get("reviewer")!=review.get("reviewer") or r.get("notes")!=review.get("notes"):
        return False
    scope={k:spec.get(k) for k in ("research_question","mechanism","hypotheses")}
    if review.get("reviewed_research_scope")!=scope:
        return False
    candidates=place/"literature_candidates.json"
    if not candidates.is_file():return False
    ids={x.get("id") for x in read(candidates).get("sources",[])}
    if not set(review.get("source_ids",[])).issubset(ids):return False
    return True


def approve(home,card_id,reviewer,notes,source_ids,*,confirmed=False):
    place,state,_=initialize(home,card_id)
    if not confirmed:
        raise ValueError("Explicit --full-text-checked required; model metadata is not a novelty review")
    reviewer=reviewer.strip();notes=notes.strip()
    if len(reviewer)<2 or len(notes)<40:
        raise ValueError("Provide reviewer identity and substantive novelty notes (40+ characters)")
    available=place/"literature_candidates.json"
    if not available.exists():
        raise ValueError("First run pipeline run to retrieve candidate sources")
    bundle=read(available)
    mapping={x["id"]:x for x in bundle.get("sources",[]) if isinstance(x.get("id"),str)}
    ids=list(dict.fromkeys(source_ids))
    if not ids or not all(x in mapping for x in ids):
        raise ValueError("Source IDs must be from literature_candidates.json; at least one checked paper required")
    spec_path=place/"analysis_spec.json"
    spec=read(spec_path)
    if spec.get("novelty_review",{}).get("status")=="approved":
        previous=read(place/"novelty_approval.json")
        if previous.get("reviewer")==reviewer and previous.get("notes")==notes and previous.get("source_ids")==ids:
            return {"status":"previous_human_review_preserved","project":str(place)}
        raise ValueError("An approval already exists: revise with a new intake card, do not silently overwrite")
    record={"status":"human_approved_full_text","reviewer":reviewer,
            "notes":notes,"source_ids":ids,
            "reviewer_asserted_original_papers_read":True,
            "reviewed_research_scope":{k:spec.get(k) for k in
                                       ("research_question","mechanism","hypotheses")},
            "card_sha256":state["card_sha256"],"at":now(),
            "caution":"User attestation, not machine verification of full text or novelty"}
    citations=[]
    for sid in ids:
        src=mapping[sid]
        citations.append({k:src[k] for k in ("title","authors","year","doi","url") if src.get(k) is not None})
    spec["novelty_review"]={"status":"approved","reviewer":reviewer,"notes":notes}
    spec["literature"]=citations
    # Both files are private and gitignored. A partial write fails closed on run.
    save(place/"novelty_approval.json",record)
    save(spec_path,spec)
    mark(place,state,"novelty_approved","Fill analysis_spec.json design and private CSV before rerunning")
    return {"status":"human_novelty_approved","project":str(place),
            "human_reviewed_source_ids":ids}


def run_one(home,card_id,db=None,refresh_literature=False):
    place,state,card=initialize(home,card_id)
    if db is None:
        from .library import DEFAULT_DB
        db=DEFAULT_DB
    literature=ensure_literature(place,home,db,refresh_literature)
    if literature is None:
        state=mark(place,state,"blocked_missing_library",
                   "Import the Zotero research index locally or supply an existing indexed DB via --db")
        return report(place,state)
    if not literature.get("sources"):
        state=mark(place,state,"blocked_no_literature_candidates",
                   "Revise literature search terms; cannot approve novelty with zero source records")
        return report(place,state)
    spec_path=place/"analysis_spec.json"
    spec=read(spec_path)
    if not review_ok(place,state,spec):
        state=mark(place,state,"blocked_human_novelty_review",
                   "Read originals, then use pipeline approve --full-text-checked with source IDs and notes")
        return report(place,state)
    try:
        validated=prototype.validate_spec(spec)
    except (ValueError,TypeError) as exc:
        state=mark(place,state,"blocked_design_spec",
                   "Complete analysis_spec.json: "+str(exc)[:280])
        return report(place,state)
    research_data=prototype.data_file(validated,spec_path)
    if not research_data.is_file():
        state=mark(place,state,"blocked_data_missing",
                   "Provide an existing, local private CSV at data.csv_path")
        return report(place,state)
    state=mark(place,state,"analysis_running","Executing cached statistics and manuscript prototype")
    try:
        result=prototype.run(spec_path,destination=place/"output")
    except Exception as exc:
        state=mark(place,state,"analysis_failed_retryable",
                   "Correct the data/spec issue and rerun: "+type(exc).__name__+": "+str(exc)[:200])
        return report(place,state)
    if result.get("status") not in ("prototype_complete","reused_cached_run"):
        state=mark(place,state,"analysis_blocked",str(result.get("plan",{}).get("blockers",[])))
    else:
        state=mark(place,state,"draft_generated_not_publication_ready",
                   "Inspect QC_REPORT.json, verify theory/identification and review draft before submission",
                   artifact_directory=str(place/"output"))
    summary=report(place,state)
    summary["analysis_status"]=result.get("status")
    return summary


def report(place,state):
    return {"status":state.get("status"),"study_id":state.get("study_id"),
            "project":str(place),"next_action":state.get("next_action"),
            "has_literature_candidates":(place/"literature_candidates.json").is_file(),
            "has_human_novelty_review":(place/"novelty_approval.json").is_file(),
            "has_analysis_results":(place/"output"/"results.json").is_file(),
            "network_or_paid_api_calls":0}


def batch(home,db=None,limit=30):
    """Advance every intake-approved puzzle to its next gate, deterministically."""
    if not 1<=limit<=100:
        raise ValueError("Batch limit must be between 1 and 100")
    cards=sorted((Path(home).expanduser().resolve()/"projects").glob("*.json"))
    results=[]
    for card_file in cards:
        if len(results)>=limit:break
        if not CARD_RE.fullmatch(card_file.stem):continue
        try:
            card=read(card_file)
            if card.get("status")!="approved_for_literature_review":continue
            res=run_one(home,card_file.stem,db)
            results.append({"card_id":card_file.stem,"status":res["status"],
                            "next_action":res.get("next_action")})
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as exc:
            results.append({"card_id":card_file.stem,"status":"failed_safe",
                            "error":type(exc).__name__+": "+str(exc)[:150]})
    return {"status":"batch_completed_with_human_gates",
            "processed":len(results),"projects":results,
            "network_or_paid_api_calls":0}


def status(home,card_id):
    place=folder(home,card_id)
    record=place/"workflow.json"
    if not record.is_file():
        return {"status":"not_started","study_id":"p"+card_id}
    return report(place,read(record))


def demo(home):
    """Exercise intake-to-manuscript adapter on synthetic data; no novelty shortcut for real data."""
    home=Path(home).expanduser().resolve()
    # Demo card is intentionally outside actual intake inventory.
    place=home/"projects"/"factory_runs"/"factory_pipeline_demo"
    place.mkdir(parents=True,exist_ok=True)
    demo_spec_file=prototype.make_demo(place/"seed")
    synthetic=read(demo_spec_file)
    synthetic["id"]="factory_pipeline_demo"
    synthetic["title"]="Factory pipeline synthetic intake-to-manuscript demonstration"
    synthetic["research_question"]="Does a seeded synthetic treatment predict synthetic outcomes?"
    synthetic["mechanism"]="A simulated treatment-effect mechanism, not IR evidence."
    synthetic["data"]["csv_path"]=str(prototype.data_file(read(demo_spec_file),demo_spec_file))
    synthetic["novelty_review"]={"status":"demo_only"}
    spec_path=place/"analysis_spec.json"
    save(spec_path,synthetic)
    prototype.atomic_text(place/"theory_design_candidates.md",
                          "# Intake-to-theory integration (synthetic only)\n\nNo scientific claims.\n")
    save(place/"literature_candidates.json",{"sources":[],"source_count":0,
        "status":"demo_only_no_novelty_review"})
    result=prototype.run(spec_path,destination=place/"output")
    return {"status":"synthetic_pipeline_demonstration_complete",
            "stage":"intake -> draft theory -> placeholder literature -> reviewed synthetic design -> estimate -> oos -> manuscript",
            "prototype_status":result["status"],"project":str(place),
            "quality":result.get("quality"),"synthetic_only":True,
            "network_or_paid_api_calls":0}


def main(argv=None):
    p=argparse.ArgumentParser(description="Research Factory orchestration (local, approval-gated)")
    p.add_argument("--home",type=Path,default=HOME,
                   help="Root research directory (existing intake cards under projects/)")
    sub=p.add_subparsers(dest="command",required=True)
    reg=sub.add_parser("register",help="Import researcher-written JSON puzzle without LLM or approval")
    reg.add_argument("file",type=Path)
    r=sub.add_parser("run",help="Initialize, gather local literature and resume after gates")
    r.add_argument("card_id",help="16-character approved puzzle ID")
    r.add_argument("--db",type=Path,help="Existing local Zotero/estimate index")
    r.add_argument("--refresh-literature",action="store_true")
    a=sub.add_parser("approve",help="Record actual human full-text novelty approval")
    a.add_argument("card_id")
    a.add_argument("--reviewer",required=True)
    a.add_argument("--notes",required=True)
    a.add_argument("--source-id",action="append",required=True,
                   help="Exact source ID in literature_candidates.json; may repeat")
    a.add_argument("--full-text-checked",action="store_true",
                   help="Human asserts original papers read; not auto-verified")
    s=sub.add_parser("status");s.add_argument("card_id")
    b=sub.add_parser("batch",help="Advance all approved intake cards to their next gate")
    b.add_argument("--db",type=Path)
    b.add_argument("--limit",type=int,default=30)
    sub.add_parser("demo",help="Fully synthetic integration demo, no API calls")
    args=p.parse_args(argv)
    try:
        if args.command=="register":
            result=register(args.home,args.file)
        elif args.command=="run":
            result=run_one(args.home,safe_card_id(args.card_id),args.db,args.refresh_literature)
        elif args.command=="approve":
            result=approve(args.home,safe_card_id(args.card_id),args.reviewer,
                           args.notes,args.source_id,confirmed=args.full_text_checked)
        elif args.command=="status":
            result=status(args.home,safe_card_id(args.card_id))
        elif args.command=="batch":
            result=batch(args.home,args.db,args.limit)
        else:
            result=demo(args.home)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as exc:
        print("Factory pipeline stopped safely: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())

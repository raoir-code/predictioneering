"""Research-only first-stage workers behind mandatory human-review gates.

Puzzle evidence comes from specified local source documents, not invented event
facts. Literature retrieval uses page-checked local PDF profiles, never guesses
at novelty. No network, paid API, production writes, or automatic approvals.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = "research-factory-scientific-stage-starter-v0.1"
HOLY_DAYS = (
    "examples/holy_days_repeated_bargaining_model_v0.md",
    "HOLIDAY_FAST_START.md",
)


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_document(path, root=ROOT):
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError("Source must be an existing regular file, not a symlink")
    data = path.read_bytes()
    if not data or len(data) > 500_000:
        raise ValueError("Source must contain 1–500000 bytes")
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Source document must be UTF-8") from exc
    return {"path":str(path.resolve()),"sha256":hashlib.sha256(data).hexdigest(),
            "size":len(data), "text":content}


def atomically_save(path, value):
    """Never publish raw source extracts; path must be beneath ignored local inbox."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+".tmp")
    tmp.write_text(value, encoding="utf-8")
    tmp.replace(path)


def relpath(path, root):
    p = Path(path).resolve()
    try:
        return str(p.relative_to(Path(root).resolve()))
    except ValueError:
        return "external_local_source:"+p.name


def excerpt(lines, needle, *, max_chars=480):
    for i,line in enumerate(lines,1):
        if needle in re.sub(r"[*_`]+", "", line.lower()):
            return {"line":i,"text":line.strip()[:max_chars]}
    return None


def source_registry(docs, root):
    entries=[]
    for i,d in enumerate(docs,1):
        entries.append({"id":f"LOCAL-{i}","source_type":"research_note_not_independent_literature",
                        "path":relpath(d["path"],root),"sha256":d["sha256"],
                        "bytes":d["size"],"verified_against_original_file":True,
                        "independently_peer_reviewed":False})
    return entries


def prepare_holy_days(root=ROOT):
    root=Path(root).resolve()
    docs=[read_document(root/p,root) for p in HOLY_DAYS]
    registry=source_registry(docs,root)
    lines=docs[0]["text"].splitlines()
    anchors=[]
    for label, phrase in (("static_peace_benchmark","some peaceful bargain always exists"),
                          ("friction_requirement","explicit friction is required"),
                          ("conditional_reduced_form","conditional strike-incentive result"),
                          ("actor_measurement","not an israel->hezbollah directed-dyad"),
                          ("truce_measurement","not evidence of negotiated truce")):
        snippet=excerpt(lines,phrase)
        if snippet:
            anchors.append({"source_id":"LOCAL-1","issue":label,**snippet})
    if len(anchors)<4:
        raise ValueError("Holy Days theory source changed: expected measurement/model caveats are missing; manually re-audit")
    return {"kind":"holy_days_puzzle","title":"Holy Days and War",
            "question":"How, and under which bargaining frictions, do religious holidays alter the timing of attacks or restraint?",
            "source_registry":registry,"traceable_excerpts":anchors,
            "hypothesis_status":"unverified_not_a_derived_equilibrium_result",
            "observation_status":"empirical_holiday_effect_not_established_by_these_documents",
            "novelty_status":"unassessed_original_papers_not_yet_screened",
            "required_diagnosis":"Distinguish empirical pattern, theory prediction, actor measurement and endogeneity before novelty review"}


def puzzle_report(info):
    references="\n".join(f"- {x['id']}: `{x['path']}`; SHA256 `{x['sha256']}`" for x in info['source_registry'])
    cautions="\n".join(f"- {a['issue']}: {a['text']} ({a['source_id']} line {a['line']})" for a in info['traceable_excerpts'])
    return f"""# Puzzle review packet: {info['title']}

## Proposed question, NOT an established discovery

{info['question']}

## Grounding: existing local research notes

{references}

## Critical caveats from the source notes

{cautions}

## What must be decided at this first human gate

- Is the question worth pursuing even if the initial empirical pattern is null?
- Is the target phenomenon **holiday restraint**, **opportunistic attacks**, or **actual negotiated truces**? These are different outcomes.
- Does any available pilot dataset measure actual belligerent identities and attacks rather than country-level event location?
- Do we accept this as a provisional puzzle needing literature/diagnosis, without asserting novelty or an equilibrium result?

## Suggested decision: REVISE / INVESTIGATE before making novelty claims

The complete-information static bargain in the local theory note permits peace under positive fighting costs. An actual directional holiday-war claim requires an explicit, validated bargaining friction. The existing H1 screen is observational and does not establish a causal or directed-dyad effect. This packet is **not** an independent literature review, solved repeated game, or research finding.

**Next step:** Obtain independent criticism; the mandatory human gate must then approve, revise or reject the *puzzle framing*. Approval does not imply approval of the theory, data, or result.
"""


def write_critic_request(path,stage):
    payload={"stage":stage,"status":"REQUEST_ONLY_NOT_AN_INDEPENDENT_REVIEW",
      "instructions":["Read the actual stage artifacts and original source files, not merely this template.",
                       "List the most damaging alternative explanations and measurement problems.",
                       "Check whether statements cite the identified local source and exact line/page.",
                       "Return an actual JSON review with reviewer, reviewer_kind, recommendation, summary, issues, strengths and open_questions.",
                       "Recommend revise if essential claims lack original evidence. Never attest human approval."],
      "critique_schema":"research/examples/INDEPENDENT_CRITIQUE_TEMPLATE.json"}
    atomically_save(path,json.dumps(payload,indent=2,ensure_ascii=False)+"\n")


def project_draft(home,project,stage):
    return Path(home).expanduser().resolve()/"inbox"/"raw"/"scientific_stages"/project/stage


def run_puzzle(home,project,*,holy_days=False):
    from . import review_workflow as workflow
    if not holy_days:
        raise ValueError("This first worker only supports --holy-days; other puzzle briefs need the existing manual submit")
    workflow.require_ready(home,project,"puzzle")
    info=prepare_holy_days(home)
    dest=project_draft(home,project,"puzzle")
    proposal=dest/"PUZZLE_REVIEW.md"
    metadata=dest/"LOCAL_SOURCE_PROVENANCE.json"
    atomically_save(proposal,puzzle_report(info))
    atomically_save(metadata,json.dumps(info,indent=2,ensure_ascii=False)+"\n")
    result=workflow.submit(home,project,"puzzle",[proposal,metadata],
           "Source-grounded Holy Days puzzle framing with explicit theory and measurement weaknesses, not an approved finding")
    instructions=dest/"INDEPENDENT_CRITIC_REQUEST.json"
    write_critic_request(instructions,"puzzle")
    return {**result,"source_provenance":str(metadata),"critic_request":str(instructions),
            "next_action":"Obtain actual independent critique; record with review_workflow critique; human approve/revise/reject",
            "paid_api_calls":0,"external_network_calls":0}


def read_puzzle_spec(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size>60_000:
        raise ValueError("Literature search spec missing, symlinked, or oversized")
    data=json.loads(p.read_text(encoding="utf-8"))
    queries=data.get("search_queries")
    if not isinstance(queries,list) or not 1<=len(queries)<=4 or not all(isinstance(q,str) and 3<=len(q.strip())<=180 for q in queries):
        raise ValueError("Provide 1–4 explicit literature search_queries, length 3–180")
    return data, [q.strip() for q in queries]


def literature_report(result,source):
    lines=["# Literature evidence shortlist — NOT novelty approval","",
           "This search covers only indexed, locally available, page-verified PDF evidence. It does not search the entire literature.",
           "A verified passage is NOT a verified interpretation, complete model, or novel contribution.","",
           f"Input specification SHA256: `{source}`","",
           "## Search coverage"]
    for q in result["queries"]:
        lines.append(f"- {q['query']}: {q['retrieved_candidate_matches']} matching extracted evidence passages")
    lines += ["","## Original pages to inspect"]
    for hit in result['selected_evidence']:
        lines.append(f"- {hit['title']} — source `{hit['source_id']}`, PDF page {hit['pdf_page']}, evidence `{hit['evidence_id']}` (review status {hit['human_review_status']}); SHA256 `{hit['pdf_sha256']}`")
    lines += ["","## Mandatory human investigation","- Read the full original arguments, equilibria and contrary studies, not just matching passages.",
              "- Document alternative mechanisms and scope conditions; verify source titles/pages and bibliographic metadata.",
              "- An independent critic must assess omission and novelty risk before a human literature-stage approval.",
              "- **Never infer novelty solely from these search results.**"]
    return "\n".join(lines)+"\n"


def run_literature(home,project,spec,db):
    from . import review_workflow as workflow
    workflow.require_ready(home,project,"literature")
    source,queries=read_puzzle_spec(spec)
    db=Path(db).expanduser()
    if not db.is_file():
        raise ValueError("Missing private indexed PDF knowledge database; cannot produce credible literature packet")
    from . import puzzle_evidence
    evidence=puzzle_evidence.assemble(db,home=home,queries=queries,limit=16,max_per_paper=3)
    dest=project_draft(home,project,"literature")
    if not evidence.get("selected_evidence"):
        dest.mkdir(parents=True,exist_ok=True)
        failure={"status":"BLOCKED_NO_PAGE_VERIFIED_SOURCES","queries":queries,
                 "db_sha256":sha_file(db),"next_action":"Ingest PDFs/revise searches; literature stage NOT submitted or approved"}
        log=dest/"MISSING_SOURCES.json"
        atomically_save(log,json.dumps(failure,indent=2)+"\n")
        return {"status":"blocked_no_page_verified_sources","reason":"No original passages returned; do not accept metadata as a literature review",
                "details":str(log),"network_or_paid_api_calls":0}
    src=sha_file(spec)
    metadata=dest/"LITERATURE_EVIDENCE.json"
    report=dest/"LITERATURE_SCREEN.md"
    atomically_save(metadata,json.dumps({"search_spec_sha256":src,"db_sha256":sha_file(db),
                                         "evidence":evidence},indent=2,ensure_ascii=False)+"\n")
    atomically_save(report,literature_report(evidence,src))
    result=workflow.submit(home,project,"literature",[metadata,report],
          "Offline PDF page-verified candidate literature screen, pending full-text scientific evaluation")
    critic=dest/"INDEPENDENT_CRITIC_REQUEST.json"
    write_critic_request(critic,"literature")
    return {**result,"critic_request":str(critic),"source_count":len(evidence['selected_evidence']),
            "next_action":"Read originals, perform independent critical literature review and obtain human sign-off; no novelty claim",
            "paid_api_calls":0,"external_network_calls":0}


def main(argv=None):
    parser=argparse.ArgumentParser(description="Source-grounded stage workers behind mandatory approvals; zero paid calls")
    parser.add_argument("--home",type=Path,default=ROOT)
    sub=parser.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("puzzle",help="Produce guarded Holy Days puzzle review package")
    a.add_argument("project")
    a.add_argument("--holy-days",action="store_true",required=True)
    b=sub.add_parser("literature",help="Search page-indexed local PDF library after prior approvals")
    b.add_argument("project")
    b.add_argument("--spec",type=Path,required=True)
    b.add_argument("--db",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.cmd=="puzzle":out=run_puzzle(args.home,args.project,holy_days=args.holy_days)
        else:out=run_literature(args.home,args.project,args.spec,args.db)
        print(json.dumps(out,indent=2,ensure_ascii=False));return 0
    except (OSError,ValueError,TypeError,KeyError,RuntimeError) as exc:
        print("Scientific stage starter stopped safely: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())

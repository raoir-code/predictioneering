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

**Next step:** Read this proposal and choose **APPROVE** (for the next diagnostic stage), **REVISE** (with precise instructions), or **REJECT**. An AI second opinion is optional. Puzzle approval does not certify theory, data, novelty, or results.
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
    state=workflow.require_ready(home,project,"puzzle")
    if state["stages"]["puzzle"]["status"] == "needs_revision":
        raise ValueError("Do not reuse the unchanged puzzle template after a revision request; run review_workflow revision-brief and submit an actually revised document")
    info=prepare_holy_days(home)
    dest=project_draft(home,project,"puzzle")
    proposal=dest/"PUZZLE_REVIEW.md"
    metadata=dest/"LOCAL_SOURCE_PROVENANCE.json"
    atomically_save(proposal,puzzle_report(info))
    atomically_save(metadata,json.dumps(info,indent=2,ensure_ascii=False)+"\n")
    result=workflow.submit(home,project,"puzzle",[proposal,metadata],
           "Source-grounded Holy Days puzzle framing with explicit theory and measurement weaknesses, not an approved finding")
    return {**result,"source_provenance":str(metadata),
            "next_action":"Human reads review packet and chooses approve, revise, or reject; optional critique available",
            "paid_api_calls":0,"external_network_calls":0}


def run_diagnosis(home, project):
    """Cautious first diagnostic report from HUMAN-APPROVED puzzle evidence.

    Not a historical forecast reconstruction, full literature review or test
    of a theory. Missing data explicitly stays missing.
    """
    from . import review_workflow as workflow
    state=workflow.require_ready(home, project, "diagnosis")
    if state["stages"]["diagnosis"]["status"] == "needs_revision":
        raise ValueError("Do not rerun an unchanged diagnosis template; use the human revision brief and submit a substantive revision")
    approved=workflow.require_approved(home,project,"puzzle")
    entries={a["name"]:a for a in state["stages"]["puzzle"]["artifacts"]}
    if "PUZZLE_REVIEW.md" not in entries or "LOCAL_SOURCE_PROVENANCE.json" not in entries:
        raise ValueError("Diagnosis worker requires the vetted Holy Days puzzle artifact and provenance; do not guess")
    root=workflow.location(home,project)
    original=root/entries["PUZZLE_REVIEW.md"]["snapshot"]
    metadata=root/entries["LOCAL_SOURCE_PROVENANCE.json"]["snapshot"]
    info=json.loads(metadata.read_text(encoding="utf-8"))
    if info.get("kind")!="holy_days_puzzle" or not info.get("traceable_excerpts"):
        raise ValueError("Approved puzzle provenance lacks Holy Days traceable evidence")
    # Verify source note bytes still equal the approved registry; no silent source revision.
    for item in info["source_registry"]:
        rel=item["path"]
        if rel.startswith("external_local_source:"):
            raise ValueError("External source not safely resolvable")
        p=Path(home).resolve()/rel
        if not p.is_file() or sha_file(p)!=item["sha256"]:
            raise ValueError("Source note differs from approved puzzle provenance")
    dest=project_draft(home,project,"diagnosis")
    report=dest/"DIAGNOSIS_REPORT.md"
    evidence=dest/"DIAGNOSIS_EVIDENCE.json"
    text=f"""# Holy Days and War — diagnostic decision

**Status:** theoretical/measurement diagnostic only; empirical and novelty claims unverified.

## Approved puzzle

{info['question']}

Approved puzzle decision token: `{approved}`. Prior puzzle report SHA256: `{sha_file(original)}`.

## What the prior notes actually establish

A complete-information, divisible-prize static bargaining benchmark permits a peaceful bargain when fighting is costly. Holiday shifts in relative power change outside options but do not, by themselves, establish increased war onset. This is a conditional theoretical observation in the approved local note, not a new verified equilibrium of a repeated game.

## Mechanisms to distinguish

- **Own-holiday costs/readiness:** might discourage attacks; could be overwhelmed by countervailing incentives.
- **Opponent-holiday vulnerability:** might invite opportunistic attacks, but preparation and anticipation could eliminate the advantage.
- **Failed bargaining:** a directional war-on-holiday prediction requires commitment, information, deadlines or another explicit friction.
- **Formal ceasefire:** zero ACLED events is not proof of negotiated truce; independently dated agreements would be necessary.

## Empirical obstacles

- The pilot's Actor1-in-Lebanon outcome is not a verified Israel–Hezbollah target dyad.
- Contemporaneous event classification, holiday timing, conflict phase and anticipation confound causal interpretation.
- We do not yet have a page-verified original-literature explanation, proven repeated-game equilibrium, credible cross-theater evidence, or a comprehensive matched dataset.

## What you must decide

**Suggested action: APPROVE as a narrow diagnostic agenda** if you agree that these rival mechanisms merit the upcoming literature/novelty review; **REVISE** to narrow the substantive question or address a missing rival. This is not approval of any empirical holiday effect.

**Next only after your approval:** source-backed original-paper literature review, followed by a separate novelty gate.
"""
    atomically_save(report,text)
    proof={"project":project,"stage":"diagnosis","puzzle_approval_token":approved,
           "puzzle_artifact_sha256":sha_file(original),
           "provenance_sha256":sha_file(metadata),"source_notes":info["source_registry"],
           "empirical_effect_proven":False,"repeated_game_equilibrium_proven":False,
           "new_primary_sources_reviewed":0,"novelty_verified":False,
           "status":"diagnostic_agenda_not_empirical_finding"}
    atomically_save(evidence,json.dumps(proof,indent=2,ensure_ascii=False)+"\n")
    submitted=workflow.submit(home,project,"diagnosis",[report,evidence],
             "Guarded Holy Days theory and measurement diagnosis with unresolved rival mechanisms")
    return {**submitted,"report":str(report),"next_action":"Human approve, revise or reject the diagnosis; no automatic literature-stage work"}


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
              "- You must assess omissions and novelty risk before approving; a second opinion is optional.",
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
    return {**result,"source_count":len(evidence['selected_evidence']),
            "next_action":"Read originals and decide whether to approve or revise the literature screen; no novelty claim",
            "paid_api_calls":0,"external_network_calls":0}


def main(argv=None):
    parser=argparse.ArgumentParser(description="Source-grounded stage workers behind mandatory approvals; zero paid calls")
    parser.add_argument("--home",type=Path,default=ROOT)
    sub=parser.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("puzzle",help="Produce guarded Holy Days puzzle review package")
    a.add_argument("project")
    a.add_argument("--holy-days",action="store_true",required=True)
    d=sub.add_parser("diagnosis",help="Diagnose the human-approved Holy Days puzzle using local sources")
    d.add_argument("project")
    b=sub.add_parser("literature",help="Search page-indexed local PDF library after prior approvals")
    b.add_argument("project")
    b.add_argument("--spec",type=Path,required=True)
    b.add_argument("--db",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.cmd=="puzzle":out=run_puzzle(args.home,args.project,holy_days=args.holy_days)
        elif args.cmd=="diagnosis":out=run_diagnosis(args.home,args.project)
        else:out=run_literature(args.home,args.project,args.spec,args.db)
        print(json.dumps(out,indent=2,ensure_ascii=False));return 0
    except (OSError,ValueError,TypeError,KeyError,RuntimeError) as exc:
        print("Scientific stage starter stopped safely: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())

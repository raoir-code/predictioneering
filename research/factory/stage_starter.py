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
            "framing_version":"conceptual_puzzle_v2",
            "question":"Why, and under what conditions, would predictable religious holidays affect the timing or risk of military conflict when adversaries anticipate and respond to each other?",
            "source_registry":registry,"traceable_excerpts":anchors,
            "hypothesis_status":"not_formulated_at_puzzle_stage",
            "observation_status":"holiday_conflict_effect_not_established",
            "novelty_status":"unassessed_original_papers_not_yet_screened",
            "required_diagnosis":"Examine rival strategic intuitions, whether the apparent puzzle survives existing theory, and alternative non-strategic explanations"}


def puzzle_report(info):
    references="\n".join(f"- {x['id']}: `{x['path']}`; SHA256 `{x['sha256']}`" for x in info['source_registry'])
    return f"""# Puzzle: Religious Holidays and Strategic Conflict

## Central question

{info['question']}

## Competing strategic intuitions

**Opportunity.** A holiday might temporarily change routines, staffing, vigilance, or readiness. An opponent could anticipate a window of vulnerability and consider attacking then.

**Anticipation.** Yet holiday dates are generally public and predictable. The potentially vulnerable side can anticipate the same incentive, change readiness, or take other precautions.

**Strategic response.** Once the attacker anticipates those precautions, the apparent advantage may weaken, disappear, or even reverse. Both sides' choices depend on expectations about the other's choices.

## Why this is puzzling

The naive intuition that holidays make attacks more attractive clashes with the equally plausible intuition that predictable vulnerability encourages preparation. Neither intuition alone tells us whether conflict becomes more likely, less likely, or simply moves in time.

The interesting question is **whether predictable, shared knowledge of a possible vulnerability can produce a distinctive conflict-timing pattern once both sides respond strategically.** This is an open theoretical question, not a claim that any holiday effect exists.

## Boundary of this stage

This proposal does **not** assert an observed holiday effect, settle a bargaining model, identify the relevant friction, establish novelty, specify hypotheses, choose countries or datasets, or infer causality. Own-holiday readiness, opponent-holiday opportunities, and negotiated truces are distinct possibilities for later evaluation, not findings or preselected outcomes.

## Local background provenance (for later stages)

{references}

These local notes document earlier thinking and measurement limitations. Their empirical screens, H1/H2/H3 labels, equilibrium conjectures, and source-specific qualifications belong in **Diagnosis, Literature, Formal Model, Hypotheses, Data, and Design**, rather than serving as the Puzzle-stage result. The source registry preserves where that work came from without asking the researcher to endorse it now.

## Human decision

**APPROVE:** This unresolved strategic tension is worth investigating, even if subsequent diagnosis or empirical work finds no effect.

**REVISE:** The central tension itself needs sharpening, a competing intuition is missing, or the scope is too broad.

**REJECT:** The conceptual question is not worth pursuing.

Approval only authorizes the next **Diagnosis** stage. It does not approve novelty, mechanisms, hypotheses, data, estimates, or publication. Optional independent critique is advisory, not mandatory.
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


def revise_holy_days_puzzle(home, project):
    """Resubmit a genuinely revised conceptual puzzle without rewriting prior snapshots.

    Requires the researcher's explicit revision decision first. Does not approve.
    """
    from . import review_workflow as workflow
    state=workflow.require_ready(home,project,"puzzle")
    previous=state["stages"]["puzzle"]
    if previous["status"] != "needs_revision" or not previous.get("human_revision_notes"):
        raise ValueError("Human must request a puzzle revision first: review_workflow revise PROJECT puzzle --reason ...")
    entries={a["name"]:a for a in previous.get("artifacts",[])}
    if "PUZZLE_REVIEW.md" not in entries:
        raise ValueError("Previous puzzle source snapshot missing; refusing to manufacture revision history")
    old=workflow.location(home,project)/entries["PUZZLE_REVIEW.md"]["snapshot"]
    if not old.is_file() or sha_file(old)!=entries["PUZZLE_REVIEW.md"]["sha256"]:
        raise ValueError("Previous puzzle snapshot missing or changed")
    info=prepare_holy_days(home)
    dest=project_draft(home,project,"puzzle")
    proposal=dest/"PUZZLE_REVIEW.md"
    metadata=dest/"LOCAL_SOURCE_PROVENANCE.json"
    new_report=puzzle_report(info)
    if hashlib.sha256(new_report.encode("utf-8")).hexdigest()==sha_file(old):
        raise ValueError("Generated puzzle is unchanged; a substantive revision is required")
    atomically_save(proposal,new_report)
    atomically_save(metadata,json.dumps(info,indent=2,ensure_ascii=False)+"\n")
    submitted=workflow.submit(home,project,"puzzle",[proposal,metadata],
        "Revised conceptual Holy Days puzzle: competing opportunity and anticipation intuitions; no premature hypotheses or dataset")
    return {**submitted,"source_provenance":str(metadata),
            "previous_revision_preserved":True,"next_action":"Human review revised puzzle; do not advance before approval",
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
    if not original.is_file() or sha_file(original)!=entries["PUZZLE_REVIEW.md"]["sha256"]:
        raise ValueError("Approved puzzle snapshot missing or hash-invalid")
    approved_puzzle_text=original.read_text(encoding="utf-8")
    if not approved_puzzle_text.strip() or len(approved_puzzle_text)>12000:
        raise ValueError("Approved puzzle must be substantive and at most 12,000 characters")
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

## Approved puzzle (verbatim from the human-approved, SHA256-bound snapshot)

{approved_puzzle_text}

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



def revise_holy_days_literature(home, project, *, leads_path=None, external_notes=None):
    """Resubmit a genuinely different, relevance-screened holiday bibliography.

    Publisher abstracts are leads, not page-audited full-text evidence. No
    unreviewed result is promoted to a proven finding. No network or paid calls.
    """
    from . import review_workflow as workflow
    state=workflow.require_ready(home, project, "literature")
    prior=state["stages"]["literature"]
    if prior["status"] != "needs_revision" or not prior.get("human_revision_notes"):
        raise ValueError("A human revision decision is required before redoing literature")
    old_artifacts={a["name"]:a for a in prior.get("artifacts",[])}
    old_ref=old_artifacts.get("LITERATURE_SCREEN.md")
    if not old_ref:
        raise ValueError("Missing prior literature snapshot; cannot preserve revision history")
    previous=workflow.location(home,project)/old_ref["snapshot"]
    if not previous.is_file() or sha_file(previous)!=old_ref["sha256"]:
        raise ValueError("Prior literature snapshot missing or altered")
    workflow.require_approved(home,project,"puzzle")
    workflow.require_approved(home,project,"diagnosis")

    leads_path=Path(leads_path) if leads_path else ROOT/"examples"/"HOLY_DAYS_LITERATURE_LEADS.json"
    leads_document=read_document(leads_path)
    data=json.loads(leads_document["text"])
    sources=data.get("sources")
    if data.get("schema_version")!="holiday_literature_leads_v1" or not isinstance(sources,list) or len(sources)<4:
        raise ValueError("Expected at least four scoped holiday literature leads")
    classes={"core_direct","adjacent_design","theory","data_resource"}
    fields=("id","title","authors","year","url","classification","outcome",
            "holiday_exposure","scope_limited_finding","relevance","verification")
    seen=set()
    direct=0
    for item in sources:
        if not isinstance(item,dict) or any(not isinstance(item.get(key),str) or not item[key].strip()
                                            for key in fields if key!="year"):
            raise ValueError("Every source requires complete source, outcome, relevance and verification fields")
        if not isinstance(item.get("year"),int) or item["classification"] not in classes:
            raise ValueError("Invalid paper year or conceptual role")
        if not item["url"].startswith("https://"):
            raise ValueError("Sources must use verified HTTPS original/institutional URLs")
        key=(item["id"],item["url"])
        if item["id"] in seen or item["url"] in seen:
            raise ValueError("Duplicated literature identifier or URL")
        seen.update(key)
        direct+=(item["classification"]=="core_direct")
    if direct<3:
        raise ValueError("Insufficient direct holiday-violence evidence for meaningful revision")

    notes_record=None
    if external_notes is not None:
        note=read_document(external_notes)
        notes_record={"sha256":note["sha256"],"file_name":Path(note["path"]).name,
                      "status":"researcher_supplied_unverified_context_not_a_citation"}
    sections=[
        "# Holy Days and War — targeted literature screening (revision)",
        "",
        "**Scientific status: ABSTRACT/ENTRY SCREEN ONLY; full original-paper review remains outstanding.**",
        "These sources were deliberately selected for conceptual relevance, not keyword overlap.",
        "The factory does not claim page-verified full-text readings, a proven effect, or novelty.",
        "",
        "## Synthesis for scientific triage",
        "",
        "**Holiday effects are not a single estimand.** Terrorist attacks, communal riots,",
        "civil ceasefire agreements, and interstate onset are distinct outcomes.",
        "Reese et al. and Chinda et al. both study holiday-associated violence but report",
        "different holiday-type patterns in different populations. This is a question",
        "for comparison, not a contradiction that can be pooled into a universal sign.",
        "The audience-support and ritual-friction channels may be distinct from",
        "strategic surprise or negotiated holiday restraint.",
        "",
        "## Core: directly measure holiday-associated violence",
    ]
    labels={"core_direct":"Core: directly measure holiday-associated violence",
            "adjacent_design":"Adjacent: calendar identification or mechanism",
            "data_resource":"Separate outcome: negotiated holiday ceasefires",
            "theory":"Theory-only: strategic anticipation and surprise"}
    for cls in ("core_direct","adjacent_design","data_resource","theory"):
        if cls!="core_direct":
            sections.extend(["", "## "+labels[cls]])
        for item in sources:
            if item["classification"]!=cls:
                continue
            sections += [
                "",
                "### "+item["authors"]+" ("+str(item["year"])+"): "+item["title"],
                "- **Original/institutional source:** "+item["url"],
                "- **Outcome:** "+item["outcome"],
                "- **Holiday definition:** "+item["holiday_exposure"],
                "- **Reported claim (limited to checked source):** "+item["scope_limited_finding"],
                "- **Why it actually counts / limits:** "+item["relevance"],
                "- **Verification:** "+item["verification"],
            ]
    sections += [
        "",
        "## Exclusions from revision 1",
        "The original keyword matches on nuclear proliferation, diversionary war,",
        "generic arms buildups, and rivalry dynamics are excluded from the main",
        "holiday review: none establishes a holiday mechanism or measures a holiday effect.",
        "They can be reconsidered later ONLY for a specific theoretical argument with",
        "actual supporting passages, not to inflate coverage.",
        "",
        "## Outstanding original-paper work before approving a complete review",
        "1. Read originals and confirm sample, variables, identification and actual tables",
        "   for each direct-effect study; record source PDF SHA256 and page numbers.",
        "2. Search systematically for contradictory or missing direct studies, especially",
        "   military interstate conflict onset rather than terrorist/communal events.",
        "3. Distinguish attacker-constituency holidays, defender holidays, shared holidays,",
        "   and formally declared ceasefires; do not assume one mechanism fits all.",
        "4. Treat the external research summary as leads, never as primary citation evidence.",
        "5. Novelty is NOT assessed and the model/hypothesis is NOT chosen here.",
        "",
        "## Provenance",
        "- Literature-lead manifest SHA256: "+leads_document["sha256"],
        "- Prior rejected screening SHA256: "+sha_file(previous),
        "- Researcher revision request: "+prior["human_revision_notes"],
    ]
    if notes_record is not None:
        sections.append("- Optional external notes SHA256: "+notes_record["sha256"]+
                        " (unverified leads, not source evidence)")
    sections += ["","## Researcher decision",
                 "APPROVE only if treating this strictly as a *scoped candidate screen*;",
                 "REVISE if a full original-paper literature review is required before advancing.",
                 "No source here is asserted page-audited by this revised worker.",""]
    report_text="\n".join(sections)
    if hashlib.sha256(report_text.encode("utf-8")).hexdigest()==sha_file(previous):
        raise ValueError("Literature revision made no substantive change")
    dest=project_draft(home,project,"literature")
    report=dest/"LITERATURE_SCREEN.md"
    evidence=dest/"LITERATURE_EVIDENCE.json"
    proof={
        "status":"scoped_external_source_screen_full_text_pending",
        "project":project,"stage":"literature",
        "literature_leads_sha256":leads_document["sha256"],
        "previous_rejected_screen_sha256":sha_file(previous),
        "original_full_text_page_verified_by_this_worker":False,
        "novelty_verified":False,
        "sources":sources,
        "optional_external_notes":notes_record,
        "human_revision_reason":prior["human_revision_notes"],
        "external_network_calls":0,
        "paid_api_calls":0,
    }
    atomically_save(report,report_text)
    atomically_save(evidence,json.dumps(proof,indent=2,ensure_ascii=False)+"\n")
    result=workflow.submit(home,project,"literature",[report,evidence],
        "Targeted holiday literature screen; checked publisher/institutional leads, full-text verification pending")
    return {**result,"report":str(report),"source_count":len(sources),
            "original_papers_page_audited":0,
            "next_action":"Human assess scoped source relevance; full-text/source-page audit required before claiming comprehensive review",
            "external_network_calls":0,"paid_api_calls":0}


def main(argv=None):
    parser=argparse.ArgumentParser(description="Source-grounded stage workers behind mandatory approvals; zero paid calls")
    parser.add_argument("--home",type=Path,default=ROOT)
    sub=parser.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("puzzle",help="Produce guarded Holy Days puzzle review package")
    a.add_argument("project")
    a.add_argument("--holy-days",action="store_true",required=True)
    v=sub.add_parser("revise-puzzle",help="Resubmit a human-requested conceptual Holy Days revision without losing prior history")
    v.add_argument("project")
    v.add_argument("--holy-days",action="store_true",required=True)
    d=sub.add_parser("diagnosis",help="Diagnose the human-approved Holy Days puzzle using local sources")
    d.add_argument("project")
    b=sub.add_parser("literature",help="Search page-indexed local PDF library after prior approvals")
    b.add_argument("project")
    b.add_argument("--spec",type=Path,required=True)
    b.add_argument("--db",type=Path,required=True)
    lr=sub.add_parser("revise-literature",help="Resubmit scoped, separately checked holiday paper leads after a human revision request")
    lr.add_argument("project")
    lr.add_argument("--leads",type=Path,default=ROOT/"examples"/"HOLY_DAYS_LITERATURE_LEADS.json")
    lr.add_argument("--external-notes",type=Path)
    args=parser.parse_args(argv)
    try:
        if args.cmd=="puzzle":out=run_puzzle(args.home,args.project,holy_days=args.holy_days)
        elif args.cmd=="revise-puzzle":out=revise_holy_days_puzzle(args.home,args.project)
        elif args.cmd=="diagnosis":out=run_diagnosis(args.home,args.project)
        elif args.cmd=="revise-literature":out=revise_holy_days_literature(args.home,args.project,
                                                        leads_path=args.leads,external_notes=args.external_notes)
        else:out=run_literature(args.home,args.project,args.spec,args.db)
        print(json.dumps(out,indent=2,ensure_ascii=False));return 0
    except (OSError,ValueError,TypeError,KeyError,RuntimeError) as exc:
        print("Scientific stage starter stopped safely: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())

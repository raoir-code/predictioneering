"""Read-only next-step guide for the human-gated Research Paper Factory.

Usage: python -m research.factory.guide holy-days
No API calls, no revisions, no signatures. Reports the next action without
bypassing the original scientific review gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import review_workflow as gates
from . import theory_fabricator as theory

ROOT = Path(__file__).resolve().parents[1]
PY = '"$HOME/.venvs/predictioneering-research/bin/python"'
FLOW = ("puzzle", "literature", "formal_model", "hypotheses", "design",
        "data", "analysis", "validation", "manuscript", "qc")
STAGE_REQUIREMENTS = {
    "hypotheses": "Confirm that a checked, solved formal model supports the proposed hypotheses.",
    "design": "Supply a researcher-reviewed study specification (--spec PATH).",
    "data": "Supply approved, direction-verified real observations; avoid synthetic demos.",
    "analysis": "Run only after approved data/design and inspect the actual results.",
    "validation": "Check out-of-sample, robustness, calibration and identification as applicable.",
    "manuscript": "Draft only from approved, source-grounded analysis and theory.",
    "qc": "Audit originals, replication materials, equilibrium proof, and manuscript claims.",
}


def guide(home, project):
    """Return one actionable next step grounded in signed local stage state."""
    project = gates.safe_project(project)
    overview = gates.overview(home, project)
    active = overview["stages"]
    first = next((x for x in active if x["status"] != "approved"), None)
    status = first["status"] if first else "approved"
    stage = first["stage"] if first else "finished"
    result = {
        "project": project,
        "stage": stage,
        "stage_status": status,
        "next_action": "",
        "command": "",
        "notes": [],
        "network_or_paid_api_calls": 0,
        "guide_path": "research/FACTORY_RUNBOOK.md",
    }
    if first is None:
        result["next_action"] = "All workflow gates signed. Independently verify scientific readiness before sharing results."
        result["notes"] = ["A completed pipeline is not automatically a validated paper."]
        return result

    if status in ("awaiting_human_approval", "awaiting_critique"):
        result["next_action"] = "Read the submitted stage report, then approve or request revisions."
        result["command"] = (
            PY + " -m research.factory.review_workflow review " +
            project + " " + stage
        )
        result["notes"] = [
            "Do not approve before examining the stage's evidence and limitations.",
            "Use review_workflow approve/revise only after a human decision.",
        ]
        return result

    if stage == "formal_model":
        dest = theory.folder(home, project)
        blueprint = dest / "THEORY_BLUEPRINT.json"
        approval = dest / "BLUEPRINT_APPROVAL.json"
        if not blueprint.is_file():
            result["next_action"] = "Create and scientifically review a conventional-game blueprint."
            result["notes"] = [
                "Start with theory_fabricator brief/propose using a carefully selected baseline.",
                "See the runbook for the first-time commands. Do not reuse the one-shot demo as the solution.",
            ]
        elif not approval.is_file():
            plan = json.loads(blueprint.read_text(encoding="utf-8"))
            number = plan.get("generation", {}).get("revision_number", 0)
            result["blueprint_revision"] = number
            result["next_action"] = "Review the latest blueprint. Give Claude corrections or explicitly approve the architecture."
            result["command"] = (
                PY + " -m research.factory.theory_fabricator review " +
                project + " --confirm-share-evidence --model claude-opus-5-5 " +
                "--input-rate 4 --output-rate 20 --max-usd 1.00 --max-tokens 12000"
            )
            result["notes"] = [
                "Review the COMPLETE " + str(dest / "BLUEPRINT_REVIEW.md") +
                " before approving.",
                "Explicit human APPROVE signs the architecture only; no mathematical equilibrium is established.",
                "Revisions incur API charges; verify current model and token pricing.",
            ]
            if theory.unresolved_claude_attempts(home, project):
                result["notes"].insert(
                    0, "A failed newer Claude response is unresolved; never approve the older model by accident."
                )
        else:
            # A signed architecture is only permission to BEGIN mathematics,
            # not a theorem. This explicit numeric adapter cannot bypass proof.
            formal = dest.parent / "formal_workbench"
            work_order = formal / "MODEL_CONTRACT.json"
            if not work_order.is_file():
                result["next_action"] = (
                    "Prepare the formal game's explicit equations, assumptions, "
                    "and numerical-check work order."
                )
                result["command"] = (
                    PY + " -m research.factory.formal_workbench prepare " + project
                )
            else:
                try:
                    contract = json.loads(work_order.read_text(encoding="utf-8"))
                    signed_sha = json.loads(
                        approval.read_text(encoding="utf-8")
                    )["blueprint_sha256"]
                except (OSError, ValueError, KeyError):
                    raise ValueError("Cannot read formal work order or signature; recheck local scientific state")
                if contract.get("approved_blueprint_sha256") != signed_sha:
                    raise ValueError("Formal work order is for a different blueprint version; "
                                     "archive it before preparing the new game")
                report = formal / "DEMO_SYNTHETIC_NUMERIC_DIAGNOSTIC.json"
                if not report.is_file():
                    result["next_action"] = (
                        "Run a synthetic numerical equilibrium smoke test "
                        "before deriving a general proof."
                    )
                    result["command"] = (
                        PY + " -m research.factory.formal_workbench demo " + project
                    )
                else:
                    proof = formal / "derivations" / "PROOF_DRAFT.json"
                    if not proof.is_file():
                        partials = sorted(
                            (formal / "derivations" / "attempts").glob(
                                "CLAUDE_FORMAL_PARTIAL_*.txt")
                        )
                        if partials:
                            result["next_action"] = (
                                "Claude's previous derivation was cut off. "
                                "Try zero-cost recovery before a new paid call."
                            )
                            result["command"] = (
                                PY + " -m research.factory.formal_reasoner recover " +
                                project
                            )
                            result["notes"].append(
                                "If recovery reports incomplete JSON, run "
                                "formal_reasoner draft again with current pricing "
                                "and --max-tokens 12000. The prompt is now compact; "
                                "the retry is billable."
                            )
                        else:
                            result["next_action"] = (
                                "Ask Claude to draft an auditable equilibrium "
                                "derivation from the signed blueprint."
                            )
                            result["command"] = (
                                PY + " -m research.factory.formal_reasoner draft " +
                                project + " --confirm-share-evidence "
                                "--model claude-opus-5-5 --input-rate 4 "
                                "--output-rate 20 --max-usd 1.00 --max-tokens 12000"
                            )
                            result["notes"].append(
                                "This optional Claude step is billable and produces "
                                "an UNVERIFIED candidate, never a proved theorem."
                            )
                    else:
                        result["next_action"] = (
                            "Inspect/revise the Claude mathematical derivation, then "
                            "independently verify its proof and all deviations."
                        )
                        result["command"] = (
                            PY + " -m research.factory.formal_reasoner review " +
                            project + " --confirm-share-evidence "
                            "--model claude-opus-5-5 --input-rate 4 "
                            "--output-rate 20 --max-usd 1.00 --max-tokens 12000"
                        )
                        result["notes"].append(
                            "A full verified game JSON still must be supplied to "
                            "science_mvp produce PROJECT formal_model; no automatic approval."
                        )
            result["notes"] = [
                "The formal workbench checks selected numerical pure Markov cases, "
                "NOT all theorems or non-Markov SPE.",
                "Do not advance to empirical hypotheses before a researcher-approved full model proof.",
            ]
        return result

    if stage in ("puzzle", "literature"):
        result["next_action"] = (
            "Develop the " + stage + " stage, verify the evidence, and submit it for human review."
        )
        result["command"] = PY + " -m research.factory.review_workflow status " + project
        result["notes"] = [
            "This early stage needs project-specific source work; the guide does not invent papers or approvals.",
            "See research/FACTORY_RUNBOOK.md and the stage-specific research scripts.",
        ]
        return result

    result["next_action"] = "Prepare and submit the " + stage + " stage for human review."
    if stage == "design":
        result["command"] = (
            PY + " -m research.factory.science_mvp produce " +
            project + " design --spec /path/to/approved_study.json"
        )
    else:
        result["command"] = (
            PY + " -m research.factory.science_mvp produce " +
            project + " " + stage
        )
    result["notes"] = [
        STAGE_REQUIREMENTS.get(stage, "Verify all evidence and dependencies."),
        "The stage gate will refuse missing input requirements or unapproved dependencies.",
        "Review generated artifacts and explicitly sign the stage before moving on.",
    ]
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Read-only Paper Factory next-step guide")
    p.add_argument("project")
    p.add_argument("--home", type=Path, default=ROOT)
    args = p.parse_args(argv)
    try:
        result = guide(args.home, args.project)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Paper Factory guide stopped: " + str(exc), file=sys.stderr)
        return 1
    print("Paper Factory | " + result["project"])
    print("Current stage: " + result["stage"] + " (" + result["stage_status"] + ")")
    if "blueprint_revision" in result:
        print("Blueprint revision: " + str(result["blueprint_revision"]))
    print("NEXT: " + result["next_action"])
    if result["command"]:
        print("\nRun:\n" + result["command"])
    for note in result["notes"]:
        print("- " + note)
    print("\nComplete workflow: " + result["guide_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

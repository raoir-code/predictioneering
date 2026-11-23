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
                "APPROVE signs the architecture only; no mathematical equilibrium is established.",
                "Revisions incur API charges; verify current model and token pricing.",
            ]
            if theory.unresolved_claude_attempts(home, project):
                result["notes"].insert(
                    0, "A failed newer Claude response is unresolved; never approve the older model by accident."
                )
        else:
            result["next_action"] = "Solve and independently verify the repeated-game equilibrium before submitting formal_model."
            result["command"] = (
                PY + " -m research.factory.science_mvp produce " +
                project + " formal_model --model /path/to/verified_model.json"
            )
            result["notes"] = [
                "The model must reference the approved blueprint SHA, and provide all equations and proof checks.",
                "Do not substitute the earlier conditional 2x2 inspection-game candidate.",
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

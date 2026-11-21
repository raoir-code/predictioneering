# Research Factory — mandatory human approval and revision gates (v0.7)

**Status:** Real, local, offline approval state machine, not an autonomous research scientist. Every **orchestrated** stage produces frozen artifacts, awaits **independent critique**, then awaits **your explicit human approval, revision or rejection** before a downstream stage may begin. The legacy standalone Python commands do not magically inherit these restrictions: use the guarded `review_workflow` entrypoint or call its `require_ready` / `require_approved` functions from future adapters. No background execution, Claude API charges, automatic merging or publication.

## Twelve checkpoints

`puzzle → diagnosis → literature → novelty → formal_model → hypotheses → data → design → analysis → validation → manuscript → qc`

* **puzzle**: What is surprising and worth studying? This can be a forecast miss or a conventional theoretical puzzle (such as Holy Days).
* **diagnosis**: Reconstruct or substantiate the phenomenon; distinguish technical artifacts and existing explanations. Not every puzzle requires forecasting logs.
* **literature**: Research original scholarly sources and competing explanations with verifiable citations.
* **novelty**: Explicit adversarial review of the precise proposed contribution.
* **formal_model**: Game specification, equilibrium argument, proofs, comparative statics, limitations.
* **hypotheses**: Frozen empirical predictions derived from the model, before examining results.
* **data**: Dataset discovery and provenance, license, coverage, validity, and approved content hash; **do not upload or commit restricted data**.
* **design**: Preregister data joins, variables, estimand, statistics, uncertainty and OOS plan.
* **analysis**: Actual Python results, figures and diagnostics from the *approved* dataset and design.
* **validation**: Sensitivity, falsification, external checks, held-out forecast performance.
* **manuscript**: Overleaf LaTeX ZIP with results, figures, bibliography, citation ledger, and unresolved deficiencies.
* **qc**: Independent end-to-end scientific, replication and editorial review. Never silently publish.

Each stage's review packet contains the submitted work, immutable snapshot SHA256 values, stage-specific checks, independent review findings, and your decision. The dashboard displays all stages and stops. State is in `research/projects/factory_runs/<project>/human_gates/` (**gitignored**, never publicly synced). Advisory file locking prevents simultaneous commands from overwriting each other's decisions; snapshots, decision files and a hash-chained event history preserve an audit trail. Snapshots are copied and marked read-only, with SHA checks on every dependent access. This protects against accidental alteration, not a malicious operator with local write access.

## Initialize the first real project

```bash
cd ~/predictioneering-research-test
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m research.factory.review_workflow init holy-days --title 'Holy Days and War'
"$P" -m research.factory.review_workflow status holy-days
```

The only initially runnable stage is `puzzle`. Nothing is submitted or approved by `init`. To submit a researcher/Claude-produced **actual** artifact:

```bash
"$P" -m research.factory.review_workflow submit holy-days puzzle \
  --artifact /path/to/real_puzzle.md \
  --summary 'The observed phenomenon, theory expectation, rival explanations and key questions'
```

The command freezes the artifact and writes:

`research/projects/factory_runs/holy-days/human_gates/review_packets/puzzle.md`

**This stage is now `awaiting_critique`, not approved.** Have a separate reviewer/Claude critic inspect *the real source files* and create a private JSON report. No paid reviewer is automatically launched. A minimal **substantive** report format:

```json
{
  "reviewer": "Independent Critic Name",
  "reviewer_kind": "independent_ai",
  "recommendation": "revise",
  "summary": "The motivating case has an unresolved alternative explanation that requires checking original evidence.",
  "issues": [
    {
      "severity": "major",
      "description": "The event classification may not match the outcome studied in existing work.",
      "suggested_fix": "Verify the event definition and compare at least two original studies."
    }
  ],
  "strengths": [],
  "open_questions": ["Is the proposed mechanism already explained by bargaining theory?"]
}
```

The reviewer identity and recommendation must be real, not placeholders. `reviewer_kind` identifies the external independent reviewer; the tool does **not** itself verify that a Claude model or person performed the review. Cite original passages in the stage artifacts/report when relevant; this stage manager cannot establish scientific truth from JSON.

Record the critique, then *you* decide:

```bash
"$P" -m research.factory.review_workflow critique holy-days puzzle \
  --report /path/to/real_independent_review.json

# Approved only when the independent review is satisfactory:
"$P" -m research.factory.review_workflow approve holy-days puzzle \
  --reviewer 'Researcher' \
  --notes 'I have read the stage artifact and critical review, and approve advancing.'

# Or request revision instead of approval:
"$P" -m research.factory.review_workflow revise holy-days puzzle \
  --reason 'Clarify the scope conditions and incorporate the missing counterexamples.'

# Or reject altogether:
"$P" -m research.factory.review_workflow reject holy-days puzzle \
  --reason 'Existing literature already explains the apparent research puzzle.'
```

A critique recommending REVISE/REJECT or raising major unresolved issues blocks ordinary approval; a human can override only with `--override-critic` and a **substantive 60+ character justification**, retained in the signed decision record. The final human approver cannot be the same person as the named independent critic. The approval token is bound to the exact stage revision, review snapshot and upstream approvals.

Once `puzzle` is approved, `diagnosis` becomes ready, and so on; every checkpoint repeats the same process. **Changing `formal_model`** marks hypotheses, data, design, analysis, validation, manuscript and QC **stale**. It does not rerun or erase earlier source-reviewed literature. Changing `manuscript` invalidates QC only. Old immutable snapshots are retained.

## Guarded execution of the two existing automated workers

Most scientific stages still require separately produced research artifacts. Two **real** existing workers are now callable through the gates:

```bash
# After data + design (and all prior stages) are independently critiqued and approved:
"$P" -m research.factory.review_workflow produce holy-days analysis \
  --spec /path/to/the-approved-study.json

# Analysis now STOPS for independent critique and your human sign-off.
# After that and a separately approved validation stage:
"$P" -m research.factory.review_workflow produce holy-days manuscript \
  --spec /path/to/the-approved-study.json \
  --formal-model /path/to/the-approved-formal_model.json
```

For `produce analysis`, `design` approval must include the **byte-exact study spec** and `data` approval must include a **private** `data_manifest.json` containing `{"data_sha256":"<SHA256 of exact CSV bytes>"}`. The guarded runner recomputes the actual CSV hash and rejects changes. It calls the existing fingerprinted `prototype.run`, submits actual results/QC/replication artifacts to the approval state, and **stops**; it cannot autoapprove results. To produce the paper, the worker verifies the approved formal-model hash and the **unchanged approved analysis results**, then calls the existing `paper_sprint.run`; again the Overleaf ZIP is **submitted for review, not approved**.

The *unapproved* standalone `python -m research.factory.prototype` and `python -m research.factory.paper_sprint` demo commands remain accessible for testing; do not use those to bypass scientific signoffs on a real study. An independent Claude critique generator, automated literature/data acquisition and direct stage-to-worker wiring beyond these two computational adapters still need implementation.

## What is intentionally NOT claimed

* An independent critique is a **required input**, not automatically generated by this release; the caller must obtain it through an authorized reviewer or later agent.
* A signed approval does not prove the science is correct. Citations, source-claims, model equilibria and empirical inferences still require substantive auditing.
* Existing stand-alone research scripts are not globally blocked; the *new guarded entrypoint* enforces the checks.
* There is no unattended end-to-end research run, automatic expensive Claude call, dataset discovery service, merge, or publication.
* The user is accountable for final research approval; no AI can impersonate that sign-off.

## Tests

Run `"$P" -m unittest discover -s research/tests -q`. New tests exercise skipping stages, requesting revisions, reject/reopen, reviewer independence, critic overrides, snapshot tampering, dependent invalidation, and guarded synthetic analysis/Overleaf production. The examples run with no networking or paid API.

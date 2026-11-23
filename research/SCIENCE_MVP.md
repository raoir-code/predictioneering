# Research Factory — fast MVP workflow

**Start here instead of memorizing commands:** [FACTORY_RUNBOOK.md](FACTORY_RUNBOOK.md).
To see exactly what to run next:

```bash
cd ~/predictioneering-research-test
git pull --ff-only
"$HOME/.venvs/predictioneering-research/bin/python" -m research.factory.guide holy-days
```

The guide reads signed workflow state, costs nothing, and never modifies a
research artifact or approves it. Follow its next-action instruction; run it
again after each human-gated step.

**Status:** runnable orchestration, **not** an autonomous scientist or a validated paper.
Data and paper drafts stay in private, gitignored local folders; no paid API calls.

## 1. One-time upgrade (preserves Holy Days revision 3 puzzle and revision 2 literature approvals)

```bash
cd ~/predictioneering-research-test
git pull --ff-only
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m unittest discover -s research/tests -q
"$P" -m research.factory.review_workflow activate-mvp holy-days
"$P" -m research.factory.science_mvp status holy-days
```

The opt-in **10-stage profile** is:

`puzzle → literature+contribution → formal_model → hypotheses → design → data → analysis → validation → manuscript → qc`

Existing Diagnosis/Novelty approval files and their hashes remain unchanged and readable.
It does **not** automatically claim that the current preliminary literature screen establishes novelty.

### Fastest visible demonstration (Holy Days, synthetic)

```bash
"$P" -m research.factory.paper_sprint holy-days-demo
```

Creates a real empirical calculation, two PDF figures, and an Overleaf ZIP under
`research/projects/factory_runs/holy_days_synthetic_demo/package/`, but all
**event dates and outcomes are fabricated**. The game is a conditional
inspection-game **candidate** and the holiday indicator is not a real holiday calendar.
It verifies indifference algebra from the actual 2x2 payoff matrix, not the
full equilibrium parameter domain or historical evidence.

We also committed `research/examples/HOLY_DAYS_2X2_MODEL_CANDIDATE.json` and
`research/examples/HOLY_DAYS_STUDY_CANDIDATE.json` as **reviewable starting
points only**. The latter requires an authorized private, direction-validated
interstate dyad-day risk panel and is not presently data-complete.

## 2. Formal model MUST start with an approved theory blueprint

The formal-model stage now has two internal steps: **architecture proposal** (the source-grounded baseline + exactly one change) and **mathematical solution**. Human review of the architecture is required **before** model equations in the 10-stage MVP profile. The old 12-stage pilot remains available for backward compatibility.

The previous Holy Days one-shot inspection game is NOT the researcher's desired repeated ultimatum model. Its pending revision must be rejected for revision locally; no old signed puzzle/literature decisions are touched:

```bash
"$P" -m research.factory.review_workflow revise holy-days formal_model \
  --reason "Replace one-shot inspection game with a conventional infinitely repeated ultimatum/bargaining game plus ONE predictable four-state holiday calendar innovation."
"$P" -m research.factory.theory_fabricator brief holy-days \
  --baseline "Conventional infinitely repeated ultimatum game; holiday state affects one existing payoff or continuation primitive"
"$P" -m research.factory.theory_fabricator propose holy-days \
  --baseline "Conventional infinitely repeated ultimatum game; holiday state affects one existing payoff or continuation primitive" \
  --candidate research/examples/HOLY_DAYS_THEORY_BLUEPRINT_CANDIDATE.json
open research/inbox/raw/scientific_stages/holy-days/theory_blueprint/BLUEPRINT_REVIEW.md
```

The proposal is a **model plan**, not a proof. Its starting proposer protocol (e.g., alternating or fixed proposer), discounting, rejection continuation, calendar process, and candidate cost change all need human judgment. Review the blueprint; revise the file and re-propose if anything is wrong. To sign off **only the architecture**:

```bash
"$P" -m research.factory.theory_fabricator approve holy-days \
  --reviewer Researcher --notes "Approved conventional repeated bargaining benchmark and one holiday-state innovation; mathematical solution still required."
```

A subsequent formal_model.json must match the SHA256 of the approved blueprint and explicitly name the same baseline game and one change. The formal-model worker will reject an unrelated model. The genuine infinite-horizon equilibrium is **not yet solved** and cannot be replaced with the old inspection game.

**Optional automation:** the fabricator can generate an unreviewed blueprint via an explicitly authorized Claude API call (`propose --send-to-claude --confirm-share-evidence` with model, current token rates, and per-call dollar cap); offline is the default. API generation does not count as human approval or source verification.

### Revisions upon revisions — permanent Model Fabricator workflow

The architecture remains **unreviewed** until an explicit human `approve`.
After each proposed blueprint, create/update a private text file with **only the
latest round's feedback**, then run `revise`. Repeat as often as needed:

```bash
D="research/inbox/raw/scientific_stages/holy-days/theory_blueprint"
P="$HOME/.venvs/predictioneering-research/bin/python"
# Edit $D/REVISION_FEEDBACK.md with the next round's requested corrections.
"$P" -m research.factory.theory_fabricator revise holy-days \
  --feedback-file "$D/REVISION_FEEDBACK.md" \
  --confirm-share-evidence --model claude-opus-5-5 \
  --input-rate 4 --output-rate 20 --max-usd 1.00 --max-tokens 12000
open "$D/BLUEPRINT_REVIEW.md"
"$P" -m research.factory.theory_fabricator history holy-days
```

Each successful revision is saved as `THEORY_BLUEPRINT.json`, with the old
blueprint/review archived in `history/<sha>/`. The revision number, exact
researcher feedback, parent SHA, and generation provenance are retained in the
new blueprint. The source snapshots remain signed and unchanged. The `history`
command lists versions and their linkage. Sending an approved blueprint back
to Claude is blocked until the researcher reopens the approval.

Claude generation may fail even with adequate budget, and **failed calls can be
billable**. Invalid complete JSON is saved under `attempts/` for local replay.
Truncated or malformed responses are saved as `CLAUDE_PARTIAL_*.txt` with
diagnostics, while the previous blueprint remains untouched. A truncated
response is **not** a valid revision. The output default is 12,000 tokens
(allowed 512–20,000); the dollar setting is a conservative pre-call estimate,
not guaranteed billed cost. The full prior revision history is never sent to
Claude, so repeated rounds do not accumulate prompt size.

### Simplified interactive review and recovery

For a saved Claude response rejected with `invalid JSON (Extra data)`,
first recover the complete first JSON object **without another API call**:

```bash
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m research.factory.theory_fabricator recover holy-days
```

This selects the latest `CLAUDE_PARTIAL_*.txt` from this project's private
`attempts/` directory, verifies the original signed source inputs and parent
blueprint SHA, and extracts one complete valid blueprint object. It preserves
all trailing text and the original response, and refuses ambiguous multiple-JSON
responses or incomplete objects. The recovered architecture remains **unreviewed**.

For a much simpler human-in-the-loop interface, run:

```bash
"$P" -m research.factory.theory_fabricator review holy-days \
  --confirm-share-evidence --model claude-opus-5-5 \
  --input-rate 4 --output-rate 20 --max-usd 1.00 --max-tokens 12000
```

The terminal summarizes the current design and asks: **What should I change?**
Type a short correction to make another (billable) Claude API revision, type
`SHOW` to display the full review, or type `APPROVE` to approve the
**architecture only**, not its proof. A `@/path/to/feedback.md` answer
loads a longer existing feedback file. Each successful revision is archived.
`APPROVE` requires explicit typing; no model response self-approves.
The command doesn't call the API just to view the existing design.

### Recovering from an accidentally approved older blueprint

If Claude's later revision fails and the old blueprint was accidentally
approved, **do not begin the formal model**. Reopen explicitly:

```bash
"$P" -m research.factory.theory_fabricator reopen holy-days \
  --reason "Newer requested model changes were not yet incorporated"
```

This withdraws only the local theory-architecture approval and archives its
original signed record under `approval_history/`; the current blueprint and
approved scholarly source snapshots remain intact. Reopening is refused if the
formal-model stage has already been approved, to avoid untracked downstream
dependencies. Then run `revise` with the saved feedback or retry `recover`.
A failed Claude draft is **never** an approved revision.

The interactive `review` now warns if a newer Claude revision failed
against the current draft. Typing `APPROVE` in that case does **not** sign the
older draft. Only `APPROVE CURRENT` deliberately accepts that older design,
and the waiver is recorded in its signature. Otherwise successful revisions
remain subject to explicit human approval.

### Continue after the separately reviewed formal solution

Use `research/examples/FORMAL_MODEL_TEMPLATE.json` for **file format only**.
The formal model must state players, actions, timing, payoffs, solution concept,
equilibrium argument and the actual comparative-static derivations.
Any proposed repeated-game equilibrium must satisfy Bellman recursion,
best responses, off-path incentives, all holiday states and baseline recovery.

```bash
"$P" -m research.factory.science_mvp produce holy-days formal_model \
  --model /path/to/fully_derived_repeated_bargaining_model.json
```

Each subsequent stage also requires a human approval checkpoint:

| Ready stage | Command |
|---|---|
| hypotheses | `"$P" -m research.factory.science_mvp produce holy-days hypotheses` |
| design | `"$P" -m research.factory.science_mvp produce holy-days design --spec /path/to/study.json` |
| data | `"$P" -m research.factory.science_mvp produce holy-days data` |
| analysis | `"$P" -m research.factory.science_mvp produce holy-days analysis` |
| validation | `"$P" -m research.factory.science_mvp produce holy-days validation` |
| manuscript | `"$P" -m research.factory.science_mvp produce holy-days manuscript` |
| qc | `"$P" -m research.factory.science_mvp produce holy-days qc` |

A private, approved study CSV is still required for genuine empirical analysis. No source data or papers are copied to GitHub.

## 3. Fast mechanical acceptance test

```bash
"$P" -m unittest discover -s research/tests -p 'test_science_mvp.py' -v
"$P" -m research.factory.paper_sprint demo
```

These generate synthetic data and a real Overleaf-ready ZIP; they do **not** prove a holiday model, validate causal identification, or establish novelty. `PAPER_QC.json` intentionally fails scientific signoff until original-paper, equilibrium, robustness and replication checks are independently completed.

**Current blockers for Holy Days:** full-text source/novelty audit, justified solved game, valid attacker–defender conflict data, honest identification, and human source/proof/results review. Do not publish a synthetic or unreviewed template as a scientific finding.

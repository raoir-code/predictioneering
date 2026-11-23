# RAO CORP Paper Factory — Start Here

**Purpose:** one place to find the next command for any paper, without reconstructing
previous chat sessions. Nothing advances without a human science-quality review.
The factory is a gated research workflow, not a validated autonomous scholar.

## Always start with one command

On the research worktree:

```bash
cd ~/predictioneering-research-test
git pull --ff-only
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m research.factory.guide holy-days
```

Replace `holy-days` with another project slug. The guide is **read-only**:
no Claude calls, payments, approvals, or file modifications. It reports the
current signed workflow stage and the command required next.

## The scientific pipeline

```text
Research puzzle
   ↓ human approval
Literature / candidate contribution
   ↓ human approval (NOT a novelty claim by itself)
Theory blueprint → Claude proposal ↔ human critique ↔ revisions
   ↓ human approval of ARCHITECTURE ONLY
Formal game solution + independent proof checking
   ↓ human approval
Empirical hypotheses
   ↓ human approval
Research design + identification
   ↓ human approval
Authorized real data, validated mappings
   ↓ human approval
Estimation / analysis
   ↓ human approval
Out-of-sample tests / robustness / validation
   ↓ human approval
Manuscript / Overleaf package
   ↓ human approval
Scientific QC and replication review
```

Check the current stage if necessary:

```bash
"$P" -m research.factory.science_mvp status holy-days
"$P" -m research.factory.review_workflow status holy-days
```

**A missing proof, unverified literature gap, or inadequate data is a blocker,
not permission to advance with synthetic or unsupported findings.**

## Theory blueprint: the one interaction you will use frequently

For an already generated blueprint:

```bash
"$P" -m research.factory.theory_fabricator review holy-days \
  --confirm-share-evidence --model claude-opus-5-5 \
  --input-rate 4 --output-rate 20 --max-usd 1.00 --max-tokens 12000
```

The program displays the current blueprint and asks what you want changed.
Enter ordinary-language feedback to generate another Claude revision. Enter
`SHOW` to read the full report or `APPROVE` **only after** you have carefully
reviewed the complete model. Enter `QUIT` to stop without approving.
An `APPROVE CURRENT` override exists only for deliberately signing an older
draft despite a failed newer attempt; use it exceptionally.

The current complete review is private, at:

`research/inbox/raw/scientific_stages/holy-days/theory_blueprint/BLUEPRINT_REVIEW.md`

You may share its text with your reviewer. All successful versions remain in
`history/`; the revision ledger is:

```bash
"$P" -m research.factory.theory_fabricator history holy-days
```

A new paper with no blueprint needs a signed puzzle and literature first; then
use `theory_fabricator brief` and `propose` with a human-chosen baseline.
See `research/SCIENCE_MVP.md` for the complete initial setup.

## What if something breaks?

| Symptom | What to do |
|---|---|
| Claude output is truncated or invalid JSON | The existing blueprint remains. Inspect `attempts/` and try `theory_fabricator recover PROJECT`; if it rejects the saved text, use another `revise` with your feedback. |
| Claude schema rejects the response | Read the saved attempt + diagnostic; fix/replay the proposal or issue a new review revision. Never pretend it is approved. |
| A prior blueprint was accidentally approved | `theory_fabricator reopen PROJECT --reason "Requested correction still missing"`; old signature is archived. |
| Unsure which scientific gate is next | Run `research.factory.guide PROJECT`, which reads current workflow state. |
| Need to change an already approved upstream scholarly input | Use `review_workflow revise PROJECT STAGE --reason "..."`; downstream gates must be invalidated and reviewed again. |
| Git conflicts or local state mismatch | Stop and investigate; don't force-push or overwrite private signed research artifacts. |

## After architecture approval — formal mathematics

The next task is to **derive and independently verify** a formal equilibrium,
not to generate hypotheses. The one-command `guide` walks through three
distinct steps, all bound to the signed blueprint SHA:

**1. Prepare a formal-game contract and verify the constant-power benchmark:**

```bash
"$P" -m research.factory.formal_workbench prepare holy-days
```

Creates `FORMAL_WORK_ORDER.md`, an explicit one-period bargaining/war
contract, an **exact symbolic benchmark identity** showing existence of a
peaceful *stationary Markov equilibrium when holiday power does not change*,
and an unfilled parameter template. No paid API call, no false formal-model
submission.

**2. Run a finite-state numerical smoke test:**

```bash
"$P" -m research.factory.formal_workbench demo holy-days
```

Enumerates 16 pure stationary war/peace policies in one **arbitrary synthetic
four-state cycle**, checks conditional Bellman and best-response residuals,
and writes a human-readable diagnostic. This is **not** a global theorem,
equilibrium uniqueness proof, mixed-strategy analysis or empirical result.
Researcher-chosen cases can be checked via `formal_workbench check holy-days
--case /path/to/numeric_case.json`. The real calendar order and admissible
parameter ranges must be scientifically justified.

**3. Ask Claude to propose, not certify, an analytical derivation:**

```bash
"$P" -m research.factory.formal_reasoner draft holy-days \
  --confirm-share-evidence --model claude-opus-5-5 \
  --input-rate 4 --output-rate 20 --max-usd 1.00 --max-tokens 12000
```

Claude receives the approved architecture and restricted benchmark, not the
entire revision history. It produces `formal_workbench/derivations/
PROOF_REVIEW.md` and an unverified structured draft. Iterate with:

```bash
"$P" -m research.factory.formal_reasoner review holy-days \
  --confirm-share-evidence --model claude-opus-5-5 \
  --input-rate 4 --output-rate 20 --max-usd 1.00 --max-tokens 12000
```

Type natural-language corrections, `SHOW`, or `QUIT`. Typing `APPROVE`
does **not** sign a mathematical result; the proof worker refuses to certify
one. Every successful revision is archived with its source SHA, parent SHA
and researcher feedback. Failed or truncated API responses are saved without
overwriting the prior draft. Claude calls are billable; review and numerical
checks are not.

**If Claude hits the output-token limit:** Its partial text and diagnostic
remain in `formal_workbench/derivations/attempts/`, and earlier drafts are
untouched. Before paying to rerun, try:

```bash
"$P" -m research.factory.formal_reasoner recover holy-days
```

This performs **zero API calls**, verifies the signed blueprint and any
parent draft, and only accepts a COMPLETE valid JSON object within the saved
text. If the text really stops mid-JSON, recovery will explicitly refuse.
Then repeat the `formal_reasoner draft` command above; its revised prompt
now targets a short, checkable initial derivation rather than an exhaustively
long solution in one response. The retry is billable. The `guide` command
points to recovery when it sees an earlier truncated draft.

**Only after a researcher independently audits** all Bellman equations,
unilateral deviations, off-path play, admissible parameter regions, calendar
states and benchmark recovery may a fully argued model JSON be submitted:

```bash
"$P" -m research.factory.science_mvp produce holy-days formal_model \
  --model /path/to/fully_derived_and_checked_game.json
```

The separate `review_workflow` human approval gate still applies.
The symbolic derivative checker in `science_mvp` is conditional on an
asserted equilibrium and **does not certify game-theoretic optimality**.

The command checks structure and symbolic conditions, **not** all equilibrium
claims or novelty. Read the new review packet and use the human
`review_workflow approve` or `revise` gate; do not sign without source and
proof examination. Then run `research.factory.guide holy-days` again.

For the subsequent stages, refer to `research/SCIENCE_MVP.md`. Each stage
requires its own inputs, audit, and separate human signoff; the guide can
identify the next eligible stage but does not fabricate missing data or theory.

**Where we stopped November 23, 2026:** the Holy Days Claude architecture
revision was successfully generated, remains unreviewed, and requires reading
its entire `BLUEPRINT_REVIEW.md` before human approval. It has **not**
produced a proved repeated-bargaining equilibrium.

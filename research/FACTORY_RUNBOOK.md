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

**If a revision instead ends with `The read operation timed out`:** This is
a *network read timeout*, not a model proof or JSON validation result.
The original worker allowed only 120 seconds; the worker now allows
900 seconds for long responses. Timeout may occur without any response
body being returned locally, so `recover` cannot recover that call.
The existing proof draft remains untouched, and a retry may incur a
second API charge. Relaunch `formal_reasoner review PROJECT` and
resubmit the feedback if another revision is warranted.

**4. Run the generalized finite-cycle falsification solver (no API charges):**

```bash
"$P" -m research.factory.formal_solver audit holy-days \
  --cases 400 --seed 20261123 --max-phases 8
```

This compares the unverified Claude war-set equations against an independently
implemented direct Bellman/incentive evaluator across the worked example, a
known **multiple-equilibrium** example, a constant-power benchmark and 400
reproducible synthetic cases. Results are saved privately to
`formal_workbench/FORMAL_SOLVER_AUDIT.md` and `.json`. It enumerates
all `2^N` pure phase-Markov policies for each calendar, supports repeated
ordinary/holiday phases and up to **12** phases in one exhaustive case;
a long real calendar (e.g. 365 days) still requires a scalable algorithm.

`--case /path/to/user_case.json` adds a researcher-specified case using the
signed `PARAMETER_CASE_TEMPLATE.json` schema. No datasets or source papers
are sent to an API. A numerical pass does **not** establish uniqueness,
mixed-strategy existence, non-Markov SPE, a general parameter theorem or
equilibrium selection. If any contradiction appears, inspect the saved
examples and revise mathematics; do NOT approve the formal model. Revisions
to `PROOF_DRAFT.json` invalidate the guide's saved-audit checkpoint.

**5. Prepare a focused mathematical proof and equilibrium-selection review** from
the last solver audit, without another API call:

```bash
"$P" -m research.factory.formal_proof_brief holy-days
```

This validates that the signed blueprint, current unverified Claude proof SHA
and last numerical audit agree, then writes private
`formal_workbench/FORMAL_PROOF_FEEDBACK.txt`. It includes the precise proof
obligations: verify the finite-cycle war-set fixed point and boundaries;
establish or refute general pure-MPE existence; check the unique-peace
sufficient bound; and distinguish predictions that hold in **every** pure
equilibrium from those requiring an explicit equilibrium selection rule.

To **request a new, billable Claude revision**, run the existing interactive
`formal_reasoner review` command above. At `>`, paste the path prefixed
by `@`, e.g. `@research/inbox/raw/scientific_stages/holy-days/formal_workbench/FORMAL_PROOF_FEEDBACK.txt`.
The read-only `formal_proof_brief` command itself neither contacts Claude
nor certifies anything. After Claude revises, rerun the offline numerical
audit: it will be considered stale until reconfirmed against the new
`PROOF_DRAFT.json` SHA. If pure MPEs disagree on onset or war occurrence,
keep those as **set-valued predictions**, not invented numerical probabilities.

**6. Create an unsigned set-valued formal-model handoff (no more fake derivatives):**

```bash
"$P" -m research.factory.finite_war_set_handoff holy-days
```

This **only** writes a private, incomplete `FORMAL_MODEL_HANDOFF_CANDIDATE.json`
pinned to the signed blueprint, current unverified proof and latest passed
offline audit. It preserves war-set multiplicity, refuses to assert general
pure-MPE existence or a selected equilibrium, and leaves `hypotheses: []`
intentionally blank. This is NOT model approval and does not contact Claude.

The next scientific task is to examine the proof critically, specify at
least one **substantively defensible** hypothesis explicitly labeled
`selection_invariant` or `conditional_on_equilibrium`, and justify its
empirical sign, assumptions and construct mapping. For conditional predictions,
the approved research design must state substantive
`design.equilibrium_scope_conditions`; an unconditional probability cannot
be reverse-engineered from multiple pure war sets.

**7. Screen the theory-to-empirics restrictions without forcing a sign:**

```bash
"$P" -m research.factory.formal_hypothesis_review holy-days
```

This writes private `HYPOTHESIS_REVIEW.md` and `.json` beside the handoff,
pinned to the current candidate, proof SHA and numerical audit. It lists the
constant-power peace case, sufficient unique-peace region, necessary conditions
for A-driven and B-driven war, and a multiple-equilibrium example. These are
**researcher-reviewable structural implications, not estimated coefficients
or signed empirical hypotheses**. It also records measurement and identification
obstacles, especially the lack of a universal positive holiday-onset effect.
No source data is fetched, no claim is signed, and no model is approved.

Only after the human-reviewed candidate has those fields populated may the
researcher submit it to the **existing** formal-model approval gate:

```bash
"$P" -m research.factory.science_mvp produce holy-days formal_model \
  --model research/inbox/raw/scientific_stages/holy-days/formal_workbench/FORMAL_MODEL_HANDOFF_CANDIDATE.json
```

The adapter checks the *consistency and provenance* of the draft, not the
correctness of its equilibrium proof or its prediction sign. The analyst must
review the generated `FORMAL_CHECKS.md` before approving. Then the project
continues through hypotheses, prespecified design, private observed data,
analysis, validation, manuscript and scientific QC. **The later manuscript
renderer still needs a discrete-war-set-aware adaptation; do not claim the
new handoff alone makes the complete Overleaf package work.**

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

**Current Holy Days milestone, November 23, 2026:** the research architecture
is signed and Claude has produced a revised, **UNVERIFIED** mathematical
derivation. The offline solver enumerated 26,032 pure policy masks over 403
synthetic cases: no numerical contradictions, seven instances of multiple
pure MPE, and no cases without a pure MPE. This is not a general existence
proof, a unique equilibrium, or empirical evidence. The set-valued model
handoff can now prepare a private **incomplete** model candidate; explicit
hypotheses, scientific review, source-validated real data, estimation,
validation and final Overleaf manuscript work remain outstanding.

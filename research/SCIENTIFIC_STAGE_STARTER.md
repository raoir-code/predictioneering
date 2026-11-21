# Research Factory v0.8 — guarded puzzle and PDF-literature stage starters

**Scope:** Research-only code in draft PR #1. This is **not** an automated scientific critic, a claim of novelty, or a finished research project. It performs no network/API calls and does not access, change, or reconfigure production forecasts.

## Start Holy Days at its **puzzle** checkpoint

After `review_workflow init holy-days --title 'Holy Days and War'`, run:

```bash
cd ~/predictioneering-research-test
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m research.factory.stage_starter puzzle holy-days --holy-days
```

The worker first checks `review_workflow.require_ready('puzzle')`. It reads the **actual versioned local research notes** `research/examples/holy_days_repeated_bargaining_model_v0.md` and `research/HOLIDAY_FAST_START.md`. If their key cautionary text disappears or the source files are missing, it stops rather than inventing a new scientific finding. It saves a puzzle proposal and hash/line-linked provenance to `research/inbox/raw/scientific_stages/holy-days/puzzle/` (ignored by Git). Then `review_workflow.submit` makes an independently checkable snapshot and changes the puzzle stage to `awaiting_critique`.

Inspect the generated human review packet:

```
research/projects/factory_runs/holy-days/human_gates/review_packets/puzzle.md
```

The private file `INDEPENDENT_CRITIC_REQUEST.json` is **instructions for obtaining** an independent review. It is **not** a critique and **cannot** be passed as a review to approve the stage. A different human or an explicitly authorized independent AI critic must read the actual sources and write a substantive JSON review in the structure of `research/examples/INDEPENDENT_CRITIQUE_TEMPLATE.json`.

Record that real critique and then decide:

```bash
"$P" -m research.factory.review_workflow critique holy-days puzzle --report /path/to/actual_critic_review.json
"$P" -m research.factory.review_workflow status holy-days
# You, not an agent, must decide whether to approve, revise or reject.
```

If the critique identifies gaps, **revise** rather than approve. A human approval of puzzle *framing* is not approval of the model, literature, data, causal inference, or manuscript. After puzzle approval, `diagnosis` becomes ready; it still requires its **own** source-grounded artifact, independent critique and human signoff.

## Literature worker, only **after** puzzle AND diagnosis approvals

After the actual `literature` stage becomes ready, edit `research/examples/HOLY_DAYS_LITERATURE_QUERIES.json` as needed and run:

```bash
"$P" -m research.factory.stage_starter literature holy-days \
    --spec research/examples/HOLY_DAYS_LITERATURE_QUERIES.json \
    --db research/datasets/private/research_library.sqlite3
```

This invokes the existing `puzzle_evidence.assemble` against the **local indexed, page-checked PDF evidence**. It records the precise PDF file hash, page, evidence ID and review status; deduplicates passages and includes multiple paper candidates. It **does not** search the web, retrieve missing PDFs, summarize the complete papers, or verify novelty. If the local index is absent or returns no passage, the worker writes a **private blocked report** and does not submit/approve the literature stage. Otherwise it submits the candidate evidence for a separate critical full-text review, with human approval still mandatory. Only source documents actually indexed in the Mac PDF library are covered.

## Scientific limitations

The Holy Days local note itself says the static bargaining benchmark predicts **peace**, that a distinct repeated-game friction is required for attack timing, and that H1 is a **country/event-level exploratory** measure, not a directed-belligerent causal estimate. We must decide whether the paper is about own-holiday restraint, opponent-holiday opportunism, or actual negotiated truces; each requires different outcomes and possibly different data. This worker intentionally preserves those unresolved choices.

No independent AI critique is fabricated or automatically paid. These two stage adapters **only** perform puzzle framing and page-verified preliminary literature retrieval. The actual `diagnosis`, comprehensive external literature acquisition, adversarial scholarly synthesis, formal model solution, and data discovery remain to be connected behind the existing 12 approval gates. After the user approves each stage, new work begins at the next stage; older accepted science remains frozen.

## Verification

```
"$P" -m unittest discover -s research/tests -q
"$P" -m research.factory.review_workflow status holy-days
```

The new `test_stage_starter.py` includes ten tests, including one test using the actual approval controller when running inside the full repository. Its no-controller fallback skips that integration test rather than claiming it ran.

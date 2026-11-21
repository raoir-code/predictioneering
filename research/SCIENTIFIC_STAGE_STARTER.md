# Research Factory v0.8 — guarded puzzle and PDF-literature stage starters

**Scope:** Research-only code in draft PR #1. This is **not** an automated scientific critic, a claim of novelty, or a finished research project. It performs no network/API calls and does not access, change, or reconfigure production forecasts.

## Start Holy Days at its **puzzle** checkpoint

After `review_workflow init holy-days --title 'Holy Days and War'`, run:

```bash
cd ~/predictioneering-research-test
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m research.factory.stage_starter puzzle holy-days --holy-days
```

The worker first checks `review_workflow.require_ready('puzzle')`. It reads the **actual versioned local research notes** `research/examples/holy_days_repeated_bargaining_model_v0.md` and `research/HOLIDAY_FAST_START.md`. If their key cautionary text disappears or the source files are missing, it stops rather than inventing a new scientific finding. It saves a puzzle proposal and hash/line-linked provenance to `research/inbox/raw/scientific_stages/holy-days/puzzle/` (ignored by Git). Then `review_workflow.submit` makes an independently checkable snapshot and changes the puzzle stage to `awaiting_human_approval`.

Inspect the generated human review packet:

```
research/projects/factory_runs/holy-days/human_gates/review_packets/puzzle.md
```

**Your approval is now the only required gate.** No independent AI reviewer is needed to approve the puzzle. Run `review_workflow review holy-days puzzle` to view the full report preview and then `approve` or `revise` with your own instructions. Optional independent criticism can be supplied via `critique --report` if useful. The worker does not make a paid model call.

After puzzle approval, the new `stage_starter diagnosis holy-days` produces a source-constrained diagnostic report and stops for your review again. Re-running an unchanged templated puzzle or diagnosis after you request revisions is deliberately blocked; export `review_workflow revision-brief`, have an authorized researcher or agent repair the scientific document, and resubmit. Original source data, proof and novelty remain unverified.

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

No independent AI critique is fabricated or automatically paid. These three stage adapters cover **puzzle framing, constrained diagnosis, and preliminary local-PDF literature retrieval**. Comprehensive external literature acquisition, full-text synthesis, formal equilibrium solving, automatic scientific revisions, and data discovery remain to be connected behind the existing 12 approval gates. After the user approves each stage, new work begins at the next stage; older accepted science remains frozen.

## Verification

```
"$P" -m unittest discover -s research/tests -q
"$P" -m research.factory.review_workflow status holy-days
```

The new `test_stage_starter.py` includes ten tests, including one test using the actual approval controller when running inside the full repository. Its no-controller fallback skips that integration test rather than claiming it ran.

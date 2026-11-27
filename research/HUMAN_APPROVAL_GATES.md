# Research Factory — human-controlled scientific checkpoints (v0.9)

**The only mandatory gate is the researcher's explicit approval.** Independent AI review is optional and advisory. Every orchestrated stage produces a readable scientific artifact and an approval packet, then stops. The factory never approves on your behalf. Local approvals and raw data stay in ignored `research/projects/` and `research/inbox/`; the forecasting engine and production branch remain untouched.

## Run your existing Holy Days project

From `~/predictioneering-research-test`:

```bash
P="$HOME/.venvs/predictioneering-research/bin/python"
git pull --ff-only
"$P" -m unittest discover -s research/tests -q
"$P" -m research.factory.review_workflow review holy-days puzzle
open research/projects/factory_runs/holy-days/human_gates/review_packets/puzzle.md
```

The report now **embeds the submitted Markdown scientific work** (a bounded preview) and links directly to its frozen complete snapshot. The previous `awaiting_critique` status is recognized as *awaiting your decision*; do **not** reinitialize or resubmit Holy Days. The file `PUZZLE_REVIEW.md` is the substantive puzzle proposal, not independent literature or empirical evidence.

After you have actually reviewed the report, choose one:

```bash
# Your own approval, no AI reviewer needed:
"$P" -m research.factory.review_workflow approve holy-days puzzle --reviewer Researcher --notes 'Fine to investigate'

# OR request a substantive revision, without approving:
"$P" -m research.factory.review_workflow revise holy-days puzzle --reason 'Separate own-holiday restraint from opponent-holiday opportunity; redo the framing'

# For a revision, export a source-linked work order for the next worker:
"$P" -m research.factory.review_workflow revision-brief holy-days puzzle
```

The revision brief preserves your exact instructions, prior snapshot hashes, stage-specific checks, and approved dependencies. **Exporting it does not itself redo the science.** A researcher or authorized AI worker must produce a changed artifact and submit it for your next review. The old approved work remains frozen; only dependent later stages become stale. `reject` is also supported.

On approval of the puzzle, advance exactly **one** stage:

```bash
"$P" -m research.factory.stage_starter diagnosis holy-days
"$P" -m research.factory.review_workflow review holy-days diagnosis
open research/projects/factory_runs/holy-days/human_gates/review_packets/diagnosis.md
```

The diagnosis currently uses the approved Holy Days source note and clearly labels unverified empirical/theory claims; it is not a validated original research result. You again choose approve or revise. After diagnosis approval, the existing `stage_starter literature` can screen page-linked local Zotero PDFs; it requires an explicit literature-search specification and a populated private PDF database. That is a **source shortlist**, not a full scholarly synthesis or established novelty.

## Complete stage sequence

`puzzle → diagnosis → literature → novelty → formal_model → hypotheses → data → design → analysis → validation → manuscript → qc`

After *each* stage: **generate research → view report → approve/revise → only then unlock next stage**. Reports show what was produced, actual content where safe, source-provenance links, checks, open questions, optional reviewer comments, revision instructions, and approval decision. The immutable-by-convention snapshots are SHA256-verified and approvals bind to upstream tokens. An approved revision invalidates only descendants (e.g., changing a formal model does not discard unrelated prior literature).

### Optional second opinion

An independent review may still be submitted with `review_workflow critique PROJECT STAGE --report private_review.json` before your decision. Its conclusions appear in the packet but **cannot block your approval**. AI review is **not** secretly run or billed. The deprecated `--override-critic` flag is unnecessary.

### Guarded analysis and manuscript

Existing guarded commands continue to enforce the unchanged data/spec/formal-model approvals:

```bash
"$P" -m research.factory.review_workflow produce holy-days analysis --spec /path/to/approved_study.json
"$P" -m research.factory.review_workflow produce holy-days manuscript --spec /path/to/approved_study.json --formal-model /path/to/approved_model.json
```

They operate **only after all relevant earlier stages are approved**, submit results for *your* review, and never automatically proceed. For analysis, `data` approval must include the private `data_manifest.json` with the exact CSV SHA256; `design` must include the exact study spec. For manuscript, `formal_model` must include the exact model JSON, and analysis results must be unchanged since approval. Do not put restricted raw ACLED data into the project ZIP or GitHub.

## Status and limits

The controller and its tested adapters now cover **puzzle framing, Holy Days theoretical diagnosis, local-PDF literature screening, Python analysis, and Overleaf manuscript packaging**. Other stages can be submitted manually with substantive sourced artifacts and signed off using the same gates. **Automated full-text literature synthesis, original equilibrium solving/proof auditing, dataset discovery, autonomous content revisions, validation, and manuscript scientific QC are not yet connected.** Those require new research workers and further tests. Legacy stand-alone research commands do not automatically inherit the gates; use the guarded entrypoints for real research.

Run the full research suite with `"$P" -m unittest discover -s research/tests -q`. These are engineering tests, not a certification of scientific novelty or conclusions.

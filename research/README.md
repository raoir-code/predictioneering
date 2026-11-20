# Predictioneering Research Factory — Phase 1 (Puzzle Finder)

**Isolated addition:** The `research/` package does not import or modify the forecasting
engine, forecasting configuration, DAG parameters, or existing pipelines. There is
no automation that writes to Predictioneering model files.

The current Phase 1 ingests a work log or diagnostic text file, asks Claude to
identify 0–3 possible research puzzles, and saves local puzzle cards for a
researcher's approval or rejection. These cards are **ideas, not established
findings**; claimed novelty is explicitly unverified. No papers or predictions
are generated in this phase.

## Before you run it

From your existing repository root, set API credentials **in your shell**, not
in tracked files. A Claude chat subscription does not automatically include
Anthropic API credits.

```bash
export ANTHROPIC_API_KEY='YOUR_ANTHROPIC_API_KEY'
export CLAUDE_MODEL='YOUR_AVAILABLE_MODEL_ID'
```

This first version uses only the Python standard library (no new dependencies).

## Run

```bash
python -m research.factory ingest /path/to/worklog.md --kind worklog
python -m research.factory ingest /path/to/diagnostic.txt --kind diagnostic
python -m research.factory list
python -m research.factory show PUZZLE_ID
python -m research.factory approve PUZZLE_ID
python -m research.factory reject PUZZLE_ID
python -m unittest discover -s research/tests -v
```

**Human checkpoint:** The Puzzle Finder proposes cards, but will not start a
research project without explicit approval. A literature-review module can be
added later without changing the intake interface.

## Privacy and reliability

- Private work logs, processing records, and project cards stay local under
  ignored `research/inbox/` and `research/projects/` directories; never commit
  work logs or API keys to this **public** GitHub repository.
- Complete logs are fingerprinted so rerunning a successful log creates no
  duplicate call or charge. Incomplete/failed processing may be retried.
- Source snapshots and state files are written atomically. Card identifiers are
  deterministic, preventing duplicates after partial failures.
- Source quotations are checked against the original text. Missing/mismatched
  quotations are flagged as unverified rather than presented as evidence.
- Failed Claude API calls preserve a local error status for debugging.
- Automated tests mock Claude; a real API call has **not** been verified yet.
- This tool processes a *supplied* Markdown/plain-text log. Automatic discovery
  of logs and diagnostics is intentionally deferred to the next phase.


## First end-to-end empirical paper candidate

For the **Holy Days and Hard Bargains** multiyear ACLED own-holiday H1 screen, see [HOLIDAY_FAST_START.md](HOLIDAY_FAST_START.md). It automates a cached 2022–2025 local ACLED extraction, calendar construction, a zero-inclusive daily panel, and an exploratory Poisson estimate in one command. Requires the Python packages in research/requirements.txt. This study is explicitly **non-causal and not a validated dyadic opponent-holiday estimate**.

For its theoretical benchmark and necessary bargaining frictions, see [holy_days_repeated_bargaining_model_v0.md](examples/holy_days_repeated_bargaining_model_v0.md). Neither this extension nor the existing research factory modifies production forecasting code.


## Integrated research factory v0.2

The integrated **local, approval-gated** runner is documented at [FACTORY_PIPELINE.md](FACTORY_PIPELINE.md). Run `python -m research.factory.pipeline demo` to test intake-to-paper wiring on explicitly synthetic data. Use `python -m research.factory.pipeline register /path/to/puzzle.json` to import a researcher-authored puzzle without a model call, or `python -m research.factory.pipeline run 16_HEX_INTAKE_CARD_ID` to advance an already intake-approved card. The runner queries only the **local** Zotero/hazard index and stops for a human original-paper novelty check and a researcher-supplied empirical design; repeating `run` resumes the analysis and draft generation after those gates. `python -m research.factory.pipeline batch` advances approved cards to their next gate. No paid API or public upload is performed.


## Weekly factory operation (offline v0.3)

See [WEEKLY_FACTORY.md](WEEKLY_FACTORY.md) for the safe `python -m research.factory.weekly` command. The weekly runner inventories an explicitly supplied local inbox, registers researcher-written JSON puzzle briefs as **pending approval**, advances existing approved cards through the integrated local pipeline, writes private checkpoint reports, and can generate an **uninstalled** Mac launchd schedule file. It does not invoke Claude or ingest forecasting logs on its own; novelty, data/design and publication gates remain mandatory.

# Research Factory v0.4 — actual forecast miss discovery

**Purpose:** Bridge production's resolved forecast log to the isolated, human-gated Research Factory. The scanner does not touch production code or logs, use Anthropic, or make external requests. Its output is a diagnostic queue, **not** established theory.

## Run against real resolved markets

From the research checkout:

~~~bash
cd ~/predictioneering-research-test
git pull --ff-only
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m unittest discover -s research/tests -q
"$P" -m research.factory.forecast_misses --brier-log predictions/brier_log.jsonl
open research/inbox/forecast_misses/README.md
~~~

The last command reads the production resolver's existing resolved Brier JSONL and generates local, gitignored MISSES_SCREEN.json and README.md in research/inbox/forecast_misses/. It independently recomputes model and market squared errors from conditional_p, market_p_at_first, and outcome, rather than trusting cached score fields.

**A critical scientific caveat:** A forecast timestamp before the *market's resolution* does not establish that the forecast preceded the underlying real-world event. Market prices logged as paired with the model are also not independently timestamp-verified. Reports are suitable for triage, **not** a fair, publishable Brier competition.

## What the scanner evaluates

- Resolved binary contracts with valid probabilities, timestamps and unique IDs; excludes malformed, unresolved, conflicting-resolution or post-resolution forecasts.
- Predeclared slices of contract type, translator relation, dyad, and event-topic keyword. Default minimum support is 5 contracts and 3 potential independent event families.
- Model Brier, logged-market Brier, false-negative and false-positive counts, family-average excess Brier and extreme failures. A screen requires average family excess Brier of at least 0.04 and 2 extreme model losses.
- Approximate sibling contracts: same dyad/question template and resolution dates within 3 days. These are **possible** duplicates, not verified independent event identities; contract and family counts are both disclosed.
- Up to 6 top diagnostic candidates by default. The associated mechanism is deliberately described as UNKNOWN, with coding, timing, ontology and calibration alternatives.

Do not treat a high-ranked miss slice as proof of an IR theoretical gap. Results are post hoc, overlapping and subject to multiple-testing and dependent-contract concerns.

## Create candidate puzzle cards and run the next Factory stage

After inspecting the diagnoses, explicitly register them as **pending** human intake cards:

~~~bash
"$P" -m research.factory.forecast_misses \
  --brier-log predictions/brier_log.jsonl --register
"$P" -m research.factory list

# For a genuinely substantive and verified candidate only:
"$P" -m research.factory show PUZZLE_ID
"$P" -m research.factory approve PUZZLE_ID
"$P" -m research.factory.pipeline run PUZZLE_ID
~~~

Registration is stable and idempotent; approval is **never** automatic. The integrated runner then retrieves local Zotero/hazard literature candidates, prepares the theory and design workbooks, and blocks on independent full-text novelty review. Once a researcher supplies a defensible design, dataset and necessary approvals, the existing estimation/OOS/manuscript machinery resumes. See FACTORY_PIPELINE.md.

## Optional weekly feed

The weekly runner accepts the forecast log only when explicitly supplied. Default weekly runs never touch production logs.

~~~bash
mkdir -p research/inbox/weekly

# Safe preview: does not register cards
"$P" -m research.factory.weekly plan --inbox research/inbox/weekly \
  --brier-log predictions/brier_log.jsonl

# Opted-in weekly pass, registering new pending diagnostic cards
"$P" -m research.factory.weekly run --inbox research/inbox/weekly \
  --brier-log predictions/brier_log.jsonl \
  --register-miss-candidates --execute
~~~

No background scheduling is installed by these commands; existing launchd files are unchanged. No paid API calls, licensed raw notes, or live scraping are involved. The next scientific milestone is fair pre-event timestamp verification, dependent-contract adjudication, independent theory/novelty assessment, and prospective holdout evaluation.

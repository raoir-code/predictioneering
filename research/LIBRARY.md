# Research Factory: Local Knowledge Library (Phase 2A)

The library index is **local and private**. It does not edit Zotero or any
Predictioneering forecasting files. It uses Python's built-in SQLite module.

## One-time setup from your Mac

In your **isolated research checkout**:

```bash
cd ~/predictioneering-research-test
git pull --ff-only
python3 -m unittest discover -s research/tests -v

python3 -m research.factory.library import \
  --zotero ~/Downloads/conflict_predict_Zotero_JSON.json \
  --hazards ~/Downloads/conflict_hazard_library_v1.0.csv

python3 -m research.factory.library stats
python3 -m research.factory.library search "ceasefire"
```

If either export is stored elsewhere, substitute its actual path.
The database is written to **`research/datasets/private/research_library.sqlite3`**,
a directory excluded by `research/.gitignore`. Do not commit the raw exports,
the local database, private PDFs, or API credentials to this public repository.

## Run the leaky-ceasefire pilot

First, test retrieval without spending Claude API credits:

```bash
python3 -m research.factory.library_review \
  research/examples/leaky_ceasefire.json --local-only --retrieve-only
```

Next, add OpenAlex discovery, still without calling Claude:

```bash
python3 -m research.factory.library_review \
  research/examples/leaky_ceasefire.json --retrieve-only
```

For a **preliminary literature synthesis**, run with `ANTHROPIC_API_KEY`
and `CLAUDE_MODEL` securely set in your local shell:

```bash
python3 -m research.factory.library_review research/examples/leaky_ceasefire.json
```

OpenAlex may require an API key depending on usage rules. Set an optional
`OPENALEX_API_KEY` locally. If external search fails, locally indexed Zotero
records remain usable, **and the review is flagged as incomplete**.

## What this system knows — and does not know

- Zotero CSL JSON has bibliographic metadata and some abstracts, **not attached PDFs**.
- Hazard CSV stores all rows and original coefficient, SE, p-value, model type,
  sample flag, and raw source columns. These estimates have different
  outcomes/models and must **not** be pooled, treated as causal, or automatically
  used as adjustment covariates.
- Relevant source candidates are retrieved from Zotero first; OpenAlex supplies
  additional candidates. Claude examines candidate metadata/abstracts only.
- Local matching is deliberately inexpensive, lexical, and not equivalent to
  expert bibliographic search. Inspect false positives and missed seminal work.
- Every proposed literature gap remains **unverified** until a researcher reads
  the closest full-text papers and explicitly approves the contribution.

## Reliability / cost

- Imports track input SHA-256. Re-importing unchanged files does nothing.
- Re-importing updated files replaces their prior records transactionally.
- Failed imports leave previously indexed records untouched.
- Literature results cache locally; successful repeated runs avoid duplicate
  calls. A changed source file or research specification triggers a fresh scan.
- `--retrieve-only` does no Claude synthesis; `--local-only` does no OpenAlex
  network search. Use both to debug at zero API cost.

## Pilot caveat

The supplied Zotero export has 1,002 references, including 548 abstracts.
The supplied hazard CSV has 847 estimates from 99 studies, of which 573 are
flagged for its analysis sample. The Zotero records include the ETH/PRIO
ceasefire dataset paper but little directly targeted ceasefire scholarship.
The hazard file does not currently contain directly labeled ceasefire estimates.
External paper discovery and full-text verification therefore matter.

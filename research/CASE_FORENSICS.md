# Predictioneering Research Factory — forensic dossiers + optional Claude diagnostic v0.5

## What was actually implemented

Two **research-only** components. `case_dossiers` reads resolved outcomes, individually
logged forecasts **when available**, partial historical node traces and market
metadata without changing any of those files. It produces private, source-hashed,
**time-partitioned** evidence dossiers. It never concludes that a historical DAG
node caused an error or that an undated/retrospectively retrieved market-rule
record was known earlier. `diagnostic_critic` prepares a skeptical structured
Claude assessment and rejects invented source IDs, unsupported publication
claims and unjustified puzzle advancement. Neither auto-registers nor approves
scientific puzzles or changes Predictioneering production.

## Run on actual local forecasting history — no APIs

From the isolated research checkout:

```bash
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m unittest discover -s research/tests -q
"$P" -m research.factory.case_dossiers \
  --brier-log predictions/brier_log.jsonl \
  --predictions-log predictions/log.jsonl \
  --node-history pipeline/node_score_history.jsonl \
  --market-meta pipeline/market_meta.json \
  --top 4
"$P" -m research.factory.diagnostic_critic \
  research/inbox/forecast_misses/CASE_DOSSIERS_PRIVATE.json
```

The dossier command writes `research/inbox/forecast_misses/CASE_DOSSIERS_PRIVATE.json`
(gitignored). The critic command by default **only previews** the evidence
package; it cannot invoke an API without further authorization.
To reconstruct a specific case, use `--market-id MARKET_ID` (repeatable, max 12).
The default four are **top positive excess Brier candidates** with approximate
sibling deduplication, not a scientific claim of four independent events.

**Known gap:** The `predictions/log.jsonl` currently committed on GitHub is
empty; your local Mac may have more data. If absent/empty, the dossier labels
individual forecast and actual-model reasoning as **unverified**. Historical
node traces do not prove which variables or code were actually used. An
existing resolver `first_prediction_ts` is not event occurrence time. Do not
resort to the current codebase to hallucinate historical model states.

## Optional evidence you can add without exposing raw licensed texts

`--news-manifest /path/to/news.json` is a **local list** of *sourced* metadata:

```json
[
  {"id":"news-001","title":"Example contemporaneous reporting",
   "url":"https://example.org/story","published_at":"2026-10-01T14:00:00Z",
   "retrieved_at":"2026-11-21T16:00:00Z","dyad":"Iran-Iraq",
   "license":"metadata-only"}
]
```

The factory sorts news by `published_at` relative to the **forecast time**,
keeps undated links separate, and says published-before is **not proof that the
engine read the article**. It does **not** automatically fetch or fact-check
news, ACLED, newspaper archives or academic articles yet. Only URL/title/date
metadata are included, not copied paid article contents. Filter via optional
`market_id`/`dyad` fields. A human must confirm correct article version/event
time. Use separate manifests for sources and independent control cases.

`--model-context /path/to/model_context.json` optionally accepts an array
of versioned, independently timestamped model snapshots:

```json
[
 {"id":"recorded-model-001","captured_at":"2026-10-01T10:00:00Z",
  "code_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "summary":"Historically captured model assumptions (not a verified causal attribution)",
  "assumptions":["Explicit source-backed assumption"]}
]
```

Only context with a verifiable `captured_at` **before the forecast** is shown
as historical. The tool cannot independently verify a snapshot date or code
hash against a Git history; these inputs still require review.

## Opt-in Claude investigative stage

Do **not** run it until historical evidence and news links have been reviewed.
The CLI has no live browser. First inspect the default offline plan. To make
one **explicitly paid** request, set `ANTHROPIC_API_KEY` and `CLAUDE_MODEL` in
your private environment. Read the **current** Anthropic API price per million
input/output tokens for that model, then supply those rates yourself:

```bash
"$P" -m research.factory.diagnostic_critic \
  research/inbox/forecast_misses/CASE_DOSSIERS_PRIVATE.json \
  --send-to-claude --confirm-share-evidence \
  --input-rate YOUR_CURRENT_INPUT_RATE \
  --output-rate YOUR_CURRENT_OUTPUT_RATE \
  --max-usd YOUR_REQUEST_BUDGET
```

The command sends **curated case metadata**, never raw licensed articles or
entire forecast histories. A conservative payload-length budget screen prevents
accidental over-budget requests but is not an API billing guarantee. The reply
is schema-checked; fabricated source IDs and unsupported puzzle advancement
fail. Actual API usage tokens and **estimated** cost at user-supplied rates
are saved in `research/inbox/forecast_misses/CLAUDE_DIAGNOSIS_PRIVATE.json`.
Identical completed requests reuse cache without another API charge.

## Critical outstanding work

1. Historical source capture: contemporaneous versions of market rules, model
   code, DAG weights, input evidence, and original forecast logs.
2. Targeted dated news acquisition and reliable event-time verification, with
   licensure and archival provenance.
3. Independent game-theory/library retrieval and matched successes, not just
   failures. Only then should a human decide whether a generalizable research
   puzzle exists.

No live Claude request or automatic historical news retrieval was performed
while developing this module. Tests are synthetic/offline; run the actual
command on your Mac to inspect real coverage.

# Phase 1c — Cached scientific paper profiles (opt-in Anthropic API)

The 137 conflict PDFs are indexed with private, page-numbered text.
This stage creates lightweight evidence cards for each paper. Each card groups
research questions, theories, mechanisms, formal models, assumptions, hypotheses,
designs, findings, and limitations under page-linked quotations from the original
PDF text. **These are machine-extracted provisional notes, not independently
verified scientific claims or mathematical proofs.**

## Zero-cost preview (do this first)

~~~bash
cd ~/predictioneering-research-test
git pull --ff-only
python3 -m unittest discover -s research/tests -v

python3 -m research.factory.paper_profiles plan \
  --folder "$HOME/Desktop/Grad School/Predictioneering/Conflict" \
  --file "Bas and Coe" --model "planning-only"
~~~

The preview does not call Claude or send PDF text anywhere. It reports
the pages, API-call estimate and characters that would be sent. For accurate
per-model caching checks, use a real available model ID instead of planning-only.

## Optional: explicitly approved, paid single-paper pilot

The following commands SEND PAPER PASSAGES to the Anthropic API and incur
usage-based charges. Only run when comfortable with source access terms and
sending this text to Anthropic:

~~~bash
export ANTHROPIC_API_KEY='YOUR_API_KEY'
export CLAUDE_MODEL='YOUR_AVAILABLE_MODEL_ID'

python3 -m research.factory.paper_profiles plan \
  --folder "$HOME/Desktop/Grad School/Predictioneering/Conflict" \
  --file "Bas and Coe" --model "$CLAUDE_MODEL"

python3 -m research.factory.paper_profiles run \
  --folder "$HOME/Desktop/Grad School/Predictioneering/Conflict" \
  --file "Bas and Coe" --limit 1 --max-calls 10 --send-to-claude

python3 -m research.factory.paper_profiles show "Bas and Coe"
python3 -m research.factory.paper_profiles search "preventive war"
~~~

Without --send-to-claude, run refuses API calls. The default --limit 1 processes
at most one paper. The default --max-calls 10 caps attempted paid requests for
that run, not dollar spending. If a paper requires more calls, it is deferred.
Usage output includes input/output tokens; actual cost depends on model pricing.

## How it works

- Every indexed text page is included in a chunk; no abstract-only truncation.
- Claude extracts quotations and preliminary claim categories per chunk.
- A quotation must match the indicated PDF page or the evidence is rejected.
- Every successfully validated chunk is cached locally. After failure, completed
  chunks are reused without further model calls.
- A full paper profile is saved only after all text chunks are processed.
- Paper profiles can be searched locally with zero API calls.
- Expensive puzzle-specific research and novelty checking are separate stages.

## Cautions

Quotation verification means the quoted text appears on the cited PDF page;
it does NOT establish that Claude's interpretation is scientifically correct.
PDF extraction loses some equations, figures and tables. Mathematical model
reconstruction and empirical claims require checking the original typeset PDF.
Absence from an automated card does not establish absence from the paper.
PDF page indexes are different from printed journal pagination.

The repository stores only code and tests. Extracted text, raw model responses
and profiles stay in the ignored, private local SQLite database:
research/datasets/private/research_library.sqlite3. Original PDFs are never
modified, and live forecasting code and main branch are untouched.
Before bulk processing, evaluate one real paper profile and its API usage.


## Recovery from incomplete JSON in the first pilot

The initial Bas and Coe run made seven Anthropic calls and stopped on an invalid
JSON reply before saving the complete profile. Successful earlier chunks should
remain cached in the private database. Do **not** delete that database or
change the model ID. The updated adapter now requests schema-constrained JSON,
uses a larger output ceiling, flags max-token truncation, and reports usage even
when the API returns invalid or truncated text.

~~~bash
cd ~/predictioneering-research-test
git pull --ff-only
python3 -m unittest discover -s research/tests -v

# Free: verify the exact model's surviving cached chunks first.
python3 -m research.factory.paper_profiles plan \
  --folder "$HOME/Desktop/Grad School/Predictioneering/Conflict" \
  --file "Bas and Coe" --model "$CLAUDE_MODEL"
~~~

Expected with unchanged model and PDF: **6 cached of 8**, requiring **2 new
calls**. If the preview instead shows zero cached, do not run the paid command:
check that CLAUDE_MODEL is identical to the previous run, and that the database
and PDF inventory were not replaced or re-imported.

If you explicitly approve those remaining API calls:

~~~bash
python3 -m research.factory.paper_profiles run \
  --folder "$HOME/Desktop/Grad School/Predictioneering/Conflict" \
  --file "Bas and Coe" --limit 1 --max-calls 3 --send-to-claude

python3 -m research.factory.paper_profiles show "Bas and Coe"
~~~

This is a paid operation that transmits the outstanding PDF passages to
Anthropic. With matching cache keys the already saved six chunks are not
sent again. Verify all claims against the original PDF afterward.

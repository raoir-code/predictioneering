# Station 2 — Literature discovery (pilot)

**Purpose:** Compare an approved puzzle against scholarly metadata, identify potentially
relevant explanatory camps, and identify papers requiring human full-text review.

**This is a novelty screening tool, not a completed literature review.** OpenAlex
may miss important publications; abstracts cannot establish what a paper
actually proves, and Claude can misread abstracts. The output is explicitly
`needs_full_text_and_human_review`. Do not describe a proposed gap as proven.

## First test — leaky ceasefires

From the local, isolated research-branch checkout, with your Anthropic API
credentials still in your current terminal session:

```bash
python3 -m unittest discover -s research/tests -v
python3 -m research.factory.literature research/examples/leaky_ceasefire.json
```

The optional `OPENALEX_API_KEY` increases OpenAlex's API budget; basic searches
can use its keyless allowance. Never paste either API key into a chat or commit
it to the public repository.

The scanner searches up to four phrases, deduplicates records, saves sources
and a preliminary gap map locally under ignored `research/inbox/` paths, and
resumes after failures without fetching the same bibliography again.

**Research QC:** Every AI-proposed source reference is checked against retrieved
OpenAlex IDs. Unsupported IDs fail the stage. The metadata may be inaccurate
or incomplete, so the researcher must read the most relevant original articles
before deciding whether the puzzle is novel. Original work, datasets, and
substantive claims are NOT verified by this module.

The new code has no authority to change live Predictioneering forecasts.

# Phase 1e — Scale the scientific-profile library safely

This stage follows the successful 50-page Bas–Coe pilot and the source-level
audit. It does not require supplemental mathematical proofs before continuing
exploratory research. All model-extracted profiles remain provisional until
claims are checked against original sources.

## First: free three-paper pilot plan

~~~bash
cd ~/predictioneering-research-test
git pull --ff-only
python3 -m unittest discover -s research/tests -q

python3 -m research.factory.library_batch plan \
  --folder "$HOME/Desktop/Grad School/Predictioneering/Conflict" \
  --model "$CLAUDE_MODEL" \
  --max-papers 3 --max-calls 20 --order theory
~~~

This makes ZERO API calls. It reads the private indexed PDF text and model
cache, then returns current-profile counts, a shortlist, exact remaining
uncached chunk/API-call counts and source characters, and per-paper OPTIONAL
PAID shell commands. It skips completed profiles for this model and prefers
partially cached papers to avoid duplicate processing.

The title-based theory relevance score is only a heuristic. It does not
establish novelty, evidentiary quality or research value. Alternative flags:
--order smallest (minimize calls) or --match "bargaining" (restrict candidates).

The hard cap is 20 suggested paid requests, not 20 USD. Output token
charges depend on model pricing. If a paid model call fails, successful
previous chunks remain cached. A different model or source revision may
invalidate cache reuse.

## Optional explicit paid pilot

Inspect the per-paper field command_if_explicitly_approved from the plan.
Executing one of those commands uploads that paper's indexed passages
to Anthropic and incurs API charges. Only do this if the paper's access
terms permit processing with Anthropic. Process one or two new papers
first and check quality before attempting a larger batch.

After completing each source:

~~~bash
python3 -m research.factory.profile_audit audit \
  --file "PART_OF_NEW_PAPER_FILENAME" --limit 12 --stratified

python3 -m research.factory.profile_audit model-packet \
  --file "PART_OF_NEW_PAPER_FILENAME" --limit 8
~~~

## Free, cross-paper source-linked theory search

~~~bash
python3 -m research.factory.theory_catalog search \
  "preventive war commitment problems" --limit 12

# Strict mode only includes claims humans explicitly reviewed and approved:
python3 -m research.factory.theory_catalog search \
  "preventive war commitment problems" --limit 12 --approved-only
~~~

Search results report Zotero identifier, original indexed PDF page, verified
source quote, provisional interpretation, and human review decision. The
search rechecks quotations against current stored PDF pages and excludes
obsolete source versions and human-rejected evidence. Approved-only
returns no results until explicit source reviews have been recorded with
profile_audit mark and the --confirm-source-reviewed gate.

Quotation presence does not prove interpretation, causality, equilibrium
conditions, or scientific novelty. This index is for evidence discovery;
mathematical models, graphs and tables still require the actual source
PDF if the fact matters.

## Quality gate

Sample at least two additional papers, preferably with distinct methods,
to assess misclassified theory findings, overclaiming, and equation loss.
Only then consider a broader paid extraction. Neither this planner nor the
catalog invokes Claude, modifies PDFs, or changes production forecasts.


## Pilot portfolio quality dashboard

~~~bash
python3 -m research.factory.portfolio_quality
~~~

This is offline and audits every current paper profile against its current
indexed PDF text: profile totals, source quote matches, flagged categories,
and human review status by paper. No Claude calls or uploads.

The audit now reports a tentative source_type_hint field for evidence marked
empirical_finding: simulation_result_candidate if the claim or quote mentions
simulations; prior_literature_result_candidate if the claim references earlier
work; and finding_origin_unresolved otherwise. The cross-paper theory catalog
also returns these hints. They never silently recode an original profile.
The unresolved class is not proof of observational evidence. All cues are
heuristic and original-source interpretation still needs human inspection.


## From a Puzzle Finder candidate to a literature evidence packet

This is the first **offline operational bridge** to the Puzzle Finder.
It retrieves current source-quote-checked cards across the locally profiled
PDFs and selects citations **round-robin by paper** (default at most 3 per
paper), rather than allowing one prolific paper to dominate all results.

~~~bash
# Explore freely without a puzzle card:
python3 -m research.factory.puzzle_evidence --query "war escalation rivalry" --max-per-paper 2

# Or connect an existing Puzzle Finder candidate:
python3 -m research.factory list
python3 -m research.factory.puzzle_evidence --puzzle PUZZLE_ID --save

# Or use an existing literature review spec with search_queries:
python3 -m research.factory.puzzle_evidence --spec research/examples/YOUR_SPEC.json --save
~~~

--save creates a **private, ignored local JSON** in research/inbox/records; it
never commits the paper passages. No Anthropic call, payment, OpenAlex request,
or production forecasting changes. By default, returned claims are **unreviewed**
unless already individually approved with the profile review gate; use
--approved-only for those that have explicit source-review attestations.

This packet is a citation-bearing **candidate** bibliography, not a completed
novelty review, empirical identification argument, formal proof or manuscript.
It searches the **currently profiled papers only**; the other indexed PDFs
must still be separately screened, and external literature is not covered.

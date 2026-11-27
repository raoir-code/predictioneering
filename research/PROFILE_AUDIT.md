# Phase 1d — Scientific evidence audit (offline, no API calls)

The first full Bas and Coe paper profile contained 76 page-linked evidence entries.
Verifying that quotations exist on PDF pages does NOT establish that the linked
claims are entailed by those quotes. This phase creates a structured, auditable
human quality-control queue without editing the existing profile or PDF.

## Run (zero charge)

From your research checkout:

~~~bash
cd ~/predictioneering-research-test
git pull --ff-only
python3 -m unittest discover -s research/tests -q

# Prioritized audit of the current Bas and Coe profile:
python3 -m research.factory.profile_audit audit --file "Bas and Coe" --limit 12

# A representative, reproducible sample across claim categories:
python3 -m research.factory.profile_audit audit \
  --file "Bas and Coe" --limit 12 --stratified

# Focus on theoretical assumptions, formal propositions, and context:
python3 -m research.factory.profile_audit model-packet \
  --file "Bas and Coe" --limit 12
~~~

Both commands work from the already indexed, gitignored SQLite database.
No Anthropic keys, model credits or network calls are used. All original
PDFs, indexed passages and model-generated profiles remain unchanged.

## What the audit actually checks

1. Quotation provenance: rechecks that each quoted passage appears on the
   claimed PDF page index using the original indexed text.
2. Heuristic flags: short quotations, empirical results that appear to be
   theoretical/simulation findings, numerical claims without matching numbers
   in local text context, and conclusions that require inspecting a PDF
   figure/table. These are review prompts, not automatic truth judgments.
3. Formal-model review: highlights claims about propositions, assumptions,
   payoffs, beliefs and equilibrium, and supplies local page context.
   The model-packet deliberately leaves players, timing, information, payoffs,
   transitions, equilibrium conditions and comparative statics UNVERIFIED
   until the original typeset mathematics has been checked.
4. Provenance: PDF hash, evidence ID, model, extractor version and optional
   human decisions are retained privately. Changed PDF hashes invalidate
   lookup of old reviews against a new PDF.

This phase does NOT claim that a correct quote proves its paraphrase,
reconstruct equations, extract typeset figures, or scientifically verify
the entire paper.

## Human review (explicit)

After opening the original PDF and reading the relevant portion:

~~~bash
python3 -m research.factory.profile_audit mark \
  --file "Bas and Coe" \
  --evidence-id "p13-f8b33871b5" \
  --decision needs_revision \
  --note "Short quote does not establish the full Proposition 1 condition."
~~~

For an actual approval, explicitly confirm source review:

~~~bash
python3 -m research.factory.profile_audit mark \
  --file "Bas and Coe" \
  --evidence-id "p13-f8b33871b5" \
  --decision approved \
  --note "Checked the statement and conditions in the typeset PDF." \
  --confirm-source-reviewed
~~~

Decisions are approved, rejected, and needs_revision. The model output is not
overwritten, and a single approved passage does not verify an entire paper.
Do not mark a claim approved until its source meaning and mathematical
conditions have been checked, not just its literal words.

## Before any large batch

Review a sample covering formal models, mechanisms, empirical findings, and
figures/tables. Estimate false-positive and omission rates for our extraction.
Treat the library as provisional until methods and equations are independently
validated. The next stage can add adjudication and verified mathematical
reconstruction once we have measured this first-pass QC signal.

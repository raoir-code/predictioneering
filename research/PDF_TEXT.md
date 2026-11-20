# Phase 1b — Local PDF text ingestion and search

This is the first non-LLM layer of the permanent scientific knowledge library:
page-indexed retrieval with provenance to the original private PDFs.
No paid API calls, PDF uploads, or scientific claims are generated. Originals
remain read-only.

## Mac setup and commands

Run in the separate research checkout:

~~~bash
brew install poppler
cd ~/predictioneering-research-test
git pull --ff-only
python3 -m unittest discover -s research/tests -v

# Refresh inventory and improve DOI/title matching using PDF first pages.
python3 -m research.factory.pdf_inventory "$HOME/Desktop/Grad School/Predictioneering/Conflict"

# Pilot: index five PDFs.
python3 -m research.factory.pdf_text extract "$HOME/Desktop/Grad School/Predictioneering/Conflict" --limit 5

# Verify that exact passages and PDF page references are searchable.
python3 -m research.factory.pdf_text search "bargaining war"

# Full extraction, skipping the five already indexed files:
python3 -m research.factory.pdf_text extract "$HOME/Desktop/Grad School/Predictioneering/Conflict"
~~~

Derived text is stored only in the existing private, gitignored SQLite database:
research/datasets/private/research_library.sqlite3. Two new tables contain
source hash/processing status and one record per extractable PDF page. No data
or PDFs are written to the GitHub repository.

## Interpretation and limitations

- Search is basic keyword retrieval, not semantic understanding.
- Some scanned PDFs may have no extractable text. Only add OCR after measuring
  this gap; failed extraction never masquerades as real text.
- Page references are 1-indexed PDF pages, NOT journal page numbering. Verify
  scientific claims against original pages.
- Unknown bibliography matches remain searchable by file name, but not verified
  under a Zotero citation.
- Files changed after inventory must be inventoried again. Stale hashes are
  excluded from search. Extraction failures are retryable.
- This tool does NOT yet produce AI paper summaries, mathematical model
  reconstructions, verified citations, or novelty assessments. Those are
  separate stages to implement after full-text extraction succeeds.

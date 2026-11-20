# PDF inventory: first step toward a permanent scientific knowledge library

The inventory tool recursively scans your local PDF directory **read-only**,
links papers conservatively to the Zotero metadata already imported, and stores
only local inventory metadata under
`research/datasets/private/research_library.sqlite3`.

It does **not** summarize papers, run Claude, upload PDFs, call the network, or
change live Predictioneering forecasting code.

## Run it on the Mac

From the separate research checkout:

```bash
cd ~/predictioneering-research-test
git pull --ff-only
python3 -m unittest discover -s research/tests -v
python3 -m research.factory.pdf_inventory "$HOME/Desktop/Grad School/Predictioneering/Conflict"
```

The command walks nested folders, counts PDFs, detects exact duplicates,
identifies papers that match the existing Zotero bibliography, and reports
how many files are unmatched or need manual review.

If `pdftotext` (Poppler) is installed, it uses the first two pages of each
PDF only to improve DOI/title matching and check extractable text. Otherwise
it falls back to filename matching. To enable the optional extractor on macOS,
install Poppler with `brew install poppler`, then run the scan again.
Scanned PDF contents are **never** uploaded to GitHub.

Run the command a second time and unchanged PDFs are skipped. Changes to the
Zotero JSON bibliography invalidate previous matches so PDFs are re-matched.

## Scientific caution

Matching a PDF to a citation does **not** verify its findings or equations.
An unmatched PDF is not necessarily missing from Zotero; automatic matches
are intentionally conservative. Without `pdftotext` or another PDF parser,
the inventory is not a full-text knowledge base.

Our next stage, after inspecting coverage, will extract page-indexed text and
build cached, source-supported theoretical and empirical profiles. The separate
theory-heavy Zotero collection may contain metadata without PDFs, and we
should not invent missing full-text evidence.

## Privacy

The source PDF folders remain unchanged. The local SQLite database is covered
by `research/.gitignore` and must not be committed. No raw PDFs, embeddings,
abstracts, work logs, or API keys should be committed to this public repository.

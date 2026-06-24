# Design: `rename-papers` skill

**Date:** 2026-06-24
**Status:** Approved (design phase)

## Summary

A new Claude Code skill, `rename-papers`, that renames scientific paper and
book PDFs into a Harvard-style filename with the DOI appended at the end. It
reads metadata from the PDF, confirms it against the CrossRef API, and uses a
dry-run-first batch flow so the user reviews all proposed renames before any
file changes. Files that are not scholarly documents are skipped silently;
scholarly files that cannot be renamed are listed with an explicit reason.

## Goals

- Turn messy paper filenames into a consistent, citation-style name.
- Be accurate: only use DOIs literally found in the file; never hallucinate.
- Be safe: dry-run first, no overwrites, reversible via an undo log.
- Be quiet about noise: don't list files that aren't papers/books.
- Be transparent about failure: every unrenamed paper gets a stated reason.

## Filename format

```
<FirstAuthorSurname>, <Initial>. [et al.] (<Year>) <Title> - <DOI>.pdf
```

Example:

```
Smith, J. et al. (2023) Deep learning for graphs - 10.1000_xyz123.pdf
```

Rules:
- **Authors:** first author `Surname, Initial.`; append ` et al.` whenever there
  is more than one author.
- **Year:** four-digit publication year in parentheses.
- **Title:** as returned by CrossRef (falling back to PDF-parsed title).
- **DOI:** appended after ` - `; `/` replaced with `_`.
- **Sanitization:** illegal filename characters (`/ \ : * ? " < > |`) replaced
  with `_`; whitespace collapsed; title truncated so the total filename stays
  under ~200 characters.

## Architecture

New skill at `~/.claude/skills/rename-papers/`:

```
rename-papers/
├── SKILL.md             # when-to-use + the workflow Claude follows
├── scripts/
│   └── rename_papers.py # deterministic extract -> resolve -> build -> rename pipeline
└── references/
    └── format-rules.md  # the exact naming spec, documented separately from code
```

Trigger: the user asks to rename / organize scientific papers or PDFs by
citation.

## Approach: hybrid (script + Claude fallback)

The Python script handles the common case deterministically and cheaply. Files
the script cannot confidently resolve are set aside in a "needs review" list,
and the SKILL.md instructs Claude to open just those PDFs and resolve them
manually. This keeps bulk processing fast and accurate while still handling
awkward stragglers.

## Pipeline (`rename_papers.py`)

1. **Scan** — given a folder path, find all `*.pdf` files.
2. **Classify** — decide whether each file is a scientific paper or book.
   Signals: a detected DOI, academic structure (abstract / references section /
   journal markers), or a book identifier (ISBN). Tuned to be slightly cautious:
   clearly non-scholarly files are dropped; ambiguous files go to "needs review"
   rather than being silently dropped, so a real paper is never lost without
   explanation.
3. **Extract** — read embedded PDF metadata + first ~2 pages of text via
   `pypdf`; find a DOI with the regex `10.\d{4,}/\S+`.
4. **Resolve** — if a DOI is found, query CrossRef
   (`https://api.crossref.org/works/{doi}`) for canonical first-author
   surname+initial, year, and title. On network failure, fall back to
   PDF-parsed metadata and flag low confidence.
5. **Build name** — apply the filename format and sanitization rules above.
6. **Output** — print an `old -> new` table for confident files and a separate
   "needs review" list (each with a reason). Also write the full result set as
   JSON to a temp file.
7. **Rename** — only when invoked with `--apply` (default is dry run). On apply:
   resolve name collisions by appending ` (2)`, and write an undo log of
   old/new pairs.

## Already-conformant papers

The skill **leaves already-well-named papers alone** (decision: option 1). After
classifying a file as scholarly and building the proposed name, if the existing
filename already conveys the same citation — i.e. it already contains the DOI, or
matches the target pattern allowing for stylistic differences (underscores vs
spaces/commas, `et al.` spacing) — the file is treated as already conformant and
**not renamed**. These are not shown in the "needs review" list; at most they are
summarized as a count ("N papers already well-named, left unchanged"). This
avoids mass-renaming hundreds of files that already work. Only files whose names
clearly fail to convey the citation are proposed for renaming.

## Output groups

- **Renamed** — `old -> new`.
- **Needs review** — file is a paper/book but could not be auto-renamed; each
  entry includes a specific reason (e.g. "no DOI found in PDF", "CrossRef had no
  record", "no publication year found", "PDF encrypted/corrupt").
- **Skipped silently** — not a scholarly document (random PDF, non-PDF, image,
  etc.); not shown in output at all.
- **Already conformant** — scholarly and already well-named; left unchanged,
  reported only as a count.

## Error handling

- Unreadable / encrypted / corrupt PDF → "needs review" with reason; never
  crashes the batch.
- No DOI or CrossRef miss → fall back to PDF-parsed metadata; flag for review.
- **Missing publication year → "needs review"** (reason: "no publication year
  found"). Not silently given a placeholder.
- Never overwrite an existing file.
- Never hallucinate a DOI — only DOIs literally present in the file are used.
- Undo log (JSON of old/new pairs) written on `--apply` so a batch can be
  reversed.

## SKILL.md workflow

1. Run the script in dry-run mode on the target folder.
2. Show the user the `old -> new` preview table and the "needs review" list.
3. For "needs review" files, open those PDFs and determine the citation
   manually.
4. Present the complete proposed set (auto + manually resolved).
5. On user confirmation, run the script with `--apply`.

## Testing

- Unit tests (no network, no real PDFs) for pure functions: DOI regex, filename
  sanitization, name builder, collision handling, classification heuristic.
- CrossRef lookup tested against a mocked / canned API response.
- A small fixture folder with sample PDFs for an end-to-end dry-run test.

## Validation (manual dry-run, 2026-06-24)

Tested the approach by hand on `~/Downloads` (653 PDFs). On a sample of
cryptically/generically-named files, the classifier correctly skipped admin
documents (insurance terms, invoices, PRIIPS docs, pension statements, a travel
itinerary, a Danish regulation, an LLM prompt) and routed scholarly-but-no-DOI
files (a journal book-review section, a ProQuest cover page) to "needs review"
with reasons. Key finding: the messy-named PDFs in Downloads are almost all
non-scholarly, while the real papers are already well-named — which is what
motivated the "leave already-conformant papers alone" rule above.

## Refinement (2026-06-24): variant markers + wrong-DOI safety

Real-data testing on `~/Downloads` exposed two gaps. This refinement closes them.

### Variant markers
The format had no slot for distinguishing copies of the same paper (annotated
vs clean, v2, same-year a/b), so they collided and lost their markers.

- `extract_variant_marker(filename) -> str | None` detects, from the original
  filename: `ANNOTATED`; version tags (`v2`, `v3`, `_v2`); OS duplicate counters
  (`(1)`); and same-year suffixes (`(2015a)` → `a`, `(2015b)` → `b`).
- `build_filename(meta, max_len=200, variant=None)`: when `variant` is set,
  append ` [marker]` after the DOI, before `.pdf` (still within the 200-char cap).
- `process_folder` computes the marker from each file's original name and passes
  it through, so annotated/v2/a-b copies get distinct names and no longer collide.

### Wrong-DOI safety (two checks, before proposing a rename)
The pipeline used the first DOI found, which could belong to a cited work.

- `extract_all_dois(text) -> list[str]` (distinct, order-preserving).
- **Bibliography check:** ≥ 4 distinct DOIs in the scanned pages → needs-review,
  reason "multiple DOIs found (likely a bibliography/reference list)".
- **Author cross-check:** normalize CrossRef's first-author surname (lowercase,
  strip diacritics so `Köchling` = `kochling`); if the original filename has an
  alphabetic token but the surname is absent from it, route to needs-review,
  reason "CrossRef author '<name>' not found in filename — possible wrong DOI".
  Surnames under 3 chars skip the check; number/hash-only names are exempt.

### Validated cases
12 ANNOTATED/v2/a-b groups keep distinct names; `Samlet_Litteraturliste` →
review (bibliography); `Derwall→Bauer` and `Mouritsen→Andon` → review (author
mismatch).

## Refinement (2026-06-24): timestamped undo logs

The undo log used a fixed path (`rename-undo.json`) overwritten on every
`--apply`, so each run destroyed the prior run's undo history. Fix:

- Each `--apply` writes `rename-undo-<YYYYMMDD-HHMMSS>.json` in the target folder
  (full per-run history, never overwritten).
- It also writes `rename-undo.json` as a copy of the most recent run (a "latest"
  pointer for easy discovery).
- `timestamped_undo_filename(stamp) -> str` returns `rename-undo-<stamp>.json`
  (pure, testable). `main` stamps with the real clock and copies the result to
  the latest pointer.

## Non-goals (YAGNI)

- No citation styles other than the agreed Harvard-with-DOI filename format.
- No GUI; no watching folders; no automatic background runs.
- No moving/sorting files into subfolders — renaming only.

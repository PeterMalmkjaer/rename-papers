---
name: rename-papers
description: Use when the user wants to rename, clean up, or organize scientific paper or book PDFs into a citation-style filename (Harvard format with the DOI appended). Triggers on requests like "rename these papers", "fix my PDF filenames", "organize my papers folder by citation".
---

# rename-papers

Renames scientific paper/book PDFs to `Surname, I. [et al.] (Year) Title - DOI.pdf`.
See `references/format-rules.md` for the exact format.

## Workflow

1. **Dry run.** Run the pipeline on the user's folder (never rename yet):
   `python3 scripts/rename_papers.py "<FOLDER>" --json /tmp/rename-papers.json`
   This prints three things: files to **rename** (old → new), files that **need
   review** (with reasons), and counts of already-well-named and skipped files.
   Non-scholarly files are skipped silently and never listed.

2. **Resolve "needs review" by hand.** For each needs-review file, open the PDF
   yourself, find the DOI or citation, and decide the correct name using
   `references/format-rules.md`. If a file genuinely has no usable citation,
   leave it and tell the user why.

3. **Confirm with the user.** Show the complete proposed set (auto renames +
   any you resolved manually). Wait for explicit approval.

4. **Apply.** Run with `--apply`:
   `python3 scripts/rename_papers.py "<FOLDER>" --apply`
   This renames the auto-detected files and writes `rename-undo.json` in the
   folder so the batch can be reversed.

## Notes
- Default is always dry run; `--apply` is the only thing that changes files.
- Requires `pypdf` (`pip install pypdf`).
- Never invent a DOI; if CrossRef has no record, the file goes to needs review.

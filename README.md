# rename-papers

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Beta](https://img.shields.io/badge/status-beta%20%E2%80%94%20experimental-orange.svg)](#)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

Rename scientific paper and book PDFs into consistent, Harvard-style filenames
with the DOI appended — verified against [CrossRef](https://www.crossref.org/),
dry-run first, and fully reversible.

```
Abramson_et_al_(2024)_AlphaFold3_Nature.pdf
  ->  Abramson, J. et al. (2024) Accurate structure prediction of biomolecular interactions with AlphaFold 3 - 10.1038_s41586-024-07487-w.pdf
```

It is packaged as a [Claude Code](https://claude.com/claude-code) skill but the
pipeline is a plain Python script you can run on its own.

> ⚠️ **Beta — experimental use only.** This is early, experimental software
> provided **as is, with no warranty of any kind** (see [LICENSE](LICENSE)). It
> renames your files. Always use the dry run first, review the proposed changes,
> and keep a backup. Use at your own risk.

## Filename format

```
Surname, I. [et al.] (Year) Title - DOI [variant].pdf
```

- **Authors** — first author `Surname, I.`; ` et al.` whenever there is more than one author.
- **Year** — four-digit publication year from CrossRef.
- **Title** — from CrossRef, falling back to the PDF's embedded title.
- **DOI** — appended after ` - `, with `/` replaced by `_`.
- **Variant** — an optional ` [ANNOTATED]` / ` [v2]` / ` [a]` tag preserved from the original filename so annotated/versioned copies stay distinct.
- Illegal filename characters are sanitized; the name is capped at ~200 characters (title truncated to fit).

## How it works

For every `*.pdf` in a folder, the pipeline:

1. extracts the embedded metadata and first pages of text;
2. classifies the file — non-scholarly documents (invoices, statements, etc.) are **skipped silently**;
3. finds the DOI and confirms canonical author/year/title via CrossRef;
4. proposes a new name, or routes the file to **needs-review** with a reason.

Files are sorted into four groups:

| Group | Meaning |
|-------|---------|
| **rename** | A clean new name was produced (`old -> new`). |
| **needs review** | A paper/book that couldn't be auto-renamed — each with a reason. |
| **skipped** | Not a scholarly document. Not listed. |
| **already conformant** | Already well-named (DOI already in the filename). Left unchanged, counted only. |

### Safety checks

- **Never invents a DOI** — only DOIs literally found in the file are used.
- **Bibliography guard** — a file with many distinct DOIs (a reference list) goes to needs-review instead of grabbing a cited work's DOI.
- **Author cross-check** — if CrossRef's first author doesn't appear in the original filename, the file goes to needs-review (catches a wrong DOI).
- **Never overwrites** — name collisions get a ` (2)` suffix.
- **Reversible** — every `--apply` writes a timestamped undo log.

## Usage

Requires Python 3 and [`pypdf`](https://pypi.org/project/pypdf/):

```bash
pip install pypdf
```

**1. Dry run** (default — nothing is renamed). Write the result to JSON so you can apply exactly what you reviewed:

```bash
python3 scripts/rename_papers.py "/path/to/papers" --json /tmp/rename-papers.json
```

**2. Review** the printed `rename` and `needs review` lists.

**3. Apply** the reviewed set — pass the JSON back via `--from-json` so the applied set can't drift from the preview:

```bash
python3 scripts/rename_papers.py "/path/to/papers" --apply --from-json /tmp/rename-papers.json
```

Each apply writes `rename-undo-<YYYYMMDD-HHMMSS>.json` (a permanent per-run log)
plus `rename-undo.json` (a copy of the latest run) in the target folder.

> Applying with `--apply` but **without** `--from-json` re-scans the folder and
> may differ from your dry-run preview; the script warns when you do this.

## As a Claude Code skill

With this repo installed under `~/.claude/skills/`, just ask Claude to "rename
the papers in <folder>". It runs the dry run, resolves the needs-review files by
opening the PDFs, confirms the full set with you, and applies on approval. See
[`SKILL.md`](SKILL.md).

## Development

```bash
python3 -m pytest tests/ -v
```

The pipeline is decomposed into small, independently tested pure functions
(DOI extraction, classification, name building, CrossRef mapping, collision
handling) plus the `process_folder` orchestrator. CrossRef and PDF I/O are
injected so tests need no network or real PDFs.

Design notes live in [`docs/`](docs/).

## License

[MIT](LICENSE) © 2026 Peter Malmkjær. Provided "as is", without warranty of any
kind. Beta / experimental — use at your own risk.

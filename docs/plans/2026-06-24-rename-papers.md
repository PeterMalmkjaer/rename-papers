# rename-papers Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code skill, `rename-papers`, that renames scientific paper/book PDFs into a Harvard-style filename with the DOI appended, using a dry-run-first batch flow.

**Architecture:** A pure-Python pipeline (`rename_papers.py`) decomposed into small testable functions — DOI extraction, classification, CrossRef lookup, filename building, collision handling, and orchestration. PDF I/O uses `pypdf`; metadata is confirmed against the CrossRef HTTP API (injected as a callable so it is mockable in tests). A `SKILL.md` tells Claude how to drive it, including opening "needs review" PDFs by hand.

**Tech Stack:** Python 3 (stdlib + `pypdf`), CrossRef REST API, `pytest`, `pymupdf` (test fixtures only).

## Global Constraints

- Skill lives at `~/.claude/skills/rename-papers/`.
- Filename format: `Surname, I. [et al.] (Year) Title - DOI.pdf` where `/` in the DOI becomes `_`.
- Author rule: first author `Surname, I.`; append ` et al.` whenever there is more than one author.
- Illegal filename chars `/ \ : * ? " < > |` → `_`; whitespace collapsed; total filename ≤ 200 chars (title truncated to fit).
- Never overwrite an existing file; never invent a DOI (only DOIs literally found in the file are used).
- Dry run is the default; renaming happens only with `--apply`, which also writes an undo log.
- Missing publication year → "needs review" (never a placeholder).
- Non-scholarly files are skipped silently (not listed). Already-well-named papers are left unchanged and only counted.
- Output groups: `rename`, `review` (with reason), `skip` (silent), `conformant` (counted).

---

### Task 1: Project scaffold + `sanitize_filename()`

**Files:**
- Create: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Create: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`
- Create: `~/.claude/skills/rename-papers/tests/conftest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `sanitize_filename(name: str) -> str` — replaces illegal chars with `_`, collapses whitespace, strips ends.

- [ ] **Step 1: Set up test import path**

Create `~/.claude/skills/rename-papers/tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
```

- [ ] **Step 2: Write the failing test**

Create `~/.claude/skills/rename-papers/tests/test_rename_papers.py`:

```python
from rename_papers import sanitize_filename


def test_sanitize_replaces_illegal_chars():
    assert sanitize_filename('a/b:c*d?"e<f>g|h\\i') == "a_b_c_d__e_f_g_h_i"


def test_sanitize_collapses_whitespace_and_strips():
    assert sanitize_filename("  hello   world  ") == "hello world"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rename_papers'`

- [ ] **Step 4: Write minimal implementation**

Create `~/.claude/skills/rename-papers/scripts/rename_papers.py`:

```python
"""rename-papers: rename scientific paper PDFs into Harvard-style names with DOI."""
import re

_ILLEGAL = re.compile(r'[/\\:*?"<>|]')
_WHITESPACE = re.compile(r"\s+")


def sanitize_filename(name: str) -> str:
    name = _ILLEGAL.sub("_", name or "")
    name = _WHITESPACE.sub(" ", name).strip()
    return name
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
cd ~/.claude/skills/rename-papers
git init -q 2>/dev/null; git add -A
git commit -m "feat(rename-papers): scaffold + sanitize_filename"
```

---

### Task 2: `extract_doi()`

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `extract_doi(text: str) -> str | None` — returns the first DOI found, trailing punctuation stripped, or `None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rename_papers.py`:

```python
from rename_papers import extract_doi


def test_extract_doi_finds_doi():
    assert extract_doi("see doi 10.1016/j.aos.2021.101282 here") == "10.1016/j.aos.2021.101282"


def test_extract_doi_strips_trailing_period():
    assert extract_doi("DOI: 10.2307/1885099.") == "10.2307/1885099"


def test_extract_doi_returns_none_when_absent():
    assert extract_doi("no identifier here") is None
    assert extract_doi("") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_extract_doi_finds_doi -v`
Expected: FAIL — `ImportError: cannot import name 'extract_doi'`

- [ ] **Step 3: Write minimal implementation**

Add to `rename_papers.py`:

```python
_DOI_RE = re.compile(r"10\.\d{4,}/[^\s\"<>,;()\[\]]+", re.IGNORECASE)


def extract_doi(text):
    if not text:
        return None
    m = _DOI_RE.search(text)
    if not m:
        return None
    return m.group(0).rstrip(".")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): extract_doi"
```

---

### Task 3: Data model + `build_filename()`

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Consumes: `sanitize_filename`.
- Produces:
  - `Author(family: str, given: str = "")` dataclass.
  - `PaperMeta(authors: list[Author], year: int | None, title: str | None, doi: str | None)` dataclass.
  - `build_filename(meta: PaperMeta, max_len: int = 200) -> str` — returns the proposed filename ending in `.pdf`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rename_papers.py`:

```python
from rename_papers import Author, PaperMeta, build_filename


def _meta(authors, year=2023, title="Deep learning for graphs", doi="10.1000/xyz123"):
    return PaperMeta(authors=authors, year=year, title=title, doi=doi)


def test_build_filename_single_author():
    m = _meta([Author("Smith", "John")])
    assert build_filename(m) == "Smith, J. (2023) Deep learning for graphs - 10.1000_xyz123.pdf"


def test_build_filename_multiple_authors_et_al():
    m = _meta([Author("Smith", "John"), Author("Jones", "Amy")])
    assert build_filename(m) == "Smith, J. et al. (2023) Deep learning for graphs - 10.1000_xyz123.pdf"


def test_build_filename_author_without_given_name():
    m = _meta([Author("Smith", "")])
    assert build_filename(m) == "Smith (2023) Deep learning for graphs - 10.1000_xyz123.pdf"


def test_build_filename_truncates_long_title_under_max_len():
    m = _meta([Author("Smith", "John")], title="x" * 400)
    name = build_filename(m, max_len=80)
    assert len(name) <= 80
    assert name.startswith("Smith, J. (2023) ")
    assert name.endswith(" - 10.1000_xyz123.pdf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_build_filename_single_author -v`
Expected: FAIL — `ImportError: cannot import name 'Author'`

- [ ] **Step 3: Write minimal implementation**

Add to `rename_papers.py` (add `from dataclasses import dataclass, field` and `from typing import Optional` near the top imports):

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Author:
    family: str
    given: str = ""


@dataclass
class PaperMeta:
    authors: list = field(default_factory=list)
    year: Optional[int] = None
    title: Optional[str] = None
    doi: Optional[str] = None


def build_filename(meta, max_len=200):
    first = meta.authors[0]
    author_part = f"{first.family}, {first.given[0]}." if first.given else first.family
    if len(meta.authors) >= 2:
        author_part += " et al."
    doi_safe = (meta.doi or "").replace("/", "_")
    title = meta.title or ""
    suffix = f" - {doi_safe}.pdf"
    prefix = f"{author_part} ({meta.year}) "

    name = sanitize_filename(f"{prefix}{title}{suffix}")
    if len(name) > max_len:
        overflow = len(name) - max_len
        title = title[: max(0, len(title) - overflow)].rstrip()
        name = sanitize_filename(f"{prefix}{title}{suffix}")
    return name
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): data model + build_filename"
```

---

### Task 4: `classify_document()`

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Classification(kind: str, reason: str = "")` dataclass — `kind` is one of `"paper"`, `"not_paper"`, `"ambiguous"`.
  - `classify_document(text: str, has_doi: bool, embedded_title: str = "") -> Classification`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rename_papers.py`:

```python
from rename_papers import Classification, classify_document


def test_classify_doi_is_paper():
    assert classify_document("anything", has_doi=True).kind == "paper"


def test_classify_invoice_is_not_paper():
    assert classify_document("INVOICE #: 554", has_doi=False, embedded_title="Invoice").kind == "not_paper"


def test_classify_scholarly_markers_is_paper():
    text = "Abstract\nThis paper studies... References\nSmith et al."
    assert classify_document(text, has_doi=False).kind == "paper"


def test_classify_unknown_is_ambiguous():
    assert classify_document("Haze Aur Cel.M SUE", has_doi=False).kind == "ambiguous"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_classify_doi_is_paper -v`
Expected: FAIL — `ImportError: cannot import name 'Classification'`

- [ ] **Step 3: Write minimal implementation**

Add to `rename_papers.py`:

```python
@dataclass
class Classification:
    kind: str
    reason: str = ""


_NONSCHOLARLY = [
    "invoice", "faktura", "forsikringsbetingelser", "priips",
    "central information", "aftalevilkår", "terms of use", "terms of service",
    "bekendtgørelse", "kørselsvejledning", "pensionsoplysninger", "erklæring",
    "purchase order", "receipt", "boarding pass",
]
_SCHOLARLY = [
    "abstract", "references", "bibliography", "journal", "isbn",
    "doi:", "et al", "this paper", "literature review", "we find that",
    "cite this", "proceedings",
]


def classify_document(text, has_doi, embedded_title=""):
    if has_doi:
        return Classification("paper", "DOI present")
    blob = f"{embedded_title}\n{text}".lower()
    if any(k in blob for k in _NONSCHOLARLY):
        return Classification("not_paper", "matched non-scholarly marker")
    if any(k in blob for k in _SCHOLARLY):
        return Classification("paper", "matched scholarly marker")
    return Classification("ambiguous", "no clear scholarly markers")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): classify_document"
```

---

### Task 5: `is_already_conformant()` + `resolve_collision()`

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `is_already_conformant(current_name: str, doi: str | None) -> bool` — true if the current filename already contains the DOI (raw or `/`→`_` form), case-insensitive.
  - `resolve_collision(target: str, taken: set[str]) -> str` — returns `target`, or `"<stem> (N).<ext>"` with the lowest free `N≥2`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rename_papers.py`:

```python
from rename_papers import is_already_conformant, resolve_collision


def test_already_conformant_detects_doi_in_name():
    name = "AbdelRahim_et_al_(2022)_Trust_10.1016_j.aos.2021.101282.pdf"
    assert is_already_conformant(name, "10.1016/j.aos.2021.101282") is True


def test_already_conformant_false_without_doi_match():
    assert is_already_conformant("random.pdf", "10.1016/j.aos.2021.101282") is False
    assert is_already_conformant("random.pdf", None) is False


def test_resolve_collision_returns_target_when_free():
    assert resolve_collision("a.pdf", set()) == "a.pdf"


def test_resolve_collision_appends_lowest_free_number():
    taken = {"a.pdf", "a (2).pdf"}
    assert resolve_collision("a.pdf", taken) == "a (3).pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_resolve_collision_returns_target_when_free -v`
Expected: FAIL — `ImportError: cannot import name 'is_already_conformant'`

- [ ] **Step 3: Write minimal implementation**

Add to `rename_papers.py`:

```python
def is_already_conformant(current_name, doi):
    if not doi:
        return False
    low = current_name.lower()
    return doi.lower() in low or doi.replace("/", "_").lower() in low


def resolve_collision(target, taken):
    if target not in taken:
        return target
    stem, dot, ext = target.rpartition(".")
    base = stem if dot else target
    suffix = f".{ext}" if dot else ""
    n = 2
    while f"{base} ({n}){suffix}" in taken:
        n += 1
    return f"{base} ({n}){suffix}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): conformance + collision helpers"
```

---

### Task 6: `crossref_lookup()`

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Consumes: `Author`, `PaperMeta`.
- Produces:
  - `crossref_lookup(doi: str, fetch: Callable[[str], dict]) -> PaperMeta | None` — maps a CrossRef `works` response to `PaperMeta`; returns `None` on any error or empty message.
  - `http_get_json(url: str) -> dict` — default fetcher using `urllib` (not unit-tested; used in production).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rename_papers.py`:

```python
from rename_papers import crossref_lookup

_CROSSREF_OK = {
    "message": {
        "author": [{"family": "Smith", "given": "John"}, {"family": "Jones", "given": "Amy"}],
        "title": ["Deep Learning for Graphs"],
        "issued": {"date-parts": [[2023, 5]]},
    }
}


def test_crossref_lookup_maps_fields():
    meta = crossref_lookup("10.1000/xyz123", fetch=lambda url: _CROSSREF_OK)
    assert meta.authors[0].family == "Smith"
    assert meta.authors[0].given == "John"
    assert len(meta.authors) == 2
    assert meta.year == 2023
    assert meta.title == "Deep Learning for Graphs"
    assert meta.doi == "10.1000/xyz123"


def test_crossref_lookup_returns_none_on_error():
    def boom(url):
        raise RuntimeError("network down")
    assert crossref_lookup("10.1000/xyz123", fetch=boom) is None


def test_crossref_lookup_returns_none_on_empty():
    assert crossref_lookup("10.1000/xyz123", fetch=lambda url: {}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_crossref_lookup_maps_fields -v`
Expected: FAIL — `ImportError: cannot import name 'crossref_lookup'`

- [ ] **Step 3: Write minimal implementation**

Add to `rename_papers.py` (add `import json`, `import urllib.request`, and `from typing import Callable` to imports):

```python
import json
import urllib.request


def http_get_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "rename-papers/1.0 (mailto:peter.malmkjaer@gmail.com)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def crossref_lookup(doi, fetch):
    try:
        data = fetch(f"https://api.crossref.org/works/{doi}")
    except Exception:
        return None
    msg = (data or {}).get("message")
    if not msg:
        return None
    authors = [
        Author(family=a.get("family", ""), given=a.get("given", ""))
        for a in msg.get("author", [])
        if a.get("family")
    ]
    title_list = msg.get("title") or []
    title = title_list[0] if title_list else None
    year = None
    for key in ("published-print", "published-online", "issued"):
        parts = (msg.get(key) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            year = parts[0][0]
            break
    return PaperMeta(authors=authors, year=year, title=title, doi=doi)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): crossref_lookup"
```

---

### Task 7: `extract_pdf_text_and_meta()` (PDF I/O)

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `extract_pdf_text_and_meta(path: str, max_pages: int = 2) -> tuple[str, str]` — returns `(text, embedded_title)`. Raises on unreadable/encrypted/corrupt PDFs (caller handles).

- [ ] **Step 1: Write the failing test** (uses `pymupdf`/`fitz` to generate a real fixture PDF)

Append to `tests/test_rename_papers.py`:

```python
import fitz  # pymupdf, test-only
from rename_papers import extract_pdf_text_and_meta


def test_extract_pdf_text_and_meta(tmp_path):
    pdf = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "A Test Paper\nAbstract\nDOI 10.1000/xyz123")
    doc.set_metadata({"title": "A Test Paper"})
    doc.save(str(pdf))
    doc.close()

    text, title = extract_pdf_text_and_meta(str(pdf))
    assert "10.1000/xyz123" in text
    assert title == "A Test Paper"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_extract_pdf_text_and_meta -v`
Expected: FAIL — `ImportError: cannot import name 'extract_pdf_text_and_meta'`

- [ ] **Step 3: Write minimal implementation**

Add to `rename_papers.py`:

```python
def extract_pdf_text_and_meta(path, max_pages=2):
    from pypdf import PdfReader

    reader = PdfReader(path)
    title = ""
    if reader.metadata and reader.metadata.title:
        title = str(reader.metadata.title)
    text = ""
    for page in reader.pages[:max_pages]:
        text += (page.extract_text() or "") + "\n"
    return text, title
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py -v`
Expected: PASS (all). If `pypdf` is missing: `pip install pypdf`.

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): extract_pdf_text_and_meta"
```

---

### Task 8: `process_folder()` orchestration

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Consumes: `extract_doi`, `classify_document`, `crossref_lookup`, `is_already_conformant`, `build_filename`, `extract_pdf_text_and_meta`, `http_get_json`.
- Produces:
  - `FileResult(path: str, group: str, proposed: str | None = None, reason: str = "")` dataclass — `group` is one of `"rename"`, `"review"`, `"skip"`, `"conformant"`.
  - `process_folder(folder: str, extractor=extract_pdf_text_and_meta, fetcher=http_get_json) -> list[FileResult]` — runs the full dry-run pipeline over every `*.pdf` in `folder` (sorted), no renaming.

- [ ] **Step 1: Write the failing test** (inject fakes — no real PDFs or network)

Append to `tests/test_rename_papers.py`:

```python
from rename_papers import FileResult, process_folder


def _touch(folder, name):
    p = folder / name
    p.write_bytes(b"%PDF-1.4 fake")
    return p


def test_process_folder_groups_results(tmp_path):
    _touch(tmp_path, "paper.pdf")
    _touch(tmp_path, "invoice.pdf")
    _touch(tmp_path, "noyear.pdf")
    _touch(tmp_path, "Smith_(2023)_10.1000_xyz.pdf")

    fake_text = {
        "paper.pdf": ("Abstract DOI 10.1000/xyz", "A Paper"),
        "invoice.pdf": ("INVOICE #: 12", "Invoice"),
        "noyear.pdf": ("Abstract DOI 10.1000/noyear", "NoYear"),
        "Smith_(2023)_10.1000_xyz.pdf": ("Abstract DOI 10.1000/xyz", "Conformant"),
    }

    def extractor(path, max_pages=2):
        import os
        return fake_text[os.path.basename(path)]

    def fetcher(url):
        if url.endswith("10.1000/xyz"):
            return {"message": {"author": [{"family": "Smith", "given": "John"}],
                                "title": ["A Paper"], "issued": {"date-parts": [[2023]]}}}
        if url.endswith("10.1000/noyear"):
            return {"message": {"author": [{"family": "Doe", "given": "Jane"}],
                                "title": ["No Year"], "issued": {"date-parts": [[None]]}}}
        return {}

    results = {r.path.split("/")[-1]: r for r in process_folder(str(tmp_path), extractor=extractor, fetcher=fetcher)}

    assert results["paper.pdf"].group == "rename"
    assert results["paper.pdf"].proposed == "Smith, J. (2023) A Paper - 10.1000_xyz.pdf"
    assert results["invoice.pdf"].group == "skip"
    assert results["noyear.pdf"].group == "review"
    assert "year" in results["noyear.pdf"].reason.lower()
    assert results["Smith_(2023)_10.1000_xyz.pdf"].group == "conformant"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_process_folder_groups_results -v`
Expected: FAIL — `ImportError: cannot import name 'FileResult'`

- [ ] **Step 3: Write minimal implementation**

Add to `rename_papers.py` (add `import glob`, `import os`):

```python
import glob
import os


@dataclass
class FileResult:
    path: str
    group: str
    proposed: Optional[str] = None
    reason: str = ""


def process_folder(folder, extractor=extract_pdf_text_and_meta, fetcher=http_get_json):
    results = []
    paths = sorted(glob.glob(os.path.join(folder, "*.pdf")))
    for path in paths:
        name = os.path.basename(path)
        try:
            text, etitle = extractor(path)
        except Exception as exc:
            results.append(FileResult(path, "review", reason=f"could not read PDF: {exc}"))
            continue

        doi = extract_doi(text)
        cls = classify_document(text, has_doi=bool(doi), embedded_title=etitle)

        if cls.kind == "not_paper":
            results.append(FileResult(path, "skip"))
            continue
        if not doi:
            reason = "could not classify; no DOI found" if cls.kind == "ambiguous" else "no DOI found in PDF"
            results.append(FileResult(path, "review", reason=reason))
            continue

        meta = crossref_lookup(doi, fetcher)
        if meta is None:
            results.append(FileResult(path, "review", reason="CrossRef had no record for DOI"))
            continue
        if not meta.authors:
            results.append(FileResult(path, "review", reason="no author found"))
            continue
        if meta.year is None:
            results.append(FileResult(path, "review", reason="no publication year found"))
            continue
        if is_already_conformant(name, doi):
            results.append(FileResult(path, "conformant"))
            continue

        results.append(FileResult(path, "rename", proposed=build_filename(meta)))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): process_folder orchestration"
```

---

### Task 9: `apply_renames()` + undo log

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Consumes: `FileResult`, `resolve_collision`.
- Produces: `apply_renames(results: list[FileResult], folder: str, undo_log_path: str) -> list[dict]` — renames only `group == "rename"` entries, resolves collisions, writes an undo log (`[{"from","to"}]`) as JSON, returns the undo list.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rename_papers.py`:

```python
import json as _json
from rename_papers import apply_renames


def test_apply_renames_renames_and_writes_undo(tmp_path):
    src = tmp_path / "old.pdf"
    src.write_bytes(b"%PDF fake")
    results = [FileResult(str(src), "rename", proposed="Smith, J. (2023) T - 10.1_x.pdf")]
    undo_path = tmp_path / "undo.json"

    undo = apply_renames(results, str(tmp_path), str(undo_path))

    assert (tmp_path / "Smith, J. (2023) T - 10.1_x.pdf").exists()
    assert not src.exists()
    assert undo == [{"from": "old.pdf", "to": "Smith, J. (2023) T - 10.1_x.pdf"}]
    assert _json.loads(undo_path.read_text()) == undo


def test_apply_renames_resolves_collision(tmp_path):
    (tmp_path / "Target.pdf").write_bytes(b"existing")
    src = tmp_path / "old.pdf"
    src.write_bytes(b"%PDF fake")
    results = [FileResult(str(src), "rename", proposed="Target.pdf")]

    undo = apply_renames(results, str(tmp_path), str(tmp_path / "undo.json"))

    assert undo == [{"from": "old.pdf", "to": "Target (2).pdf"}]
    assert (tmp_path / "Target (2).pdf").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_apply_renames_renames_and_writes_undo -v`
Expected: FAIL — `ImportError: cannot import name 'apply_renames'`

- [ ] **Step 3: Write minimal implementation**

Add to `rename_papers.py`:

```python
def apply_renames(results, folder, undo_log_path):
    taken = set(os.listdir(folder))
    undo = []
    for r in results:
        if r.group != "rename" or not r.proposed:
            continue
        target = resolve_collision(r.proposed, taken)
        dst = os.path.join(folder, target)
        if os.path.exists(dst):
            continue
        os.rename(r.path, dst)
        taken.discard(os.path.basename(r.path))
        taken.add(target)
        undo.append({"from": os.path.basename(r.path), "to": target})
    with open(undo_log_path, "w", encoding="utf-8") as f:
        json.dump(undo, f, indent=2, ensure_ascii=False)
    return undo
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): apply_renames with undo log"
```

---

### Task 10: CLI (`print_report` + `main`)

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Consumes: `process_folder`, `apply_renames`, `FileResult`.
- Produces:
  - `format_report(results: list[FileResult]) -> str` — renders the rename table, the needs-review list with reasons, and a conformant/skip summary count. Skipped files are not listed individually.
  - `main(argv: list[str] | None = None) -> int` — argparse CLI: positional `folder`, `--apply`, optional `--json PATH`. Dry run by default.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rename_papers.py`:

```python
from rename_papers import format_report


def test_format_report_lists_renames_and_reviews_hides_skips():
    results = [
        FileResult("/x/old.pdf", "rename", proposed="Smith, J. (2023) T - 10.1_x.pdf"),
        FileResult("/x/q.pdf", "review", reason="no DOI found in PDF"),
        FileResult("/x/junk.pdf", "skip"),
        FileResult("/x/good.pdf", "conformant"),
    ]
    out = format_report(results)
    assert "old.pdf" in out
    assert "Smith, J. (2023) T - 10.1_x.pdf" in out
    assert "no DOI found in PDF" in out
    assert "junk.pdf" not in out          # skipped files are silent
    assert "1" in out                      # conformant count appears
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_format_report_lists_renames_and_reviews_hides_skips -v`
Expected: FAIL — `ImportError: cannot import name 'format_report'`

- [ ] **Step 3: Write minimal implementation**

Add to `rename_papers.py` (add `import argparse` and `import sys`):

```python
import argparse
import sys


def format_report(results):
    renames = [r for r in results if r.group == "rename"]
    reviews = [r for r in results if r.group == "review"]
    n_conformant = sum(1 for r in results if r.group == "conformant")
    n_skipped = sum(1 for r in results if r.group == "skip")

    lines = []
    lines.append(f"== Rename ({len(renames)}) ==")
    for r in renames:
        lines.append(f"  {os.path.basename(r.path)}")
        lines.append(f"    -> {r.proposed}")
    lines.append("")
    lines.append(f"== Needs review ({len(reviews)}) ==")
    for r in reviews:
        lines.append(f"  {os.path.basename(r.path)} — {r.reason}")
    lines.append("")
    lines.append(f"Already well-named (unchanged): {n_conformant}")
    lines.append(f"Skipped (not scholarly): {n_skipped}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rename scientific paper PDFs to Harvard-style names with DOI.")
    parser.add_argument("folder", help="folder containing PDFs")
    parser.add_argument("--apply", action="store_true", help="actually rename (default: dry run)")
    parser.add_argument("--json", dest="json_path", help="write full results as JSON to this path")
    args = parser.parse_args(argv)

    results = process_folder(args.folder)
    print(format_report(results))

    if args.json_path:
        payload = [{"path": r.path, "group": r.group, "proposed": r.proposed, "reason": r.reason} for r in results]
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    if args.apply:
        undo_path = os.path.join(args.folder, "rename-undo.json")
        undo = apply_renames(results, args.folder, undo_path)
        print(f"\nRenamed {len(undo)} files. Undo log: {undo_path}")
    else:
        print("\n(dry run — nothing renamed; pass --apply to rename)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes + full suite**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/ -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): CLI report + main"
```

---

### Task 11: `SKILL.md` + `references/format-rules.md`

**Files:**
- Create: `~/.claude/skills/rename-papers/SKILL.md`
- Create: `~/.claude/skills/rename-papers/references/format-rules.md`

**Interfaces:**
- Consumes: the finished `scripts/rename_papers.py`.
- Produces: the skill manifest + workflow Claude follows. (No automated test; verified by manual dry run in Step 3.)

- [ ] **Step 1: Write `references/format-rules.md`**

```markdown
# rename-papers — filename format rules

Format: `Surname, I. [et al.] (Year) Title - DOI.pdf`

- First author `Surname, Initial.`; append ` et al.` when there is more than one author.
- Year: four-digit publication year in parentheses; missing year → needs review.
- Title: from CrossRef, falling back to PDF-parsed title.
- DOI: appended after ` - `, with `/` replaced by `_`.
- Illegal chars `/ \ : * ? " < > |` → `_`; whitespace collapsed; filename ≤ 200 chars (title truncated to fit).
- Never overwrite; never invent a DOI; only DOIs literally found in the file are used.

Example: `Smith, J. et al. (2023) Deep learning for graphs - 10.1000_xyz123.pdf`
```

- [ ] **Step 2: Write `SKILL.md`**

```markdown
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
```

- [ ] **Step 3: Verify the skill end-to-end (manual dry run on a temp folder)**

Run:
```bash
cd ~/.claude/skills/rename-papers
python3 scripts/rename_papers.py "$HOME/Downloads" --json /tmp/rp.json | head -40
```
Expected: a report printed with Rename / Needs review sections and conformant/skipped counts; `/tmp/rp.json` written; no files renamed.

- [ ] **Step 4: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "docs(rename-papers): SKILL.md + format rules"
```

---

## Self-Review

**Spec coverage:**
- Filename format → Task 3 (`build_filename`) + Task 11 (rules doc). ✓
- Read metadata from PDF → Task 7. ✓
- DOI extraction (no hallucination) → Task 2 + pipeline only uses found DOIs (Task 8). ✓
- CrossRef confirmation → Task 6. ✓
- Classification / silent skip of non-papers → Task 4 + Task 8 (`skip` group) + Task 10 (hidden in report). ✓
- Needs-review with reasons (incl. missing year) → Task 8 + Task 10. ✓
- Already-conformant left alone + counted → Task 5 + Task 8 + Task 10. ✓
- Dry-run-first, `--apply` only renames → Task 10. ✓
- No overwrite + collision handling → Task 5 + Task 9. ✓
- Undo log → Task 9. ✓
- SKILL.md workflow incl. manual review of stragglers → Task 11. ✓
- Tests (pure fns no network, mocked CrossRef, fixture PDF) → Tasks 1–9. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `PaperMeta`, `Author`, `Classification`, `FileResult` defined once and reused with matching field names; `crossref_lookup(doi, fetch)`, `process_folder(folder, extractor, fetcher)`, `apply_renames(results, folder, undo_log_path)`, `build_filename(meta, max_len)` signatures consistent across tasks. ✓

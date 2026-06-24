# rename-papers Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add variant-marker preservation and two wrong-DOI safety checks to the existing `rename-papers` skill.

**Architecture:** Extend `scripts/rename_papers.py` with pure helpers (`extract_variant_marker`, `extract_all_dois`, surname normalization), thread a `variant` argument through `build_filename`, and wire the two new safety checks + variant tagging into `process_folder`. All TDD, no network/PDFs in tests.

**Tech Stack:** Python 3 stdlib (`re`, `unicodedata`), pytest.

## Global Constraints

- Edit only `~/.claude/skills/rename-papers/scripts/rename_papers.py` and its test file; no behavior change to unrelated functions.
- Variant marker rendered as ` [marker]` appended after the DOI, before `.pdf`; still within the 200-char cap.
- Variant markers detected from the ORIGINAL filename: `ANNOTATED`; version `vN`; same-year suffix `(YYYYa)`→`a`; OS dup counter `(N)` (1-2 digits).
- Bibliography check: ≥ 4 distinct DOIs in scanned text → needs-review, reason `"multiple DOIs found (likely a bibliography/reference list)"`.
- Author cross-check: compare CrossRef first-author surname to original filename after normalizing both (lowercase, strip diacritics, strip non-alphanumeric). Skip if normalized surname < 3 chars or the filename has no alphabetic token ≥ 4. On mismatch → needs-review, reason `"CrossRef author '<family>' not found in filename — possible wrong DOI"`.
- Run tests: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/ -v`. All previously-passing tests must still pass.

---

### Task R1: `extract_variant_marker()`

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Produces: `extract_variant_marker(filename: str) -> str | None` — returns a space-joined marker string detected from the filename stem, or `None`.

- [ ] **Step 1: Write the failing test** (append to test file)

```python
from rename_papers import extract_variant_marker


def test_variant_marker_annotated():
    assert extract_variant_marker("Frey_(1993)_Foo_ANNOTATED.pdf") == "ANNOTATED"


def test_variant_marker_version():
    assert extract_variant_marker("Gallus_Frey_(2016)_Awards_v2.pdf") == "v2"


def test_variant_marker_year_letter():
    assert extract_variant_marker("An_et_al_(2015a)_Template.pdf") == "a"
    assert extract_variant_marker("Bauer_et_al_(2004b)_Ethical.pdf") == "b"


def test_variant_marker_dup_counter():
    assert extract_variant_marker("Mergers_in_the_Indian_Banking_Sector_Tre (1).pdf") == "(1)"


def test_variant_marker_plain_year_is_not_a_marker():
    assert extract_variant_marker("Autor_(2015)_Why_Jobs.pdf") is None


def test_variant_marker_none():
    assert extract_variant_marker("Smith_(2023)_Clean.pdf") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_variant_marker_annotated -v`
Expected: FAIL — `ImportError: cannot import name 'extract_variant_marker'`

- [ ] **Step 3: Write minimal implementation** (add after `extract_doi`)

```python
_MARKER_ANNOTATED = re.compile(r"annotated", re.IGNORECASE)
_MARKER_VERSION = re.compile(r"(?:^|[ _\-(])(v\d+)(?:[ _\-).]|$)", re.IGNORECASE)
_MARKER_YEARLETTER = re.compile(r"\(\d{4}([a-z])\)")
_MARKER_DUPCOUNT = re.compile(r"\((\d{1,2})\)")


def extract_variant_marker(filename):
    stem = os.path.splitext(os.path.basename(filename or ""))[0]
    markers = []
    if _MARKER_ANNOTATED.search(stem):
        markers.append("ANNOTATED")
    mv = _MARKER_VERSION.search(stem)
    if mv:
        markers.append(mv.group(1).lower())
    my = _MARKER_YEARLETTER.search(stem)
    if my:
        markers.append(my.group(1))
    else:
        md = _MARKER_DUPCOUNT.search(stem)
        if md:
            markers.append(f"({md.group(1)})")
    return " ".join(markers) if markers else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/ -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): extract_variant_marker"
```

---

### Task R2: `extract_all_dois()`

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py`
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Produces: `extract_all_dois(text: str) -> list[str]` — distinct DOIs in first-seen order, trailing periods stripped.

- [ ] **Step 1: Write the failing test**

```python
from rename_papers import extract_all_dois


def test_extract_all_dois_distinct_in_order():
    text = "10.1/a and 10.2/b then 10.1/a again, 10.3/c."
    assert extract_all_dois(text) == ["10.1/a", "10.2/b", "10.3/c"]


def test_extract_all_dois_empty():
    assert extract_all_dois("") == []
    assert extract_all_dois("no doi here") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_extract_all_dois_distinct_in_order -v`
Expected: FAIL — `ImportError: cannot import name 'extract_all_dois'`

- [ ] **Step 3: Write minimal implementation** (add after `extract_doi`)

```python
def extract_all_dois(text):
    if not text:
        return []
    seen = []
    for m in _DOI_RE.finditer(text):
        d = m.group(0).rstrip(".")
        if d not in seen:
            seen.append(d)
    return seen
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/ -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): extract_all_dois"
```

---

### Task R3: `build_filename` variant parameter

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py` (function `build_filename`, currently lines ~78-95)
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Produces: `build_filename(meta, max_len=200, variant=None)` — when `variant` is truthy, append ` [variant]` after the DOI, before `.pdf`.

- [ ] **Step 1: Write the failing test**

```python
def test_build_filename_with_variant_marker():
    m = PaperMeta(authors=[Author("Frey", "Bruno"), Author("Gallus", "Jana")],
                  year=2017, title="Towards an Economics of Awards", doi="10.1111/joes.12127")
    assert build_filename(m, variant="ANNOTATED") == (
        "Frey, B. et al. (2017) Towards an Economics of Awards - 10.1111_joes.12127 [ANNOTATED].pdf"
    )


def test_build_filename_variant_none_unchanged():
    m = PaperMeta(authors=[Author("Smith", "John")], year=2023, title="T", doi="10.1/x")
    assert build_filename(m) == "Smith, J. (2023) T - 10.1_x.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_build_filename_with_variant_marker -v`
Expected: FAIL — `TypeError: build_filename() got an unexpected keyword argument 'variant'`

- [ ] **Step 3: Replace the `build_filename` function with**

```python
def build_filename(meta, max_len=200, variant=None):
    if not meta.authors:
        raise ValueError("build_filename requires at least one author")
    first = meta.authors[0]
    author_part = f"{first.family}, {first.given[0]}." if first.given else first.family
    if len(meta.authors) >= 2:
        author_part += " et al."
    doi_safe = (meta.doi or "").replace("/", "_")
    title = meta.title or ""
    tag = f" [{variant}]" if variant else ""
    suffix = f" - {doi_safe}{tag}.pdf"
    prefix = f"{author_part} ({meta.year}) "

    name = sanitize_filename(f"{prefix}{title}{suffix}")
    if len(name) > max_len:
        overflow = len(name) - max_len
        title = title[: max(0, len(title) - overflow)].rstrip()
        name = sanitize_filename(f"{prefix}{title}{suffix}")
    return name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/ -v`
Expected: PASS (all — existing build_filename tests still pass since `variant` defaults to None)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): build_filename variant marker"
```

---

### Task R4: Normalization helpers + integrate checks into `process_folder`

**Files:**
- Modify: `~/.claude/skills/rename-papers/scripts/rename_papers.py` (add `import unicodedata`; add helpers; rewrite `process_folder` body, currently lines ~171-208)
- Test: `~/.claude/skills/rename-papers/tests/test_rename_papers.py`

**Interfaces:**
- Consumes: `extract_all_dois`, `extract_variant_marker`, `build_filename`, `crossref_lookup`, `classify_document`, `is_already_conformant`.
- Produces:
  - `_normalize(s: str) -> str` — lowercase, strip diacritics, strip non-alphanumeric.
  - `_has_alpha_token(name: str) -> bool` — true if the name has an alphabetic token ≥ 4 chars.
  - `BIBLIOGRAPHY_DOI_THRESHOLD = 4` module constant.
  - `process_folder` now: routes ≥4-DOI files and author-mismatch files to `review`, and passes the detected variant into `build_filename`.

- [ ] **Step 1: Write the failing tests**

```python
from rename_papers import process_folder, FileResult


def _fake_pipeline(tmp_path, files, text_map, crossref_map):
    for n in files:
        (tmp_path / n).write_bytes(b"%PDF fake")

    def extractor(path, max_pages=2):
        return text_map[os.path.basename(path)], ""

    def fetcher(url):
        doi = url.rsplit("/works/", 1)[-1]
        return crossref_map.get(doi, {})

    return {os.path.basename(r.path): r
            for r in process_folder(str(tmp_path), extractor=extractor, fetcher=fetcher)}


def test_process_folder_bibliography_to_review(tmp_path):
    res = _fake_pipeline(
        tmp_path,
        ["biblio.pdf"],
        {"biblio.pdf": "refs 10.1/a 10.2/b 10.3/c 10.4/d 10.5/e"},
        {},
    )
    assert res["biblio.pdf"].group == "review"
    assert "bibliograph" in res["biblio.pdf"].reason.lower() or "multiple doi" in res["biblio.pdf"].reason.lower()


def test_process_folder_author_mismatch_to_review(tmp_path):
    res = _fake_pipeline(
        tmp_path,
        ["Derwall_et_al_(2005)_Ethical.pdf"],
        {"Derwall_et_al_(2005)_Ethical.pdf": "Abstract 10.1/x"},
        {"10.1/x": {"message": {"author": [{"family": "Bauer", "given": "Rob"}],
                                "title": ["The Ethical Mutual Fund Debate"],
                                "issued": {"date-parts": [[2007]]}}}},
    )
    r = res["Derwall_et_al_(2005)_Ethical.pdf"]
    assert r.group == "review"
    assert "bauer" in r.reason.lower()


def test_process_folder_author_match_renames_with_variant(tmp_path):
    res = _fake_pipeline(
        tmp_path,
        ["Frey_Gallus_(2017)_Awards_ANNOTATED.pdf"],
        {"Frey_Gallus_(2017)_Awards_ANNOTATED.pdf": "Abstract 10.1111/joes.12127"},
        {"10.1111/joes.12127": {"message": {"author": [{"family": "Frey", "given": "Bruno"},
                                                       {"family": "Gallus", "given": "Jana"}],
                                            "title": ["Towards an Economics of Awards"],
                                            "issued": {"date-parts": [[2017]]}}}},
    )
    r = res["Frey_Gallus_(2017)_Awards_ANNOTATED.pdf"]
    assert r.group == "rename"
    assert r.proposed.endswith("[ANNOTATED].pdf")


def test_process_folder_hyphenated_surname_not_flagged(tmp_path):
    res = _fake_pipeline(
        tmp_path,
        ["GregorySmith_Wright_(2019)_Tournaments.pdf"],
        {"GregorySmith_Wright_(2019)_Tournaments.pdf": "Abstract 10.1093/oep/gpy033"},
        {"10.1093/oep/gpy033": {"message": {"author": [{"family": "Gregory-Smith", "given": "Ian"}],
                                            "title": ["Winners and losers"],
                                            "issued": {"date-parts": [[2019]]}}}},
    )
    assert res["GregorySmith_Wright_(2019)_Tournaments.pdf"].group == "rename"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/test_rename_papers.py::test_process_folder_bibliography_to_review -v`
Expected: FAIL (currently the bibliography file would be renamed, not reviewed)

- [ ] **Step 3: Implement**

Add `import unicodedata` to the imports block at the top.

Add these helpers and constant (place them just above `process_folder`):

```python
BIBLIOGRAPHY_DOI_THRESHOLD = 4


def _normalize(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _has_alpha_token(name):
    return any(len(tok) >= 4 for tok in re.split(r"[^A-Za-z]+", name) if tok.isalpha())
```

Replace the body of `process_folder` with:

```python
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

        all_dois = extract_all_dois(text)
        doi = all_dois[0] if all_dois else None
        cls = classify_document(text, has_doi=bool(doi), embedded_title=etitle)

        if cls.kind == "not_paper":
            results.append(FileResult(path, "skip"))
            continue
        if not doi:
            reason = "could not classify; no DOI found" if cls.kind == "ambiguous" else "no DOI found in PDF"
            results.append(FileResult(path, "review", reason=reason))
            continue
        if len(all_dois) >= BIBLIOGRAPHY_DOI_THRESHOLD:
            results.append(FileResult(path, "review",
                                      reason="multiple DOIs found (likely a bibliography/reference list)"))
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

        surname_norm = _normalize(meta.authors[0].family)
        if len(surname_norm) >= 3 and _has_alpha_token(name) and surname_norm not in _normalize(name):
            results.append(FileResult(path, "review",
                                      reason=f"CrossRef author '{meta.authors[0].family}' not found in filename — possible wrong DOI"))
            continue

        if is_already_conformant(name, doi):
            results.append(FileResult(path, "conformant"))
            continue

        variant = extract_variant_marker(name)
        results.append(FileResult(path, "rename", proposed=build_filename(meta, variant=variant)))
    return results
```

- [ ] **Step 4: Run the full suite**

Run: `cd ~/.claude/skills/rename-papers && python3 -m pytest tests/ -v`
Expected: PASS (all — new tests plus every prior test)

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/rename-papers && git add -A
git commit -m "feat(rename-papers): bibliography + author-mismatch checks, variant tagging"
```

---

### Task R5: Re-run real dry-run on Downloads (verification)

**Files:** none (verification only).

- [ ] **Step 1: Dry-run and compare against the known cases**

Run:
```bash
cd ~/.claude/skills/rename-papers
python3 scripts/rename_papers.py "$HOME/Downloads" --json /tmp/rename-papers2.json >/dev/null 2>&1
python3 - <<'PY'
import json, os, collections
d=json.load(open('/tmp/rename-papers2.json'))
c=collections.Counter(x['group'] for x in d)
print("counts:", dict(c), "total", len(d))
ren=[x for x in d if x['group']=='rename']
tgt=collections.Counter(x['proposed'] for x in ren)
print("rename collisions remaining:", sum(1 for v in tgt.values() if v>1))
# annotated tagged?
print("tagged [ANNOTATED]:", sum(1 for x in ren if '[ANNOTATED]' in x['proposed']))
# known bad cases now in review?
rev={os.path.basename(x['path']):x['reason'] for x in d if x['group']=='review'}
for f in ["Design_and_Løsninger_(2015)_Samlet_Litteraturliste.pdf",
          "Derwall_et_al_(2005)_The_Ethical_Mutual_Fund_Performance.pdf",
          "Mouritsen_(2025)_Fraud_Auditing.pdf"]:
    print(f"{f[:45]:45} -> {'REVIEW: '+rev[f][:50] if f in rev else 'NOT in review'}")
PY
```
Expected: the three known-bad files now appear in review; `[ANNOTATED]`-tagged renames present; rename collisions reduced.

This task has no commit (verification only).

---

## Self-Review

**Spec coverage:** variant detection (R1) + threading (R3, R4); bibliography check (R2 + R4); author cross-check w/ diacritic + hyphen handling (R4); validated on real data (R5). ✓
**Placeholder scan:** none. ✓
**Type consistency:** `extract_variant_marker(filename)`, `extract_all_dois(text)`, `build_filename(meta, max_len, variant)`, `_normalize`, `_has_alpha_token`, `BIBLIOGRAPHY_DOI_THRESHOLD` used consistently across R1-R4. ✓

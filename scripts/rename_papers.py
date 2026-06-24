"""rename-papers: rename scientific paper PDFs into Harvard-style names with DOI."""
import re
import json
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

_ILLEGAL = re.compile(r'[/\\:*?"<>|]')
_WHITESPACE = re.compile(r"\s+")


def sanitize_filename(name: str) -> str:
    name = _ILLEGAL.sub("_", name or "")
    name = _WHITESPACE.sub(" ", name).strip()
    return name


_DOI_RE = re.compile(r"10\.\d{4,}/[^\s\"<>,;()\[\]]+", re.IGNORECASE)


def extract_doi(text):
    if not text:
        return None
    m = _DOI_RE.search(text)
    if not m:
        return None
    return m.group(0).rstrip(".")


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

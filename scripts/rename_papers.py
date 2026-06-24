"""rename-papers: rename scientific paper PDFs into Harvard-style names with DOI."""
import re
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

"""rename-papers: rename scientific paper PDFs into Harvard-style names with DOI."""
import re

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

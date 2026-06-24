"""rename-papers: rename scientific paper PDFs into Harvard-style names with DOI."""
import re

_ILLEGAL = re.compile(r'[/\\:*?"<>|]')
_WHITESPACE = re.compile(r"\s+")


def sanitize_filename(name: str) -> str:
    name = _ILLEGAL.sub("_", name or "")
    name = _WHITESPACE.sub(" ", name).strip()
    return name

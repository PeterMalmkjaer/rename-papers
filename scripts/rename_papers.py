"""rename-papers: rename scientific paper PDFs into Harvard-style names with DOI."""
import re
import json
import glob
import os
import argparse
import sys
import unicodedata
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


_MARKER_ANNOTATED = re.compile(r"annotated", re.IGNORECASE)
_MARKER_VERSION = re.compile(r"(?:^|[ _\-(])(v\d+)(?:[ _\-).]|$)", re.IGNORECASE)
_MARKER_YEARLETTER = re.compile(r"\(\d{4}([a-z])\)")
_MARKER_DUPCOUNT = re.compile(r"\((\d{1,2})\)")


_DOI_ANY_RE = re.compile(r"10\.\d+/[^\s\"<>,;()\[\]]+", re.IGNORECASE)


def extract_all_dois(text):
    if not text:
        return []
    seen = []
    for m in _DOI_ANY_RE.finditer(text):
        d = m.group(0).rstrip(".")
        if d not in seen:
            seen.append(d)
    return seen


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


@dataclass
class FileResult:
    path: str
    group: str
    proposed: Optional[str] = None
    reason: str = ""


BIBLIOGRAPHY_DOI_THRESHOLD = 4


def _normalize(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _has_alpha_token(name):
    return any(len(tok) >= 4 for tok in re.split(r"[^A-Za-z]+", name) if tok.isalpha())


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
        name_norm = _normalize(name)
        if len(surname_norm) >= 3 and _has_alpha_token(name) and "_" in name and surname_norm not in name_norm:
            results.append(FileResult(path, "review",
                                      reason=f"CrossRef author '{meta.authors[0].family}' not found in filename — possible wrong DOI"))
            continue

        if is_already_conformant(name, doi):
            results.append(FileResult(path, "conformant"))
            continue

        variant = extract_variant_marker(name)
        results.append(FileResult(path, "rename", proposed=build_filename(meta, variant=variant)))
    return results


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


def load_results_from_json(json_path: str) -> list:
    with open(json_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    return [
        FileResult(
            path=item["path"],
            group=item["group"],
            proposed=item.get("proposed"),
            reason=item.get("reason", ""),
        )
        for item in items
    ]


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
    parser.add_argument("--from-json", dest="from_json", metavar="PATH",
                        help="load results from a previously written --json file and apply exactly those renames")
    args = parser.parse_args(argv)

    if args.apply and args.from_json:
        results = load_results_from_json(args.from_json)
        print(format_report(results))
    else:
        results = process_folder(args.folder)
        print(format_report(results))

        if args.json_path:
            payload = [{"path": r.path, "group": r.group, "proposed": r.proposed, "reason": r.reason} for r in results]
            with open(args.json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)

        if args.apply:
            print(
                "Warning: applying without --from-json re-scans the folder and may differ from the dry-run preview.",
                file=sys.stderr,
            )

    if args.apply:
        undo_path = os.path.join(args.folder, "rename-undo.json")
        undo = apply_renames(results, args.folder, undo_path)
        print(f"\nRenamed {len(undo)} files. Undo log: {undo_path}")
    else:
        print("\n(dry run — nothing renamed; pass --apply to rename)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

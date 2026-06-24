from rename_papers import sanitize_filename


def test_sanitize_replaces_illegal_chars():
    assert sanitize_filename('a/b:c*d?"e<f>g|h\\i') == "a_b_c_d__e_f_g_h_i"


def test_sanitize_collapses_whitespace_and_strips():
    assert sanitize_filename("  hello   world  ") == "hello world"


from rename_papers import extract_doi


def test_extract_doi_finds_doi():
    assert extract_doi("see doi 10.1016/j.aos.2021.101282 here") == "10.1016/j.aos.2021.101282"


def test_extract_doi_strips_trailing_period():
    assert extract_doi("DOI: 10.2307/1885099.") == "10.2307/1885099"


def test_extract_doi_returns_none_when_absent():
    assert extract_doi("no identifier here") is None
    assert extract_doi("") is None


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

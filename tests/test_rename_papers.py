import os
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


def test_build_filename_raises_on_empty_authors():
    import pytest
    with pytest.raises(ValueError, match="at least one author"):
        build_filename(PaperMeta(authors=[], year=2023, title="T", doi="10.1/x"))


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


from rename_papers import load_results_from_json
from rename_papers import main as _main


def test_load_results_from_json(tmp_path):
    src = tmp_path / "paper.pdf"
    src.write_bytes(b"%PDF fake")
    payload = [
        {"path": str(src), "group": "rename", "proposed": "Smith, J. (2023) T - 10.1_x.pdf", "reason": ""},
    ]
    json_file = tmp_path / "results.json"
    json_file.write_text(_json.dumps(payload), encoding="utf-8")

    results = load_results_from_json(str(json_file))

    assert len(results) == 1
    assert results[0].path == str(src)
    assert results[0].group == "rename"
    assert results[0].proposed == "Smith, J. (2023) T - 10.1_x.pdf"


def test_main_apply_from_json_renames_exactly(tmp_path):
    src = tmp_path / "old.pdf"
    src.write_bytes(b"%PDF fake")
    payload = [
        {"path": str(src), "group": "rename", "proposed": "Smith, J. (2023) T - 10.1_x.pdf", "reason": ""},
    ]
    json_file = tmp_path / "results.json"
    json_file.write_text(_json.dumps(payload), encoding="utf-8")

    _main([str(tmp_path), "--apply", "--from-json", str(json_file)])

    assert (tmp_path / "Smith, J. (2023) T - 10.1_x.pdf").exists()
    assert not src.exists()


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


from rename_papers import extract_all_dois


def test_extract_all_dois_distinct_in_order():
    text = "10.1/a and 10.2/b then 10.1/a again, 10.3/c."
    assert extract_all_dois(text) == ["10.1/a", "10.2/b", "10.3/c"]


def test_extract_all_dois_empty():
    assert extract_all_dois("") == []
    assert extract_all_dois("no doi here") == []


def test_build_filename_with_variant_marker():
    m = PaperMeta(authors=[Author("Frey", "Bruno"), Author("Gallus", "Jana")],
                  year=2017, title="Towards an Economics of Awards", doi="10.1111/joes.12127")
    assert build_filename(m, variant="ANNOTATED") == (
        "Frey, B. et al. (2017) Towards an Economics of Awards - 10.1111_joes.12127 [ANNOTATED].pdf"
    )


def test_build_filename_variant_none_unchanged():
    m = PaperMeta(authors=[Author("Smith", "John")], year=2023, title="T", doi="10.1/x")
    assert build_filename(m) == "Smith, J. (2023) T - 10.1_x.pdf"


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

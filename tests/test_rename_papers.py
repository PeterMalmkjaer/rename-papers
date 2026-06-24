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

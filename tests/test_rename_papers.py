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

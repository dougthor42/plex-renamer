from pathlib import Path

import pytest

import movie_tmdb


@pytest.mark.parametrize(
    "string, want",
    [
        ("foo.bar", False),
        ("a [1234] {tmdb-123}", False),
        ("a [134] {tmdb-}", False),
        ("a (1234) {tmdb-123}", True),
        ("Airplane! (1980) {tmdb-813}", True),
        ("New Airplane! (1980) {tmdb-813}", True),
        ("めがね めがね? (2031) {tmdb-123}", True),
        ("めがね めがね? [2031] {tmdb-123}", False),  # Wrong parens on year.
    ],
)
def test_RE_GOOD_FN(string, want):
    is_match = movie_tmdb.RE_GOOD_FN.fullmatch(string) is not None
    assert is_match is want


@pytest.mark.parametrize(
    "data, want",
    [
        (
            movie_tmdb.SearchResult(
                {"title": "foo", "id": 123, "release_date": "2031-03-03"}
            ),
            "foo (2031) {tmdb-123}",
        ),
        (
            movie_tmdb.SearchResult(
                {"title": "?", "id": 123, "release_date": "2031-03-03"}
            ),
            "FIXME (2031) {tmdb-123}",
        ),
        (
            movie_tmdb.SearchResult(
                {"title": "Guess Who?", "id": 123, "release_date": "2031-03-03"}
            ),
            "Guess Who (2031) {tmdb-123}",
        ),
        (
            movie_tmdb.SearchResult(
                {"title": "めがね?", "id": 123, "release_date": "2031-03-03"}
            ),
            "めがね (2031) {tmdb-123}",
        ),
    ],
)
def test_make_filename(data, want):
    got = movie_tmdb.make_filename(data)
    assert got == want


@pytest.mark.parametrize(
    "data, want",
    [
        ("foo [1000]", "foo"),
        ("bar (9999)", "bar"),
        ("foobarbaz (1235]", "foobarbaz (1235]"),
        ("a [1234)", "a [1234)"),
        ("abcd [123]", "abcd [123]"),
    ],
)
def test_strip_year(data, want):
    got = movie_tmdb._strip_year(data)
    assert got == want


@pytest.mark.parametrize(
    "data, want",
    [
        ("hello", "hello"),
        ("group - 11 - title", "11 - title"),
        ("foo - bar", "foo - bar"),
    ],
)
def test_strip_leading_info(data, want):
    got = movie_tmdb._strip_leading_info(data)
    assert got == want


@pytest.mark.parametrize(
    "data, want",
    [
        ("11 - title", "title"),
        ("04 - foo", "foo"),
        ("bar", "bar"),
    ],
)
def test_strip_leading_number(data, want):
    got = movie_tmdb._strip_leading_number(data)
    assert got == want


@pytest.mark.parametrize(
    "fn, want",
    [
        ("Airplane [1980]", "Airplane"),
        (
            "01 Harry Potter and the Sorcerers Stone [2001]",
            "Harry Potter and the Sorcerers Stone",
        ),
        ("Youth in Revolt", "Youth in Revolt"),
        ("Pixar Classic - 01 - Toy Story", "Toy Story"),
        ("Pixar Classic - 10 - Up (2009)", "Up"),
    ],
)
def test_get_search_term_from_fn(fn, want):
    got = movie_tmdb.get_search_term_from_fn(fn)
    assert got == want


@pytest.mark.parametrize(
    "fp, result, want",
    [
        (
            Path("/foo/bar/baz.avi"),
            movie_tmdb.SearchResult(
                {"title": "foo", "id": 123, "release_date": "2031-03-03"}
            ),
            Path("/foo/bar/foo (2031) {tmdb-123}.avi"),
        ),
        (
            Path("/foo/bar/baz.mp4"),
            movie_tmdb.SearchResult(
                {"title": "foo", "id": 123, "release_date": "2031-03-03"}
            ),
            Path("/foo/bar/foo (2031) {tmdb-123}.mp4"),
        ),
    ],
)
def test_create_new_filepath(fp, result, want):
    got = movie_tmdb.create_new_filepath(fp, result)
    assert got == want


@pytest.mark.parametrize(
    "fp, want",
    [
        (Path("/foo/bar.avi"), Path("/foo/bar/bar.avi")),
        (
            Path("/foo/bar (1234) {tmdb-1234}.avi"),
            Path("/foo/bar (1234) {tmdb-1234}/bar (1234) {tmdb-1234}.avi"),
        ),
        (
            Path("/media/tyr/thor/Video/Movies/Monsters, Inc. (2001) {tmdb-585}.avi"),
            Path(
                "/media/tyr/thor/Video/Movies/Monsters, Inc. (2001) {tmdb-585}/Monsters, Inc. (2001) {tmdb-585}.avi"  # noqa: E501
            ),
        ),
        (
            Path(
                "/media/tyr/thor/Video/Movies/Monsters, Inc. (2001) {tmdb-585}/Monsters, Inc. (2001) {tmdb-585}.avi"  # noqa: E501
            ),
            None,
        ),
    ],
)
def test_move_to_folder(fp, want):
    got = movie_tmdb.move_to_folder(fp, dry_run=True)
    assert got == want

"""Unit tests for the tokenize-aware source helpers that keep detectors from
matching Python they only *mention* (in a comment or string literal)."""

from __future__ import annotations

from flunk.detectors import _source


def test_iter_comments_yields_only_real_comments() -> None:
    src = (
        "x = 1  # a real comment\n"
        'BANNER = "# not a comment, just a string"\n'
        "y = 2\n"
    )
    comments = list(_source.iter_comments(src))
    assert comments == [(1, "# a real comment")]


def test_iter_comments_falls_back_on_syntax_error() -> None:
    # An unterminated bracket makes tokenize raise; the naive fallback still
    # finds the comment (and must not duplicate it).
    src = "x = (\n# still findable\n"
    comments = list(_source.iter_comments(src))
    assert comments == [(2, "# still findable")]


def test_code_lines_blanks_comment_text_but_keeps_strings() -> None:
    src = (
        'HEADER = "X-CSRF-Token"  # the header name\n'
        "# csrf-token mentioned only in a comment\n"
    )
    code = _source.code_lines(src)
    # The string literal survives; the trailing comment and comment-only line do not.
    assert 'HEADER = "X-CSRF-Token"' in code[0]
    assert "the header name" not in code[0]
    assert "csrf-token" not in "\n".join(code)

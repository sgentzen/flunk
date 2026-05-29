"""Unit tests for shared python-side detector utilities."""

from __future__ import annotations

import warnings
from pathlib import Path

from flunk.detectors._walk import parse_py


def test_parse_py_suppresses_audited_code_warnings(tmp_path: Path) -> None:
    """Invalid escape sequences in the *audited* code must not leak as
    SyntaxWarnings on flunk's own stderr."""
    src = tmp_path / "bad_escape.py"
    # `\e` and `\.` are invalid escape sequences (SyntaxWarning at parse time).
    src.write_text('p = "C:\\e"\nq = "\\."\n')
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        tree = parse_py(src)
    assert tree is not None


def test_parse_py_returns_none_on_syntax_error(tmp_path: Path) -> None:
    src = tmp_path / "broken.py"
    src.write_text("def (:\n")
    assert parse_py(src) is None


def test_parse_py_accepts_pre_read_text(tmp_path: Path) -> None:
    src = tmp_path / "ok.py"
    text = "x = 1\n"
    src.write_text(text)
    assert parse_py(src, text) is not None

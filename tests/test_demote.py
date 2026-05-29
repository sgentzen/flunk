"""Unit tests for the justification-aware demote pass."""

from __future__ import annotations

from pathlib import Path

from flunk.demote import demote
from flunk.findings import Finding


def _mk(file: Path, line: int, sev: str = "high") -> Finding:
    return Finding(
        rule_id="flunk.test",
        category="oss-catalog",
        severity=sev,
        file=file,
        line=line,
        message="test",
        replacement="something",
    )


def test_marker_within_3_lines_above_demotes(tmp_path: Path) -> None:
    src = tmp_path / "a.py"
    src.write_text(
        "# we deliberately rolled our own here\n"  # line 1
        "x = 1\n"                                   # line 2
        "y = 2\n"                                   # line 3
        "z = os.environ.get('K')  # finding here\n"  # line 4
    )
    out = demote([_mk(src, 4)])
    assert len(out) == 1
    assert out[0].severity == "medium"
    assert out[0].raw_severity == "high"
    assert out[0].demoted_by is not None


def test_marker_within_3_lines_below_demotes(tmp_path: Path) -> None:
    src = tmp_path / "b.py"
    src.write_text(
        "z = os.environ.get('K')\n"
        "y = 2\n"
        "# fall back to env var rather than failing\n"
        "x = 1\n"
    )
    out = demote([_mk(src, 1)])
    assert out[0].severity == "medium"


def test_no_marker_no_demote(tmp_path: Path) -> None:
    src = tmp_path / "c.py"
    src.write_text("z = os.environ.get('K')\n")
    out = demote([_mk(src, 1)])
    assert out[0].severity == "high"
    assert out[0].demoted_by is None


def test_nitpick_demotes_to_suppressed(tmp_path: Path) -> None:
    src = tmp_path / "d.py"
    src.write_text("# deliberately doing X\nx = 1\n")
    out = demote([_mk(src, 2, sev="nitpick")])
    assert out == []  # suppressed entirely


def test_module_docstring_justification_demotes(tmp_path: Path) -> None:
    """A project-level justification in the module docstring demotes findings
    anywhere in that file, not just within +-3 lines."""
    src = tmp_path / "f.py"
    body = '"""This module deliberately rolls its own X for reason Y."""\n'
    body += "import os\n"
    body += "filler = 1\n" * 20  # push the finding well outside the +-3 window
    body += "z = os.environ.get('K')\n"
    src.write_text(body)
    finding_line = body.count("\n")  # last line
    out = demote([_mk(src, finding_line)])
    assert out[0].severity == "medium"
    assert out[0].demoted_by is not None


def test_no_docstring_justification_no_demote(tmp_path: Path) -> None:
    src = tmp_path / "g.py"
    body = '"""An ordinary module docstring with no justification."""\n'
    body += "filler = 1\n" * 20
    body += "z = os.environ.get('K')\n"
    src.write_text(body)
    out = demote([_mk(src, body.count("\n"))])
    assert out[0].severity == "high"
    assert out[0].demoted_by is None


def test_marker_in_string_literal_doesnt_match(tmp_path: Path) -> None:
    """Markers anchor to `#` so they don't fire on string literals."""
    src = tmp_path / "e.py"
    src.write_text(
        'msg = "we deliberately fail here"\n'
        "x = os.environ.get('K')\n"
    )
    out = demote([_mk(src, 2)])
    assert out[0].severity == "high"
    assert out[0].demoted_by is None

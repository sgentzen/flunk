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


def test_function_docstring_justification_demotes(tmp_path: Path) -> None:
    """A justification in the enclosing function's docstring demotes a finding
    inside that function — even with a silent module docstring and no nearby
    `#` comment. (Module-level demote already covers the whole file; this covers
    the narrower function scope, e.g. a hand-rolled migration helper.)"""
    src = tmp_path / "h.py"
    body = '"""Ordinary module docstring, no justification."""\n'  # line 1
    body += "import os\n"                                          # line 2
    body += "def loader():\n"                                      # line 3
    body += '    """We deliberately read env directly rather than settings."""\n'  # line 4
    body += "    filler = 1\n" * 10                                # lines 5-14
    body += "    return os.environ.get('K')\n"                     # last line
    src.write_text(body)
    finding_line = body.count("\n")  # last line, well outside the +-3 window
    out = demote([_mk(src, finding_line)])
    assert out[0].severity == "medium"
    assert out[0].demoted_by is not None


def test_class_docstring_justification_demotes(tmp_path: Path) -> None:
    """A class-level docstring justification demotes findings in its body."""
    src = tmp_path / "i.py"
    body = "import os\n"                                           # line 1
    body += "class Cfg:\n"                                         # line 2
    body += '    """Config is read from env on purpose for 12-factor parity."""\n'  # line 3
    body += "    filler = 1\n" * 10                                # lines 4-13
    body += "    val = os.environ.get('K')\n"                      # last line
    src.write_text(body)
    out = demote([_mk(src, body.count("\n"))])
    assert out[0].severity == "medium"
    assert out[0].demoted_by is not None


def test_nested_scope_falls_back_to_outer_docstring(tmp_path: Path) -> None:
    """When the innermost function docstring has no justification but an
    enclosing scope does, the finding is still demoted (fall-through to the
    outer scope, then module docstring)."""
    src = tmp_path / "nest.py"
    body = "import os\n"                                           # line 1
    body += "class Cfg:\n"                                         # line 2
    body += '    """We deliberately centralize env reads here."""\n'  # line 3
    body += "    def load(self):\n"                                # line 4
    body += '        """Plain inner docstring, no marker."""\n'    # line 5
    body += "        return os.environ.get('K')\n"                 # line 6
    src.write_text(body)
    out = demote([_mk(src, 6)])
    assert out[0].severity == "medium"
    assert out[0].demoted_by is not None


def test_decorator_line_is_covered_by_scope(tmp_path: Path) -> None:
    """A finding anchored to a decorator line is still inside the function's
    justification span."""
    src = tmp_path / "deco.py"
    body = "import os\n"                                           # line 1
    body += "def deco(fn):\n    return fn\n"                       # lines 2-3
    body += "@deco\n"                                             # line 4 (decorator)
    body += "def loader():\n"                                      # line 5
    body += '    """We deliberately read env on purpose here."""\n'  # line 6
    body += "    return os.environ.get('K')\n"                     # line 7
    src.write_text(body)
    out = demote([_mk(src, 4)])  # finding on the decorator line
    assert out[0].severity == "medium"
    assert out[0].demoted_by is not None


def test_function_docstring_justification_does_not_leak_to_siblings(
    tmp_path: Path,
) -> None:
    """A function's docstring justification must not demote a finding that lives
    outside that function."""
    src = tmp_path / "j.py"
    body = "import os\n"                                           # line 1
    body += "def helper():\n"                                      # line 2
    body += '    """We deliberately do X here."""\n'               # line 3
    body += "    return 1\n"                                       # line 4
    body += "outside = os.environ.get('K')\n"                     # line 5 (module scope)
    src.write_text(body)
    out = demote([_mk(src, 5)])
    assert out[0].severity == "high"
    assert out[0].demoted_by is None


def test_plain_function_docstring_no_demote(tmp_path: Path) -> None:
    """A function docstring without any justification phrase does not demote —
    guards the `_apply_inplace_migrations`-style case where the rationale is
    explained but uses no marker vocabulary."""
    src = tmp_path / "k.py"
    body = "import os\n"                                           # line 1
    body += "def loader():\n"                                      # line 2
    body += '    """Read the data dir and boot the app cleanly."""\n'  # line 3
    body += "    return os.environ.get('K')\n"                     # line 4
    src.write_text(body)
    out = demote([_mk(src, 4)])
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

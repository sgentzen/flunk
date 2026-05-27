"""Unit tests for ranking."""

from __future__ import annotations

from pathlib import Path

from flunk.findings import Finding
from flunk.rank import rank


def _f(sev: str, cat: str, path: str, line: int = 1) -> Finding:
    return Finding(
        rule_id="x", category=cat, severity=sev,
        file=Path(path), line=line, message="m",
    )


def test_severity_first() -> None:
    a = _f("medium", "oss-catalog", "a.py")
    b = _f("high", "anti-pattern", "z.py")
    assert rank([a, b])[0] is b


def test_category_breaks_ties() -> None:
    a = _f("high", "oss-catalog", "z.py")
    b = _f("high", "anti-pattern", "a.py")
    assert rank([b, a])[0] is a  # oss-catalog ranks first


def test_file_breaks_remaining_ties() -> None:
    a = _f("high", "oss-catalog", "a.py")
    b = _f("high", "oss-catalog", "z.py")
    assert rank([b, a]) == [a, b]

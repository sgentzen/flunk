"""duplicate-retry should count only production source retry functions.

Regression guard for the false positive where pytest functions named
`test_retry_*` inflated the count (see classify / walk_py source filtering).
"""

from __future__ import annotations

from pathlib import Path

from flunk.detectors.duplicate_retry import run


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_fires_on_two_source_retry_functions(tmp_path: Path) -> None:
    _write(tmp_path / "a.py", "def retry_a():\n    pass\n")
    _write(tmp_path / "pkg" / "b.py", "def retry_b():\n    pass\n")
    findings = run(tmp_path)
    assert len(findings) == 2
    assert all(f.rule_id == "flunk.duplicate-retry" for f in findings)


def test_does_not_count_test_functions(tmp_path: Path) -> None:
    _write(tmp_path / "a.py", "def _retry_request():\n    pass\n")
    _write(
        tmp_path / "tests" / "test_thing.py",
        "def test_retry_on_error():\n    pass\n"
        "def test_retry_includes_feedback():\n    pass\n",
    )
    # Only one real source retry function -> below the >=2 threshold.
    assert run(tmp_path) == []

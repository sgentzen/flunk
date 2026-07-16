"""Unit tests for display_path, the shared finding-path renderer."""

from __future__ import annotations

from pathlib import Path

from flunk.findings import display_path


def test_relativized_to_root_with_forward_slashes(tmp_path: Path) -> None:
    target = tmp_path / "src" / "app.py"
    assert display_path(target, tmp_path) == "src/app.py"


def test_no_root_returns_path_unchanged() -> None:
    target = Path("src") / "app.py"
    assert display_path(target, None) == str(target)


def test_file_outside_root_falls_back_to_absolute(tmp_path: Path) -> None:
    # relative_to raises rather than walking up with `..`, so the absolute
    # path is the only honest rendering.
    outside = tmp_path.parent / "elsewhere" / "a.py"
    assert display_path(outside, tmp_path) == str(outside)

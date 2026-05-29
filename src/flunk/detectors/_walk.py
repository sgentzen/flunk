"""Shared utilities for python-side detectors."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from flunk.classify import is_source

SKIP_DIRS = frozenset({
    ".venv", "venv", "node_modules", ".git", "build", "dist",
    "__pycache__", ".tox", ".worktrees", ".claude",
})


def walk_py(project: Path, *, source_only: bool = True) -> Iterator[Path]:
    """Yield .py files under `project`, skipping common noise dirs.

    By default only hand-authored production source is yielded (tests,
    migrations, etc. are excluded). Pass ``source_only=False`` to yield
    every .py file regardless of kind.
    """
    for path in project.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if source_only and not is_source(path):
            continue
        yield path

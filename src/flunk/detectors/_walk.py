"""Shared utilities for python-side detectors."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

SKIP_DIRS = frozenset({
    ".venv", "venv", "node_modules", ".git", "build", "dist",
    "__pycache__", ".tox", ".worktrees", ".claude",
})


def walk_py(project: Path) -> Iterator[Path]:
    """Yield every .py file under `project`, skipping common noise dirs."""
    for path in project.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path

"""Shared utilities for python-side detectors."""

from __future__ import annotations

import ast
import warnings
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


def parse_py(path: Path, text: str | None = None) -> ast.Module | None:
    """Parse a .py file to an AST, or return None on I/O or syntax error.

    Suppresses parse-time warnings (e.g. invalid escape sequences) about the
    *audited* project: those describe the code under audit, not flunk, and must
    not leak onto flunk's own stderr. Passing the real filename keeps any
    warning we don't suppress attributable rather than `<unknown>`.
    """
    if text is None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        try:
            return ast.parse(text, filename=str(path))
        except SyntaxError:
            return None

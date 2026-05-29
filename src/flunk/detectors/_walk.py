"""Shared utilities for python-side detectors."""

from __future__ import annotations

import ast
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


def build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Map each AST node to its parent (child -> parent)."""
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def ancestors(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> Iterator[ast.AST]:
    """Yield a node's ancestors from nearest parent up to the root."""
    cur = parents.get(node)
    while cur is not None:
        yield cur
        cur = parents.get(cur)

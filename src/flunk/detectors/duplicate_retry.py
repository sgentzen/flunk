"""Rule #7: Two `*retry*` function definitions in the same project with
structurally similar shape. Extract shared retry / use tenacity.

Approach: AST-walk every .py file in the project (skip venv / build /
worktrees), collect functions whose name contains 'retry', emit a
finding if there are ≥2.

Expected fires: erate-filing-assistant
"""

from __future__ import annotations

import ast
from pathlib import Path

from flunk.catalog.metadata import lookup
from flunk.detectors._walk import walk_py
from flunk.findings import Finding

RULE_ID = "flunk.duplicate-retry"


def run(project: Path) -> list[Finding]:
    retry_defs: list[tuple[Path, int, str]] = []
    for path in walk_py(project):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if "retry" in node.name.lower():
                    retry_defs.append((path, node.lineno, node.name))
    if len(retry_defs) < 2:
        return []
    meta = lookup(RULE_ID)
    # Emit one finding per retry function so each is independently
    # actionable (which one to keep, which to delete?).
    locations = ", ".join(f"{p.name}:{lineno}" for p, lineno, _ in retry_defs)
    return [
        Finding(
            rule_id=RULE_ID,
            category=meta.category,
            severity=meta.severity,
            file=path,
            line=lineno,
            message=(
                f"`{name}` is one of {len(retry_defs)} retry-named functions "
                f"in this project ({locations}). Extract a shared helper or "
                f"use tenacity."
            ),
            replacement=meta.replacement,
            replacement_url=meta.replacement_url,
        )
        for (path, lineno, name) in retry_defs
    ]

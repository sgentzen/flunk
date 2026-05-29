"""Rule #15: Module-level mutable singleton (e.g., `_client: X | None = None`)
without a lock, sitting in a project where another file uses a lock pattern.

If the rest of the project clearly cares about thread safety
(`threading.Lock()` or `asyncio.Lock()` somewhere), an unlocked mutable
singleton stands out as inconsistent.

Expected fires: erate-prospector
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from flunk.catalog.metadata import lookup
from flunk.detectors._walk import parse_py, walk_py
from flunk.findings import Finding

RULE_ID = "flunk.module-singleton"
_LOCK_RE = re.compile(r"\b(threading\.Lock|asyncio\.Lock)\(\)")


def _module_level_optional_singletons(tree: ast.Module) -> list[tuple[int, str]]:
    """Return (lineno, name) for `_x: T | None = None` at module level."""
    out: list[tuple[int, str]] = []
    for node in tree.body:
        # `_name: Foo | None = None`
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id.startswith("_")
            and isinstance(node.value, ast.Constant)
            and node.value.value is None
        ):
            out.append((node.lineno, node.target.id))
        # `_name = None` (unannotated)
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.startswith("_")
            and isinstance(node.value, ast.Constant)
            and node.value.value is None
        ):
            out.append((node.lineno, node.targets[0].id))
    return out


def run(project: Path) -> list[Finding]:
    paths = list(walk_py(project))
    # First pass: is there any file using a Lock?
    project_uses_locks = False
    for path in paths:
        try:
            if _LOCK_RE.search(path.read_text(encoding="utf-8", errors="replace")):
                project_uses_locks = True
                break
        except OSError:
            continue
    if not project_uses_locks:
        return []
    # Second pass: find module-level Optional singletons in files that
    # themselves don't use a lock locally.
    meta = lookup(RULE_ID)
    out: list[Finding] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _LOCK_RE.search(text):
            continue
        tree = parse_py(path, text)
        if tree is None:
            continue
        for lineno, name in _module_level_optional_singletons(tree):
            out.append(
                Finding(
                    rule_id=RULE_ID,
                    category=meta.category,
                    severity=meta.severity,
                    file=path,
                    line=lineno,
                    message=(
                        f"Module-level mutable singleton `{name}` with no lock, "
                        f"in a project that uses locks elsewhere. Add a lock "
                        f"or accept the inconsistency explicitly."
                    ),
                    replacement=meta.replacement,
                    replacement_url=meta.replacement_url,
                )
            )
    return out

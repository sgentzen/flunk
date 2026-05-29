"""Rule #10: function-body imports of *first-party* modules.

An import inside a function body is usually a band-aid for a circular import.
But a circular import can only exist between modules of the same project, so
lazy-loading a third-party or stdlib dependency (playwright, pypdf, io) inside
a function is a legitimate idiom — not this smell. We therefore count only
first-party imports (the project's own top-level packages, plus relative
imports), and only flag a file with >=3 of them.

Excluded:
- third-party / stdlib imports (can't form a cycle with our code)
- `try/except ImportError` optional-dependency guards
- `if TYPE_CHECKING:` blocks (PEP 484 idiom)
- entrypoint modules (`__main__.py`): lazy CLI dispatch is known-good

Implemented as an AST detector rather than a Semgrep rule because the
first-party decision needs the imported module name, which the Semgrep
Finding doesn't carry.

Expected fires: job-stalker, erate-filing-assistant
"""

from __future__ import annotations

import ast
from pathlib import Path

from flunk.catalog.metadata import lookup
from flunk.detectors._walk import walk_py
from flunk.findings import Finding

RULE_ID = "flunk.inline-import"
THRESHOLD = 3
_OPTIONAL_DEP_EXCS = frozenset({"ImportError", "ModuleNotFoundError"})


def _first_party_roots(project: Path) -> set[str]:
    """Top-level importable package names defined by the project itself."""
    roots: set[str] = set()
    for base in (project, project / "src"):
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if child.is_dir() and (child / "__init__.py").is_file():
                roots.add(child.name)
    return roots


def _is_first_party(node: ast.Import | ast.ImportFrom, roots: set[str]) -> bool:
    if isinstance(node, ast.ImportFrom):
        if node.level > 0:  # relative import -> always first-party
            return True
        head = (node.module or "").split(".", 1)[0]
        return head in roots
    # `import a, b` -> first-party if any name's root is ours
    return any(alias.name.split(".", 1)[0] in roots for alias in node.names)


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    exc = handler.type
    if exc is None:  # bare except
        return False
    names = exc.elts if isinstance(exc, ast.Tuple) else [exc]
    return any(isinstance(n, ast.Name) and n.id in _OPTIONAL_DEP_EXCS for n in names)


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _inline_first_party_lines(tree: ast.AST, roots: set[str]) -> list[int]:
    """Line numbers of first-party imports nested in a function body."""
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def ancestors(node: ast.AST):
        cur = parents.get(node)
        while cur is not None:
            yield cur
            cur = parents.get(cur)

    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if not _is_first_party(node, roots):
            continue
        in_function = False
        excluded = False
        for anc in ancestors(node):
            if isinstance(anc, (ast.FunctionDef, ast.AsyncFunctionDef)):
                in_function = True
            elif isinstance(anc, ast.Try) and any(
                _catches_import_error(h) for h in anc.handlers
            ):
                excluded = True
            elif isinstance(anc, ast.If) and _is_type_checking(anc.test):
                excluded = True
        if in_function and not excluded:
            lines.append(node.lineno)
    return sorted(lines)


def run(project: Path) -> list[Finding]:
    roots = _first_party_roots(project)
    if not roots:
        return []
    meta = lookup(RULE_ID)
    findings: list[Finding] = []
    for path in walk_py(project):
        if path.name == "__main__.py":  # entrypoint lazy dispatch is known-good
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        lines = _inline_first_party_lines(tree, roots)
        if len(lines) < THRESHOLD:
            continue
        locs = ", ".join(str(n) for n in lines)
        findings.append(
            Finding(
                rule_id=RULE_ID,
                category=meta.category,
                severity=meta.severity,
                file=path,
                line=lines[0],
                message=(
                    f"{len(lines)} first-party imports inside function bodies "
                    f"(lines {locs}) — usually a circular-import band-aid. "
                    f"Restructure the cycle (move shared types to a third module)."
                ),
                replacement=meta.replacement,
                replacement_url=meta.replacement_url,
            )
        )
    return findings

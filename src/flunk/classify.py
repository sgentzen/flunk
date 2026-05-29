"""Classify a file as production source vs. test / template / fixture / migration.

flunk's wrapped tools (semgrep, jscpd) and AST detectors should only judge
hand-authored production source. Duplicated HTML in templates, repeated
résumé bullets in test fixtures, and copy-pasted imports across test modules
are not "AI cut corners" — they're the normal shape of those files. Counting
them is the single largest source of false positives.

Two consumers:
- `is_source()` gates the Python AST detectors (via `walk_py`).
- `NON_SOURCE_GLOBS` is handed to jscpd's `--ignore` so duplication never
  even scans non-source files.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

TEMPLATE_SUFFIXES = frozenset({".html", ".htm", ".jinja", ".jinja2", ".j2"})
_MIGRATION_DIRS = frozenset({"migrations", "alembic"})
_TEST_DIRS = frozenset({"tests", "test"})
_FIXTURE_DIRS = frozenset({"fixtures"})

# Dependency / build / VCS dirs that hold vendored third-party code, not
# hand-authored source. jscpd happily scans `.venv/Lib/site-packages/...` and
# reports vendored JS/SVG as "duplication" — thousands of false positives — so
# these must be excluded from its `--ignore` globs too, not just from the AST
# walk. Single source of truth, shared with `detectors._walk.SKIP_DIRS`.
VENDOR_DIRS = frozenset({
    ".venv", "venv", "node_modules", "site-packages", ".worktrees",
    "build", "dist", "__pycache__", ".tox", ".git",
})


class FileKind(Enum):
    SOURCE = "source"
    TEST = "test"
    TEMPLATE = "template"
    FIXTURE = "fixture"
    MIGRATION = "migration"


def _is_test_file(name: str) -> bool:
    return (
        name == "conftest.py"
        or (name.startswith("test_") and name.endswith(".py"))
        or name.endswith("_test.py")
    )


def classify(path: Path) -> FileKind:
    """Best-effort classification of a path by its kind.

    Precedence matters: a file under `migrations/` is a MIGRATION even if it
    also looks like a test, and a fixture under `tests/fixtures/` is a FIXTURE
    rather than a TEST.
    """
    parts = set(path.parts)
    name = path.name

    if parts & _MIGRATION_DIRS:
        return FileKind.MIGRATION
    if parts & _FIXTURE_DIRS:
        return FileKind.FIXTURE
    if parts & _TEST_DIRS or _is_test_file(name):
        return FileKind.TEST
    if path.suffix.lower() in TEMPLATE_SUFFIXES or "templates" in parts:
        return FileKind.TEMPLATE
    return FileKind.SOURCE


def is_source(path: Path) -> bool:
    """True only for hand-authored production source."""
    return classify(path) is FileKind.SOURCE


# Glob patterns for everything that is *not* production source. Mirrors the
# `classify()` rules plus the vendor/build dirs; handed to jscpd's `--ignore`.
NON_SOURCE_GLOBS: tuple[str, ...] = (
    "**/tests/**",
    "**/test/**",
    "**/test_*.py",
    "**/*_test.py",
    "**/conftest.py",
    "**/templates/**",
    "**/*.html",
    "**/*.htm",
    "**/*.jinja",
    "**/*.jinja2",
    "**/*.j2",
    "**/migrations/**",
    "**/alembic/**",
    "**/fixtures/**",
    "**/*.md",
    # Vendor/build dirs. NB: jscpd's --ignore was measured inert (see STATUS.md
    # 2026-05-29) — the absolute-path fix in runners/jscpd.py is what actually
    # excludes these; these globs guard any vendor dir that isn't git-ignored.
    *(f"**/{d}/**" for d in sorted(VENDOR_DIRS)),
)

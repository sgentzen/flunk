"""Unit tests for file classification (source vs test/template/fixture/...)."""

from __future__ import annotations

from pathlib import Path

import pytest

from flunk.classify import NON_SOURCE_GLOBS, VENDOR_DIRS, FileKind, classify, is_source


@pytest.mark.parametrize(
    ("relpath", "expected"),
    [
        # Production source
        ("src/flunk/cli.py", FileKind.SOURCE),
        ("job_stalker/models.py", FileKind.SOURCE),
        ("pkg/sub/handler.py", FileKind.SOURCE),
        # Tests
        ("tests/test_foo.py", FileKind.TEST),
        ("test_foo.py", FileKind.TEST),
        ("foo_test.py", FileKind.TEST),
        ("conftest.py", FileKind.TEST),
        ("tests/helpers.py", FileKind.TEST),
        ("pkg/tests/util.py", FileKind.TEST),
        # Templates
        ("templates/page.html", FileKind.TEMPLATE),
        ("app/index.htm", FileKind.TEMPLATE),
        ("emails/welcome.jinja2", FileKind.TEMPLATE),
        ("x.j2", FileKind.TEMPLATE),
        ("app/templates/sub/widget.py", FileKind.TEMPLATE),
        # Migrations
        ("migrations/0001_init.py", FileKind.MIGRATION),
        ("alembic/versions/abc123.py", FileKind.MIGRATION),
        # Fixtures
        ("tests/fixtures/resume.md", FileKind.FIXTURE),
        ("fixtures/sample.py", FileKind.FIXTURE),
    ],
)
def test_classify(relpath: str, expected: FileKind) -> None:
    assert classify(Path(relpath)) is expected


def test_is_source_true_only_for_source() -> None:
    assert is_source(Path("pkg/handler.py")) is True
    assert is_source(Path("tests/test_handler.py")) is False
    assert is_source(Path("templates/x.html")) is False
    assert is_source(Path("migrations/0001.py")) is False


@pytest.mark.parametrize(
    "vendor_dir",
    [
        ".venv", "venv", "node_modules", "site-packages", ".worktrees",
        "build", "dist", "__pycache__", ".tox", ".git",
    ],
)
def test_non_source_globs_exclude_vendor_dirs(vendor_dir: str) -> None:
    # jscpd must never scan vendored/build dirs (e.g. .venv/Lib/site-packages),
    # or it reports thousands of false-positive duplicates from third-party code.
    assert f"**/{vendor_dir}/**" in NON_SOURCE_GLOBS


def test_walk_skip_dirs_share_vendor_dirs() -> None:
    # The AST-walk skip list and jscpd's ignore globs derive from the same
    # vendor-dir set so the two scan paths can't drift apart.
    from flunk.detectors._walk import SKIP_DIRS

    assert VENDOR_DIRS <= SKIP_DIRS

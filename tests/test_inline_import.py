"""inline-import AST detector: count only first-party function-body imports.

A circular import can only happen between modules of the *same* project, so
lazy-loading a third-party/stdlib dep (playwright, pypdf, io) inside a function
is not the circular-import band-aid this rule is about — it's a legitimate
idiom. Only first-party imports count, and only at >=3 per file.
"""

from __future__ import annotations

from pathlib import Path

from flunk.detectors.inline_import import run

RULE_ID = "flunk.inline-import"


def _pkg(project: Path, name: str = "mypkg") -> Path:
    pkg = project / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("")
    return pkg


def test_fires_on_three_first_party_inline_imports(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path)
    (pkg / "a.py").write_text(
        "def f():\n"
        "    from mypkg.models import Job\n"
        "    return Job\n"
        "def g():\n"
        "    from mypkg.models import Job\n"
        "def h():\n"
        "    from mypkg.models import Job\n"
    )
    findings = run(tmp_path)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == RULE_ID
    # All occurrence lines are reported so every redundant import is actionable.
    assert "2" in f.message and "5" in f.message and "7" in f.message


def test_third_party_inline_imports_are_ignored(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path)
    (pkg / "fetch.py").write_text(
        "def a():\n"
        "    from playwright.async_api import async_playwright\n"
        "def b():\n"
        "    import pypdf\n"
        "def c():\n"
        "    from io import BytesIO\n"
    )
    assert run(tmp_path) == []


def test_optional_dep_guard_is_ignored(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path)
    (pkg / "opt.py").write_text(
        "def a():\n"
        "    try:\n"
        "        from mypkg.fast import thing\n"
        "    except ImportError:\n"
        "        thing = None\n"
        "def b():\n"
        "    from mypkg.models import X\n"
        "def c():\n"
        "    from mypkg.models import Y\n"
    )
    # Only the two unguarded imports count -> below threshold of 3.
    assert run(tmp_path) == []


def test_type_checking_guard_is_ignored(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path)
    (pkg / "tc.py").write_text(
        "from typing import TYPE_CHECKING\n"
        "def f():\n"
        "    if TYPE_CHECKING:\n"
        "        from mypkg.models import A\n"
        "    from mypkg.models import B\n"
        "def g():\n"
        "    from mypkg.models import C\n"
    )
    # A is TYPE_CHECKING-guarded; only B and C count -> below threshold.
    assert run(tmp_path) == []


def test_relative_import_counts_as_first_party(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path)
    (pkg / "rel.py").write_text(
        "def f():\n"
        "    from . import models\n"
        "def g():\n"
        "    from .models import X\n"
        "def h():\n"
        "    from ..mypkg import Y\n"
    )
    assert len(run(tmp_path)) == 1


def test_module_level_imports_are_not_inline(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path)
    (pkg / "top.py").write_text(
        "from mypkg.models import A\n"
        "from mypkg.models import B\n"
        "from mypkg.models import C\n"
        "def f():\n    return A\n"
    )
    assert run(tmp_path) == []


def test_entrypoint_dunder_main_is_excluded(tmp_path: Path) -> None:
    pkg = _pkg(tmp_path)
    (pkg / "__main__.py").write_text(
        "def cli():\n"
        "    from mypkg.a import A\n"
        "    from mypkg.b import B\n"
        "    from mypkg.c import C\n"
    )
    # Lazy CLI dispatch in an entrypoint is a known-good pattern.
    assert run(tmp_path) == []

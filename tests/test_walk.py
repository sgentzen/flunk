"""walk_py should yield only production source by default."""

from __future__ import annotations

from pathlib import Path

from flunk.detectors._walk import walk_py


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x = 1\n")


def test_walk_py_skips_tests_and_other_noise(tmp_path: Path) -> None:
    _touch(tmp_path / "pkg" / "handler.py")          # source
    _touch(tmp_path / "tests" / "test_handler.py")   # test
    _touch(tmp_path / "pkg" / "thing_test.py")       # test
    _touch(tmp_path / "conftest.py")                 # test
    _touch(tmp_path / "migrations" / "0001.py")      # migration
    _touch(tmp_path / ".venv" / "lib" / "dep.py")    # venv noise

    found = {p.relative_to(tmp_path).as_posix() for p in walk_py(tmp_path)}
    assert found == {"pkg/handler.py"}


def test_walk_py_include_all_opt_out(tmp_path: Path) -> None:
    _touch(tmp_path / "pkg" / "handler.py")
    _touch(tmp_path / "tests" / "test_handler.py")

    found = {p.relative_to(tmp_path).as_posix() for p in walk_py(tmp_path, source_only=False)}
    assert found == {"pkg/handler.py", "tests/test_handler.py"}

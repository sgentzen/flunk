"""jscpd command construction should exclude non-source files."""

from __future__ import annotations

from pathlib import Path

import flunk.runners.jscpd as jscpd_mod
from flunk.classify import NON_SOURCE_GLOBS
from flunk.runners.jscpd import build_jscpd_cmd, resolve_cmd_prefix


def test_build_cmd_includes_ignore_for_non_source() -> None:
    cmd = build_jscpd_cmd(
        ["jscpd"], Path("/proj"), Path("/out"), min_tokens=50
    )
    assert "--ignore" in cmd
    ignore_arg = cmd[cmd.index("--ignore") + 1]
    # Every non-source glob is present in the comma-joined ignore argument.
    for glob in NON_SOURCE_GLOBS:
        assert glob in ignore_arg


def test_build_cmd_carries_core_flags() -> None:
    cmd = build_jscpd_cmd(
        ["npx", "--yes", "jscpd"], Path("/proj"), Path("/out"), min_tokens=42
    )
    assert cmd[:3] == ["npx", "--yes", "jscpd"]
    assert "--min-tokens" in cmd and "42" in cmd
    assert "--reporters" in cmd and "json" in cmd


def test_build_cmd_passes_project_as_posix_path() -> None:
    # jscpd's finder feeds the project path to fast-glob, which treats
    # backslashes as escapes — a Windows native path (C:\proj) matches 0
    # files. The path must be forward-slashed so detection works.
    cmd = build_jscpd_cmd(
        ["jscpd"], Path("/proj/sub"), Path("/out"), min_tokens=50
    )
    project_arg = cmd[-1]
    assert "\\" not in project_arg


def test_build_cmd_resolves_project_to_absolute_path() -> None:
    # jscpd's default gitignore-based exclusion of vendored dirs (.venv,
    # .worktrees, node_modules) only fires when handed an ABSOLUTE path. A
    # relative '../proj' defeats it, so jscpd scans the whole vendored tree
    # and reports thousands of third-party false-positive duplicates. Resolve
    # the project path so the relative prefix can't disable the exclusion.
    cmd = build_jscpd_cmd(
        ["jscpd"], Path("../sibling"), Path("/out"), min_tokens=50
    )
    project_arg = cmd[-1]
    assert ".." not in project_arg
    assert Path(project_arg).is_absolute()
    assert project_arg == Path("../sibling").resolve().as_posix()


def test_resolve_prefix_wraps_windows_cmd_shim(monkeypatch) -> None:
    # On Windows, `npx` resolves to a `.CMD` shim that CreateProcess cannot
    # exec directly; it must be invoked via `cmd /c`.
    npx_path = r"C:\Program Files\nodejs\npx.CMD"

    def fake_which(name: str) -> str | None:
        return npx_path if name == "npx" else None

    monkeypatch.setattr(jscpd_mod.shutil, "which", fake_which)
    prefix = resolve_cmd_prefix()
    assert prefix == ["cmd", "/c", npx_path, "--yes", "jscpd"]


def test_resolve_prefix_wraps_global_jscpd_cmd(monkeypatch) -> None:
    jscpd_path = r"C:\Users\me\AppData\Roaming\npm\jscpd.cmd"
    monkeypatch.setattr(
        jscpd_mod.shutil, "which",
        lambda name: jscpd_path if name == "jscpd" else None,
    )
    prefix = resolve_cmd_prefix()
    assert prefix == ["cmd", "/c", jscpd_path]


def test_resolve_prefix_passes_plain_path_through(monkeypatch) -> None:
    # POSIX: a plain executable path is run directly, no cmd wrapper.
    jscpd_path = "/usr/local/bin/jscpd"
    monkeypatch.setattr(
        jscpd_mod.shutil, "which",
        lambda name: jscpd_path if name == "jscpd" else None,
    )
    prefix = resolve_cmd_prefix()
    assert prefix == [jscpd_path]


def test_resolve_prefix_returns_none_when_absent(monkeypatch) -> None:
    monkeypatch.setattr(jscpd_mod.shutil, "which", lambda name: None)
    assert resolve_cmd_prefix() is None


def test_short_clone_pairs_are_filtered():
    """A clone pair shorter than MIN_DUP_LINES is dropped as boilerplate noise."""
    from flunk.runners import jscpd as jscpd_runner

    report = {
        "duplicates": [
            {  # noise: 3-line generic scaffolding
                "lines": 3, "tokens": 80,
                "firstFile": {"name": "a.py", "startLoc": {"line": 10}},
                "secondFile": {"name": "b.py", "startLoc": {"line": 40}},
            },
            {  # real: 8-line copied block
                "lines": 8, "tokens": 120,
                "firstFile": {"name": "c.py", "startLoc": {"line": 5}},
                "secondFile": {"name": "d.py", "startLoc": {"line": 90}},
            },
        ]
    }
    findings = jscpd_runner._findings_from_payload(report)
    assert len(findings) == 1
    assert findings[0].file.name == "c.py"


def test_clone_pair_at_exact_min_lines_is_kept():
    """A clone pair exactly at MIN_DUP_LINES (6) is kept — the guard is strict `<`."""
    from flunk.runners import jscpd as jscpd_runner

    report = {
        "duplicates": [
            {
                "lines": jscpd_runner.MIN_DUP_LINES, "tokens": 100,
                "firstFile": {"name": "e.py", "startLoc": {"line": 1}},
                "secondFile": {"name": "f.py", "startLoc": {"line": 50}},
            },
        ]
    }
    findings = jscpd_runner._findings_from_payload(report)
    assert len(findings) == 1
    assert findings[0].file.name == "e.py"

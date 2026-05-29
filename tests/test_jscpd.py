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
    assert project_arg == Path("/proj/sub").as_posix()


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

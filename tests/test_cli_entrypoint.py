"""The installed `flunk` console script resolves and runs.

`test_cli_judge.py` drives the CLI through Typer's CliRunner, which imports
`flunk.cli.app` straight from the source tree. That never exercises the
`[project.scripts] flunk = "flunk:main"` wiring in pyproject.toml, so a broken
entry-point string or a missing `main` export would ship undetected. CI used to
cover this with a `flunk --help` smoke step; these tests cover it in-suite.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sysconfig
from importlib.metadata import EntryPoint, entry_points

_HELP_TIMEOUT_S = 60


def _flunk_console_scripts() -> list[EntryPoint]:
    """Return the console-script entry points named `flunk`."""
    return [ep for ep in entry_points(group="console_scripts") if ep.name == "flunk"]


def test_console_script_entry_point_is_declared() -> None:
    scripts = _flunk_console_scripts()
    assert len(scripts) == 1, f"expected exactly one `flunk` console script, got {scripts}"


def test_console_script_entry_point_loads_and_is_callable() -> None:
    # Catches a renamed or deleted target in src/flunk/__init__.py, which the
    # declaration test above cannot see (it only reads metadata, not code).
    scripts = _flunk_console_scripts()
    assert scripts, "no `flunk` console script registered"
    assert callable(scripts[0].load())


def test_console_script_runs_as_a_subprocess() -> None:
    # The only check that the installed executable actually launches, as
    # opposed to the entry point resolving inside this interpreter.
    #
    # Look in this interpreter's own script directory first rather than
    # trusting PATH: a non-activated shell (which is how `make test` runs)
    # has the venv's script dir off PATH, and falling back to a skip there
    # would blind local runs to the exact regression this file exists to catch.
    exe = shutil.which("flunk", path=sysconfig.get_path("scripts")) or shutil.which("flunk")
    assert exe is not None, "`flunk` console script is not installed next to sys.executable"
    proc = subprocess.run(
        [exe, "--help"],
        capture_output=True,
        text=True,
        timeout=_HELP_TIMEOUT_S,
        check=False,
        # Pin the render so an inherited FORCE_COLOR/COLUMNS can't wrap or
        # colour the output out from under the assertions below.
        env={**os.environ, "NO_COLOR": "1", "COLUMNS": "200"},
    )
    assert proc.returncode == 0, f"`flunk --help` exited {proc.returncode}: {proc.stderr}"
    # "Usage" alone only proves some Click app ran; PATH lookup could in
    # principle find a different `flunk`. Assert identity too.
    assert "Usage" in proc.stdout
    assert "flunk" in proc.stdout.lower()

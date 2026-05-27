"""Python-implemented detectors for rules semgrep can't easily express.

Each `run_*` function takes a project path and returns `list[Finding]`.
The top-level `run_all(project)` dispatches to every detector.
"""

from __future__ import annotations

from pathlib import Path

from flunk.findings import Finding

from . import (
    csrf_middleware,
    duplicate_retry,
    f811_suppression,
    module_singleton,
    requirements_vs_pyproject,
)

_DETECTORS = (
    requirements_vs_pyproject.run,
    duplicate_retry.run,
    f811_suppression.run,
    module_singleton.run,
    csrf_middleware.run,
)


def run_all(project: Path) -> list[Finding]:
    out: list[Finding] = []
    for fn in _DETECTORS:
        try:
            out.extend(fn(project))
        except Exception:  # noqa: BLE001 — detectors are best-effort
            # A buggy detector shouldn't tank the audit run.
            continue
    return out

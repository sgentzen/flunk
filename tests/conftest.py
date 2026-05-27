"""Shared pytest fixtures.

Regression project paths are path-based (not vendored). Tests skip
when the sibling project isn't present, so CI on a checkout-without-
siblings still passes the unit tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROJECTS_ROOT = _REPO_ROOT.parent


def _sibling(name: str) -> Path | None:
    p = _PROJECTS_ROOT / name
    return p if p.is_dir() else None


@pytest.fixture(scope="session")
def job_stalker() -> Path:
    p = _sibling("job-stalker")
    if p is None:
        pytest.skip("job-stalker sibling project not present")
    return p


@pytest.fixture(scope="session")
def erate_filing_assistant() -> Path:
    p = _sibling("erate-filing-assistant")
    if p is None:
        pytest.skip("erate-filing-assistant sibling project not present")
    return p


@pytest.fixture(scope="session")
def erate_prospector() -> Path:
    p = _sibling("erate-prospector")
    if p is None:
        pytest.skip("erate-prospector sibling project not present")
    return p

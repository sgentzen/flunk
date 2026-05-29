"""Regression tests: every catalog rule fires on the projects listed in its
`# Expected fires:` comment (mirrored in EXPECTED_FIRES below from
CATALOG.md's evidence column).

A rule's fixture-fire is what stops a future edit from silently breaking
the catalog's value proposition. If a regression project moves away from
a pattern (e.g. erate-filing-assistant adopts tenacity), update the
matrix here AND CATALOG.md together.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flunk import detectors as detectors_mod
from flunk.runners import semgrep as semgrep_runner

# rule_id -> tuple of conftest fixture names that should produce ≥1 hit
EXPECTED_FIRES: dict[str, tuple[str, ...]] = {
    "flunk.pydantic-settings":      ("job_stalker", "erate_filing_assistant", "erate_prospector"),
    "flunk.tenacity":               ("erate_filing_assistant",),
    "flunk.uv-pip-compile":         ("erate_filing_assistant", "erate_prospector"),
    "flunk.alembic":                ("job_stalker",),
    "flunk.sql-injection":          ("erate_filing_assistant",),
    "flunk.async-client-in-fn":     ("erate_filing_assistant",),
    # flunk.duplicate-retry: none of the 3 golden projects has >=2 *source*
    # retry functions. The prior erate-filing-assistant fire was a false
    # positive driven by pytest test_retry_* names. Behavior is covered by
    # tests/test_duplicate_retry.py instead.
    "flunk.f811-suppression":       ("erate_prospector",),
    "flunk.bare-except-security":   ("erate_filing_assistant",),
    "flunk.inline-import":          ("job_stalker", "erate_filing_assistant"),
    "flunk.secure-headers":         ("erate_filing_assistant",),
    "flunk.csrf-middleware":        ("erate_filing_assistant",),
    "flunk.humanize":               ("job_stalker",),
    "flunk.sqlite3-thread":         ("erate_filing_assistant",),
    "flunk.module-singleton":       ("erate_prospector",),
}


def _all_findings(project: Path) -> list:
    """semgrep + detectors. (jscpd skipped to keep the test fast.)"""
    return semgrep_runner.run(project) + detectors_mod.run_all(project)


# Cache findings per project across the test session.
@pytest.fixture(scope="session")
def findings_by_project() -> dict[str, list]:
    return {}


def _findings_for(project_name: str, project_path: Path, cache: dict[str, list]) -> list:
    if project_name not in cache:
        cache[project_name] = _all_findings(project_path)
    return cache[project_name]


@pytest.mark.parametrize(
    ("rule_id", "project_fixture"),
    [(rule, proj) for rule, projects in EXPECTED_FIRES.items() for proj in projects],
)
def test_rule_fires_on_expected_project(
    rule_id: str,
    project_fixture: str,
    request: pytest.FixtureRequest,
    findings_by_project: dict[str, list],
) -> None:
    project = request.getfixturevalue(project_fixture)
    all_findings = _findings_for(project_fixture, project, findings_by_project)
    hits = [f for f in all_findings if f.rule_id == rule_id]
    assert len(hits) >= 1, (
        f"{rule_id} should fire on {project_fixture} per CATALOG.md evidence column; "
        f"got {len(hits)} hits."
    )

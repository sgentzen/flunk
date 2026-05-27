"""Regression tests: every catalog rule fires on the projects listed in its
`# Expected fires:` comment.

For Weekend 1 only `flunk.pydantic-settings` exists, expected to fire on
all three regression projects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flunk.runners import semgrep as semgrep_runner


def _findings_for_rule(project: Path, rule_id: str):
    findings = semgrep_runner.run(project)
    return [f for f in findings if f.rule_id == rule_id]


@pytest.mark.parametrize("project_fixture", [
    "job_stalker",
    "erate_filing_assistant",
    "erate_prospector",
])
def test_pydantic_settings_fires(project_fixture: str, request: pytest.FixtureRequest) -> None:
    project = request.getfixturevalue(project_fixture)
    matches = _findings_for_rule(project, "flunk.pydantic-settings")
    assert len(matches) >= 1, (
        f"flunk.pydantic-settings should fire on {project_fixture} per CATALOG.md "
        f"evidence column"
    )
    # Severity is "high" per the catalog (no demote markers in these files
    # near the env-access sites — verify the rule keeps its punch).
    high = [f for f in matches if f.severity == "high"]
    assert len(high) >= 1, f"expected ≥1 high-severity hit, got {[f.severity for f in matches]}"

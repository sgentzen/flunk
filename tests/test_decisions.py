"""`.flunkignore`: record conscious 'won't do' decisions per rule.

The point is to *log* a decision, not silently skip: matching findings are
suppressed but kept in the output with the recorded reason, so the audit still
shows the maintainer consciously declined the rule (and why).
"""

from __future__ import annotations

from pathlib import Path

from flunk.decisions import apply_decisions, load_decisions
from flunk.findings import Finding


def _mk(rule_id: str, sev: str = "high") -> Finding:
    return Finding(
        rule_id=rule_id, category="oss-catalog", severity=sev,
        file=Path("x.py"), line=1, message="m", replacement="r",
    )


def test_load_decisions_parses_rule_and_reason(tmp_path: Path) -> None:
    (tmp_path / ".flunkignore").write_text(
        "# our conscious won't-do list\n"
        "flunk.alembic: single-user local app, additive migrations are deliberate\n"
        "flunk.csrf-middleware\n"   # no reason
        "\n"
    )
    d = load_decisions(tmp_path)
    assert d["flunk.alembic"].startswith("single-user local app")
    assert d["flunk.csrf-middleware"] == ""
    assert "flunk.pydantic-settings" not in d


def test_load_decisions_strips_inline_comments(tmp_path: Path) -> None:
    (tmp_path / ".flunkignore").write_text(
        "flunk.csrf-middleware            # a reason is optional\n"
        "flunk.alembic: deliberate  # and a trailing note\n"
    )
    d = load_decisions(tmp_path)
    assert d["flunk.csrf-middleware"] == ""
    assert d["flunk.alembic"] == "deliberate"


def test_load_decisions_absent_file(tmp_path: Path) -> None:
    assert load_decisions(tmp_path) == {}


def test_apply_decisions_suppresses_with_reason() -> None:
    decisions = {"flunk.alembic": "deliberate for local app"}
    out = apply_decisions([_mk("flunk.alembic", "medium")], decisions)
    assert len(out) == 1  # kept, not dropped
    assert out[0].severity == "suppressed"
    assert out[0].raw_severity == "medium"
    assert "deliberate for local app" in out[0].demoted_by


def test_apply_decisions_leaves_unlisted_rules() -> None:
    out = apply_decisions([_mk("flunk.async-client-in-fn", "high")], {"flunk.alembic": ""})
    assert out[0].severity == "high"
    assert out[0].demoted_by is None

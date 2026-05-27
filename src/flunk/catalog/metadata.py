"""rule_id → metadata mapping.

Single source of truth for severity, replacement library, and doc URL.
Kept separate from the YAML so we can lookup-and-enrich raw Semgrep
output without parsing YAML metadata fields.

Severity scale: `nitpick` < `medium` < `high`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleMeta:
    category: str           # "oss-catalog" | "duplication" | "anti-pattern"
    severity: str           # "high" | "medium" | "nitpick"
    replacement: str
    replacement_url: str | None = None


CATALOG: dict[str, RuleMeta] = {
    # 1
    "flunk.pydantic-settings": RuleMeta(
        category="oss-catalog", severity="high",
        replacement="pydantic-settings",
        replacement_url="https://docs.pydantic.dev/latest/concepts/pydantic_settings/",
    ),
    # 2
    "flunk.tenacity": RuleMeta(
        category="oss-catalog", severity="high",
        replacement="tenacity",
        replacement_url="https://tenacity.readthedocs.io/",
    ),
    # 3
    "flunk.uv-pip-compile": RuleMeta(
        category="oss-catalog", severity="medium",
        replacement="pyproject.toml + uv pip compile",
        replacement_url="https://docs.astral.sh/uv/concepts/projects/dependencies/",
    ),
    # 4
    "flunk.alembic": RuleMeta(
        category="oss-catalog", severity="medium",
        replacement="alembic",
        replacement_url="https://alembic.sqlalchemy.org/",
    ),
    # 5
    "flunk.sql-injection": RuleMeta(
        category="anti-pattern", severity="high",
        replacement="parameterized queries",
        replacement_url=None,
    ),
    # 6
    "flunk.async-client-in-fn": RuleMeta(
        category="anti-pattern", severity="high",
        replacement="module-level / lifespan-managed httpx client",
        replacement_url="https://www.python-httpx.org/async/#opening-and-closing-clients",
    ),
    # 7
    "flunk.duplicate-retry": RuleMeta(
        category="duplication", severity="high",
        replacement="extract shared retry / use tenacity",
        replacement_url="https://tenacity.readthedocs.io/",
    ),
    # 8
    "flunk.f811-suppression": RuleMeta(
        category="anti-pattern", severity="high",
        replacement="remove the duplicate def",
        replacement_url=None,
    ),
    # 9
    "flunk.bare-except-security": RuleMeta(
        category="anti-pattern", severity="medium",
        replacement="catch the specific exception class",
        replacement_url=None,
    ),
    # 10
    "flunk.inline-import": RuleMeta(
        category="anti-pattern", severity="nitpick",
        replacement="restructure to remove the cycle",
        replacement_url=None,
    ),
    # 11
    "flunk.secure-headers": RuleMeta(
        category="oss-catalog", severity="nitpick",
        replacement="secure",
        replacement_url="https://github.com/TypeError/secure",
    ),
    # 12
    "flunk.csrf-middleware": RuleMeta(
        category="oss-catalog", severity="medium",
        replacement="starlette-csrf / fastapi-csrf-protect",
        replacement_url="https://github.com/frankie567/starlette-csrf",
    ),
    # 13
    "flunk.humanize": RuleMeta(
        category="oss-catalog", severity="nitpick",
        replacement="humanize",
        replacement_url="https://python-humanize.readthedocs.io/",
    ),
    # 14
    "flunk.sqlite3-thread": RuleMeta(
        category="anti-pattern", severity="medium",
        replacement="SQLAlchemy or aiosqlite",
        replacement_url="https://docs.sqlalchemy.org/",
    ),
    # 15
    "flunk.module-singleton": RuleMeta(
        category="anti-pattern", severity="nitpick",
        replacement="add a lock or accept the inconsistency",
        replacement_url=None,
    ),
    # jscpd general duplication
    "flunk.duplication": RuleMeta(
        category="duplication", severity="medium",
        replacement="extract a shared helper",
        replacement_url=None,
    ),
}


def lookup(rule_id: str) -> RuleMeta:
    """Return metadata for a rule_id, with a safe fallback for unknown rules."""
    if rule_id in CATALOG:
        return CATALOG[rule_id]
    return RuleMeta(
        category="anti-pattern",
        severity="medium",
        replacement="(no replacement registered)",
    )

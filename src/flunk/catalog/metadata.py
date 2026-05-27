"""rule_id → metadata mapping.

Single source of truth for severity, replacement library, and doc URL.
Kept separate from the YAML so we can lookup-and-enrich raw Semgrep
output without parsing YAML metadata fields.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleMeta:
    category: str           # "oss-catalog" | "duplication" | "anti-pattern"
    severity: str           # "high" | "medium" | "nitpick"
    replacement: str        # library or approach
    replacement_url: str | None = None


CATALOG: dict[str, RuleMeta] = {
    "flunk.pydantic-settings": RuleMeta(
        category="oss-catalog",
        severity="high",
        replacement="pydantic-settings",
        replacement_url="https://docs.pydantic.dev/latest/concepts/pydantic_settings/",
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

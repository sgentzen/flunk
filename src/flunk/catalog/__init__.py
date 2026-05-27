"""flunk's curated OSS-replacement catalog.

The Semgrep YAMLs in `patterns/` describe code *shapes* that indicate a
reinvented wheel. `metadata.py` names the replacement library + severity
for each rule_id. Some rules also need a Python-side aggregation pass
(e.g. "fire only if file has ≥5 occurrences"); those live in
`post_process()`.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from flunk.findings import Finding

PATTERNS_DIR = Path(__file__).parent / "patterns"

# Per-rule aggregation thresholds. Rules listed here fire as ONE finding per
# file, only when raw match count ≥ threshold. Others fire per-occurrence.
#
# pydantic-settings: V1_SPEC originally said ≥5, but the 2026-05-26 audit
# evidence on the three regression projects showed: erate-filing-assistant
# config.py (16), erate-prospector config.py (41), job-stalker __main__.py
# (3 duplicated ANTHROPIC_API_KEY guards). Lowered to 3 so the rule fires on
# all three projects as CATALOG.md claims, and because 3+ guards in one file
# is itself a real "should be in typed settings" smell.
COUNT_PER_FILE_THRESHOLDS: dict[str, int] = {
    "flunk.pydantic-settings": 3,
}


def post_process(findings: list[Finding]) -> list[Finding]:
    """Apply per-rule aggregation. Returns a new list."""
    aggregated: dict[tuple[str, Path], list[Finding]] = defaultdict(list)
    passthrough: list[Finding] = []

    for f in findings:
        if f.rule_id in COUNT_PER_FILE_THRESHOLDS:
            aggregated[(f.rule_id, f.file)].append(f)
        else:
            passthrough.append(f)

    out: list[Finding] = list(passthrough)
    for (rule_id, _path), group in aggregated.items():
        threshold = COUNT_PER_FILE_THRESHOLDS[rule_id]
        if len(group) < threshold:
            continue
        # Emit one finding at the first occurrence's line.
        first = min(group, key=lambda x: x.line)
        out.append(
            Finding(
                rule_id=first.rule_id,
                category=first.category,
                severity=first.severity,
                file=first.file,
                line=first.line,
                message=f"{first.message} ({len(group)} occurrences in this file)",
                replacement=first.replacement,
                replacement_url=first.replacement_url,
            )
        )
    return out

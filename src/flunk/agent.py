"""Render findings as an agent-actionable fix plan.

Unlike the rich table (human-skimmable) or `--json` (a flat list of
pointers), this emits a markdown brief grouped by rule: each rule gets one
section with the *why*, the replacement, a fix sketch, and the list of
locations with code excerpts. The intent is a document you can paste to a
coding agent and have it work top-to-bottom, one section per task.

Suppressed (justification-demoted) findings are dropped — they represent
choices the author already defended, not work to do.
"""

from __future__ import annotations

from pathlib import Path

from flunk.catalog import metadata
from flunk.findings import Finding

SEVERITY_EMOJI = {"high": "\U0001f534", "medium": "\U0001f7e1", "nitpick": "⚪"}


def _is_test_path(file: Path) -> bool:
    """True if the finding sits in test code (de-prioritized in the plan)."""
    parts = {p.lower() for p in file.parts}
    if "tests" in parts or "test" in parts:
        return True
    name = file.name
    return name.startswith("test_") or name.endswith("_test.py")


def _read_lines(file: Path) -> list[str] | None:
    try:
        text = file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text.splitlines()


def _excerpt_block(file: Path, line: int, context: int = 3) -> str | None:
    """A gutter-numbered slice of `file` around `line`, hit line marked `>>`."""
    lines = _read_lines(file)
    if lines is None:
        return None
    idx = line - 1
    if idx < 0 or idx >= len(lines):
        return None
    lo = max(0, idx - context)
    hi = min(len(lines), idx + context + 1)
    width = len(str(hi))
    out = []
    for i in range(lo, hi):
        marker = ">>" if i == idx else "  "
        out.append(f"{marker} {str(i + 1).rjust(width)}  {lines[i]}")
    return "\n".join(out)


def _fence(lines: list[str]) -> str:
    """Pick a backtick fence longer than any run inside `lines`.

    CommonMark requires the fence to exceed any backtick run in the content;
    otherwise an excerpted line containing ``` would close the block early.
    """
    longest = 0
    for ln in lines:
        run = 0
        for ch in ln:
            run = run + 1 if ch == "`" else 0
            longest = max(longest, run)
    return "`" * max(3, longest + 1)


def _rel(file: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return str(file.relative_to(root)).replace("\\", "/")
        except ValueError:
            pass
    return str(file)


def _group_by_rule(findings: list[Finding]) -> dict[str, list[Finding]]:
    """Group actionable findings by rule_id, preserving rank order.

    Findings arrive ranked (severity desc, then category, then path), so
    first-seen iteration yields rule groups in that same priority order.
    Suppressed findings are excluded.
    """
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        if f.severity == "suppressed":
            continue
        groups.setdefault(f.rule_id, []).append(f)
    return groups


def _section_heading(rule_id: str, fs: list[Finding]) -> list[str]:
    sev = fs[0].severity
    emoji = SEVERITY_EMOJI.get(sev, "")
    prefix = f"{emoji} " if emoji else ""
    occ = "occurrence" if len(fs) == 1 else "occurrences"

    out = ["---", f"## {prefix}{sev.upper()} · {rule_id} · {len(fs)} {occ}"]
    if sev == "skip":
        out.append("")
        out.append("> **Judged not worth doing** — kept here with the judge's reason; no action expected.")
    out.append("")
    return out


def _why_block(fs: list[Finding], meta: metadata.RuleMeta) -> list[str]:
    """The judge's code-specific take when it judged this rule, else the catalog's."""
    judged_rationale = next((f.rationale for f in fs if f.rationale), None)
    why = judged_rationale or meta.rationale
    if not why:
        return []
    label = "Judge's take" if judged_rationale else "Why it's worse"
    return [f"**{label}:** {why}", ""]


def _fix_block(meta: metadata.RuleMeta) -> list[str]:
    fix_line = f"**Fix:** {meta.replacement}"
    if meta.replacement_url:
        fix_line += f"  → {meta.replacement_url}"
    out = [fix_line, ""]
    if meta.fix_hint:
        hint_lines = meta.fix_hint.splitlines()
        fence = _fence(hint_lines)
        out.extend([fence, *hint_lines, fence, ""])
    return out


def _location_block(f: Finding, project_root: Path | None, context: int) -> list[str]:
    note = "  ← test code; likely lower priority" if _is_test_path(f.file) else ""
    out = [f"- [ ] {_rel(f.file, project_root)}:{f.line}{note}"]
    block = _excerpt_block(f.file, f.line, context)
    if block:
        block_lines = block.splitlines()
        fence = _fence(block_lines)
        out.append(f"  {fence}python")
        out.extend(f"  {bl}" for bl in block_lines)
        out.append(f"  {fence}")
    return out


def _rule_section(
    rule_id: str, fs: list[Finding], project_root: Path | None, context: int
) -> list[str]:
    meta = metadata.lookup(rule_id)
    out = _section_heading(rule_id, fs)
    out.extend(_why_block(fs, meta))
    out.extend(_fix_block(meta))
    out.append("Locations:")
    for f in fs:
        out.extend(_location_block(f, project_root, context))
    out.append("")
    return out


def _summary_line(groups: dict[str, list[Finding]], actionable: int) -> str:
    rule_word = "rule" if len(groups) == 1 else "rules"
    finding_word = "finding" if actionable == 1 else "findings"
    return (
        f"{actionable} actionable {finding_word} across {len(groups)} {rule_word}. "
        "Work top-to-bottom; each section is one task."
    )


def build_plan(
    findings: list[Finding],
    *,
    project_root: Path | None = None,
    context: int = 3,
) -> str:
    """Return a grouped-by-rule markdown fix plan for `findings`."""
    groups = _group_by_rule(findings)
    title = project_root.name if project_root is not None else "project"

    out: list[str] = [f"# flunk fix plan — {title}"]
    if not groups:
        out.extend(["", "_No actionable findings._"])
        return "\n".join(out) + "\n"

    actionable = sum(len(v) for v in groups.values())
    out.append(_summary_line(groups, actionable))
    out.append("")
    for rule_id, fs in groups.items():
        out.extend(_rule_section(rule_id, fs, project_root, context))

    return "\n".join(out).rstrip() + "\n"

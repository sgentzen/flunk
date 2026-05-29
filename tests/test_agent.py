"""Unit tests for the agent fix-plan renderer."""

from __future__ import annotations

from pathlib import Path

from flunk.agent import _excerpt_block, _fence, _is_test_path, build_plan
from flunk.findings import Finding


def _f(rule_id: str, sev: str, path: str, line: int = 1, cat: str = "oss-catalog") -> Finding:
    return Finding(
        rule_id=rule_id, category=cat, severity=sev,
        file=Path(path), line=line, message="m",
    )


def test_empty_findings_renders_none_marker() -> None:
    out = build_plan([])
    assert "_No actionable findings._" in out


def test_groups_by_rule_with_count() -> None:
    findings = [
        _f("flunk.async-client-in-fn", "high", "a.py", 1, "anti-pattern"),
        _f("flunk.async-client-in-fn", "high", "b.py", 2, "anti-pattern"),
    ]
    out = build_plan(findings)
    assert out.count("## ") == 1  # one section, not two
    assert "2 occurrences" in out


def test_single_occurrence_is_singular() -> None:
    out = build_plan([_f("flunk.pydantic-settings", "high", "a.py")])
    assert "1 occurrence" in out
    assert "1 occurrences" not in out


def test_sections_ordered_by_input_rank() -> None:
    # build_plan preserves arrival order; rank() upstream guarantees severity desc.
    findings = [
        _f("flunk.pydantic-settings", "high", "a.py"),
        _f("flunk.humanize", "nitpick", "b.py"),
    ]
    out = build_plan(findings)
    assert out.index("flunk.pydantic-settings") < out.index("flunk.humanize")


def test_includes_rationale_and_fix_hint() -> None:
    out = build_plan([_f("flunk.pydantic-settings", "high", "a.py")])
    assert "**Why it's worse:**" in out
    assert "BaseSettings" in out  # from the curated fix_hint
    assert "**Fix:** pydantic-settings" in out


def test_suppressed_findings_excluded() -> None:
    findings = [
        _f("flunk.humanize", "suppressed", "a.py"),
        _f("flunk.pydantic-settings", "high", "b.py"),
    ]
    out = build_plan(findings)
    assert "flunk.humanize" not in out
    assert "flunk.pydantic-settings" in out
    assert "across 1 rule" in out


def test_test_path_is_marked() -> None:
    findings = [_f("flunk.duplicate-retry", "high", "tests/test_x.py", cat="duplication")]
    out = build_plan(findings)
    assert "← test code" in out


def test_non_test_path_not_marked() -> None:
    out = build_plan([_f("flunk.duplicate-retry", "high", "src/app.py", cat="duplication")])
    assert "← test code" not in out


def test_paths_relativized_to_project_root(tmp_path: Path) -> None:
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n", encoding="utf-8")
    out = build_plan([_f("flunk.pydantic-settings", "high", str(target))], project_root=tmp_path)
    assert "src/app.py:1" in out
    assert str(tmp_path) not in out  # absolute prefix stripped


def test_is_test_path_variants() -> None:
    assert _is_test_path(Path("a/tests/b.py"))
    assert _is_test_path(Path("test_foo.py"))
    assert _is_test_path(Path("foo_test.py"))
    assert not _is_test_path(Path("src/contest.py"))  # substring, not a path part


def test_excerpt_marks_hit_line(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    block = _excerpt_block(f, 3, context=1)
    assert block is not None
    lines = block.splitlines()
    assert lines == ["   2  b", ">> 3  c", "   4  d"]


def test_excerpt_missing_file_returns_none() -> None:
    assert _excerpt_block(Path("does-not-exist-xyz.py"), 1) is None


def test_excerpt_out_of_range_returns_none(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    f.write_text("only one line\n", encoding="utf-8")
    assert _excerpt_block(f, 99) is None


def test_fence_grows_past_backtick_runs() -> None:
    assert _fence(["no ticks here"]) == "```"
    assert _fence(["a ``` b"]) == "````"
    assert _fence(["x = '''", "y = ````nested````"]) == "`````"


def test_excerpt_with_backticks_uses_longer_fence(tmp_path: Path) -> None:
    f = tmp_path / "gen.py"
    # A source line that itself contains a triple-backtick must not close the fence.
    f.write_text('a = 1\nmd = "```python"\nb = 2\n', encoding="utf-8")
    out = build_plan(
        [_f("flunk.pydantic-settings", "high", str(f), line=2)],
        project_root=tmp_path,
    )
    assert "  ````python" in out  # opener grew to 4 backticks
    assert "  ````\n" in out      # matching closer


def test_summary_singular_finding() -> None:
    out = build_plan([_f("flunk.pydantic-settings", "high", "a.py")])
    assert "1 actionable finding across 1 rule" in out


def test_excerpt_embedded_in_plan(tmp_path: Path) -> None:
    f = tmp_path / "app.py"
    f.write_text("import os\ntoken = os.environ.get('X')\nprint(token)\n", encoding="utf-8")
    out = build_plan(
        [_f("flunk.pydantic-settings", "high", str(f), line=2)],
        project_root=tmp_path,
    )
    assert ">> 2  token = os.environ.get('X')" in out


def test_agent_prefers_judged_rationale(tmp_path):
    from flunk.agent import build_plan
    from flunk.findings import Finding

    f = Finding("flunk.async-client-in-fn", "anti-pattern", "medium",
                tmp_path / "a.py", 1, "msg",
                rationale="one-shot HEAD to a redirector; pooling moot", judged=True)
    (tmp_path / "a.py").write_text("httpx.AsyncClient()\n", encoding="utf-8")
    plan = build_plan([f], project_root=tmp_path)
    assert "one-shot HEAD to a redirector" in plan


def test_agent_groups_skip_separately(tmp_path):
    from flunk.agent import build_plan
    from flunk.findings import Finding

    f = Finding("flunk.duplication", "duplication", "skip",
                tmp_path / "d.py", 1, "msg",
                rationale="unrelated functions, not real duplication", judged=True)
    (tmp_path / "d.py").write_text("x = 1\n", encoding="utf-8")
    plan = build_plan([f], project_root=tmp_path)
    assert "not worth doing" in plan.lower()
    assert "unrelated functions" in plan

"""Judge enrichment logic with a fake client (no live API)."""

from __future__ import annotations

from pathlib import Path

from flunk.findings import Finding
from flunk.judge import JudgeItem, Verdict, judge_findings


class FakeClient:
    """Returns a preset verdict per (file, line)."""

    def __init__(self, verdicts: dict[tuple[str, int], Verdict]) -> None:
        self._verdicts = verdicts
        self.calls: list[str] = []

    def judge_file(self, rel_path: str, items: list[JudgeItem]) -> list[Verdict]:
        self.calls.append(rel_path)
        return [self._verdicts[(rel_path, it.line)] for it in items]


def _f(rule_id, severity, line, category="anti-pattern", file="a.py") -> Finding:
    return Finding(
        rule_id=rule_id, category=category, severity=severity,
        file=Path(file), line=line, message="generic",
    )


def test_rewrites_rationale_and_reraters_severity(tmp_path) -> None:
    f = _f("flunk.async-client-in-fn", "high", 3, file=str(tmp_path / "a.py"))
    (tmp_path / "a.py").write_text("# x\n# y\nhttpx.AsyncClient()\n", encoding="utf-8")
    client = FakeClient({
        ("a.py", 3): Verdict(severity="medium", rationale="one-shot HEAD; pooling moot", worth_doing=True),
    })
    out = judge_findings([f], client=client, project_root=tmp_path)
    assert out[0].severity == "medium"
    assert out[0].rationale == "one-shot HEAD; pooling moot"
    assert out[0].judged is True


def test_skip_verdict_sets_skip_severity(tmp_path) -> None:
    f = _f("flunk.duplication", "medium", 1, category="duplication", file=str(tmp_path / "d.py"))
    (tmp_path / "d.py").write_text("x = 1\n", encoding="utf-8")
    client = FakeClient({
        ("d.py", 1): Verdict(severity="skip", rationale="unrelated functions, not real dup", worth_doing=False),
    })
    out = judge_findings([f], client=client, project_root=tmp_path)
    assert out[0].severity == "skip"
    assert out[0].judged is True


def test_security_rule_cannot_be_downgraded(tmp_path) -> None:
    f = _f("flunk.sql-injection", "high", 1, file=str(tmp_path / "s.py"))
    (tmp_path / "s.py").write_text("q = f'... {x}'\n", encoding="utf-8")
    client = FakeClient({
        ("s.py", 1): Verdict(severity="nitpick", rationale="looks fine to me", worth_doing=False),
    })
    out = judge_findings([f], client=client, project_root=tmp_path)
    assert out[0].severity == "high"
    assert out[0].severity != "skip"
    assert out[0].rationale == "looks fine to me"


def test_security_rule_can_be_raised(tmp_path) -> None:
    f = _f("flunk.bare-except-security", "medium", 1, file=str(tmp_path / "s.py"))
    (tmp_path / "s.py").write_text("try:\n    pass\nexcept: pass\n", encoding="utf-8")
    client = FakeClient({
        ("s.py", 1): Verdict(severity="high", rationale="swallows auth failure", worth_doing=True),
    })
    out = judge_findings([f], client=client, project_root=tmp_path)
    assert out[0].severity == "high"


def test_already_suppressed_findings_skip_the_judge(tmp_path) -> None:
    f = _f("flunk.alembic", "suppressed", 1, category="oss-catalog", file=str(tmp_path / "a.py"))
    client = FakeClient({})
    out = judge_findings([f], client=client, project_root=tmp_path)
    assert out == [f]
    assert client.calls == []


def test_batches_one_call_per_file(tmp_path) -> None:
    (tmp_path / "a.py").write_text("x=1\ny=2\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("z=3\n", encoding="utf-8")
    fa1 = _f("flunk.humanize", "nitpick", 1, category="oss-catalog", file=str(tmp_path / "a.py"))
    fa2 = _f("flunk.humanize", "nitpick", 2, category="oss-catalog", file=str(tmp_path / "a.py"))
    fb = _f("flunk.humanize", "nitpick", 1, category="oss-catalog", file=str(tmp_path / "b.py"))
    client = FakeClient({
        ("a.py", 1): Verdict("nitpick", "r", True),
        ("a.py", 2): Verdict("nitpick", "r", True),
        ("b.py", 1): Verdict("nitpick", "r", True),
    })
    judge_findings([fa1, fa2, fb], client=client, project_root=tmp_path)
    assert sorted(client.calls) == ["a.py", "b.py"]

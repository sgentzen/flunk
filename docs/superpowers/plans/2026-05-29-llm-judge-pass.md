# Opt-in LLM Judge Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `flunk <path> --judge` pass that sends located findings (with code context) to Claude, which rewrites each rationale to be code-specific, re-rates severity for the call site, and may mark a finding "not worth doing" — kept in output with its reason, never silently dropped.

**Architecture:** A new `judge` pass runs after demote/profile/decisions and before rank. It is pure enrichment over `Finding` (sets `severity`, a code-specific `rationale`, a `judged` flag, and may set `severity="skip"`). The Anthropic SDK is an optional extra; the judge is injected behind a small client protocol so all logic is unit-testable with a fake client and no live API in CI. A guardrail prevents the LLM from downgrading or skipping security-category rules.

**Tech Stack:** Python 3.12, `anthropic` SDK (optional extra), forced tool-use for structured output, pytest with a fake client.

**Prerequisite:** Plan 1 (static judgment fixes) merged — this plan builds on `Finding.with_message` and the refined pipeline. Depends on the design: [docs/superpowers/specs/2026-05-29-hybrid-judgment-pass-design.md](../specs/2026-05-29-hybrid-judgment-pass-design.md)

---

## Task 1: Extend the `Finding` schema for judge output

**Files:**
- Modify: `src/flunk/findings.py`
- Test: `tests/test_findings_judge.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_findings_judge.py
"""Finding carries judge enrichment fields and a skip severity sorts last."""

from __future__ import annotations

from pathlib import Path

from flunk.findings import SEVERITY_ORDER, Finding


def test_skip_sorts_after_nitpick_before_suppressed_absent() -> None:
    assert SEVERITY_ORDER["skip"] > SEVERITY_ORDER["nitpick"]


def test_with_judgment_sets_fields() -> None:
    f = Finding(
        rule_id="flunk.async-client-in-fn", category="anti-pattern",
        severity="high", file=Path("a.py"), line=1, message="m",
    )
    j = f.with_judgment(severity="medium", rationale="one-shot here", worth_doing=True)
    assert j.severity == "medium"
    assert j.rationale == "one-shot here"
    assert j.judged is True
    assert j.raw_severity == "high"
    assert f.judged is False  # original untouched (frozen)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_findings_judge.py -v`
Expected: FAIL — `KeyError: 'skip'` / `AttributeError: 'Finding' object has no attribute 'with_judgment'`

- [ ] **Step 3: Implement**

Modify `src/flunk/findings.py`:

Update `SEVERITY_ORDER` to include `skip` (sorts after nitpick, before the demote-only `suppressed`):

```python
SEVERITY_ORDER = {"high": 0, "medium": 1, "nitpick": 2, "skip": 3, "suppressed": 4}
```

Add two fields to the `Finding` dataclass (after `demoted_by`):

```python
    judged: bool = False
    rationale: str | None = None
```

Add a method (after `with_message`, which Plan 1 added):

```python
    def with_judgment(
        self, *, severity: str, rationale: str, worth_doing: bool
    ) -> Finding:
        return replace(
            self,
            severity=severity,
            raw_severity=self.raw_severity or self.severity,
            rationale=rationale,
            judged=True,
        )
```

(`worth_doing` is accepted for caller symmetry; a `skip` severity already encodes "not worth doing", so it isn't stored separately.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_findings_judge.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/flunk/findings.py tests/test_findings_judge.py
git commit -m "feat: add judge enrichment fields + skip severity to Finding"
```

---

## Task 2: Classify which rules are security/correctness (no-downgrade guardrail)

**Files:**
- Modify: `src/flunk/catalog/metadata.py`
- Test: `tests/test_security_rules.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_security_rules.py
from flunk.catalog.metadata import SECURITY_RULES, is_security_rule


def test_security_rules_locked() -> None:
    assert is_security_rule("flunk.sql-injection")
    assert is_security_rule("flunk.csrf-middleware")
    assert is_security_rule("flunk.f811-suppression")
    assert is_security_rule("flunk.bare-except-security")


def test_judgment_rules_not_security() -> None:
    assert not is_security_rule("flunk.async-client-in-fn")
    assert not is_security_rule("flunk.duplication")
    assert not is_security_rule("flunk.humanize")


def test_set_is_subset_of_catalog() -> None:
    from flunk.catalog.metadata import CATALOG
    assert SECURITY_RULES <= set(CATALOG)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_security_rules.py -v`
Expected: FAIL — `ImportError: cannot import name 'SECURITY_RULES'`

- [ ] **Step 3: Implement**

Add to `src/flunk/catalog/metadata.py` (after the `CATALOG` dict, before `lookup`):

```python
# Rules whose severity the LLM judge may RAISE or re-explain, but never lower
# or skip — a confident-but-wrong model must not be able to bury a real
# security/correctness defect. Everything else is judgment-prone and fully
# judge-able (including a "skip" verdict).
SECURITY_RULES: frozenset[str] = frozenset({
    "flunk.sql-injection",
    "flunk.csrf-middleware",
    "flunk.f811-suppression",
    "flunk.bare-except-security",
})


def is_security_rule(rule_id: str) -> bool:
    return rule_id in SECURITY_RULES
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_security_rules.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/flunk/catalog/metadata.py tests/test_security_rules.py
git commit -m "feat: mark security/correctness rules as no-downgrade for the judge"
```

---

## Task 3: The judge core (client protocol, batching, guardrail) — no SDK yet

**Files:**
- Create: `src/flunk/judge.py`
- Test: `tests/test_judge.py`

This task builds all judge logic against an injected client protocol, fully testable with a fake. The real Anthropic client lands in Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_judge.py
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
        (str(f.file), 3): Verdict(severity="medium", rationale="one-shot HEAD; pooling moot", worth_doing=True),
    })
    out = judge_findings([f], client=client, project_root=tmp_path)
    assert out[0].severity == "medium"
    assert out[0].rationale == "one-shot HEAD; pooling moot"
    assert out[0].judged is True


def test_skip_verdict_sets_skip_severity(tmp_path) -> None:
    f = _f("flunk.duplication", "medium", 1, category="duplication", file=str(tmp_path / "d.py"))
    (tmp_path / "d.py").write_text("x = 1\n", encoding="utf-8")
    client = FakeClient({
        (str(f.file), 1): Verdict(severity="skip", rationale="unrelated functions, not real dup", worth_doing=False),
    })
    out = judge_findings([f], client=client, project_root=tmp_path)
    assert out[0].severity == "skip"
    assert out[0].judged is True


def test_security_rule_cannot_be_downgraded(tmp_path) -> None:
    f = _f("flunk.sql-injection", "high", 1, file=str(tmp_path / "s.py"))
    (tmp_path / "s.py").write_text("q = f'... {x}'\n", encoding="utf-8")
    client = FakeClient({
        (str(f.file), 1): Verdict(severity="nitpick", rationale="looks fine to me", worth_doing=False),
    })
    out = judge_findings([f], client=client, project_root=tmp_path)
    assert out[0].severity == "high"          # clamp: never below catalog severity
    assert out[0].severity != "skip"          # and never skipped
    assert out[0].rationale == "looks fine to me"  # rationale rewrite still allowed


def test_security_rule_can_be_raised(tmp_path) -> None:
    f = _f("flunk.bare-except-security", "medium", 1, file=str(tmp_path / "s.py"))
    (tmp_path / "s.py").write_text("try:\n    pass\nexcept: pass\n", encoding="utf-8")
    client = FakeClient({
        (str(f.file), 1): Verdict(severity="high", rationale="swallows auth failure", worth_doing=True),
    })
    out = judge_findings([f], client=client, project_root=tmp_path)
    assert out[0].severity == "high"


def test_already_suppressed_findings_skip_the_judge(tmp_path) -> None:
    f = _f("flunk.alembic", "suppressed", 1, category="oss-catalog", file=str(tmp_path / "a.py"))
    client = FakeClient({})
    out = judge_findings([f], client=client, project_root=tmp_path)
    assert out == [f]
    assert client.calls == []  # never sent


def test_batches_one_call_per_file(tmp_path) -> None:
    (tmp_path / "a.py").write_text("x=1\ny=2\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("z=3\n", encoding="utf-8")
    fa1 = _f("flunk.humanize", "nitpick", 1, category="oss-catalog", file=str(tmp_path / "a.py"))
    fa2 = _f("flunk.humanize", "nitpick", 2, category="oss-catalog", file=str(tmp_path / "a.py"))
    fb = _f("flunk.humanize", "nitpick", 1, category="oss-catalog", file=str(tmp_path / "b.py"))
    client = FakeClient({
        (str(fa1.file), 1): Verdict("nitpick", "r", True),
        (str(fa1.file), 2): Verdict("nitpick", "r", True),
        (str(fb.file), 1): Verdict("nitpick", "r", True),
    })
    judge_findings([fa1, fa2, fb], client=client, project_root=tmp_path)
    assert sorted(client.calls) == sorted({str(fa1.file), str(fb.file)})  # 2 calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_judge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flunk.judge'`

- [ ] **Step 3: Implement the judge core**

```python
# src/flunk/judge.py
"""Opt-in LLM judge: rewrite rationale + re-rate severity per call site.

The judge takes findings that survived demote/profile/decisions and asks an
LLM whether each one actually matters *here*, with the surrounding code. It
returns enriched findings (code-specific rationale, re-rated severity, possibly
a `skip` verdict for "located but not worth doing").

All logic here is client-agnostic: a `JudgeClient` is injected. The Anthropic
implementation lives in `judge_anthropic.py`. A guardrail forbids downgrading or
skipping security/correctness rules (see metadata.SECURITY_RULES).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from flunk.catalog import metadata
from flunk.findings import SEVERITY_ORDER, Finding

CONTEXT_LINES = 6
_JUDGE_SEVERITIES = frozenset({"high", "medium", "nitpick", "skip"})


@dataclass(frozen=True)
class JudgeItem:
    """One finding presented to the LLM."""
    rule_id: str
    line: int
    catalog_severity: str
    catalog_rationale: str | None
    excerpt: str
    is_security: bool


@dataclass(frozen=True)
class Verdict:
    severity: str
    rationale: str
    worth_doing: bool


class JudgeClient(Protocol):
    def judge_file(self, rel_path: str, items: list[JudgeItem]) -> list[Verdict]: ...


def _excerpt(file: Path, line: int, context: int = CONTEXT_LINES) -> str:
    try:
        lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    idx = line - 1
    lo, hi = max(0, idx - context), min(len(lines), idx + context + 1)
    out = []
    for i in range(lo, hi):
        marker = ">>" if i == idx else "  "
        out.append(f"{marker} {i + 1}  {lines[i]}")
    return "\n".join(out)


def _rel(file: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return str(file.relative_to(root)).replace("\\", "/")
        except ValueError:
            pass
    return str(file)


def _clamp_security(verdict: Verdict, catalog_severity: str) -> Verdict:
    """Security rules: never lower severity, never skip; rationale may change."""
    sev = verdict.severity
    if sev == "skip" or SEVERITY_ORDER.get(sev, 99) > SEVERITY_ORDER[catalog_severity]:
        sev = catalog_severity
    return Verdict(severity=sev, rationale=verdict.rationale, worth_doing=verdict.worth_doing)


def judge_findings(
    findings: list[Finding],
    *,
    client: JudgeClient,
    project_root: Path | None = None,
) -> list[Finding]:
    """Return findings enriched by the judge. Suppressed findings pass through."""
    # Partition: only judge live findings; suppressed ones are already settled.
    judgeable = [f for f in findings if f.severity != "suppressed"]
    passthrough = {id(f): f for f in findings if f.severity == "suppressed"}

    by_file: dict[Path, list[Finding]] = defaultdict(list)
    for f in judgeable:
        by_file[f.file].append(f)

    enriched: dict[int, Finding] = {}
    for file, group in by_file.items():
        items = [
            JudgeItem(
                rule_id=f.rule_id,
                line=f.line,
                catalog_severity=f.severity,
                catalog_rationale=metadata.lookup(f.rule_id).rationale,
                excerpt=_excerpt(file, f.line),
                is_security=metadata.is_security_rule(f.rule_id),
            )
            for f in group
        ]
        verdicts = client.judge_file(_rel(file, project_root), items)
        for f, verdict in zip(group, verdicts, strict=True):
            sev = verdict.severity if verdict.severity in _JUDGE_SEVERITIES else f.severity
            v = Verdict(sev, verdict.rationale, verdict.worth_doing)
            if metadata.is_security_rule(f.rule_id):
                v = _clamp_security(v, f.severity)
            enriched[id(f)] = f.with_judgment(
                severity=v.severity, rationale=v.rationale, worth_doing=v.worth_doing
            )

    # Reassemble in original order.
    return [enriched.get(id(f)) or passthrough.get(id(f)) or f for f in findings]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_judge.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/flunk/judge.py tests/test_judge.py
git commit -m "feat: judge core — per-file batching, re-rate/rewrite, security clamp"
```

---

## Task 4: Anthropic-backed `JudgeClient` (optional extra)

**Files:**
- Create: `src/flunk/judge_anthropic.py`
- Modify: `pyproject.toml` (optional extra)
- Test: `tests/test_judge_anthropic.py`

- [ ] **Step 1: Add the optional extra to `pyproject.toml`**

Insert after the `dependencies = [...]` block (before `[project.scripts]`):

```toml
[project.optional-dependencies]
judge = ["anthropic>=0.40.0"]
```

- [ ] **Step 2: Write the failing test (parse a fake tool-use response; no network)**

```python
# tests/test_judge_anthropic.py
"""AnthropicJudgeClient: prompt assembly + tool-input parsing, no network."""

from __future__ import annotations

from flunk.judge import JudgeItem
from flunk.judge_anthropic import AnthropicJudgeClient, _parse_tool_input


def _item(line: int) -> JudgeItem:
    return JudgeItem(
        rule_id="flunk.async-client-in-fn", line=line, catalog_severity="high",
        catalog_rationale="generic", excerpt=">> 3  httpx.AsyncClient()", is_security=False,
    )


def test_parse_tool_input_maps_by_index() -> None:
    items = [_item(3), _item(9)]
    tool_input = {"verdicts": [
        {"index": 0, "severity": "medium", "rationale": "one-shot", "worth_doing": True},
        {"index": 1, "severity": "skip", "rationale": "n/a", "worth_doing": False},
    ]}
    verdicts = _parse_tool_input(tool_input, items)
    assert verdicts[0].severity == "medium"
    assert verdicts[1].severity == "skip"


def test_parse_tool_input_fills_missing_with_catalog_severity() -> None:
    items = [_item(3), _item(9)]
    tool_input = {"verdicts": [
        {"index": 0, "severity": "medium", "rationale": "one-shot", "worth_doing": True},
    ]}
    verdicts = _parse_tool_input(tool_input, items)
    assert len(verdicts) == 2
    assert verdicts[1].severity == "high"       # missing -> catalog severity
    assert verdicts[1].rationale == "generic"   # missing -> catalog rationale


class _FakeMessages:
    def __init__(self, payload): self._payload = payload
    def create(self, **kwargs):
        self.kwargs = kwargs
        class _Block:
            type = "tool_use"
            input = self._payload
        class _Resp:
            content = [_Block()]
        return _Resp()


class _FakeAnthropic:
    def __init__(self, payload): self.messages = _FakeMessages(payload)


def test_judge_file_calls_model_and_parses() -> None:
    payload = {"verdicts": [
        {"index": 0, "severity": "medium", "rationale": "one-shot", "worth_doing": True},
    ]}
    sdk = _FakeAnthropic(payload)
    client = AnthropicJudgeClient(model="claude-sonnet-4-6", sdk=sdk)
    verdicts = client.judge_file("a.py", [_item(3)])
    assert verdicts[0].rationale == "one-shot"
    assert sdk.messages.kwargs["model"] == "claude-sonnet-4-6"
    # forced tool use
    assert sdk.messages.kwargs["tool_choice"]["type"] == "tool"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_judge_anthropic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flunk.judge_anthropic'`

- [ ] **Step 4: Implement**

```python
# src/flunk/judge_anthropic.py
"""Anthropic-backed JudgeClient. Requires the `judge` optional extra.

One forced-tool-use call per file: the model receives every finding in that
file (rule, catalog severity/rationale as a prior, code excerpt) and returns a
verdict per finding via a structured tool input. Parsing is index-keyed and
tolerant: a missing/garbled verdict falls back to the catalog severity/rationale
so a flaky response degrades to "no change", never to a dropped finding.
"""

from __future__ import annotations

from typing import Any

from flunk.judge import JudgeItem, Verdict

_TOOL = {
    "name": "report_verdicts",
    "description": "Report a judgment verdict for each located finding.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "0-based finding index"},
                        "severity": {"type": "string", "enum": ["high", "medium", "nitpick", "skip"]},
                        "rationale": {"type": "string", "description": "1-2 sentences, specific to THIS code"},
                        "worth_doing": {"type": "boolean"},
                    },
                    "required": ["index", "severity", "rationale", "worth_doing"],
                },
            }
        },
        "required": ["verdicts"],
    },
}

_SYSTEM = (
    "You are a senior engineer triaging static-analysis findings on AI-built "
    "Python. For each finding you see the rule, a GENERIC catalog rationale "
    "(a prior, not gospel), and the surrounding code. Judge whether it actually "
    "matters HERE. Re-rate severity for this call site, and rewrite the rationale "
    "to reason about THIS code (not the template). Use 'skip' when the pattern is "
    "present but not worth fixing in context (e.g. a one-shot call, a deliberate "
    "local trade-off, a false-positive duplication of unrelated code). Be concrete."
)


def _build_user_text(rel_path: str, items: list[JudgeItem]) -> str:
    chunks = [f"File: {rel_path}\n"]
    for i, it in enumerate(items):
        sec = " [SECURITY: severity may be raised but NOT lowered or skipped]" if it.is_security else ""
        chunks.append(
            f"--- finding index {i} ---\n"
            f"rule: {it.rule_id} (catalog severity: {it.catalog_severity}){sec}\n"
            f"catalog rationale (generic prior): {it.catalog_rationale}\n"
            f"code:\n{it.excerpt}\n"
        )
    return "\n".join(chunks)


def _parse_tool_input(tool_input: dict[str, Any], items: list[JudgeItem]) -> list[Verdict]:
    """Map the model's verdicts back onto items by index; fill gaps from catalog."""
    by_index: dict[int, dict] = {}
    for v in tool_input.get("verdicts", []):
        if isinstance(v, dict) and isinstance(v.get("index"), int):
            by_index[v["index"]] = v
    out: list[Verdict] = []
    for i, it in enumerate(items):
        v = by_index.get(i)
        if v is None:
            out.append(Verdict(it.catalog_severity, it.catalog_rationale or "", True))
            continue
        out.append(Verdict(
            severity=str(v.get("severity") or it.catalog_severity),
            rationale=str(v.get("rationale") or it.catalog_rationale or ""),
            worth_doing=bool(v.get("worth_doing", True)),
        ))
    return out


class AnthropicJudgeClient:
    def __init__(self, *, model: str, sdk: Any | None = None) -> None:
        self.model = model
        self._sdk = sdk  # injected in tests; built lazily otherwise

    def _client(self) -> Any:
        if self._sdk is not None:
            return self._sdk
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - exercised via CLI error path
            raise RuntimeError(
                "--judge needs the anthropic SDK. Install it with: "
                "pip install 'flunk[judge]'"
            ) from e
        self._sdk = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        return self._sdk

    def judge_file(self, rel_path: str, items: list[JudgeItem]) -> list[Verdict]:
        resp = self._client().messages.create(
            model=self.model,
            max_tokens=1024,
            system=_SYSTEM,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "report_verdicts"},
            messages=[{"role": "user", "content": _build_user_text(rel_path, items)}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return _parse_tool_input(block.input, items)
        # No tool block -> no change.
        return [Verdict(it.catalog_severity, it.catalog_rationale or "", True) for it in items]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_judge_anthropic.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/flunk/judge_anthropic.py pyproject.toml tests/test_judge_anthropic.py
git commit -m "feat: Anthropic-backed JudgeClient behind the flunk[judge] extra"
```

---

## Task 5: Render the `skip` verdict (table, json, agent plan)

**Files:**
- Modify: `src/flunk/rank.py`
- Modify: `src/flunk/agent.py`
- Test: `tests/test_rank.py`, `tests/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_rank.py`:

```python
def test_skip_severity_has_style_and_sorts_last(capsys):
    from rich.console import Console
    from flunk.findings import Finding
    from flunk import rank as rank_mod
    from pathlib import Path

    findings = [
        Finding("flunk.duplication", "duplication", "skip", Path("d.py"), 1,
                "located but not worth doing", rationale="unrelated funcs", judged=True),
        Finding("flunk.async-client-in-fn", "anti-pattern", "high", Path("a.py"), 1, "real"),
    ]
    ranked = rank_mod.rank(findings)
    assert ranked[0].severity == "high"      # skip sorts after high
    assert ranked[-1].severity == "skip"
    rank_mod.render_table(ranked, top=10, console=Console())
    # smoke: no exception, skip row rendered
```

Add to `tests/test_agent.py` (match the file's existing import/style):

```python
def test_agent_prefers_judged_rationale(tmp_path):
    from flunk.agent import build_plan
    from flunk.findings import Finding
    from pathlib import Path

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rank.py -k skip tests/test_agent.py -k "judged or skip" -v`
Expected: FAIL — skip has no style / agent uses only `meta.rationale` and has no skip group.

- [ ] **Step 3: Implement rank.py changes**

In `src/flunk/rank.py`, add a `skip` entry to `SEVERITY_STYLE`:

```python
SEVERITY_STYLE = {
    "high": "bold red",
    "medium": "yellow",
    "nitpick": "dim",
    "skip": "dim italic",
    "suppressed": "dim strike",
}
```

In `render_table`, where the message cell is built, surface the judged rationale and a skip note. Replace the `msg = f.message` / `if f.demoted_by` block with:

```python
        msg = f.rationale or f.message
        if f.severity == "skip":
            msg = f"[skip — not worth doing] {msg}"
        if f.demoted_by:
            msg = f"{msg} [dim](demoted: {f.demoted_by})[/dim]"
```

- [ ] **Step 4: Implement agent.py changes**

In `src/flunk/agent.py`:

(a) Prefer the judged rationale. In `build_plan`, where it does `if meta.rationale:`, change to use a per-rule judged rationale when present. Replace:

```python
        if meta.rationale:
            out.append(f"**Why it's worse:** {meta.rationale}")
            out.append("")
```

with:

```python
        judged_rationale = next((f.rationale for f in fs if f.rationale), None)
        why = judged_rationale or meta.rationale
        if why:
            label = "Judge's take" if judged_rationale else "Why it's worse"
            out.append(f"**{label}:** {why}")
            out.append("")
```

(b) Separate the skip group. In `_group_by_rule`, skip findings should still be grouped (they are not `suppressed`), so no change there. Instead, in `build_plan`, after building the section header, add a not-worth-doing banner when the group's severity is `skip`. Where `sev = fs[0].severity` is used to build the header, add right after `out.append(f"## {prefix}{sev.upper()} · {rule_id} · {n} {occ}")`:

```python
        out.append("")
        if sev == "skip":
            out.append("> **Judged not worth doing** — kept here with the judge's reason; no action expected.")
```

(Remove the now-duplicate `out.append("")` if one already follows; keep exactly one blank line before the rationale.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_rank.py tests/test_agent.py -v`
Expected: PASS (existing agent/rank tests stay green; new ones pass)

- [ ] **Step 6: Commit**

```bash
git add src/flunk/rank.py src/flunk/agent.py tests/test_rank.py tests/test_agent.py
git commit -m "feat: render judged rationale + 'not worth doing' skip group"
```

---

## Task 6: Wire `--judge` / `--judge-model` into the CLI

**Files:**
- Modify: `src/flunk/cli.py`
- Test: `tests/test_cli_judge.py`

- [ ] **Step 1: Write the failing test (uses a fake client via dependency seam)**

```python
# tests/test_cli_judge.py
"""--judge runs the judge pass; missing SDK gives a clean error."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from flunk.cli import app

runner = CliRunner()


def test_judge_flag_invokes_pass(tmp_path, monkeypatch):
    # Minimal project so the pipeline runs; stub the locators to one finding.
    from flunk import cli as cli_mod
    from flunk.findings import Finding

    monkeypatch.setattr(cli_mod.semgrep_runner, "run", lambda p, **k: [
        Finding("flunk.humanize", "oss-catalog", "nitpick", tmp_path / "a.py", 1, "m")
    ])
    monkeypatch.setattr(cli_mod.detectors_mod, "run_all", lambda p: [])
    monkeypatch.setattr(cli_mod.jscpd_runner, "run", lambda p, **k: [])
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    captured = {}

    def fake_judge(findings, *, client, project_root=None):
        captured["called"] = True
        return findings

    monkeypatch.setattr(cli_mod.judge_mod, "judge_findings", fake_judge)
    monkeypatch.setattr(
        cli_mod, "_build_judge_client", lambda model: object()
    )

    result = runner.invoke(app, [str(tmp_path), "--judge", "--json"])
    assert result.exit_code == 0
    assert captured.get("called") is True


def test_judge_missing_sdk_errors_cleanly(tmp_path, monkeypatch):
    from flunk import cli as cli_mod
    from flunk.findings import Finding

    monkeypatch.setattr(cli_mod.semgrep_runner, "run", lambda p, **k: [
        Finding("flunk.humanize", "oss-catalog", "nitpick", tmp_path / "a.py", 1, "m")
    ])
    monkeypatch.setattr(cli_mod.detectors_mod, "run_all", lambda p: [])
    monkeypatch.setattr(cli_mod.jscpd_runner, "run", lambda p, **k: [])
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    def boom(model):
        raise RuntimeError("--judge needs the anthropic SDK. Install it with: pip install 'flunk[judge]'")

    monkeypatch.setattr(cli_mod, "_build_judge_client", boom)
    result = runner.invoke(app, [str(tmp_path), "--judge"])
    assert result.exit_code == 2
    assert "flunk[judge]" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli_judge.py -v`
Expected: FAIL — no `--judge` option / no `judge_mod` / no `_build_judge_client`.

- [ ] **Step 3: Implement the CLI wiring**

In `src/flunk/cli.py`:

(a) Add the import with the other module imports:

```python
from flunk import judge as judge_mod
```

(b) Add a client-builder helper (after the `err_console` definition):

```python
def _build_judge_client(model: str):
    """Construct the Anthropic-backed judge client (kept here so tests can stub it)."""
    from flunk.judge_anthropic import AnthropicJudgeClient

    return AnthropicJudgeClient(model=model)
```

(c) Add two options to the `audit` command signature (after `profile`):

```python
    judge: bool = typer.Option(
        False,
        "--judge",
        help="Send findings to an LLM to re-rate severity and rewrite rationale "
             "for the specific code (needs `pip install 'flunk[judge]'` + "
             "ANTHROPIC_API_KEY). Off by default; the static pipeline is unchanged.",
    ),
    judge_model: str = typer.Option(
        "claude-sonnet-4-6",
        "--judge-model",
        help="Model for the --judge pass.",
    ),
```

(d) Insert the judge pass after the `.flunkignore` decisions step and before ranking. After:

```python
        findings = decisions_mod.apply_decisions(
            findings, decisions_mod.load_decisions(project)
        )
```

add:

```python
        if judge:
            status.update("[bold]Judging findings with the LLM…")
            try:
                client = _build_judge_client(judge_model)
            except RuntimeError as e:
                status.stop()
                console.print(f"[bold red]error:[/bold red] {e}")
                raise typer.Exit(code=2)
            findings = judge_mod.judge_findings(
                findings, client=client, project_root=project
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_cli_judge.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/flunk/cli.py tests/test_cli_judge.py
git commit -m "feat: wire --judge / --judge-model into the audit CLI"
```

---

## Task 7: Docs + full-suite green

**Files:**
- Modify: `README.md`
- Modify: `STATUS.md`
- Modify: `CLAUDE.md` (note the new optional extra + judge metadata location)

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Document `--judge` in README.md**

Add a short section after the quickstart:

```markdown
### Optional: LLM judgment pass

By default flunk is fully static and offline. For code-specific severity and
rationale, add `--judge`:

    pip install 'flunk[judge]'
    export ANTHROPIC_API_KEY=...          # PowerShell: $env:ANTHROPIC_API_KEY="..."
    flunk ./yourproject --judge

The judge re-rates each finding for its actual call site and rewrites the
"why it's worse" note to reason about your code. Findings it deems not worth
fixing are kept in the output under "Judged not worth doing", never silently
dropped. Security/correctness findings can be escalated but never downgraded.
Pick the model with `--judge-model` (default `claude-sonnet-4-6`).
```

- [ ] **Step 3: Note the judge in STATUS.md and CLAUDE.md**

STATUS.md — add under the v1.5 backlog or a new "Judge (2026-05-29)" note that the opt-in LLM judge pass shipped (per the design doc), pointing at `src/flunk/judge.py` + `judge_anthropic.py`.

CLAUDE.md — under "Conventions", add a bullet: *"The opt-in `--judge` LLM pass lives in `src/flunk/judge.py` (logic) + `judge_anthropic.py` (SDK client, behind the `flunk[judge]` extra). Security rules in `metadata.SECURITY_RULES` can be escalated but never downgraded/skipped by the judge."*

- [ ] **Step 4: Commit**

```bash
git add README.md STATUS.md CLAUDE.md
git commit -m "docs: document the opt-in --judge LLM pass"
```

---

## Self-review notes

- **Spec coverage:** judge component → Tasks 3–4 & 6; full authority (rewrite + re-rate + skip) → Task 3; security guardrail → Tasks 2–3; "judge everything non-suppressed" → Task 3 partition; skip kept-in-output → Task 5; packaging extra + model default → Tasks 4 & 6; stubbed-client tests, no live API → Tasks 3–6.
- **Type consistency:** `JudgeItem`, `Verdict`, `JudgeClient.judge_file`, `judge_findings(findings, *, client, project_root)`, `Finding.with_judgment(*, severity, rationale, worth_doing)`, `is_security_rule`, `SECURITY_RULES`, `_build_judge_client(model)`, `AnthropicJudgeClient(model=, sdk=)` are each defined once and used consistently across tasks.
- **Degrade-safe:** a missing/garbled LLM verdict falls back to catalog severity/rationale (`_parse_tool_input`), so the judge never drops a finding; suppressed findings bypass the judge entirely.
- **Placeholder scan:** no TBD/TODO; every code step shows complete code.
```
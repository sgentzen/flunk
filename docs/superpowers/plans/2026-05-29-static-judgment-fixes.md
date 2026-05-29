# Static Judgment Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the three deterministic misses from the 2026-05-29 job-stalker eval — async-client over-rated HIGH, duplication false-positive noise, and pydantic-settings firing on a presence-check branch — without any new dependency.

**Architecture:** All three are post-processing refinements over already-located findings. async-client severity and pydantic-settings narrowing hook into the semgrep `post_process()` pass (which already owns per-rule aggregation/filtering); duplication noise is filtered in the jscpd runner. Each fix is AST-based and offline.

**Tech Stack:** Python 3.12, `ast` (stdlib), existing semgrep/jscpd subprocess wrappers, pytest.

See design: [docs/superpowers/specs/2026-05-29-hybrid-judgment-pass-design.md](../specs/2026-05-29-hybrid-judgment-pass-design.md)

---

## Task 1: Context-aware async-client severity

**Why:** The catalog rates `flunk.async-client-in-fn` HIGH unconditionally. The eval showed four one-shot, single-host calls where HIGH overstates impact — pooling helps only when the same client is reused across repeated calls (i.e. inside a loop). Downgrade to MEDIUM unless the `httpx.AsyncClient(...)` / `httpx.Client(...)` construction is lexically inside a loop in its enclosing function.

> **Deliberate scope note:** We detect *lexical* loop nesting only (the construction is inside a `for`/`while`/`async for`/comprehension in its own function). Cross-function "this helper is called in a loop" analysis is explicitly out of scope (YAGNI) — all four eval cases are simple one-shots, and lexical detection is robust and testable. The message is written to say so honestly.

**Files:**
- Create: `src/flunk/detectors/async_client_severity.py`
- Modify: `src/flunk/catalog/__init__.py` (call the refiner at the end of `post_process`)
- Test: `tests/test_async_client_severity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_async_client_severity.py
"""async-client severity is HIGH only when the client is built inside a loop."""

from __future__ import annotations

from pathlib import Path

from flunk.detectors.async_client_severity import refine
from flunk.findings import Finding


def _finding(file: Path, line: int) -> Finding:
    return Finding(
        rule_id="flunk.async-client-in-fn",
        category="anti-pattern",
        severity="high",
        file=file,
        line=line,
        message="httpx client instantiated inside a function body.",
    )


def test_oneshot_call_downgraded_to_medium(tmp_path: Path) -> None:
    src = tmp_path / "adapter.py"
    src.write_text(
        "import httpx\n"
        "async def fetch(url):\n"
        "    async with httpx.AsyncClient() as c:\n"
        "        return await c.get(url)\n",
        encoding="utf-8",
    )
    out = refine([_finding(src, 3)])
    assert out[0].severity == "medium"
    assert out[0].raw_severity == "high"
    assert "one-shot" in out[0].message.lower()


def test_client_inside_loop_stays_high(tmp_path: Path) -> None:
    src = tmp_path / "poller.py"
    src.write_text(
        "import httpx\n"
        "async def poll(urls):\n"
        "    for url in urls:\n"
        "        async with httpx.AsyncClient() as c:\n"
        "            await c.get(url)\n",
        encoding="utf-8",
    )
    out = refine([_finding(src, 4)])
    assert out[0].severity == "high"
    assert out[0].raw_severity is None


def test_non_async_client_findings_untouched(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text("x = 1\n", encoding="utf-8")
    other = Finding(
        rule_id="flunk.alembic", category="oss-catalog", severity="medium",
        file=src, line=1, message="m",
    )
    assert refine([other]) == [other]


def test_unparseable_file_left_untouched(tmp_path: Path) -> None:
    src = tmp_path / "broken.py"
    src.write_text("def (:\n", encoding="utf-8")
    f = _finding(src, 1)
    assert refine([f]) == [f]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_async_client_severity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flunk.detectors.async_client_severity'`

- [ ] **Step 3: Write the implementation**

```python
# src/flunk/detectors/async_client_severity.py
"""Refine flunk.async-client-in-fn severity by call-site context.

The catalog rates this rule HIGH, assuming a hot path that rebuilds the
connection pool every call. That only bites when the same construction runs
repeatedly — i.e. inside a loop. A one-shot construction (a single request to
one host) pays one TLS handshake it would pay anyway, so HIGH overstates it.

We downgrade HIGH -> MEDIUM unless the httpx.AsyncClient(...) / httpx.Client(...)
construction is lexically inside a loop in its enclosing function. Lexical only:
cross-function "called in a loop" analysis is out of scope.
"""

from __future__ import annotations

import ast
from pathlib import Path

from flunk.findings import Finding

RULE_ID = "flunk.async-client-in-fn"
_LOOP_NODES = (ast.For, ast.AsyncFor, ast.While, ast.comprehension)
_CLIENT_ATTRS = frozenset({"AsyncClient", "Client"})

_ONESHOT_MSG = (
    "httpx client built inside a function body, but this is a one-shot "
    "construction (not in a loop) — connection pooling only helps when the "
    "same client is reused across repeated calls. Reuse a module-level / "
    "lifespan-managed client if these calls ever go on a hot path."
)


def _is_httpx_client_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _CLIENT_ATTRS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "httpx"
    )


def _construction_in_loop(tree: ast.AST, line: int) -> bool:
    """True if an httpx client call on `line` has a loop among its ancestors."""
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    for node in ast.walk(tree):
        if getattr(node, "lineno", None) != line or not _is_httpx_client_call(node):
            continue
        cur = parents.get(node)
        while cur is not None:
            if isinstance(cur, _LOOP_NODES):
                return True
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Stop at the enclosing function boundary: a loop further out
                # (e.g. wrapping the call site) is the cross-function case we
                # deliberately don't model.
                return False
            cur = parents.get(cur)
    return False


def refine(findings: list[Finding]) -> list[Finding]:
    """Downgrade one-shot async-client findings HIGH -> MEDIUM."""
    out: list[Finding] = []
    for f in findings:
        if f.rule_id != RULE_ID or f.severity != "high":
            out.append(f)
            continue
        try:
            tree = ast.parse(
                f.file.read_text(encoding="utf-8", errors="replace")
            )
        except (OSError, SyntaxError):
            out.append(f)
            continue
        if _construction_in_loop(tree, f.line):
            out.append(f)
        else:
            out.append(
                f.with_demote("medium", "context: one-shot construction")
                ._replace_message(_ONESHOT_MSG)
                if hasattr(f, "_replace_message")
                else f.with_demote("medium", "context: one-shot construction")
            )
    return out
```

> Note: `with_demote` sets `raw_severity` and `demoted_by`; we also need the message rewritten. `Finding` is frozen and has no message setter. Add one in Step 3b.

- [ ] **Step 3b: Add a message-replacing helper to `Finding`**

Modify `src/flunk/findings.py` — add this method to the `Finding` dataclass (after `with_demote`):

```python
    def with_message(self, new_message: str) -> Finding:
        return replace(self, message=new_message)
```

Then simplify the `refine` else-branch in `async_client_severity.py` to:

```python
        else:
            demoted = f.with_demote("medium", "context: one-shot construction")
            out.append(demoted.with_message(_ONESHOT_MSG))
```

(Remove the `hasattr`/`_replace_message` placeholder — it was a stand-in until `with_message` existed.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_async_client_severity.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Wire `refine` into `post_process`**

Modify `src/flunk/catalog/__init__.py`. Add the import at the top of the file (after the existing imports):

```python
from flunk.detectors import async_client_severity
```

Change the final `return out` of `post_process` to:

```python
    return async_client_severity.refine(out)
```

- [ ] **Step 6: Run the full suite + confirm async-client still *fires* on erate-filing-assistant**

Run: `python -m pytest tests/test_catalog.py -k async_client -v`
Expected: PASS — refinement changes severity, not whether the rule fires, so `test_catalog.py`'s `async-client-in-fn -> erate_filing_assistant` expectation still holds.

- [ ] **Step 7: Commit**

```bash
git add src/flunk/detectors/async_client_severity.py src/flunk/findings.py src/flunk/catalog/__init__.py tests/test_async_client_severity.py
git commit -m "fix: rate async-client MEDIUM for one-shot calls, HIGH only in a loop"
```

---

## Task 2: Narrow pydantic-settings to exclude presence-check branches

**Why:** The rule matched `if not os.environ.get("ANTHROPIC_API_KEY"):` in `job-stalker/__main__.py` — a presence check selecting a runner with a working fallback, not a config read that propagates `None`. All three of job-stalker's hits are this shape, so narrowing makes the rule stop firing there (the eval's desired "Skip"). The aggregation threshold is 3; dropping the presence-check matches takes the count below 3.

**Files:**
- Create: `src/flunk/catalog/env_read_filter.py`
- Modify: `src/flunk/catalog/__init__.py` (filter raw matches before aggregation)
- Modify: `tests/test_catalog.py` (remove `job_stalker` from pydantic-settings expectation, with a note)
- Modify: `docs/CATALOG.md` (update the evidence column for rule #1)
- Test: `tests/test_env_read_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_env_read_filter.py
"""os.environ.get used purely as a presence check is not a config read."""

from __future__ import annotations

from pathlib import Path

from flunk.catalog.env_read_filter import drop_presence_checks
from flunk.findings import Finding


def _f(file: Path, line: int) -> Finding:
    return Finding(
        rule_id="flunk.pydantic-settings",
        category="oss-catalog",
        severity="high",
        file=file,
        line=line,
        message="hand-rolled env parsing",
    )


def test_branch_condition_dropped(tmp_path: Path) -> None:
    src = tmp_path / "__main__.py"
    src.write_text(
        "import os\n"
        "def pick():\n"
        "    if not os.environ.get('ANTHROPIC_API_KEY'):\n"
        "        return Fallback()\n",
        encoding="utf-8",
    )
    assert drop_presence_checks([_f(src, 3)]) == []


def test_config_read_kept(tmp_path: Path) -> None:
    src = tmp_path / "config.py"
    src.write_text(
        "import os\n"
        "TOKEN = os.environ.get('API_TOKEN')\n",
        encoding="utf-8",
    )
    out = drop_presence_checks([_f(src, 2)])
    assert len(out) == 1


def test_other_rules_untouched(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text("x = 1\n", encoding="utf-8")
    other = Finding(
        rule_id="flunk.alembic", category="oss-catalog", severity="medium",
        file=src, line=1, message="m",
    )
    assert drop_presence_checks([other]) == [other]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_env_read_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'flunk.catalog.env_read_filter'`

- [ ] **Step 3: Write the implementation**

```python
# src/flunk/catalog/env_read_filter.py
"""Drop pydantic-settings matches that are presence checks, not config reads.

`os.environ.get(...)` used directly as a boolean test (`if not os.environ.get(...)`,
`while os.environ.get(...)`, `x = os.environ.get(...) or default` *as a guard*) is a
branch selector with a working fallback — not a config value read into the program
that surfaces as None deep in a call path. Those are the false positives the rule's
rationale doesn't apply to, so we exclude them before the count-threshold aggregation.

A match is a CONFIG READ (kept) when its value flows somewhere: assigned, returned,
passed as an argument, stored in a dict/attr. It is a PRESENCE CHECK (dropped) when
the call is the test expression of an `if`/`while`/`assert`, or the direct operand of
`not`, or a comparison against a constant inside such a test.
"""

from __future__ import annotations

import ast
from pathlib import Path

from flunk.findings import Finding

RULE_ID = "flunk.pydantic-settings"
_ENV_FUNCS = {("os", "environ", "get"), ("os", "getenv")}


def _is_env_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    # os.getenv(...)
    if (
        isinstance(func, ast.Attribute)
        and func.attr == "getenv"
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    ):
        return True
    # os.environ.get(...)
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    )


def _presence_check_lines(tree: ast.AST) -> set[int]:
    """Lines where an env call appears only as a branch/boolean test."""
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def in_test_position(call: ast.AST) -> bool:
        # Walk up through not/bool-op/compare wrappers; the env call is a
        # presence check iff the first "structural" ancestor is the test of
        # an if/while/assert (or an IfExp test).
        node: ast.AST = call
        cur = parents.get(node)
        while isinstance(cur, (ast.UnaryOp, ast.BoolOp, ast.Compare)):
            node, cur = cur, parents.get(cur)
        if isinstance(cur, (ast.If, ast.While)):
            return cur.test is node
        if isinstance(cur, ast.IfExp):
            return cur.test is node
        if isinstance(cur, ast.Assert):
            return cur.test is node
        return False

    lines: set[int] = set()
    for node in ast.walk(tree):
        if _is_env_call(node) and in_test_position(node):
            lines.add(node.lineno)
    return lines


def drop_presence_checks(findings: list[Finding]) -> list[Finding]:
    """Remove pydantic-settings findings whose match is a presence check."""
    cache: dict[Path, set[int]] = {}
    out: list[Finding] = []
    for f in findings:
        if f.rule_id != RULE_ID:
            out.append(f)
            continue
        if f.file not in cache:
            try:
                cache[f.file] = _presence_check_lines(
                    ast.parse(f.file.read_text(encoding="utf-8", errors="replace"))
                )
            except (OSError, SyntaxError):
                cache[f.file] = set()
        if f.line not in cache[f.file]:
            out.append(f)
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_env_read_filter.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Wire the filter into `post_process` (before aggregation)**

Modify `src/flunk/catalog/__init__.py`. Add import near the top:

```python
from flunk.catalog.env_read_filter import drop_presence_checks
```

In `post_process`, apply it to the path-filtered list before the aggregation loop. Change:

```python
    aggregated: dict[tuple[str, Path], list[Finding]] = defaultdict(list)
    passthrough: list[Finding] = []

    for f in filtered:
```

to:

```python
    filtered = drop_presence_checks(filtered)

    aggregated: dict[tuple[str, Path], list[Finding]] = defaultdict(list)
    passthrough: list[Finding] = []

    for f in filtered:
```

- [ ] **Step 6: Update the regression matrix (the job-stalker fire was a false positive)**

Modify `tests/test_catalog.py`. Change the `flunk.pydantic-settings` row of `EXPECTED_FIRES` from:

```python
    "flunk.pydantic-settings":      ("job_stalker", "erate_filing_assistant", "erate_prospector"),
```

to:

```python
    # job-stalker dropped 2026-05-29: its only hits were 3 presence-check
    # guards (`if not os.environ.get("ANTHROPIC_API_KEY")`) in __main__.py —
    # a branch with a working fallback, not a config read. env_read_filter
    # now excludes presence checks, so the count falls below the threshold.
    "flunk.pydantic-settings":      ("erate_filing_assistant", "erate_prospector"),
```

- [ ] **Step 7: Update CATALOG.md evidence for rule #1**

Read `docs/CATALOG.md`, find the `pydantic-settings` rule's evidence/`Expected fires` line listing all three projects, and update it to `erate-filing-assistant, erate-prospector` with a one-line note: *"job-stalker excluded 2026-05-29 — its os.environ hits are presence-check branches, not config reads (see env_read_filter)."* Also update the `# Expected fires:` comment in `src/flunk/catalog/patterns/pydantic_settings.yml` to match.

- [ ] **Step 8: Run the catalog regression suite**

Run: `python -m pytest tests/test_catalog.py -k pydantic -v`
Expected: PASS — pydantic-settings now expected on the two erate projects only; no job-stalker assertion remains.

- [ ] **Step 9: Commit**

```bash
git add src/flunk/catalog/env_read_filter.py src/flunk/catalog/__init__.py src/flunk/catalog/patterns/pydantic_settings.yml tests/test_env_read_filter.py tests/test_catalog.py docs/CATALOG.md
git commit -m "fix: pydantic-settings ignores presence-check branches (not config reads)"
```

---

## Task 3: Cut jscpd duplication noise

**Why:** At `min_tokens=50` the duplication runner matched generic boilerplate across unrelated functions (the eval's 10 "duplicates" were mostly `def`/`try:`/`async with` scaffolding, not real copy-paste). Raising the token floor and dropping very short clone pairs removes that noise while keeping genuine cross-file copies (e.g. the greenhouse httpx block).

**Files:**
- Modify: `src/flunk/runners/jscpd.py`
- Test: `tests/test_jscpd.py` (add a filter unit test; keep existing tests green)

- [ ] **Step 1: Read the existing jscpd tests**

Run: `python -m pytest tests/test_jscpd.py -v` and read `tests/test_jscpd.py` so the new test matches its style (it likely feeds a synthetic `jscpd-report.json` / monkeypatches `subprocess.run`). Reuse its fixtures rather than inventing new ones.

- [ ] **Step 2: Write the failing test for the line-length filter**

Add to `tests/test_jscpd.py` (adapt the report-shape helper to whatever the file already uses; this is the canonical jscpd duplicate shape):

```python
def test_short_clone_pairs_are_filtered(monkeypatch, tmp_path):
    """A clone pair shorter than MIN_DUP_LINES is dropped as boilerplate noise."""
    from flunk.runners import jscpd as jscpd_runner

    report = {
        "duplicates": [
            {  # noise: 3-line generic scaffolding
                "lines": 3, "tokens": 80,
                "firstFile": {"name": "a.py", "startLoc": {"line": 10}},
                "secondFile": {"name": "b.py", "startLoc": {"line": 40}},
            },
            {  # real: 8-line copied block
                "lines": 8, "tokens": 120,
                "firstFile": {"name": "c.py", "startLoc": {"line": 5}},
                "secondFile": {"name": "d.py", "startLoc": {"line": 90}},
            },
        ]
    }
    findings = jscpd_runner._findings_from_payload(report)
    assert len(findings) == 1
    assert findings[0].file.name == "c.py"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_jscpd.py::test_short_clone_pairs_are_filtered -v`
Expected: FAIL — `AttributeError: module 'flunk.runners.jscpd' has no attribute '_findings_from_payload'`

- [ ] **Step 4: Refactor parsing into `_findings_from_payload` and add the filter**

Modify `src/flunk/runners/jscpd.py`:

Add a module constant near `JSCPD_RULE_ID`:

```python
# Clone pairs shorter than this are almost always generic scaffolding
# (def headers, `try:` / `async with` blocks) rather than real copy-paste.
MIN_DUP_LINES = 6
```

Bump the default token floor in `run`'s signature:

```python
def run(project: Path, *, min_tokens: int = 70) -> list[Finding]:
```

Extract the payload-to-findings loop out of `run` into a new function (move the existing `meta = lookup(...)` + `for dup in payload.get("duplicates", [])` block verbatim, then add the length guard):

```python
def _findings_from_payload(payload: dict) -> list[Finding]:
    """Parse a jscpd report payload into Findings, dropping short noise pairs."""
    meta = lookup(JSCPD_RULE_ID)
    findings: list[Finding] = []
    for dup in payload.get("duplicates", []):
        lines = int(dup.get("lines") or 0)
        if lines < MIN_DUP_LINES:
            continue
        first = dup.get("firstFile", {})
        second = dup.get("secondFile", {})
        path = first.get("name") or first.get("path")
        if not path:
            continue
        tokens = int(dup.get("tokens") or 0)
        findings.append(
            Finding(
                rule_id=JSCPD_RULE_ID,
                category=meta.category,
                severity=meta.severity,
                file=Path(path),
                line=int(first.get("startLoc", {}).get("line", first.get("start", 1)) or 1),
                message=(
                    f"Duplicated block ({lines} lines, {tokens} tokens) — also at "
                    f"{second.get('name') or second.get('path', '?')}:"
                    f"{second.get('startLoc', {}).get('line', second.get('start', '?'))}. "
                    f"Extract a shared helper."
                ),
                replacement=meta.replacement,
                replacement_url=meta.replacement_url,
            )
        )
    return findings
```

Then replace the corresponding inline block at the end of `run` with:

```python
    return _findings_from_payload(payload)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_jscpd.py -v`
Expected: PASS — new test passes, existing jscpd tests still pass.

- [ ] **Step 6: Empirically confirm against job-stalker (if jscpd + node are installed)**

Run: `python -c "import sys; sys.path.insert(0, 'src'); from pathlib import Path; from flunk.runners import jscpd; print(len(jscpd.run(Path('../job-stalker'))))"`
Expected: a small number (the eval had 10; with the filter the unrelated-function pairs drop). If jscpd/node aren't installed the call returns `[]` (0) — that's fine, the unit test covers the logic. Record the before/after count in the commit message if you ran it.

- [ ] **Step 7: Commit**

```bash
git add src/flunk/runners/jscpd.py tests/test_jscpd.py
git commit -m "fix: cut jscpd duplication noise (min-tokens 70, drop clones < 6 lines)"
```

---

## Task 4: Full-suite green + update STATUS.md

**Files:**
- Modify: `STATUS.md`

- [ ] **Step 1: Run the entire test suite**

Run: `python -m pytest -q`
Expected: all tests pass (the prior 97 + the new async-client/env-filter/jscpd tests). If `test_catalog.py` reports skips for absent siblings, that's expected on a checkout without the regression projects.

- [ ] **Step 2: Append a note to STATUS.md**

Under the existing "Signal-to-noise pass (2026-05-29)" section, add:

```markdown
### Eval-driven static fixes (2026-05-29)

Driven by an external eval of a job-stalker scan ("locates well, judges poorly"):
- **async-client severity is context-aware** (detectors/async_client_severity.py): HIGH only when the client is built inside a loop; one-shot constructions are MEDIUM with a "pooling only helps under repeated calls" message.
- **pydantic-settings ignores presence checks** (catalog/env_read_filter.py): `if not os.environ.get(...)` branch guards are no longer counted as config reads. job-stalker dropped from the rule's expected-fires (its 3 hits were all presence checks).
- **jscpd noise cut**: min-tokens 50 → 70 and clone pairs < 6 lines dropped.
```

- [ ] **Step 3: Commit**

```bash
git add STATUS.md
git commit -m "docs: record eval-driven static judgment fixes in STATUS"
```

---

## Self-review notes

- **Spec coverage:** Static wins #1 (async-client) → Task 1; #3 (pydantic narrowing) → Task 2; #2 (duplication noise) → Task 3. Output/judge/packaging belong to Plan 2 (LLM judge) and are intentionally not here.
- **Type consistency:** `refine`, `drop_presence_checks`, `_findings_from_payload` are each defined once and called with the signatures shown. `Finding.with_message` is added in Task 1 Step 3b and used only there.
- **Known coupling:** Task 2 changes a golden expectation; that is deliberate and documented in code + CATALOG.md.

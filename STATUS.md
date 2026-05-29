# Status

**Current phase:** v1 ships (2026-05-26). All 15 catalog rules implemented + jscpd duplication runner + justification-demote + rich/JSON output. 27 tests pass: 5 demote, 3 rank, 19 catalog-regression (every rule × every project it's expected to fire on per CATALOG.md evidence).

## Locked decisions

- **Name:** `flunk` (verified clean on PyPI 2026-05-26; verify again immediately before first publish)
- **Scope:** Python only for v1. Single-repo. Local CLI. No cross-project analysis.
- **Pipeline:** `semgrep + jscpd` wrappers → custom OSS-catalog Semgrep rules → justification-aware demote pass → ranked `rich` output
- **Regression suite:** `job-stalker`, `erate-filing-assistant`, `erate-prospector` (all siblings under `C:\Users\sgent\projects\`)
- **Out of scope for v1:** cross-project dedup, LLM judgment, visual map, pre-flight planning hook, spec-conformance, non-Python languages

## Weekend 1 — prove the core loop

Goal: a working `flunk audit ./project` that prints real findings from one real catalog rule against one real project.

- [x] `pip index versions flunk` + `gh search repos flunk` — verified clean on 2026-05-26 (no PyPI release exists; the GitHub matches are unrelated projects: flunkydom, flunkysimulator, gargakshit/flunk-the-app)
- [x] `uv init` + project skeleton matching [docs/V1_SPEC.md](docs/V1_SPEC.md) file layout
- [x] CLI entry: `flunk ./path [--json] [--top N] [--no-demote]` (typer — single-command app, so no `audit` subcommand prefix needed; V1_SPEC will be re-titled in Weekend 2)
- [x] `runners/semgrep.py` — subprocess wrapper, parse `--json` output into common `Finding` schema
- [x] First catalog rule: `flunk/catalog/patterns/pydantic_settings.yml`. Threshold tuned to ≥3 (not ≥5) — required to fire on `job-stalker/__main__.py` per CATALOG.md "evidence: all 3 projects" claim; rationale documented in `catalog/__init__.py`.
- [x] `demote.py` — read 3 lines above/below each finding, marker regex anchored to `#` so string literals don't trigger
- [x] `rank.py` — sort by severity desc, then category, then file
- [x] Run against all three regression projects; rule fires on each (job-stalker: 1 file × 3 occurrences; erate-filing-assistant: multiple files incl. config.py × 16; erate-prospector: multiple files incl. config.py × 41)
- [x] Hand-tune until signal-to-noise is acceptable (threshold change above; defer broader tuning to Weekend 2 when more rules expose patterns)

**Definition of done:** the CLI runs end-to-end, one rule produces real findings on three real projects, justification-demote correctly suppresses a known commented case in `job-stalker` (e.g., the `_apply_inplace_migrations` doc-block).

## Weekend 2 — populate the catalog + ship

- [x] Implement the other 14 catalog rules — 9 as Semgrep YAMLs in `catalog/patterns/`, 5 as Python detectors in `detectors/` (rules #3, #7, #8, #12, #15 don't express cleanly in pure Semgrep)
- [x] `runners/jscpd.py` for within-project structural duplication (graceful fallback when node/jscpd not installed)
- [x] `rich` table output with severity color (already shipped in Weekend 1)
- [x] `pytest` regression tests — 19 parameterized tests, one per (rule, expected-project) pair; mirror of CATALOG.md's evidence column
- [x] README quickstart + install instructions
- [x] Ship: tagged v0.1.0 commits, runs on real projects

**Definition of done for v1:** you run `flunk` on every new project you start. If you don't, the product needs the LLM layer earlier than planned.

## Notable v1 deviations from spec

- **pydantic-settings threshold:** ≥3, not ≥5. `job-stalker` has 3 occurrences in its hottest file. Documented inline in `catalog/__init__.py`.
- **Rules implemented as Python detectors (not Semgrep YAML):** #3 (pyproject vs requirements.txt), #7 (duplicate retry funcs), #8 (F811 suppression — covers both inline noqa and ruff per-file-ignores), #12 (CSRF middleware), #15 (module-level singleton in lock-aware project). These need cross-file or config-file reasoning that Semgrep doesn't model cleanly.
- **`bare-except-security`:** Semgrep matches every `except Exception:`; a path-substring filter in `catalog/__init__.py` keeps only those in security/auth/crypto/csrf/jwt/token paths.
- **`secure-headers`:** aggregated per-file with threshold 2 distinct header string mentions (one mention can be a comment or a string in an unrelated file).
- **CLI signature:** `flunk <path>` (typer collapses single-command apps); spec called for `flunk audit <path>`. Cheap to add a subcommand later if multi-mode lands.

## Signal-to-noise pass (2026-05-29)

Driven by agent feedback on a real `job-stalker` scan that was ~2-of-7-rules actionable. Four phases, all TDD'd (97 tests pass). Net effect on job-stalker: **~83 → 21 findings**, only 2 high-severity.

- **Phase 1 — file classification ([classify.py](src/flunk/classify.py)):** `is_source()` gates the AST detectors via `walk_py`; `NON_SOURCE_GLOBS` feed jscpd `--ignore`. Excludes tests/templates/fixtures/migrations. Killed the `duplicate-retry` false positive (pytest `test_retry_*` names) → it now fires on none of the 3 golden projects (each has 1 source retry fn); covered by [test_duplicate_retry.py](tests/test_duplicate_retry.py) instead. jscpd duplication on job-stalker: **68 → 10** (templates/fixtures/tests/md excluded).
- **Phase 2 — inline-import as AST detector ([detectors/inline_import.py](src/flunk/detectors/inline_import.py)):** replaces the semgrep YAML (deleted). Counts only **first-party** function-body imports (a third-party lazy load can't be a circular-import band-aid), excludes `try/except ImportError`, `TYPE_CHECKING`, and `__main__.py`. Reports all occurrence lines. job-stalker: dropped the playwright + `__main__` false positives; the 4 redundant `Job` imports now surface with all 4 line numbers.
- **Phase 3 — project profiles ([profile.py](src/flunk/profile.py)):** `--profile auto|single-user-local|web-service|unknown`. A single-user-local project (SQLite, no server-grade DB/server) down-weights `alembic`, `pydantic-settings`, `csrf-middleware`, `secure-headers` one tier, tagged `profile:single-user-local`. job-stalker inferred single-user-local → pydantic-settings high→medium, alembic medium→nitpick.
- **Phase 4 — broader justification ([demote.py](src/flunk/demote.py) + [decisions.py](src/flunk/decisions.py)):** demote pass now also reads the **module docstring** (module-level justification applies to the whole file). New `.flunkignore` file records conscious "won't do" decisions (`rule_id: reason`) — matching findings are suppressed but **kept in output** with the reason, so the choice is logged not silently skipped.

Known follow-up (spawned as a separate task): the jscpd runner's npx fallback couldn't launch on Windows (`.CMD` shim); fixed in-tree via `resolve_cmd_prefix` (`cmd /c` wrap). jscpd 4.x report-path output still worth confirming.

## Eval-driven static fixes (2026-05-29)

Driven by an external eval of a job-stalker scan ("locates well, judges poorly"):
- **async-client severity is context-aware** ([async_client_severity.py](src/flunk/detectors/async_client_severity.py)): HIGH only when the client is built inside a loop (incl. comprehensions); one-shot constructions are MEDIUM with a "pooling only helps under repeated calls" message.
- **pydantic-settings ignores presence checks** ([env_read_filter.py](src/flunk/catalog/env_read_filter.py)): `if not os.environ.get(...)` branch guards are no longer counted as config reads. job-stalker dropped from the rule's expected-fires (its 3 hits were all presence checks).
- **jscpd noise cut**: min-tokens 50 → 70 and clone pairs < 6 lines dropped (`MIN_DUP_LINES`).

Known follow-up (flagged during implementation): the jscpd runner's `NON_SOURCE_GLOBS` doesn't exclude `.venv`/`site-packages`/`node_modules`/`.worktrees`, so it scans vendored deps — a separate fix. **Fixed 2026-05-29, see below.**

## jscpd vendored-deps false positives (2026-05-29)

Symptom: a jscpd run on `job-stalker` reported **3178** duplicates, almost all from `.venv/Lib/site-packages/...` and `.worktrees/.../.venv/...` vendored third-party code (the eval expected ~10).

Diagnosis was empirical, not assumed. Two changes, both TDD'd:
- **Real root cause — relative scan path defeated jscpd's exclusion** ([runners/jscpd.py](src/flunk/runners/jscpd.py)): jscpd only excludes vendored/build dirs (`.venv`, `.worktrees`, `node_modules`, ...) when handed an **absolute** path. The runner passed `project.as_posix()` (e.g. `../job-stalker`), and the `..` prefix silently disabled that exclusion — so jscpd walked the whole vendored tree. Measured directly: absolute path → 29 raw clone pairs, relative `../` path → 3178, *with `--ignore` having zero effect in either mode*. Fix: `project.resolve().as_posix()`. job-stalker findings: **3178 → 6** (29 raw pairs, `MIN_DUP_LINES` filters to 6).
- **Defense-in-depth — vendor globs in `NON_SOURCE_GLOBS`** ([classify.py](src/flunk/classify.py)): added `**/<dir>/**` for each of a new shared `VENDOR_DIRS` frozenset (`.venv`, `venv`, `node_modules`, `site-packages`, `.worktrees`, `build`, `dist`, `__pycache__`, `.tox`, `.git`). `detectors/_walk.py`'s `SKIP_DIRS` now derives from `VENDOR_DIRS` (+ `.claude`) so the AST-walk and jscpd scan paths can't drift. Note: these globs don't actually fire today (jscpd's `--ignore` was inert in the measurements above) — they're documented intent plus protection for any vendored dir that isn't git-ignored.

## v1.5+ backlog (do not start before v1 ships)

- **Pre-flight mode** — hook into Claude Code / Cursor planning output, flag the cut-corner before code is written. Highest-value v2 feature per the codebase-maturity insight in [docs/PRODUCT.md](docs/PRODUCT.md).
- **LLM judgment layer** — send HYBRID-category findings to Claude for a "is this actually a smell?" pass. Add only once the catalog has demonstrated trust.
- **Cross-project mode** — ingest a portfolio of repos, surface deduplication candidates. The user already has 2 confirmed cases of cross-project porting (`usac_data` lib, `erate-assistant` sibling) — pain is real.
- **Spec-conformance** — diff shipped code against a planning document, flag drift. Not validated in the audit experiment; do that audit pass first.
- **Visual map** — spatial UI for navigating findings. Original product framing, deprioritized after findings became the value. Revisit only if findings prove they need spatial context.
- **Languages** — TypeScript/JavaScript second, Go third.

## Risky assumption to validate post-weekend 2

That a `semgrep + curated catalog + demote pass` achieves high enough signal-to-noise to be trusted by a senior engineer running it daily. The 3-project audit said yes (~87% PATTERN+HYBRID); the proof is whether you keep running it without losing trust after a month of real use.

## Provenance

This project's product thinking, name, scope, and catalog seed were developed in a brainstorming session on 2026-05-26. The audit experiment that validated the hypothesis ran against `job-stalker`, `erate-filing-assistant`, and `erate-prospector` — all three are sibling projects.

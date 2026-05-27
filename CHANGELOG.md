# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-26

Initial release. Single-command CLI that audits a Python project for AI
cut-corner patterns. Wraps `semgrep` and `jscpd`, layers a curated catalog
of 15 OSS-replacement rules, demotes findings near justification comments,
ranks by severity, prints a `rich` table.

### Added

- `flunk <path>` CLI with `--json`, `--top`, `--no-demote` flags.
- **15 curated OSS-replacement rules** (see `docs/CATALOG.md`):
  - Pydantic-settings, tenacity, alembic, parameterized queries,
    hoist-the-httpx-client, dedupe retry funcs, fix F811 instead of
    suppressing, narrow security-path excepts, restructure circular
    imports, `secure` library for headers, `starlette-csrf` /
    `fastapi-csrf-protect` for CSRF, `humanize` for relative dates,
    SQLAlchemy/aiosqlite for sqlite3 threading, lock the module-level
    singleton, consolidate to `pyproject.toml` + `uv pip compile`.
- **9 rules as Semgrep YAMLs** in `src/flunk/catalog/patterns/`.
- **5 rules as Python detectors** in `src/flunk/detectors/` (where
  cross-file or config-file reasoning is required).
- **jscpd runner** for general within-project structural duplication,
  with a graceful fallback when `node` / `jscpd` aren't installed.
- **Justification-aware demote pass** — every finding's locality (3
  lines above + below) is checked for marker phrases (`# deliberately`,
  `# intentionally`, `# we chose`, `# fall back`, `# rather than`,
  `# tradeoff`, `# justified`, `# on purpose`). Hits demote one tier
  (high → medium → nitpick → suppressed). Markers are `#`-anchored so
  string literals don't false-trigger. Disable with `--no-demote`.
- **Severity tiering** and ranking — severity desc, then category
  (`oss-catalog` > `duplication` > `anti-pattern`), then file path.
- **27 tests** — 5 demote unit, 3 rank unit, 19 parameterized catalog
  regressions (every rule × every project it's expected to fire on per
  CATALOG.md's evidence column).

### Notes on the catalog

- `pydantic-settings` threshold is `≥3` env-access calls per file, not
  `≥5` as the original V1 spec called for. `job-stalker`'s hottest file
  has 3 occurrences; the original threshold would have silently dropped
  CATALOG.md's "fires on all three projects" guarantee. Rationale lives
  inline in `src/flunk/catalog/__init__.py`.
- `inline-import` is aggregated per-file at threshold 3 with
  `TYPE_CHECKING` and `try/except ImportError` exclusions. Tuned down
  from a 437-hit explosion on a real project to a few dozen actionable
  per-file findings, without losing CATALOG.md-required fires on
  `job-stalker` and `erate-filing-assistant`.
- `secure-headers` is aggregated per-file at threshold 2 distinct
  header-string mentions (defends against a single Referrer-Policy
  reference in an unrelated file).
- `bare-except-security` is filtered by path substring
  (`security|auth|crypto|csrf|jwt|token`) — a bare except in
  `services/cleanup.py` isn't the smell; one in `auth/jwt.py` is.

[unreleased]: https://github.com/sgentzen/flunk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sgentzen/flunk/releases/tag/v0.1.0

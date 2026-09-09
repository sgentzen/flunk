# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-09

### Added

- The justification-demote pass now reads the **enclosing function or class
  docstring**, not just nearby `#` comments and the module docstring. A
  rationale written on a helper -- "We deliberately read env directly rather
  than going through settings" -- now demotes findings inside that scope.
  Innermost scope wins, falling back to the module docstring; decorator lines
  count as part of the scope ([#8]).
- `tests/test_cli_entrypoint.py` covers the `flunk` console script end to end:
  that it is declared, that its target loads and is callable, and that the
  installed executable actually launches. Previously nothing exercised the
  `[project.scripts]` wiring, so a broken entry point could ship undetected
  ([#13]).

### Fixed

- `flunk` no longer reports a false `duplicate-code` style clone between
  `agent.py` and `judge.py`. The byte-for-byte duplicated `_rel()` helper was
  extracted to `findings.display_path`, taking `src/flunk` to zero jscpd
  clones ([#11]).

### Changed

- **CI installs dependencies wheels-only.** The `uv sync` step is split in two:
  third-party dependencies install under `--no-build`, so no dependency's build
  backend executes during a CI run, followed by a plain sync for flunk's own
  editable install (which has no wheel and must be built). Note this is
  defence-in-depth rather than containment -- CI then runs `pytest`, which
  imports those packages, so `--no-build` narrows the window from install-time
  to import-time ([#13]).
- **CI fails on a stale lockfile.** `uv sync` now passes `--locked`, so a
  `pyproject.toml` change without a regenerated `uv.lock` breaks the build
  instead of silently installing the previous dependency set ([#13]).
- Cleared all outstanding SonarCloud issues; the quality gate is green
  ([#10], [#13]).

## [0.1.1] — 2026-06-19

### Fixed

- Detectors no longer flag flunk's own source. Running `flunk` on flunk
  reported two false positives — a HIGH-severity `f811-suppression` on a
  documentation comment that *quotes* `# noqa: F811`, and a `csrf-middleware`
  hit on the detector's own regex-pattern strings and a `csrf-token` comment.
  Both detectors now match the **code layer** via a new tokenize-aware helper
  (`detectors/_source.py`): the F811 rule anchors to real comment directives,
  and the CSRF rule strips comments while keeping string literals (a header or
  cookie name like `"X-CSRF-Token"` is a real signal). The F811 per-file-ignore
  config path is unchanged ([#7]).

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

[unreleased]: https://github.com/sgentzen/flunk/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/sgentzen/flunk/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/sgentzen/flunk/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/sgentzen/flunk/releases/tag/v0.1.0
[#7]: https://github.com/sgentzen/flunk/pull/7
[#8]: https://github.com/sgentzen/flunk/pull/8
[#10]: https://github.com/sgentzen/flunk/pull/10
[#11]: https://github.com/sgentzen/flunk/pull/11
[#13]: https://github.com/sgentzen/flunk/pull/13

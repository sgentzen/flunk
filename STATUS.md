# Status

**Current phase:** Weekend 1 complete (2026-05-26). Core loop ships: `flunk` CLI runs end-to-end with the `pydantic-settings` rule, justification-demote, and ranked rich/JSON output. Verified against all three regression projects; 11 unit + integration tests pass.

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

- [ ] Implement the other 14 catalog rules (see [docs/CATALOG.md](docs/CATALOG.md))
- [ ] Add `runners/jscpd.py` for within-project structural duplication
- [ ] `rich` table output with severity color
- [ ] `pytest` regression tests using the three projects as fixtures (path-based, not vendored)
- [ ] README quickstart + install instructions
- [ ] Ship as a private CLI you actually run

**Definition of done for v1:** you run `flunk` on every new project you start. If you don't, the product needs the LLM layer earlier than planned.

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

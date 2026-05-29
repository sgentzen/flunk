# flunk — AI Assistant Guide

## What this is

A static-analysis CLI that audits Python projects for AI cut-corners. Wraps `semgrep` and `jscpd`, layers a curated catalog of "reinvented wheel" patterns on top, demotes findings near justification comments, ranks by severity, prints a `rich` table.

## Tech stack

- Python 3.12+
- `semgrep` (wrapped via subprocess, `--json` output)
- `jscpd` (wrapped via subprocess, `--reporters json`)
- `typer` for CLI
- `rich` for output

No web framework, no DB, no async. This is a CLI tool — keep it simple.

## Where to find what

- [docs/PRODUCT.md](docs/PRODUCT.md) — why this exists and who it's for
- [docs/V1_SPEC.md](docs/V1_SPEC.md) — what to build for v1
- [docs/CATALOG.md](docs/CATALOG.md) — the 15 seed rules, with per-project evidence
- [STATUS.md](STATUS.md) — current phase + checklisted next steps

## Conventions

- Catalog rules live in `flunk/catalog/patterns/*.yml` (Semgrep YAMLs)
- Each rule's `message` names the OSS library that does it better
- Rule metadata (severity, replacement library, why) lives in `flunk/catalog/metadata.py`
- Every catalog rule must include a `# Expected fires:` comment listing which regression projects it should match — used by tests to detect regressions
- No new top-level dependencies without checking they're justified — we're the BS detector; don't be the BS
- The opt-in `--judge` LLM pass lives in `src/flunk/judge.py` (client-agnostic core: per-file batching, severity re-rating, code-specific rationale) + `src/flunk/judge_anthropic.py` (the Anthropic-backed client, behind the `flunk[judge]` optional extra). Security rules in `metadata.SECURITY_RULES` can be escalated but never downgraded or skipped by the judge.

## Regression suite

Three real-world Python projects validated the v1 hypothesis (see PRODUCT.md). Use them as the golden test set:

- `../job-stalker` — actively developed, well-justified codebase (most JUDGMENT-heavy)
- `../erate-filing-assistant` — v1.0 shipped, less defensive justification (94% PATTERN+HYBRID)
- `../erate-prospector` — production, mature, most refactored

Catalog rules should light up on these projects in the ways predicted by CATALOG.md. The demote pass should correctly suppress findings where the author has justified the choice with a comment.

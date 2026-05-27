# flunk

A BS detector for AI-built Python code.

Single-command CLI that audits a Python project for the patterns where AI took shortcuts: reinvented OSS libraries, hand-rolled retry logic, structurally duplicated code, inline circular-import workarounds, and the other tells that show up when an agent is graded by tests-pass rather than by an experienced reviewer.

```bash
flunk ./path/to/project
```

## Install

```bash
# 1. flunk itself
uv tool install flunk          # or: pipx install flunk

# 2. semgrep (required — flunk wraps it)
uv tool install semgrep        # or: pipx install semgrep

# 3. jscpd (optional — adds within-project duplication detection)
npm install -g jscpd           # or rely on flunk's `npx --yes jscpd` fallback
```

Python 3.12+. Works on Windows, macOS, Linux. (On Windows, `semgrep` runs natively via OSS engine.)

## Usage

```bash
flunk ./my-project                    # default: rich table, top 25 findings
flunk ./my-project --top 100          # show more
flunk ./my-project --json             # machine-readable
flunk ./my-project --no-demote        # show everything, even justified findings
```

Exit code is always `0` when the audit completes — flunk is a report, not a gate. Wire it into your own CI with `--json` and a script that decides what to fail on.

## What it catches

15 curated OSS-replacement rules, each backed by evidence from real-world Python projects. Full list in [docs/CATALOG.md](docs/CATALOG.md). Highlights:

| Trigger | Replacement |
|---|---|
| ≥3 `os.environ.get` calls in one file | `pydantic-settings` |
| Hand-rolled `for attempt in range(...)` retry with sleep | `tenacity` |
| f-string interpolation into `.execute()` | parameterized queries |
| `httpx.AsyncClient(...)` inside a function body | module-level / lifespan singleton |
| Hand-rolled `_apply_migrations()` running raw `ALTER TABLE` | `alembic` |
| `"X days ago"` formatter | `humanize` |
| `# noqa: F811` or per-file F811 ignore | delete the duplicate def |
| `sqlite3.connect(..., check_same_thread=False)` | SQLAlchemy / aiosqlite |
| Custom CSRF middleware | `starlette-csrf` / `fastapi-csrf-protect` |
| Custom X-Frame-Options / CSP / Referrer-Policy middleware | `secure` library |
| Module-level mutable singleton without a lock | add a lock or accept inconsistency |

Plus general structural duplication via jscpd, and an anti-pattern bucket for bare `except Exception:` in security/auth/crypto paths, inline imports inside function bodies, and module-level mutable singletons.

## How it avoids being noisy

**Justification-aware demote pass.** Every finding's locality (3 lines above + below) is checked for marker phrases like `# deliberately`, `# intentionally`, `# we chose`, `# fall back`, `# rather than`, `# tradeoff`, `# justified`, `# on purpose`. Hits get demoted one severity tier (high → medium → nitpick → suppressed). Markers are anchored to `#` so string literals don't false-trigger.

Disable with `--no-demote` when you want the raw view.

**Severity tiering.** `high` = worth your attention now. `medium` = look at it before shipping. `nitpick` = noise floor, easy wins. Findings are sorted severity-desc, then by category (oss-catalog > duplication > anti-pattern), then by file path.

## Output

Rich table by default:

```
                   flunk findings (62 total, showing top 25)
+--------+-------------+----------------------------+----------------+---------------+
| sev    | category    | file:line                  | message        | replacement   |
+--------+-------------+----------------------------+----------------+---------------+
| high   | oss-catalog | backend/config.py:9        | File hand-...  | pydantic-set… |
| high   | oss-catalog | backend/clients/sf.py:42   | httpx client…  | module-level… |
| medium | oss-catalog | backend/middleware.py:18   | Custom CSRF…   | starlette-cs… |
| ...
```

`--json` for piping:

```json
[
  {
    "rule_id": "flunk.pydantic-settings",
    "category": "oss-catalog",
    "severity": "high",
    "file": "...\\backend\\config.py",
    "line": 9,
    "message": "...",
    "replacement": "pydantic-settings",
    "replacement_url": "https://docs.pydantic.dev/latest/concepts/pydantic_settings/",
    "raw_severity": null,
    "demoted_by": null
  }
]
```

## Status

v1 ships with 15 rules + jscpd + justification-aware demote. See [STATUS.md](STATUS.md) for current phase and [docs/PRODUCT.md](docs/PRODUCT.md) for the product thesis.

## Docs

- [docs/PRODUCT.md](docs/PRODUCT.md) — problem, audience, validated hypothesis
- [docs/V1_SPEC.md](docs/V1_SPEC.md) — what ships first
- [docs/CATALOG.md](docs/CATALOG.md) — 15 seed rules with per-project evidence
- [STATUS.md](STATUS.md) — current phase + weekend-scoped next steps

## Why "flunk"

Names the verdict. The tool grades AI-generated code against patterns a senior engineer would catch in review — if your code flunks, it's because the AI cut a corner you wouldn't have.

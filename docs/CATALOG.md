# v1 OSS-pattern catalog

15 seed entries. Each is evidence-backed — verified against at least one of the three regression projects (`job-stalker`, `erate-filing-assistant`, `erate-prospector`) during the 2026-05-26 audit experiment.

The human-readable rule descriptions are below. The actual Semgrep YAML lives in `flunk/catalog/patterns/`; metadata (severity, replacement library, doc URL) lives in `flunk/catalog/metadata.py`.

| # | Trigger | Replacement | Severity | Evidence |
|---|---|---|---|---|
| 1 | `os.environ.get` ≥3× in one file (presence-check branches excluded) with manual `int()` / `float()` / `.lower() == "true"` coercion | `pydantic-settings` | high | `erate-filing-assistant`, `erate-prospector` (job-stalker excluded 2026-05-29 — its os.environ hits are presence-check branches, not config reads (see env_read_filter)) |
| 2 | Hand-rolled retry: `for attempt in range(...); ... sleep(2**...)` or equivalent exponential backoff loop | `tenacity` | high | `erate-filing-assistant` |
| 3 | `pyproject.toml` exists with no `[project.dependencies]` while `requirements.txt` / `.in` declares deps | Consolidate to pyproject + `uv pip compile` lockfile | medium | `erate-filing-assistant`, `erate-prospector` |
| 4 | `_apply_inplace_migrations()` or `ALTER TABLE` runner pattern w/o a migration tool | `Alembic` | medium | `job-stalker` |
| 5 | `f"... where='{user_input}' ..."` interpolation into anything passed to `.params` / `.execute` / HTTP `params` | Parameterize the query | high | `erate-filing-assistant` (SoQL) |
| 6 | `httpx.AsyncClient(...)` instantiated inside a function body (not class field or module-level) | Reuse the client | high | `erate-filing-assistant` |
| 7 | Two `*retry*` function definitions in the same project with structurally similar shape | Extract shared retry / use tenacity | high | none of the 3 (prior `erate-filing-assistant` evidence was a false positive — pytest `test_retry_*` names, now excluded by source filtering; covered by `tests/test_duplicate_retry.py`) |
| 8 | Function defs suppressed by per-file `F811` ruff ignore | Remove duplicate, don't suppress | high | `erate-prospector` |
| 9 | Bare `except Exception:` in security/auth/crypto paths | Catch specifically | medium | `erate-filing-assistant` |
| 10 | ≥3 inline imports of **first-party** modules inside function bodies in one file (circular-import band-aid). Third-party/stdlib lazy loads, `try/except ImportError` guards, `TYPE_CHECKING` blocks, and `__main__.py` entrypoints are excluded. AST detector, not Semgrep. | Restructure the cycle | nitpick | `job-stalker`, `erate-filing-assistant` |
| 11 | Custom middleware setting `X-Frame-Options` + `CSP` + `Referrer-Policy` | `secure` library | nitpick | `erate-filing-assistant` |
| 12 | Custom CSRF token validate/issue middleware | `starlette-csrf` / `fastapi-csrf-protect` | medium | `erate-filing-assistant` |
| 13 | Hand-rolled "X ago" / "Xd ago" date formatter | `humanize` | nitpick | `job-stalker` |
| 14 | Raw `sqlite3.connect(..., check_same_thread=False)` in a web app | SQLAlchemy or aiosqlite | medium | `erate-filing-assistant` |
| 15 | Module-level mutable singleton (e.g. `_client: X \| None = None`) without a lock, sitting in a project where another file uses a lock pattern | Add lock or accept inconsistency | nitpick | `erate-prospector` |

## Justification-demote markers

The demote pass downgrades severity one tier when any of these phrases appears (case-insensitive, regex) either **within 3 lines of a finding as a `#` comment**, or **anywhere in the module docstring** (a module-level justification applies to the whole file):

- `deliberately`
- `intentionally`
- `we chose`
- `fall back`
- `rather than`
- `tradeoff`
- `justified`
- `on purpose`

In comments these are anchored to `#` so a string literal like `"we deliberately fail"` doesn't match; in the module docstring they match unanchored (the docstring is itself a deliberate statement of intent).

The starter list comes directly from comment phrases observed in `job-stalker`'s justified findings during the audit.

## Project profiles

flunk infers the project's deployment shape (`--profile auto`, the default) and down-weights infra-oriented rules one tier when it doesn't fit:

- **single-user-local** (uses SQLite, no production server / server-DB driver): down-weights `alembic`, `pydantic-settings`, `csrf-middleware`, `secure-headers` — these are defensible trade-offs for a local single-user tool, not cut corners. The down-weight is tagged `profile:single-user-local` so it's visible, not silent.
- **web-service** (gunicorn/uwsgi/etc. or a server-grade DB driver like psycopg/asyncpg): no change — the production answer is the right one.
- **unknown**: no change (uncertainty never silently suppresses).

Override inference with `--profile single-user-local|web-service|unknown`.

## `.flunkignore` decisions

A project can record conscious "won't do" decisions in a `.flunkignore` file at its root, one per line as `rule_id: reason` (reason optional). Matching findings are **suppressed but kept in the output** with the reason attached — the decision is logged, not silently skipped:

```
# we audited these and decided they don't apply here
flunk.alembic: single-user local app, additive migrations are deliberate
flunk.pydantic-settings: presence check only; the key is consumed by the SDK
```

## Rule authoring rules

- Each rule's Semgrep `message` field should: (a) name the smell in one phrase, (b) name the OSS replacement, (c) include a link to the relevant doc when stable.
- Severity scale: `nitpick` < `medium` < `high`. Demote moves one tier down (high → medium → nitpick → suppressed).
- Every rule must include a `# Expected fires:` comment listing which regression projects it should match. The test suite uses this to detect regressions when rules are edited.
- Prefer Semgrep's *structural* patterns over text regex. Catalog entries are about code shape, not string matching.

## Catalog growth principles

The catalog is the IP. Bad entries kill the product faster than missing entries — every false positive trains the user to ignore flunk's output. So:

- **No speculation.** Every entry must have evidence from a real codebase (yours or someone else's, but real). Don't add `tortoise-orm` as a replacement for hand-rolled ORM patterns until you've seen the hand-rolled-ORM pattern in the wild.
- **Demote-test before merging.** Every entry must pass through the demote logic on a known justified case. If demote can't rescue the justified version, the rule needs refinement.
- **Severity is sticky.** Once an entry ships at `high`, don't downgrade casually — `high` is a promise to the user that this finding is worth their attention. If the entry keeps producing low-value hits, fix the pattern; don't lower the severity.

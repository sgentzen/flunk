# v1 CLI spec

## Command

```bash
flunk audit ./path/to/project [--json] [--top N] [--no-demote]
```

## Pipeline (executed in order)

### 1. Wrappers (table stakes)

Run `semgrep --config=auto --json --quiet ./project` and `jscpd --reporters json --silent ./project`. Parse both into a common `Finding` schema. ~5 days of work; not novel, but covers commodity static analysis so v1 feels comprehensive on day one without us writing 5 years of linter rules.

### 2. OSS-catalog layer (the differentiator)

Ship a `flunk/catalog/patterns/` directory of custom Semgrep YAMLs. Each rule looks for the *shape* of a reinvented wheel; metadata names the library that does it better. v1 catalog: 15 entries — see [CATALOG.md](CATALOG.md).

### 3. Justification-aware demote pass

For every finding, read 3 lines above and 3 lines below in the source file. If the locality contains any of (case-insensitive) — `# deliberately`, `# intentionally`, `# we chose`, `# fall back`, `# rather than`, `# tradeoff`, `# justified`, `# on purpose` — demote severity one tier.

`--no-demote` disables this (review-mode pass: "show me everything the rules caught, including stuff I justified").

### 4. Ranking + render

Sort findings: severity desc, then category (OSS-catalog > duplication > anti-pattern), then file path. Default top 25 to stdout via `rich` table. `--json` emits the full list as JSON to stdout.

## Output format

Default `rich` table columns:

- severity (color-coded: red = high, yellow = medium, dim = nitpick)
- category
- file:line
- one-line message
- suggested replacement (when from OSS-catalog)

`--json`: array of finding objects, all fields.

## File layout

```
src/flunk/             # uv init --package layout
  __init__.py          # wires `main()` → typer app
  cli.py               # typer entry, defines `audit` command
  findings.py          # shared Finding dataclass
  runners/
    __init__.py
    semgrep.py         # subprocess wrapper, JSON parser
    jscpd.py           # subprocess wrapper, JSON parser
  catalog/
    __init__.py
    patterns/          # Semgrep YAMLs — the IP
      pydantic_settings.yml
      tenacity.yml
      ... (15 total — see CATALOG.md)
    metadata.py        # rule_id → {library, why, severity, replacement_url}
  demote.py            # justification-aware demote pass
  rank.py              # ranking + render
pyproject.toml         # `flunk = "flunk:main"` script entry
README.md
CLAUDE.md
STATUS.md
docs/
  PRODUCT.md
  V1_SPEC.md
  CATALOG.md
tests/
  conftest.py          # exposes paths to regression projects
  fixtures/
  test_demote.py
  test_rank.py
  test_catalog.py      # parameterized over the three regression projects
```

## Finding schema

```python
@dataclass(frozen=True)
class Finding:
    rule_id: str                      # e.g., "flunk.pydantic-settings"
    category: str                     # "oss-catalog" | "duplication" | "anti-pattern"
    severity: str                     # "high" | "medium" | "nitpick"
    file: Path
    line: int
    message: str                      # one-line description
    replacement: str | None = None    # library/approach suggestion
    replacement_url: str | None = None
    raw_severity: str | None = None   # pre-demote severity, if demoted
    demoted_by: str | None = None     # marker that triggered demote, if any
```

## Explicitly out of v1

- **Cross-project detection.** The within-project version covers the immediate pain. v2.
- **LLM judgment layer.** Icing for the long tail of HYBRID and JUDGMENT findings. Add only once the catalog has earned trust.
- **Visual map.** Findings became the value, not the map. Revisit only if findings prove they need spatial context.
- **Pre-flight planning hook.** Compelling per the codebase-maturity insight, but requires integration with Claude Code / Cursor planning output. v2.
- **Spec-conformance.** We didn't run that audit pass. v2.
- **Non-Python languages.** Python only. Add TypeScript second, Go third.

## The risky bet

The entire product hinges on the catalog being curated well. 15 entries that nail real pain → users adopt. 15 entries with false positives → uninstall in a week.

**Mitigation:** every catalog rule must be tested against all three regression projects before merge. False-positive rate on those projects is the gating metric. If a rule fires somewhere it shouldn't, either the pattern is wrong or it needs a justification-demote rescue — fix the rule, don't ship it.

## What ships first (Weekend 1)

A single working rule: `pydantic_settings.yml`. It must:

- Detect ≥5 `os.environ.get(...)` calls in a single file
- Fire on `config.py` in all three regression projects
- Get correctly demoted on at least one false-positive locality
- Print a useful `rich` table

If that works, the rest of the catalog is mechanical. If it doesn't, the architecture is wrong and we re-spec before continuing.

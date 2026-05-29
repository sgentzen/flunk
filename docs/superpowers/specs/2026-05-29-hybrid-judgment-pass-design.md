# flunk — Hybrid Judgment Pass (design)

**Date:** 2026-05-29
**Status:** approved (design); pending implementation plan
**Driver:** External eval of a real `job-stalker` scan. Verdict: *flunk locates patterns well but judges context poorly.* Severities don't track real impact (HIGH on one-shot single-host httpx calls), one rule is misdiagnosed (pydantic-settings fired on a branch, not a config read), and the "Why it's worse" blurbs read as generic per-rule templates rather than reasoning about the specific code.

## Problem

The eval's three failures have **different root causes** in the current architecture:

| Eval complaint | Root cause |
|---|---|
| "Why it's worse" blurbs are generic templates | `RuleMeta.rationale` — one static string per rule, pasted verbatim into every finding |
| async-client rated HIGH but marginal here | severity is hardcoded per-rule; only `INFRA_RULES` get a context adjustment (profile pass), and async-client isn't one |
| pydantic-settings misdiagnosed (a branch, not a config read) | the Semgrep pattern can't distinguish a presence-check branch from a config read |
| duplication is noise (10 unrelated functions) | jscpd token-CPD at `min_tokens=50` matches generic boilerplate |

The deepest complaint — generic rationale — **cannot be fixed statically**; a static tool can only pick a better canned blurb, never write "this is a one-shot HEAD to a redirector, so pooling buys nothing." Severity-correctness and duplication noise **can** be improved statically.

This matches the project's own backlog: an **LLM judgment layer** was always planned, gated on *"add only once the catalog has demonstrated trust."* This eval is that trust test — and it confirms the gate is met for *locating* (trustworthy) while *judging* is the gap.

## Approach: hybrid

Keep flunk static, offline, and deterministic **by default**. Add deterministic static fixes to the default path, plus an **opt-in `--judge` LLM pass** that supplies the code-specific judgment a static tool structurally cannot.

## Architecture

Current pipeline:

```
locate (semgrep / jscpd / detectors) → demote → profile → rank → render (table / json / agent)
```

New:

```
locate → demote → profile → [--judge: LLM pass] → rank → render
```

The judge slots in **after profile, before rank**:
- It only sees findings that survived demote/profile (no call wasted on something `.flunkignore` already killed).
- Re-rank runs *after* the judge, so its severity edits reorder output.
- It is pure enrichment over the existing `Finding` fields (`severity`, `rationale`/message, plus a new `skip` verdict) — everything downstream already keys off those.

## Component: LLM judge (`src/flunk/judge.py`)

- **Trigger:** `flunk <path> --judge`. Off by default; the static pipeline is unchanged when absent.
- **Dependency:** `anthropic` SDK as an **optional extra** (`pip install flunk[judge]`). Core install stays dependency-free. `--judge` without the extra installed → clean error naming the extra.
- **API key:** read `ANTHROPIC_API_KEY` from env (single presence read — not a config subsystem; does not warrant pydantic-settings).
- **Input per finding:** `rule_id`, the catalog's generic `rationale` (passed as a *prior*, not gospel), and a code excerpt with surrounding context (reuse `agent._excerpt_block`, widened window).
- **Batching:** group findings **by file**; one structured-output call per file so the model sees each file's context once and can reason across sites (e.g. "one-shot vs. in a loop"). Bounded concurrency across files.
- **Output (structured tool-use schema), per finding:**
  - `severity`: `high | medium | nitpick | skip`
  - `rationale`: code-specific, 1–2 sentences
  - `worth_doing`: bool
- **Determinism marker:** judged findings carry `judged: true` so judged output is never mistaken for a static run.

### Guardrail (because the judge runs on *all* findings)

The judge runs on every non-suppressed finding, including security/correctness rules. To stop a confident-but-wrong LLM from burying a real vulnerability:

- For **security-category anti-pattern rules** (`sql-injection`, `csrf-middleware`, `f811-suppression`, `bare-except-security`): the judge may **raise** severity or rewrite rationale, but **cannot downgrade** below the catalog severity and **cannot set `skip`**.
- For **oss-catalog and duplication rules**: full authority, including `skip`.

This needs a small classification of which rules are "security/correctness" vs. "judgment-prone" — derivable from `category` plus an explicit set, lives next to `metadata.py`.

## Static wins (ship regardless of `--judge`)

Deterministic fixes to the eval's misses, in the default path:

1. **async-client severity → context-aware.** In the async-client detector, only HIGH when the `httpx.AsyncClient(...)` construction is inside a loop, or the enclosing function is invoked in a loop / `asyncio.gather`; otherwise MEDIUM with a "one-shot — pooling buys little" framing. Fixes the four single-host one-shots rated HIGH.
2. **Kill duplication noise.** Raise jscpd `--min-tokens` (50 → ~70) and post-filter clone pairs whose two sites are different top-level def/function names *and* under N lines — the shape that produced the 10 unrelated-function false positives. Genuine cross-file copies (the greenhouse httpx echo) survive.
3. **Narrow pydantic-settings.** Exclude `os.environ.get(...)` used directly as a boolean/branch condition (`if not os.environ.get(...)`) — a presence check, not a config read propagating `None`. Fixes the `__main__.py` false positive.

## Output / UX

- A `skip` verdict renders in a distinct **"Judged not worth doing"** group (table + agent plan), showing the judge's reason — kept in output, never silently dropped (mirrors `.flunkignore`).
- The agent fix-plan (`agent.py`) prefers the judged rationale when present, else the catalog rationale.

## Configuration

- `--judge` — enable the LLM pass (default off).
- `--judge-model` — default `claude-sonnet-4-6` (judgment nuance is the point; Haiku risks reproducing the "generic" problem). Override allowed.

## Testing

- **Static fixes — TDD against the golden projects** (the eval *is* `job-stalker`, so these are directly checkable):
  - async-client drops to MEDIUM on the four sites.
  - duplication on `job-stalker` drops the 9 noise pairs, keeps the legitimate one.
  - pydantic-settings stops firing on `__main__.py`.
  - Existing catalog-regression tests stay green.
- **Judge — stubbed/recorded LLM client, no live API in CI:**
  - prompt assembly (correct excerpt + prior),
  - security-downgrade guardrail (security rule cannot be downgraded or skipped),
  - skip-grouping in render,
  - structured-output schema parsing + malformed-response handling.

## Out of scope

- Pre-flight (planning-time) detection — still v2.
- Cross-project dedup, spec-conformance, non-Python languages.
- Caching/persisting judge results across runs (possible later optimization).

## Risks

- **Non-determinism:** judged runs vary. Mitigated by keeping `--judge` opt-in, marking judged findings, and keeping the static path as the trustworthy default.
- **Cost / latency:** one call per file. Bounded concurrency; Sonnet default is a deliberate quality-over-cost choice the user can override.
- **LLM over-trust on security:** mitigated by the no-downgrade guardrail above.

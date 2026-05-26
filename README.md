# flunk

A BS detector for AI-built Python code.

Single-command CLI that audits a Python project for the patterns where AI took shortcuts: reinvented OSS libraries, hand-rolled retry logic, structurally duplicated code, inline circular-import workarounds, and the other tells that show up when an agent is graded by tests-pass rather than by an experienced reviewer.

```bash
flunk audit ./path/to/project
```

## Status

Pre-v1. Product validated through a 3-project audit experiment (see [docs/PRODUCT.md](docs/PRODUCT.md)). Build sequence is in [STATUS.md](STATUS.md).

## Docs

- [docs/PRODUCT.md](docs/PRODUCT.md) — problem, audience, validated hypothesis
- [docs/V1_SPEC.md](docs/V1_SPEC.md) — what ships first
- [docs/CATALOG.md](docs/CATALOG.md) — the 15 seed OSS-pattern rules with per-project evidence
- [STATUS.md](STATUS.md) — current phase + weekend-scoped next steps

## Why "flunk"

Names the verdict. The tool grades AI-generated code against patterns a senior engineer would catch in review — if your code flunks, it's because the AI cut a corner you wouldn't have.

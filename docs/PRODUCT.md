# Product thinking

## The problem

When you direct AI agents to build software (Claude Code, Cursor, Lovable, Replit Agent, etc.), the AI's primary success criterion is "tests pass + dev deploys cleanly." That criterion is insufficient. Common failure modes:

1. **Reinvented wheels.** AI hand-rolls retry logic, auth, validation, config parsing, age formatters — even when a well-known library exists. Tests pass because the wheel works; the cut corner is invisible until you read the code.
2. **Within-project duplication.** AI writes the same pattern twice in different forms — two retry implementations in `services/`, two ways to load YAML, two "humanize this date" functions.
3. **Anti-patterns survive.** Bare `except Exception:` in security paths, raw `sqlite3` with `check_same_thread=False` in a web app, f-string interpolation into query strings.
4. **Refactoring debt accumulates silently.** Inline circular-import workarounds, lint suppressions hiding duplicate functions, 1100-line god-config files.

A senior engineer would catch these in code review. AI agents don't catch them, and you can't review every line yourself when the AI is producing them at volume.

## The user

A senior engineer who directs AI agents to build software. Distrusts the agents. Has high standards because they "do this stuff without AI for a living." Manages multiple projects. Wants a tool that catches what they'd catch — without them reading every diff line by line.

**Not the buyer:** AI-skeptical engineers who already review every line manually (don't need it). Vibe-coders who don't care about cut-corners (wouldn't run it). Enterprise procurement (this isn't a SonarQube replacement).

## The product

A single-command CLI that audits a Python project for the patterns above. Wraps existing static-analysis tools (semgrep, jscpd) for commodity coverage; differentiates via a curated catalog of "reinvented wheel" patterns and a justification-aware demote pass that respects comments where the author has deliberately chosen the smell.

## Why "BS detector" is the right framing

This is not a comprehensive linter. It's not a security scanner. It's not a code-review tool. It's specifically a *trust verification* tool for AI-generated code — designed to catch when the AI took a shortcut and bluffed past test coverage.

## Validation: the 3-project audit experiment

**Hypothesis:** most "AI cut corners" findings in real Python codebases are pattern-detectable. If so, `semgrep + curated catalog` is sufficient for v1. If not, v1 needs an LLM-driven judgment layer from day one.

**Methodology:** hand-audit 3 real Python projects, categorize each finding as:

- **PATTERN** — a static rule with no taste could catch this
- **HYBRID** — a rule narrows the search, but human/LLM must confirm
- **JUDGMENT** — requires architectural taste no rule can capture
- **SPEC** — requires comparing against a planning document

**Decision rule:** if PATTERN + HYBRID ≥ 60%, build the static-analysis detector. If JUDGMENT ≥ 60%, build the LLM-driven detector. If SPEC ≥ 30%, pull spec-conformance forward to v1.

**Results:**

| Project | Maturity | PATTERN | HYBRID | JUDGMENT | P+H |
|---|---|---|---|---|---|
| job-stalker | actively developed | 40% | 47% | 13% | **87%** |
| erate-filing-assistant | v1.0 shipped | 56% | 39% | 5% | **94%** |
| erate-prospector | production, bi-weekly cadence | 43% | 36% | 21% | **79%** |
| **Average** | | **46%** | **41%** | **13%** | **87%** |

**Verdict:** ~87% PATTERN+HYBRID average across three data points, well over the 60% threshold. **Build the detector.** SPEC was not tested in this round; treat it as v2 territory until validated separately.

## Two insights that should shape v1

### 1. Justification-aware demote pass is table stakes, not nice-to-have

In `job-stalker`, ~half the findings had comments explicitly justifying the choice (e.g., "we issue the ALTER here so an old SQLite file boots cleanly without a full migration tool"). In `erate-filing-assistant`, the same code patterns had almost no defensive comments.

A detector that flags both without reading the surrounding context will be perceived as a tool that doesn't get the joke. Senior engineers will turn it off in a week. **The justification-demote pass is what separates flunk from existing linters.**

### 2. The detector's value decays as a codebase matures

`erate-prospector` (most mature) had the lowest PATTERN+HYBRID ratio (79%) and the highest JUDGMENT ratio (21%). The obvious wheel-reinventions had already been refactored OUT — what remained was taste-driven.

Product implication: **flunk delivers most value in the first 6 months of a new AI-built project.** By month 18+, findings flip into JUDGMENT territory that pattern matching can't catch. This argues hard for a **pre-flight (planning-time) detection mode in v2** — catching the issue when the AI proposes it, before it hardens into codebase debt.

## What got dropped from the original framing

The product started as "an app that visualizes architecture, database, and data flows for project managers and auditors." That framing was abandoned mid-brainstorm in favor of the BS-detector framing because:

- "PM / owner / auditor" was three different products with three different buyers and three different willingness-to-pay levels
- The real user was the senior engineer directing AI — a personal pain, not an organizational one
- Visualization was the *interface* the user had imagined; the *value* was actually catching the AI cut-corners. The map can come back as a v2 navigation layer once findings exist to navigate.

See conversation history (2026-05-26 brainstorm session) for the full reasoning.

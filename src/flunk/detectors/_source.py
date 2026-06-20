"""Tokenize-aware helpers so detectors match code, not text that merely
*mentions* a pattern.

A detector that greps raw file text will flag a comment or string literal that
only talks about the pattern it hunts for — including flunk's own detector
source, whose regexes and docstrings necessarily quote the very things they
catch. Splitting real comments from code (and keeping string literals, which
are a legitimate signal) fixes that. This is the same lesson `demote.py` learned
when it anchored its markers to `#`.
"""

from __future__ import annotations

import io
import tokenize


def _readline(source: str):
    # tokenize wants a trailing newline; a missing one raises TokenError on EOF.
    if not source.endswith("\n"):
        source += "\n"
    return io.StringIO(source).readline


def _naive_comments(source: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        hash_at = line.find("#")
        if hash_at != -1:
            out.append((lineno, line[hash_at:]))
    return out


def iter_comments(source: str) -> list[tuple[int, str]]:
    """Return ``(lineno, comment_text)`` for each real Python comment.

    A ``#`` inside a string literal is not a comment and is skipped. If the
    source can't be tokenized (e.g. a syntax error), fall back to a naive
    per-line scan from the first ``#`` so a broken file still gets best-effort
    coverage rather than silently going unscanned.

    Results are collected fully before returning, so a tokenize error partway
    through never yields a partial-then-duplicated list.
    """
    out: list[tuple[int, str]] = []
    try:
        for tok in tokenize.generate_tokens(_readline(source)):
            if tok.type == tokenize.COMMENT:
                out.append((tok.start[0], tok.string))
        return out
    except (tokenize.TokenError, SyntaxError, ValueError):
        return _naive_comments(source)


def code_lines(source: str) -> list[str]:
    """Return the source lines (0-indexed, aligned with ``splitlines()``) with
    comment text blanked out.

    String literals are preserved — a header or cookie name in a string is a
    real signal — so only ``#`` comments are removed. A pattern that appears
    *only* in a comment no longer counts as code. Falls back to the raw lines
    if the source can't be tokenized.
    """
    lines = source.splitlines()
    try:
        for tok in tokenize.generate_tokens(_readline(source)):
            if tok.type == tokenize.COMMENT:
                row, col = tok.start  # row is 1-indexed
                i = row - 1
                if 0 <= i < len(lines):
                    lines[i] = lines[i][:col]
        return lines
    except (tokenize.TokenError, SyntaxError, ValueError):
        return source.splitlines()

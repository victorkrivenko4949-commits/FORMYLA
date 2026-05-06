# -*- coding: utf-8 -*-
"""
Lightweight LaTeX validator used by the JIT filter in prep_planner.

Strategy
--------
For every `$...$` block in `task_text` we run cheap structural checks first
(unpaired dollars, unbalanced braces). If those pass, we run
`latex2mathml.converter.convert(block)` which fully parses the LaTeX. If
the parse raises ANY exception we mark the task as broken and report the
first failing block + reason.

Design notes
------------
- The validator is deliberately *permissive*: missing/optional features
  that KaTeX renders fine on the frontend should not be flagged. We only
  catch hard parse errors.
- Results are memoised with `functools.lru_cache` keyed on text content
  so revalidating the same task during one process lifetime is free.
- If `latex2mathml` is not installed we degrade to a no-op that always
  returns "valid" plus a hint reason. This guarantees the planner can
  never deadlock the user because of a missing dev dependency.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import List, Tuple

try:
    from latex2mathml.converter import convert as _latex_to_mathml  # type: ignore
    _VALIDATOR_AVAILABLE = True
except Exception:  # pragma: no cover -- only on misconfigured machines
    _latex_to_mathml = None
    _VALIDATOR_AVAILABLE = False


# We have to handle BOTH inline $...$ and display $$...$$ math. The order
# matters: pull out $$...$$ first (longest match), then what's left is inline.
# Using non-greedy capture and DOTALL so multi-line display blocks work.
_DISPLAY_RE = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)
_INLINE_RE = re.compile(r'\$([^$]+)\$')

# Truly empty display math: $$<whitespace>$$.
_EMPTY_DISPLAY_RE = re.compile(r'\$\$\s*\$\$')

# Maximum length of a block we will pass to latex2mathml. Anything longer is
# almost certainly an unclosed dollar swallowing huge prose.
_BLOCK_MAX_LEN = 800


def is_validator_available() -> bool:
    return _VALIDATOR_AVAILABLE


def _extract_math_blocks(text: str) -> List[str]:
    """
    Return a list of math-block contents, after splitting out $$...$$ blocks
    first and then inline $...$ from what remains. The returned strings DO NOT
    include the surrounding dollars.
    """
    blocks: List[str] = []
    # 1) Pull out display math.
    def _grab_display(m):
        blocks.append(m.group(1))
        # Replace the match with a placeholder so the inline pass cannot
        # accidentally re-grab parts of it.
        return ' \x00 '
    stripped = _DISPLAY_RE.sub(_grab_display, text)
    # 2) Inline math from what's left.
    blocks.extend(_INLINE_RE.findall(stripped))
    return blocks


def _quick_structural_issues(text: str) -> List[str]:
    """
    Cheap pre-checks that don't need latex2mathml.

    Note: we MUST consider that `$$` is valid display-math syntax, and that
    two adjacent inline blocks `$A$ $B$` are also valid. So:
      - Truly empty `$$  $$` is flagged.
      - For inline blocks we extract them and check each is non-blank.
      - `$` parity is computed AFTER stripping display blocks.
    """
    issues: List[str] = []
    if not text:
        return issues

    # Empty display math blocks.
    if _EMPTY_DISPLAY_RE.search(text):
        issues.append('empty_math')

    # Strip display math first, then count remaining `$` for parity.
    no_display = _DISPLAY_RE.sub('', text)
    if no_display.count('$') % 2 != 0:
        issues.append('unpaired_dollar')

    # Empty inline math blocks: $...$ with whitespace-only inside.
    for inner in _INLINE_RE.findall(no_display):
        if not inner.strip():
            issues.append('empty_math')
            break

    # Unbalanced braces is still a deal-breaker for KaTeX.
    if text.count('{') != text.count('}'):
        issues.append('unbalanced_braces')

    return issues


# We cache by the actual string. Tasks usually fit comfortably under 64KB,
# and the cache is bounded so memory usage stays small.
@lru_cache(maxsize=4096)
def _validate_cached(text: str) -> Tuple[bool, Tuple[str, ...]]:
    """Internal worker; returns (is_ok, tuple_of_reasons)."""
    if not text:
        return True, ()

    structural = _quick_structural_issues(text)
    if structural:
        return False, tuple(structural)

    if not _VALIDATOR_AVAILABLE:
        # Don't block users when the dev dependency is missing.
        return True, ('validator_unavailable',)

    for block in _extract_math_blocks(text):
        block = block.strip()
        if not block:
            return False, ('empty_math',)
        if len(block) > _BLOCK_MAX_LEN:
            return False, ('math_block_too_long',)
        try:
            _latex_to_mathml(block)
        except Exception as exc:  # noqa: BLE001 -- any parse error counts
            return False, ('latex_parse_error', type(exc).__name__)

    return True, ()


def is_task_text_renderable(text: str) -> Tuple[bool, List[str]]:
    """
    Public API.

    Returns
    -------
    (True,  [])              -- task_text is safe to render.
    (True,  ['validator_unavailable'])  -- latex2mathml missing; treated as ok.
    (False, ['<reason>',...])           -- task_text would break in KaTeX.
    """
    ok, reasons = _validate_cached(text or '')
    return ok, list(reasons)


__all__ = ['is_task_text_renderable', 'is_validator_available']

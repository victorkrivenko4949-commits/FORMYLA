# -*- coding: utf-8 -*-
"""JSON parsing with LaTeX backslash fix."""
import json
import re


def parse_json_with_latex(text):
    """Parse JSON containing unescaped LaTeX backslashes."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract JSON object
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        text = m.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fix: double all single backslashes not followed by valid JSON escape chars.
    # NOTE (v2.5 hotfix): we deliberately EXCLUDE ``b`` and ``f`` from the
    # allowlist because LaTeX commands like ``\boxed{...}`` and ``\frac{...}``
    # were being silently interpreted as the JSON escapes ``\b`` (backspace)
    # and ``\f`` (formfeed), which corrupted output to ``\oxed{...}`` /
    # ``\rac{...}``.  Within an olympiad math pipeline these legitimate JSON
    # escapes never occur, so re-doubling them is safe.
    # Original JSON spec valid escapes: \\ \" \/ \b \f \n \r \t \uXXXX
    VALID_ESCAPES = '"\\/nrtu'
    fixed = re.sub(
        r'\\(?![' + VALID_ESCAPES + '])',
        r'\\\\',
        text
    )
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Second pass: also try preserving original text but pre-doubling \b / \f
    # before parsing in case the model emitted a literal backspace already.
    text2 = text.replace('\b', r'\\b').replace('\f', r'\\f')
    try:
        return json.loads(text2)
    except json.JSONDecodeError:
        pass

    # Last resort: raise with truncated text for debugging
    raise json.JSONDecodeError("Cannot parse JSON after LaTeX fix", text[:200], 0)

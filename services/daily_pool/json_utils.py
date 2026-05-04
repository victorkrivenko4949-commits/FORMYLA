# -*- coding: utf-8 -*-
"""
Shared JSON parsing utilities for pipeline services.
Handles LaTeX backslash escaping issues in model outputs.
"""
import json
import re


def parse_json_with_latex(text: str) -> dict:
    """
    Parse JSON that may contain unescaped LaTeX backslashes.

    Models often return JSON with \\( \\) \\[ \\] \\frac etc.
    that aren't properly escaped for JSON strings.
    """
    # First try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fix unescaped backslashes: replace \ followed by non-JSON-escape chars
    # JSON valid escapes: \\ \" \/ \b \f \n \r \t \uXXXX
    fixed = re.sub(
        r'\\(?!["\\/bfnrtu])',
        r'\\\\',
        text
    )
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # More aggressive: try to find JSON object boundaries
    # and parse just that
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        candidate = match.group(0)
        fixed2 = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', candidate)
        try:
            return json.loads(fixed2)
        except json.JSONDecodeError:
            pass

    # Last resort: raise
    raise json.JSONDecodeError("Cannot parse JSON even after LaTeX fix", text, 0)

import json
import re


def safe_parse_llm_json(raw):
    """Parse JSON from LLM, handling LaTeX and markdown."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    # Remove markdown code block
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) >= 3:
            text = "\n".join(lines[1:])
            idx = text.rfind("```")
            if idx >= 0:
                text = text[:idx].strip()
    # Attempt 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Attempt 2: fix single backslashes in string values
    try:
        fixed = re.sub(
            r'(?<!\\)\\(?!["\\/bfnrtu])',
            r'\\\\',
            text
        )
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # Attempt 3: brute force double all backslashes
    try:
        fixed2 = text.replace("\\", "\\\\")
        fixed2 = fixed2.replace("\\\\\\\\", "\\\\")
        fixed2 = fixed2.replace('\\\\"', '\\"')
        fixed2 = fixed2.replace("\\\\n", "\\n")
        fixed2 = fixed2.replace("\\\\t", "\\t")
        return json.loads(fixed2)
    except Exception:
        return {"_parse_error": "all attempts failed", "_raw": raw[:500]}


if __name__ == "__main__":
    tests = [
        '{"x": 1}',
        '```json\n{"x":1}\n```',
        '{"sol": "$\\\\frac{a}{b}$"}',
        '{"sol": "$\\frac{a}{b}$"}',
    ]
    for i, t in enumerate(tests):
        r = safe_parse_llm_json(t)
        ok = r is not None and "_parse_error" not in r
        print(f"Test {i+1}: {'OK' if ok else 'FAIL'} -> {r}")

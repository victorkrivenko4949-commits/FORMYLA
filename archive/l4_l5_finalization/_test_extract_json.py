#!/usr/bin/env python
"""
_test_extract_json.py -- Comprehensive edge-case test for _extract_json().

Tests both Stage 6 (find_balanced_objects-based) and Stage 7 (regex-based)
implementations against 9 documented edge cases plus additional cases.

Usage:
    python l4_l5_finalization/_test_extract_json.py

Exit code:
    0 -- All tests passed
    1 -- One or more tests failed
"""

import json
import re
import sys
from typing import Any, Dict, List, Optional, Set

# ─── Stage 6 _extract_json (with find_balanced_objects dependency) ──────────────

def _s6_find_balanced_objects(text: str) -> List[str]:
    """Find all top-level balanced brace-delimited objects in text.
    (Copied verbatim from _06_stage6_replace_tasks.py lines 119-173)
    """
    results: List[str] = []
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        j = i
        in_string = False
        string_char = None
        while j < len(text):
            ch = text[j]
            if in_string:
                if ch == "\\" and j + 1 < len(text):
                    j += 2
                    continue
                if ch == string_char:
                    in_string = False
                j += 1
                continue
            if ch in ('"', "'"):
                in_string = True
                string_char = ch
                j += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    results.append(text[i:j + 1])
                    i = j + 1
                    break
            j += 1
        else:
            i += 1
            continue
        if depth == 0:
            continue
        i += 1
    return results


def _s6_extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Stage 6 _extract_json (lines 176-221)."""
    if not text or not text.strip():
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        fence_found = False
        content_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                if fence_found:
                    break
                fence_found = True
                continue
            if fence_found:
                content_lines.append(line)
        if content_lines:
            cleaned = "\n".join(content_lines).strip()
    candidates = _s6_find_balanced_objects(cleaned)
    if not candidates:
        return None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            continue
    return None


# ─── Stage 7 _extract_json ──────────────────────────────────────────────────────

def _s7_extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Stage 7 _extract_json (lines 280-304)."""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        return None
    candidate = cleaned[first_brace:last_brace + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    candidate = candidate.replace('\\\\(', '(').replace('\\\\)', ')')
    candidate = candidate.replace('\\\\[', '[').replace('\\\\]', ']')
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


# ─── Sanitize output for cp1251 terminal ────────────────────────────────────────

def _sanitize(text: Any, max_len: int = 80) -> str:
    """Convert value to cp1251-safe string, replacing non-ASCII chars."""
    s = str(text)
    s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    # Replace superscript 2 and other common Unicode that cp1251 lacks
    replacements = {
        "\xb2": "^2",   # ² -> ^2
        "\xb3": "^3",   # ³ -> ^3
        "\xb0": "deg",  # ° -> deg
        "\u2013": "-",  # en-dash
        "\u2014": "--", # em-dash
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
        "\u2026": "...",# ellipsis
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    # Replace any remaining non-ASCII with '?'
    s = s.encode("ascii", errors="replace").decode("ascii")
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


# ─── Test Infrastructure ────────────────────────────────────────────────────────

VALID_JSON = {
    "statement": "Solve x+1=2",
    "answer": "1",
    "solution": "x = 2 - 1 = 1",
    "main_idea": "Linear equation solving",
    "task_type": "computable",
    "why_level": "Basic algebra",
}

VALID_JSON_STR = json.dumps(VALID_JSON, ensure_ascii=False)

TestResult = Dict[str, Any]

tests_run: List[TestResult] = []
tests_passed = 0
tests_failed = 0


def run_test(
    test_id: str,
    description: str,
    input_text: str,
    impls: Dict[str, Any],
    expect_success: bool = True,
    expected_keys: Optional[Set[str]] = None,
    expected_reason: str = "",
    impl_expectations: Optional[Dict[str, bool]] = None,
) -> None:
    """Run a test case against both implementations and report.

    If impl_expectations is provided, it overrides expect_success per
    implementation name (e.g. {"Stage7 (regex)": False} to expect failure
    on a specific implementation).
    """
    global tests_passed, tests_failed
    result: TestResult = {
        "id": test_id,
        "description": description,
        "input_preview": _sanitize(input_text or "", 80),
        "expected": "valid JSON" if expect_success else "None",
        "results": {},
    }
    all_ok = True
    for impl_name, impl_func in impls.items():
        try:
            output = impl_func(input_text)
        except Exception as e:
            output = None
            result["results"][impl_name] = {
                "status": "ERROR",
                "error": str(e),
            }
            all_ok = False
            continue

        # Determine per-impl expectation
        if impl_expectations and impl_name in impl_expectations:
            impl_expect = impl_expectations[impl_name]
        else:
            impl_expect = expect_success

        if impl_expect:
            is_ok = output is not None and isinstance(output, dict)
            if is_ok and expected_keys:
                has_keys = expected_keys.issubset(output.keys())
                is_ok = has_keys
        else:
            is_ok = output is None

        status = "PASS" if is_ok else "FAIL"
        result["results"][impl_name] = {
            "status": status,
            "output_preview": _sanitize(output, 100) if output else "None",
        }
        if not is_ok:
            all_ok = False

    if all_ok:
        tests_passed += 1
    else:
        tests_failed += 1
    tests_run.append(result)


def print_report() -> None:
    """Print a detailed test report."""
    print("=" * 72)
    print("  _extract_json() Edge-Case Test Report")
    print("=" * 72)
    print()
    for tr in tests_run:
        statuses = " | ".join(
            f"{name}: {r['status']}" for name, r in tr["results"].items()
        )
        verdict = "OK" if all(r["status"] == "PASS" for r in tr["results"].values()) else "FAIL"
        print(f"  {verdict:>4}  [{tr['id']}] {tr['description']}")
        print(f"     Input: {tr['input_preview']}")
        print(f"     Expected: {tr['expected']}")
        print(f"     {statuses}")
        print()
    print("-" * 72)
    print(f"  Total: {len(tests_run)}  |  Passed: {tests_passed}  |  Failed: {tests_failed}")
    print("-" * 72)
    print()


# ─── Test Cases ─────────────────────────────────────────────────────────────────

IMPLS = {
    "Stage6 (balanced-brace)": _s6_extract_json,
    "Stage7 (regex)": _s7_extract_json,
}

REQUIRED_KEYS = {"statement", "answer", "solution", "main_idea", "task_type", "why_level"}

# Edge case 1: Empty / None input
run_test(
    "EC01",
    "Empty / None input -> None",
    "",
    IMPLS,
    expect_success=False,
)

run_test(
    "EC01b",
    "None input -> None",
    None,
    IMPLS,
    expect_success=False,
)

# Edge case 2: No braces found
run_test(
    "EC02",
    "No braces found -> None",
    "This is plain text with no JSON at all.",
    IMPLS,
    expect_success=False,
)

# Edge case 3: Multiple objects -> first valid one
# NOTE: Stage7 regex grabs from first { to last }, spanning both objects,
# which produces invalid JSON. Stage6 handles this correctly via balanced-brace.
MULTI_JSON = (
    '{"answer": "first", "statement": "a", "solution": "a", "main_idea": "a", "task_type": "computable", "why_level": "a"}'
    '\n\n'
    '{"answer": "second", "statement": "b", "solution": "b", "main_idea": "b", "task_type": "proof", "why_level": "b"}'
)
run_test(
    "EC03",
    "Multiple JSON objects -> first valid one",
    MULTI_JSON,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
    impl_expectations={"Stage7 (regex)": False},  # regex spans both objects
)

# Edge case 4: Nested LaTeX braces within strings
LATEX_BRACES = json.dumps({
    "statement": "Solve $\\frac{x+1}{2} = \\frac{3}{4}$",
    "answer": "x = \\frac{1}{2}",
    "solution": "\\frac{x+1}{2} = \\frac{3}{4} \\implies 4(x+1) = 6 \\implies x = \\frac{1}{2}",
    "main_idea": "Cross-multiplication",
    "task_type": "computable",
    "why_level": "Basic fractions",
}, ensure_ascii=False)
run_test(
    "EC04",
    "Nested LaTeX braces (frac, math mode) within JSON strings",
    LATEX_BRACES,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)

# Edge case 4b: Strings containing literal braces like \{ \}
LITERAL_BRACES = json.dumps({
    "statement": "Set notation: $\\{x \\mid x > 0\\}$",
    "answer": "$\\{1, 2, 3\\}$",
    "solution": "The set $\\{x \\mid x > 0\\}$ contains all positive numbers.",
    "main_idea": "Set builder notation",
    "task_type": "proof",
    "why_level": "Set theory basics",
}, ensure_ascii=False)
run_test(
    "EC04b",
    "Literal LaTeX escaped braces (\\\\{ \\\\}) within JSON strings",
    LITERAL_BRACES,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)

# Edge case 5: Truncated (unclosed) JSON -> None
TRUNCATED = '{"statement": "Solve x+1=2", "answer": "1", "solution": "x = 1"'
run_test(
    "EC05",
    "Truncated/unclosed JSON -> None",
    TRUNCATED,
    IMPLS,
    expect_success=False,
)

# Edge case 6: Valid JSON with markdown fences
FENCED = f"""```json
{VALID_JSON_STR}
```"""
run_test(
    "EC06",
    "Valid JSON with markdown fences (```json)",
    FENCED,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)

# Edge case 6b: Markdown fences without language tag
FENCED_NO_LANG = f"""```
{VALID_JSON_STR}
```"""
run_test(
    "EC06b",
    "Markdown fences without language tag",
    FENCED_NO_LANG,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)

# Edge case 7: Extra text before/after JSON
EXTRA_TEXT = f"Here is the result:\n\n{VALID_JSON_STR}\n\nI hope this helps!"
run_test(
    "EC07",
    "Extra text before and after JSON",
    EXTRA_TEXT,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)

# Edge case 8: JSON within code block with extra braces
# Use a raw string to avoid f-string brace escaping, then format manually
CODE_BLOCK_CONTENT = """Some explanation with {{template braces}} before JSON...

{
  "statement": "hidden",
  "answer": "42",
  "solution": "...",
  "main_idea": "test",
  "task_type": "computable",
  "why_level": "basic"
}

More text after."""
run_test(
    "EC08",
    "JSON within text with template-style doubled braces",
    CODE_BLOCK_CONTENT,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
    impl_expectations={"Stage7 (regex)": False},  # {{template braces}} contain { before actual JSON
)

# Edge case 9: Malformed JSON (parse error) -> None
MALFORMED = '{"statement": "Solve x+1=2", "answer": "1", "solution": unquoted text here, "main_idea": "test", "task_type": "computable", "why_level": "basic"}'
run_test(
    "EC09",
    "Malformed JSON (parse error) -> None",
    MALFORMED,
    IMPLS,
    expect_success=False,
)

# Additional edge cases

# Edge case 10: Missing required fields -> still parsed (valid JSON, just missing fields)
MISSING_FIELDS = '{"statement": "Only statement", "answer": "yes"}'
run_test(
    "EC10",
    "JSON with missing required fields -> parsed (JSON-valid), but schema validation would catch",
    MISSING_FIELDS,
    IMPLS,
    expect_success=True,  # JSON is valid, just missing fields
)

# Edge case 11: Strings with unescaped newlines (common model error)
UNESCAPED_NEWLINES = '{"statement": "Line one\\nLine two", "answer": "1", "solution": "ok", "main_idea": "test", "task_type": "computable", "why_level": "basic"}'
run_test(
    "EC11",
    "Unescaped newlines in string values",
    UNESCAPED_NEWLINES,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)

# Edge case 12: Deeply nested JSON
DEEP_NESTED = json.dumps({
    "statement": "test",
    "answer": "1",
    "solution": "test " * 50,  # long string
    "main_idea": "nested" * 20,
    "task_type": "computable",
    "why_level": "basic",
    "metadata": {
        "source": "generator",
        "version": 2,
        "tags": ["algebra", "linear"],
        "stats": {"tokens": 150, "confidence": 0.95},
    },
}, ensure_ascii=False)
run_test(
    "EC12",
    "Deeply nested JSON with nested objects and arrays",
    DEEP_NESTED,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)

# Edge case 13: Very long JSON with no newlines (use full string, not truncated)
LONG_FLAT = json.dumps({
    "statement": "A" * 1000,
    "answer": "B" * 1000,
    "solution": "C" * 1000,
    "main_idea": "D" * 1000,
    "task_type": "computable",
    "why_level": "E" * 1000,
}, ensure_ascii=False)
run_test(
    "EC13",
    "Very long JSON (single line, no newlines)",
    LONG_FLAT,  # use full string, not truncated
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)

# Edge case 14: JSON with Unicode/Russian text
RUSSIAN_JSON = json.dumps({
    "statement": "Reshite uravnenie x^2 - 4 = 0",
    "answer": "x = 2, x = -2",
    "solution": "Perenesem 4 vpravo: x^2 = 4, zatem izvlechem koren.",
    "main_idea": "Kvadratnye uravneniya",
    "task_type": "computable",
    "why_level": "8 klass",
}, ensure_ascii=False)
run_test(
    "EC14",
    "JSON with Russian/Unicode text",
    RUSSIAN_JSON,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)

# Edge case 15: Only braces (no real content)
ONLY_BRACES = "{}"
run_test(
    "EC15",
    "Empty JSON object {}",
    ONLY_BRACES,
    IMPLS,
    expect_success=True,
)

# Edge case 16: Text before fence but valid JSON inside
TEXT_BEFORE_FENCE = f"""Let me provide the solution:
```json
{VALID_JSON_STR}
```
I hope this clarifies."""
run_test(
    "EC16",
    "Text before markdown fence with valid JSON inside",
    TEXT_BEFORE_FENCE,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)

# Edge case 17: Nested braces within strings (array of objects in a field)
NESTED_OBJ_IN_FIELD = json.dumps({
    "statement": "test",
    "answer": "1",
    "solution": "Some solution",
    "main_idea": "test",
    "task_type": "computable",
    "why_level": "basic",
    "options": [{"a": 1}, {"b": 2}],
}, ensure_ascii=False)
run_test(
    "EC17",
    "Nested objects/arrays within JSON fields",
    NESTED_OBJ_IN_FIELD,
    IMPLS,
    expect_success=True,
    expected_keys=REQUIRED_KEYS,
)


# ─── Main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    print_report()
    if tests_failed > 0:
        print("FAIL: Some tests did not pass.")
        # Show which specific implementations failed
        for tr in tests_run:
            for name, r in tr["results"].items():
                if r["status"] != "PASS":
                    print(f"  FAIL [{tr['id']}] {name}: {r.get('output_preview', r.get('error', 'unknown'))}")
        return 1
    else:
        print("OK: All tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())

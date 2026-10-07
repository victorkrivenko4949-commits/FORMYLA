#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnose JSON parsing failure for 'Метод интервалов' cell."""
import json
import os
import sys
import re

sys.path.insert(0, os.path.dirname(__file__))
from ai.deepseek_client import DeepSeekClient

GRADE = 9
TOPIC = "Метод интервалов"

SYSTEM_PROMPT = """You are a mathematics olympiad problem generator. You MUST respond with ONLY a valid JSON object, no other text.

Generate exactly ONE olympiad-level mathematics problem. The response must be a valid JSON object with exactly these fields:
- "statement": the problem text (may include LaTeX with $$...$$)
- "answer": the correct answer
- "solution": a brief solution or explanation

Example:
{"statement": "Find all integers $$n$$ such that $$n^2 + 3n + 2$$ is a perfect square.", "answer": "n = -1, -2", "solution": "Factor as (n+1)(n+2). For product of two consecutive integers to be a square..."}

IMPORTANT: Output ONLY the JSON object. No markdown, no code fences, no explanations."""

PROMPT = """Generate one olympiad-level mathematics problem for grade 9, topic: "Метод интервалов" (Interval method).

This is for an olympiad training system. The problem should be challenging but appropriate for grade 9 students.
Include the problem statement, answer, and solution.

Respond with ONLY a valid JSON object."""


def _fix_invalid_escapes(text: str) -> str:
    replacements = {
        '\\(': '(', '\\)': ')', '\\[': '[', '\\]': ']',
        '\\{': '{', '\\}': '}', '\\<': '<', '\\>': '>',
        '\\|': '|', '\\`': '`', '\\_': '_', '\\*': '*',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r'\\([^"\\/bfnrtu])', r'\1', text)
    return text


def _strip_control_chars(text: str) -> str:
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)


def safe_parse_single_object(text: str):
    if not text:
        return None
    text = text.strip()

    # Strip markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    # Find outermost { ... } with brace-depth tracking (escape-aware)
    brace_depth = 0
    obj_start = -1
    obj_end = -1
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text) and text[i+1] in '{}':
            i += 2
            continue
        if ch == '{':
            if brace_depth == 0:
                obj_start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and obj_start >= 0:
                obj_end = i + 1
                break
        i += 1

    if obj_start < 0 or obj_end <= obj_start:
        return None, "No valid JSON object found via brace tracking"

    json_str = text[obj_start:obj_end]

    # Phase 1 analysis
    print(f"\n{'='*60}")
    print(f"EXTRACTED JSON STRING (repr):")
    print(repr(json_str[:500]))

    # Check for problematic characters
    problems = []
    for idx, c in enumerate(json_str):
        if ord(c) < 32 and c not in '\n\r\t':
            problems.append(f"  pos={idx}: char={repr(c)} ord={ord(c)}")
    if problems:
        print(f"\nCONTROL CHARACTERS IN JSON STRING (before fix):")
        for p in problems:
            print(p)
    else:
        print(f"\nNo control chars found in extracted JSON string.")

    # Check for literal newlines inside string values
    in_string = False
    for idx, c in enumerate(json_str):
        if c == '"' and (idx == 0 or json_str[idx-1] != '\\'):
            in_string = not in_string
        if in_string and c in '\n\r':
            print(f"WARNING: Literal {repr(c)} at pos {idx} INSIDE a string value!")

    # Phase 2: apply fixes
    fixed = _fix_invalid_escapes(json_str)
    stripped = _strip_control_chars(fixed)

    print(f"\nAFTER FIXES (repr):")
    print(repr(stripped[:500]))

    # Phase 3: try json.loads
    print(f"\n{'='*60}")
    print("JSON PARSE ATTEMPTS:")
    
    strategies = [
        ("json.loads (standard)", lambda s: json.loads(s)),
        ("single-quote fix", lambda s: json.loads(s.replace("'", '"'))),
        ("trailing comma fix", lambda s: json.loads(re.sub(r',\s*([\]}])', r'\1', s.replace("'", '"')))),
    ]
    
    for name, strategy in strategies:
        try:
            result = strategy(stripped)
            if isinstance(result, dict):
                print(f"  [OK] {name}: SUCCESS")
                print(f"    keys: {list(result.keys())}")
                return result, None
        except json.JSONDecodeError as e:
            print(f"   {name}: FAILED")
            print(f"    Error: {e}")
            # Show context around error position
            pos = e.pos if hasattr(e, 'pos') else 0
            if pos > 0:
                start = max(0, pos - 30)
                end = min(len(stripped), pos + 30)
                ctx = stripped[start:end]
                print(f"    Context around error: ...{repr(ctx)}...")

    return None, "All JSON parse strategies failed"


def main():
    client = DeepSeekClient()
    
    print(f"Making API call for g{GRADE}|{TOPIC}...")
    raw = client.generate(
        prompt=PROMPT,
        system_prompt=SYSTEM_PROMPT,
        max_tokens=4000,
        temperature=0.7,
    )

    print(f"\n{'='*60}")
    print(f"RAW RESPONSE (len={len(raw)}):")
    print(f"repr: {repr(raw[:1000])}")
    print(f"\nPlain text preview:")
    print(raw[:800])
    
    # Save raw response to file
    out_file = "_diagnose_raw_output.txt"
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write("=== RAW RESPONSE (plain) ===\n")
        f.write(raw)
        f.write("\n\n=== RAW RESPONSE (repr) ===\n")
        f.write(repr(raw))
    
    print(f"\nSaved raw response to {out_file}")

    result, error = safe_parse_single_object(raw)
    if result:
        print(f"\n{'='*60}")
        print(f"[OK] PARSING SUCCEEDED!")
        print(f"statement: {result.get('statement', '')[:100]}")
        print(f"answer: {result.get('answer', '')[:100]}")
    else:
        print(f"\n{'='*60}")
        print(f"[ERROR] PARSING FAILED: {error}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test render_task_text function."""
import re
import markdown as md_lib

def render_task_text(text):
    if not text:
        return ''
    placeholders = {}
    _counter = [0]
    def _protect(m):
        key = f'XMATHX{_counter[0]}XENDX'
        placeholders[key] = m.group(0)
        _counter[0] += 1
        return key
    text = re.sub(r'\$\$[\s\S]+?\$\$', _protect, text)
    text = re.sub(r'\$[^\$\n]+?\$', _protect, text)
    text = re.sub(r'\\\[[\s\S]+?\\\]', _protect, text)
    text = re.sub(r'\\\([\s\S]+?\\\)', _protect, text)
    try:
        html = md_lib.markdown(text, extensions=['nl2br', 'tables'])
    except Exception:
        html = text.replace('\n', '<br>')
    for key, val in placeholders.items():
        html = html.replace(key, val)
    return html

tests = [
    ("# header", "# Zadacha 1\nFind $x^2 + 3x$."),
    ("sqrt LaTeX", "Compute $\\sqrt{45 - \\sqrt{2023 - \\sqrt{45 + \\sqrt{2023}}}}$"),
    ("display math", "Solve:\n$$x^2 + \\frac{1}{x^2} = 7$$"),
    ("bold/italic", "**Important**: find *all* solutions"),
    ("backslash-paren", "Prove that \\(n^3 - n\\) is divisible by 6"),
]

results = []
all_ok = True
for name, inp in tests:
    out = render_task_text(inp)
    ok = True
    if name == "# header":
        ok = "<h1>" in out and "#" not in out.replace("</h1>", "").replace("<h1>", "").split(">")[-1]
    elif name == "sqrt LaTeX":
        ok = "$\\sqrt{" in out and "sqrt{" in out
    elif name == "display math":
        ok = "$$" in out and "\\frac" in out
    elif name == "bold/italic":
        ok = "<strong>" in out and "<em>" in out and "**" not in out
    elif name == "backslash-paren":
        ok = "\\(n^3 - n\\)" in out
    
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_ok = False
    results.append(f"[{status}] {name}")
    results.append(f"  IN:  {inp[:80]}")
    results.append(f"  OUT: {out[:120]}")
    results.append("")

with open("scripts/test_render_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(results))
    f.write(f"\n{'ALL TESTS PASSED' if all_ok else 'SOME TESTS FAILED'}\n")

# Exit code
import sys
sys.exit(0 if all_ok else 1)

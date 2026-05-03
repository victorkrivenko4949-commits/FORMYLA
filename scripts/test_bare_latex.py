#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test bare LaTeX wrapping in render_task_text."""
import re
import markdown as md_lib

# Copy of the regex and functions from app.py
_BARE_LATEX_RE = re.compile(
    r'(?<!\$)(?<!\\\()'
    r'(\\(?:sqrt|frac|dfrac|tfrac|binom|sum|prod|int|lim|log|ln|sin|cos|tan|tg|ctg'
    r'|arcsin|arccos|arctan|text|mathrm|mathbf|mathbb|operatorname'
    r'|leq|geq|neq|le|ge|ne|pm|mp|times|cdot|div|equiv|approx|sim'
    r'|alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|iota|kappa|lambda'
    r'|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega'
    r'|infty|partial|nabla|forall|exists|in|notin|subset|supset|cup|cap'
    r'|lfloor|rfloor|lceil|rceil|langle|rangle|ldots|cdots|vdots|ddots'
    r'|overline|underline|hat|tilde|vec|bar|dot'
    r'|left|right|big|Big|bigg|Bigg)'
    r'(?:\{[^}]*\}|[^a-zA-Z\s])*'
    r'(?:\{[^}]*\})*'
    r'[^$\n]*?)'
    r'(?=[\s.,;:!?)}\]]|$)',
    re.UNICODE
)

def _wrap_bare_latex(text):
    if not text or '\\' not in text:
        return text
    if '$' in text or '\\(' in text:
        return text
    return _BARE_LATEX_RE.sub(r'$\1$', text)

def render_task_text(text):
    if not text:
        return ''
    text = _wrap_bare_latex(text)
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

# Tests
tests = [
    ("bare sqrt", 
     r"Neravenstvo (\sqrt(x3 - 10x + 7) + 1) |x3 - 18x + 28| \leq 0.",
     lambda out: "$\\sqrt" in out or "$\\leq" in out),
    
    ("bare frac",
     r"Najdite \frac{a}{b} esli a = 5.",
     lambda out: "$\\frac{a}{b}$" in out),
    
    ("already has $",
     r"Najdite $\sqrt{45}$ i $\frac{1}{2}$.",
     lambda out: "$\\sqrt{45}$" in out and "$\\frac{1}{2}$" in out),
    
    ("no latex at all",
     "Petya napisal chisla ot 1 do 10.",
     lambda out: "$" not in out and "Petya" in out),
    
    ("already has backslash-paren",
     r"Dokazhite chto \(n^3 - n\) delitsya na 6.",
     lambda out: "\\(n^3 - n\\)" in out),
]

results = []
all_ok = True
for name, inp, check in tests:
    out = render_task_text(inp)
    ok = check(out)
    if not ok:
        all_ok = False
    results.append(f"[{'PASS' if ok else 'FAIL'}] {name}")
    results.append(f"  IN:  {inp[:100]}")
    results.append(f"  OUT: {out[:150]}")
    results.append("")

with open("scripts/test_bare_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(results))
    f.write(f"\n{'ALL TESTS PASSED' if all_ok else 'SOME TESTS FAILED'}\n")

import sys
sys.exit(0 if all_ok else 1)

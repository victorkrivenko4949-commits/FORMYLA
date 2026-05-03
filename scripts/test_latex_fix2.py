#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import markdown as md_lib

_LATEX_COMMANDS = (
    'sqrt|frac|dfrac|tfrac|binom|sum|prod|int|lim|log|ln|sin|cos|tan|tg|ctg'
    '|arcsin|arccos|arctan|text|mathrm|mathbf|mathbb|operatorname'
    '|leq|geq|neq|le|ge|ne|pm|mp|times|cdot|div|equiv|approx|sim'
    '|alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|iota|kappa|lambda'
    '|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega'
    '|infty|partial|nabla|forall|exists|notin|subset|supset|cup|cap'
    '|lfloor|rfloor|lceil|rceil|langle|rangle|ldots|cdots|vdots|ddots'
    '|overline|underline|hat|tilde|vec|bar|dot|triangle|angle'
)

def _fix_latex_parens(text):
    text = re.sub(r'\\(sqrt|frac|text|mathrm|mathbf|mathbb|overline|underline|hat|tilde|vec)\(([^)]*)\)', r'\\\1{\2}', text)
    return text

def _wrap_bare_latex(text):
    if not text or '\\' not in text:
        return text
    if '$' in text or '\\(' in text:
        return text
    text = _fix_latex_parens(text)
    text = re.sub(
        r'(\\(?:' + _LATEX_COMMANDS + r')(?:\{[^}]*\})*(?:\s*[_^]\s*(?:\{[^}]*\}|[a-zA-Z0-9]))*)',
        r'$\1$',
        text
    )
    return text

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

tests = [
    ("screenshot text",
     r"Neravenstvo (\sqrt(x3 - 10x + 7) + 1) |x3 - 18x + 28| \leq 0.",
     lambda out: "$\\sqrt{x3 - 10x + 7}$" in out and "$\\leq$" in out),

    ("already has $ delimiters",
     r"V $\triangle ABC$ storony $AB$ i $BC$ ravny.",
     lambda out: "$\\triangle ABC$" in out and "$AB$" in out),

    ("bare frac with braces",
     r"Najdite \frac{a}{b} esli a = 5.",
     lambda out: "$\\frac{a}{b}$" in out),

    ("no latex",
     "Petya napisal chisla ot 1 do 10.",
     lambda out: "$" not in out),

    ("bare leq geq",
     r"x \leq 5 i y \geq 3",
     lambda out: "$\\leq$" in out and "$\\geq$" in out),
]

results = []
all_ok = True
for name, inp, check in tests:
    out = render_task_text(inp)
    ok = check(out)
    if not ok:
        all_ok = False
    results.append(f"[{'PASS' if ok else 'FAIL'}] {name}")
    results.append(f"  IN:  {inp[:120]}")
    results.append(f"  OUT: {out[:180]}")
    results.append("")

with open("scripts/test_latex_fix2_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(results))
    f.write(f"\n{'ALL TESTS PASSED' if all_ok else 'SOME TESTS FAILED'}\n")

sys.exit(0 if all_ok else 1)

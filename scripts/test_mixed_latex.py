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
    text = _fix_latex_parens(text)
    if '$' not in text and '\\(' not in text:
        text = re.sub(
            r'(\\(?:' + _LATEX_COMMANDS + r')(?:\{[^}]*\})*(?:\s*[_^]\s*(?:\{[^}]*\}|[a-zA-Z0-9]))*)',
            r'$\1$', text)
        return text
    math_pattern = re.compile(
        r'(\$\$[\s\S]+?\$\$|\$[^\$\n]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])'
    )
    parts = math_pattern.split(text)
    bare_re = re.compile(
        r'(\\(?:' + _LATEX_COMMANDS + r')(?:\{[^}]*\})*(?:\s*[_^]\s*(?:\{[^}]*\}|[a-zA-Z0-9]))*)'
    )
    for i in range(0, len(parts), 2):
        parts[i] = bare_re.sub(r'$\1$', parts[i])
    text = ''.join(parts)
    return text

def render_task_text(text):
    if not text:
        return ''
    text = _wrap_bare_latex(text)
    placeholders = {}
    _counter = [0]
    def _protect(m):
        key = 'XMATHX' + str(_counter[0]) + 'XENDX'
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

# TESTS
tests = [
    ("mixed: $ + bare leq",
     "V $\\triangle ABC$ ugol $A = 60$. Dokazhite chto $AB \\leq AC$.",
     ["$\\triangle ABC$", "$A = 60$", "$AB \\leq AC$"]),

    ("mixed: $ + bare sqrt outside",
     "Najdite $x$ esli \\sqrt{x+1} = 5.",
     ["$x$", "$\\sqrt{x+1}$"]),

    ("fully bare",
     "Neravenstvo \\sqrt(x+7) \\leq 0.",
     ["$\\sqrt{x+7}$", "$\\leq$"]),

    ("fully wrapped",
     "V $\\triangle ABC$ storony $AB = 5$ i $BC = 7$.",
     ["$\\triangle ABC$", "$AB = 5$", "$BC = 7$"]),

    ("bare with backslash-paren",
     "Dokazhite \\(n^2\\) delitsya na \\leq 4.",
     ["\\(n^2\\)", "$\\leq$"]),
]

results = []
all_ok = True
for name, inp, expected_fragments in tests:
    out = render_task_text(inp)
    ok = all(frag in out for frag in expected_fragments)
    if not ok:
        all_ok = False
    results.append('[' + ('PASS' if ok else 'FAIL') + '] ' + name)
    results.append('  IN:  ' + inp[:120])
    results.append('  OUT: ' + out[:180])
    if not ok:
        for frag in expected_fragments:
            if frag not in out:
                results.append('  MISSING: ' + frag)
    results.append('')

with open('scripts/test_mixed_results.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
    f.write('\n' + ('ALL TESTS PASSED' if all_ok else 'SOME TESTS FAILED') + '\n')

sys.exit(0 if all_ok else 1)

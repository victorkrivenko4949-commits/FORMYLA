#!/usr/bin/env python3
"""
Analyze LaTeX issues in adaptive tasks.
"""
import sqlite3, re, json, os
from collections import defaultdict
from datetime import datetime

DB_PATH = os.path.join("instance", "formyla.db")
REPORT_DIR = os.path.join("data", "audit")
JSON_REPORT = os.path.join(REPORT_DIR, "latex_issues_report.json")
MD_REPORT = os.path.join(REPORT_DIR, "latex_issues_report.md")
MAX_SAMPLES = 5

LATEX_N_CMDS = {
    'neq','nabla','notin','neg','nu','nleq','ngeq','nmid',
    'nsubseteq','nsupseteq','ncong','nsim','nrightarrow',
    'nleftarrow','not','newline','newcommand','nolimits',
    'nonumber','nparallel'
}


def check_literal_backslash_n(text):
    """A) HAS_LITERAL_BACKSLASH_N"""
    BS2N = chr(92)*2 + 'n'
    if BS2N in text:
        return True
    for m in re.finditer(chr(92)+chr(92)+'n', text):
        pos = m.end()
        if m.start() > 0 and text[m.start()-1] == chr(92):
            continue
        if pos < len(text) and text[pos].isalpha():
            rest = text[pos:]
            skip = any(rest.startswith(c[1:]) for c in LATEX_N_CMDS)
            if skip:
                continue
            return True
        else:
            return True
    return False


def check_hline_outside_env(text):
    """B) HLINE_OUTSIDE_ENV"""
    BS = chr(92)
    if BS+'hline' not in text:
        return False
    env_pat = r'\\begin\{(array|matrix|pmatrix|bmatrix|vmatrix|tabular)\}'
    if re.search(env_pat, text):
        envs = list(re.finditer(env_pat, text))
        end_pat = r'\\end\{(array|matrix|pmatrix|bmatrix|vmatrix|tabular)\}'
        ends = list(re.finditer(end_pat, text))
        for hl in re.finditer(r'\\hline', text):
            inside = False
            for es, ee in zip(envs, ends):
                if es.start() < hl.start() < ee.end():
                    inside = True
                    break
            if not inside:
                return True
        return False
    else:
        return True


def build_math_map(text):
    """Build boolean map of math mode positions."""
    n = len(text)
    in_math = [False] * n
    i = 0
    BS = chr(92)
    while i < n:
        if i < n-1 and text[i] == BS and text[i+1] == '(':
            j = text.find(BS+')', i+2)
            if j != -1:
                for k in range(i, min(j+2, n)): in_math[k] = True
                i = j + 2
                continue
        if i < n-1 and text[i] == BS and text[i+1] == '[':
            j = text.find(BS+']', i+2)
            if j != -1:
                for k in range(i, min(j+2, n)): in_math[k] = True
                i = j + 2
                continue
        if i < n-1 and text[i] == '$' and text[i+1] == '$':
            j = text.find('$$', i+2)
            if j != -1:
                for k in range(i, min(j+2, n)): in_math[k] = True
                i = j + 2
                continue
            else:
                i += 2
                continue
        if text[i] == '$':
            j = text.find('$', i+1)
            if j != -1:
                for k in range(i, j+1): in_math[k] = True
                i = j + 1
                continue
            else:
                i += 1
                continue
        i += 1
    return in_math


def check_bare_sqrt_frac(text):
    """C) BARE_SQRT_FRAC"""
    latex_cmds = list(re.finditer(r'\\(sqrt|frac)\b', text))
    if not latex_cmds:
        return False
    in_math = build_math_map(text)
    for m in latex_cmds:
        if not in_math[m.start()]:
            return True
    return False


def check_lsqrtl_pattern(text):
    """D) LSQRTL_PATTERN"""
    return bool(re.search(r'l(sqrt|frac|cdot)l', text, re.IGNORECASE))


def check_unclosed_dollar(text):
    """E) UNCLOSED_DOLLAR"""
    cleaned = text.replace('$$', '')
    return cleaned.count('$') % 2 != 0


def check_russian_in_latex_cmd(text):
    """F) RUSSIAN_IN_LATEX_CMD"""
    return bool(re.search(r'\\[\u0430-\u044f\u0410-\u042f\u0451\u0401]', text))


def check_double_dollar_broken(text):
    """G) DOUBLE_DOLLAR_BROKEN"""
    if '$$$' in text:
        return True
    if re.search(r'(?<!\$)\$\$(?!\$)', text):
        parts = text.split('$$')
        if len(parts) % 2 == 0:
            return True
    return False


def analyze():
    os.makedirs(REPORT_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT id, class_level, difficulty_level, task_text FROM adaptive_tasks').fetchall()
    total = len(rows)
    print(f'Total tasks: {total}')
    checks = {
        'HAS_LITERAL_BACKSLASH_N': check_literal_backslash_n,
        'HLINE_OUTSIDE_ENV': check_hline_outside_env,
        'BARE_SQRT_FRAC': check_bare_sqrt_frac,
        'LSQRTL_PATTERN': check_lsqrtl_pattern,
        'UNCLOSED_DOLLAR': check_unclosed_dollar,
        'RUSSIAN_IN_LATEX_CMD': check_russian_in_latex_cmd,
        'DOUBLE_DOLLAR_BROKEN': check_double_dollar_broken,
    }
    by_type = defaultdict(int)
    by_grade = defaultdict(lambda: defaultdict(int))
    samples = defaultdict(list)
    issues_ids = set()
    for row in rows:
        tid = row['id']
        grade = row['class_level']
        text = row['task_text'] or ''
        for itype, fn in checks.items():
            try:
                if fn(text):
                    by_type[itype] += 1
                    by_grade[grade][itype] += 1
                    issues_ids.add(tid)
                    if len(samples[itype]) < MAX_SAMPLES:
                        prev = text[:250].replace(chr(10), chr(92)+'n')
                        samples[itype].append({'id': tid, 'grade': grade, 'preview': prev})
            except Exception as e:
                print(f'ERROR {itype} id={tid}: {e}')
    con.close()
    report = {
        'generated_at': datetime.now().isoformat(),
        'total_tasks': total,
        'issues_count': len(issues_ids),
        'by_type': dict(by_type),
        'by_grade': {str(g): dict(by_grade[g]) for g in sorted(by_grade)},
        'samples': dict(samples),
    }
    with open(JSON_REPORT, 'w', encoding='utf-8') as jf:
        json.dump(report, jf, ensure_ascii=False, indent=2)
    print(f'JSON: {JSON_REPORT}')
    md = []
    md.append('# LaTeX Issues Report')
    md.append(f'**Date:** {datetime.now()}')
    md.append(f'**Total:** {total}')
    md.append(f'**With issues:** {len(issues_ids)}')
    md.append('')
    md.append('| Type | Count |')
    md.append('|---|---|')
    for it in checks:
        md.append(f'| {it} | {by_type.get(it,0)} |')
    md.append('')
    for it, sl in samples.items():
        md.append(f'### {it} ({by_type.get(it,0)})')
        for s in sl:
            md.append(f'- ID {s["id"]} (grade {s["grade"]}): {s["preview"][:150]}')
        md.append('')
    with open(MD_REPORT, 'w', encoding='utf-8') as mf:
        mf.write(chr(10).join(md))
    print(f'MD: {MD_REPORT}')
    print(f'TOTAL: {len(issues_ids)} issues out of {total}')
    for it in checks:
        c = by_type.get(it, 0)
        if c > 0:
            print(f'  {it}: {c}')


if __name__ == '__main__':
    analyze()

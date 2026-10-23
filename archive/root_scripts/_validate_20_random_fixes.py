# -*- coding: utf-8 -*-
"""
Validate 20 random AI-fixed tasks from bad_tasks_cache.json + report.
Checks LaTeX syntax and correspondence to solution.
All console output sanitized for cp1251 compatibility.
"""
import json
import random
import re
from pathlib import Path

CACHE_PATH = Path("pipeline/output/bad_tasks_cache.json")
REPORT_PATH = Path("pipeline/output/bad_tasks_report.json")

def _safe(text: str, maxlen: int = 0) -> str:
    """Strip all chars outside cp1251 printable range, replace with '?'.
       Optionally truncate to maxlen."""
    result = []
    for ch in str(text):
        if ord(ch) < 32 or ord(ch) > 255:
            result.append('?')
        else:
            result.append(ch)
    s = ''.join(result)
    if maxlen and len(s) > maxlen:
        s = s[:maxlen]
    return s


def check_latex_issues(text: str) -> list[str]:
    issues = []
    # Count $ delimiters
    dollar_count = text.count('$')
    if dollar_count % 2 != 0:
        issues.append(f"ODD $ signs ({dollar_count})")

    # Count $$ pairs
    dd_count = text.count('$$')
    if dd_count % 2 != 0:
        issues.append(f"ODD $$ count ({dd_count})")

    # Check braces in math mode
    in_math = False
    brace_balance = 0
    for ch in text:
        if ch == '$':
            in_math = not in_math
            if not in_math:
                brace_balance = 0
        if in_math:
            if ch == '{':
                brace_balance += 1
            elif ch == '}':
                brace_balance -= 1

    # Check \( and \) balance
    l_paren = text.count('\\(')
    r_paren = text.count('\\)')
    if l_paren != r_paren:
        issues.append(f"IMBALANCED \\(...\\) ({l_paren} vs {r_paren})")

    # Check \[ and \] balance
    l_bracket = text.count('\\[')
    r_bracket = text.count('\\]')
    if l_bracket != r_bracket:
        issues.append(f"IMBALANCED \\[...\\] ({l_bracket} vs {r_bracket})")

    # Check for broken unicode
    for ch in ['\uf8f1', '\uf8f2', '\uf8f3', '\uf8f4', '\ufffd']:
        if ch in text:
            issues.append(f"BROKEN UNICODE U+{ord(ch):04X}")

    return issues


def main():
    with open(REPORT_PATH, encoding='utf-8') as f:
        report = json.load(f)

    with open(CACHE_PATH, encoding='utf-8') as f:
        cache = json.load(f)

    # Build lookup: set_id_probnum -> entry from report
    report_lookup = {}
    for t in report['bad_tasks']:
        key = f"{t['set_id']}_{t['problem_num']}"
        report_lookup[key] = t

    # Get all cache keys that have valid extractions (not "Не удалось")
    valid_keys = [k for k, v in cache.items()
                  if len(v) > 50 and not v.startswith('Не удалось')]

    print(f"Cache entries: {len(cache)}, valid extractions: {len(valid_keys)}")

    random.seed(42)
    sample_keys = random.sample(valid_keys, min(20, len(valid_keys)))

    print(f"\n{'='*80}")
    print(f"VALIDATING {len(sample_keys)} RANDOM FIXED TASKS")
    print(f"{'='*80}\n")

    passed = 0
    issues_found = 0
    details = []

    for idx, key in enumerate(sample_keys, 1):
        new_text = cache[key]
        report_entry = report_lookup.get(key, {})
        old_text = report_entry.get('old_text', 'N/A')
        solution = report_entry.get('solution', 'N/A')
        set_id = report_entry.get('set_id', '?')
        prob_num = report_entry.get('problem_num', '?')
        olympiad = report_entry.get('olympiad', '?')
        grade = report_entry.get('grade', '?')

        print(f"--- #{idx} [{key}] {_safe(olympiad)} gr.{grade} prob#{prob_num} ---")
        print(f"  OLD: {_safe(old_text, 100)}")
        new_preview = new_text[:200].replace('\n', '\\n').replace('\r', '')
        print(f"  NEW: {_safe(new_preview, 200)}")

        latex_issues = check_latex_issues(new_text)

        # Ensure solution is a string
        if not isinstance(solution, str):
            solution = str(solution)

        # Check for solution correspondence
        sol_clean = solution.replace('\\n', '\n') if isinstance(solution, str) else ''
        new_clean = new_text.replace('\\n', '\n')

        # Heuristic: does the new text appear in the solution or vice versa?
        new_in_sol = len(new_clean) > 30 and new_clean[:30] in sol_clean
        sol_in_new = len(sol_clean) > 30 and sol_clean[:30] in new_clean
        has_correspondence = new_in_sol or sol_in_new

        issues = list(latex_issues)
        if not has_correspondence and len(new_clean) > 50 and len(sol_clean) > 50 and solution != 'N/A':
            issues.append("NO CORRESPONDENCE with solution (text differs significantly)")

        if issues:
            print(f"  ISSUES ({len(issues)}):")
            for iss in issues:
                print(f"    [!] {_safe(iss)}")
            print(f"  SOLUTION (first 100): {_safe(sol_clean, 100)}")
            issues_found += 1
        else:
            print(f"  [OK] LaTeX balanced, corresponds to solution")
            passed += 1

        details.append({
            'key': key,
            'olympiad': olympiad,
            'grade': grade,
            'prob_num': prob_num,
            'passed': len(issues) == 0,
            'issues': issues,
            'old_text': old_text[:200],
            'new_text': new_text[:300],
            'solution': solution[:300],
        })
        print()

    print(f"{'='*80}")
    print(f"RESULTS: {passed}/{len(sample_keys)} passed, {issues_found}/{len(sample_keys)} with issues")
    print(f"{'='*80}\n")

    # Save detailed report as JSON for later analysis
    report_path = Path("pipeline/output/validation_20_report.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_sampled': len(sample_keys),
            'passed': passed,
            'issues': issues_found,
            'sample_keys': sample_keys,
            'details': details,
        }, f, ensure_ascii=False, indent=2)
    print(f"JSON report saved to {report_path}")

    # Also save a text summary
    txt_path = Path("pipeline/output/validation_20_report.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"Validation Report for {len(sample_keys)} random fixed tasks\n")
        f.write(f"Passed: {passed}, Issues: {issues_found}\n\n")
        for d in details:
            status = "OK" if d['passed'] else f"ISSUES: {d['issues']}"
            f.write(f"  {d['key']} ({d['olympiad']} gr.{d['grade']} prob#{d['prob_num']}): {status}\n")
    print(f"Text report saved to {txt_path}")


if __name__ == '__main__':
    main()

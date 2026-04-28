#!/usr/bin/env python3
"""
Fix LaTeX issues in adaptive tasks (FORMYLA).
Usage:
  python scripts/fix_latex_adaptive.py --dry-run
  python scripts/fix_latex_adaptive.py --commit
"""
import sqlite3, re, json, os, sys, shutil
from datetime import datetime

DB_PATH = os.path.join("instance", "formyla.db")
BACKUP_DIR = os.path.join("data", "backups")
REPORT_DIR = os.path.join("data", "audit")

LATEX_N_CMDS = {
    'neq','nabla','notin','neg','nu','nleq','ngeq','nmid',
    'nsubseteq','nsupseteq','ncong','nsim','nrightarrow',
    'nleftarrow','not','newline','newcommand','nolimits',
    'nonumber','nparallel'
}


def fix_literal_backslash_n(text):
    """Fix literal backslash-n to real newlines."""
    BS = chr(92)
    # Double-escaped first
    text = text.replace(BS*2 + 'n', chr(10))
    # Now handle single literal backslash-n
    # But protect LaTeX commands like \neq etc.
    result = []
    i = 0
    while i < len(text):
        if text[i] == BS and i+1 < len(text) and text[i+1] == 'n':
            # Check if this is a LaTeX command
            rest = text[i+2:]
            is_cmd = False
            if rest and rest[0].isalpha():
                for cmd in LATEX_N_CMDS:
                    if ('n' + rest).startswith(cmd):
                        is_cmd = True
                        break
            if is_cmd:
                result.append(BS)
                result.append('n')
                i += 2
            else:
                result.append(chr(10))
                i += 2
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


def fix_bare_sqrt_frac(text):
    """Wrap bare \\frac{...}{...} and \\sqrt{...} in $...$."""
    BS = chr(92)
    # Fix \frac{...}{...} outside math mode
    # Simple approach: find \frac or \sqrt not preceded by $ and wrap
    changed = False
    # We need to check if each occurrence is inside math mode
    # Import build_math_map from analyzer
    def build_math_map(t):
        n = len(t)
        im = [False] * n
        ii = 0
        while ii < n:
            if ii < n-1 and t[ii] == BS and t[ii+1] == '(':
                j = t.find(BS+')', ii+2)
                if j != -1:
                    for k in range(ii, min(j+2, n)): im[k] = True
                    ii = j + 2; continue
            if ii < n-1 and t[ii] == BS and t[ii+1] == '[':
                j = t.find(BS+']', ii+2)
                if j != -1:
                    for k in range(ii, min(j+2, n)): im[k] = True
                    ii = j + 2; continue
            if ii < n-1 and t[ii] == '$' and t[ii+1] == '$':
                j = t.find('$$', ii+2)
                if j != -1:
                    for k in range(ii, min(j+2, n)): im[k] = True
                    ii = j + 2; continue
                else: ii += 2; continue
            if t[ii] == '$':
                j = t.find('$', ii+1)
                if j != -1:
                    for k in range(ii, j+1): im[k] = True
                    ii = j + 1; continue
                else: ii += 1; continue
            ii += 1
        return im

    # Find all bare \frac and \sqrt, wrap each in $...$
    # Process from end to start to preserve positions
    pat = re.compile(r'\\(sqrt|frac)')
    matches = list(pat.finditer(text))
    if not matches:
        return text
    in_math = build_math_map(text)
    bare = [m for m in matches if not in_math[m.start()]]
    if not bare:
        return text

    # For each bare match, find the extent of the expression
    # and wrap in $...$
    for m in reversed(bare):
        start = m.start()
        # Find end of expression
        pos = m.end()
        cmd = m.group(1)
        # Count braces
        groups_needed = 2 if cmd == 'frac' else 1
        end = pos
        for _ in range(groups_needed):
            # Skip whitespace
            while end < len(text) and text[end] in ' \t':
                end += 1
            if end < len(text) and text[end] == '{':
                depth = 1
                end += 1
                while end < len(text) and depth > 0:
                    if text[end] == '{': depth += 1
                    elif text[end] == '}': depth -= 1
                    end += 1
            else:
                # No brace - take single char/token
                if end < len(text):
                    end += 1
        # Also grab trailing content that looks like it belongs
        # (e.g. exponents, subscripts)
        while end < len(text) and text[end] in '^_':
            end += 1
            if end < len(text) and text[end] == '{':
                depth = 1
                end += 1
                while end < len(text) and depth > 0:
                    if text[end] == '{': depth += 1
                    elif text[end] == '}': depth -= 1
                    end += 1
            elif end < len(text):
                end += 1
        expr = text[start:end]
        text = text[:start] + '$' + expr + '$' + text[end:]
    return text


def apply_fixes(text):
    """Apply all fixes to text. Returns (new_text, list_of_fix_types)."""
    fixes = []
    original = text
    # 1. Fix literal backslash-n
    new = fix_literal_backslash_n(text)
    if new != text:
        fixes.append('HAS_LITERAL_BACKSLASH_N')
        text = new
    # 2. Fix bare sqrt/frac
    new = fix_bare_sqrt_frac(text)
    if new != text:
        fixes.append('BARE_SQRT_FRAC')
        text = new
    return text, fixes


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('--dry-run', '--commit'):
        print('Usage: python fix_latex_adaptive.py --dry-run|--commit')
        sys.exit(1)
    mode = sys.argv[1]
    commit = mode == '--commit'

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT id, class_level, task_text FROM adaptive_tasks').fetchall()
    print(f'Total tasks: {len(rows)}')

    # Ensure task_text_archive column exists
    cols = [r[1] for r in con.execute('PRAGMA table_info(adaptive_tasks)').fetchall()]
    if 'task_text_archive' not in cols:
        con.execute('ALTER TABLE adaptive_tasks ADD COLUMN task_text_archive TEXT')
        con.commit()
        print('Added column task_text_archive')

    if commit:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = os.path.join(BACKUP_DIR, f'formyla_db_{stamp}.db')
        shutil.copy2(DB_PATH, backup)
        print(f'Backup: {backup}')

    changes = []
    by_type = {}
    for row in rows:
        tid = row['id']
        text = row['task_text'] or ''
        new_text, fix_types = apply_fixes(text)
        if fix_types:
            changes.append({'id': tid, 'grade': row['class_level'],
                'old': text[:200], 'new': new_text[:200], 'types': fix_types})
            for ft in fix_types:
                by_type[ft] = by_type.get(ft, 0) + 1
            if commit:
                con.execute(
                    'UPDATE adaptive_tasks SET task_text_archive = task_text '
                    'WHERE id = ? AND task_text_archive IS NULL', (tid,))
                con.execute(
                    'UPDATE adaptive_tasks SET task_text = ? WHERE id = ?',
                    (new_text, tid))

    if commit:
        con.commit()
    con.close()

    # Report
    print(f'\nMode: {mode}')
    print(f'Tasks to fix: {len(changes)}')
    print(f'By type: {by_type}')
    print()
    # Show samples
    shown = {}
    for c in changes:
        for t in c['types']:
            shown.setdefault(t, 0)
            if shown[t] < 3:
                print(f'--- {t} | ID {c["id"]} (grade {c["grade"]}) ---')
                print(f'  OLD: {repr(c["old"])}')
                print(f'  NEW: {repr(c["new"])}')
                print()
                shown[t] += 1
    if commit:
        print(f'COMMITTED {len(changes)} changes.')
    else:
        print(f'DRY-RUN complete. Use --commit to apply.')


if __name__ == '__main__':
    main()

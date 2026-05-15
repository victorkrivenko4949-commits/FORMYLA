"""Fix LaTeX commands that lost their leading backslash because their JSON
was decoded with single-backslash escapes.

Symptoms in DB:
  - form-feed char (\\x0C) appears where '\\f...' was supposed to be
    (LLM wrote "\\frac" with single \\, JSON parser ate \\f as form-feed)
  - tab char (\\x09) appears where '\\t...' was meant
    ("\\triangle" -> tab + "riangle")
  - similarly: \\n (-> newline char), \\r (-> CR), \\b (-> backspace)

Strategy:
  1. Find every U+000C (form feed) and replace with the most likely LaTeX
     command starting with "\\f" — by looking at the trailing letters.
  2. Same for U+0009 (tab) -> "\\t..." commands. Real tabs in solutions are
     extremely unlikely (LLM emits spaces).
  3. Same for U+0008 (backspace).
  4. Newlines (U+000A) are tricky because they are real text separators.
     Only fix if directly followed by lowercase letters that form a known
     LaTeX command.
"""
import sqlite3
import os
import sys
import re
import json
import datetime as _dt

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "formyla.db")
BACKUP_DIR = os.path.join(ROOT, "adaptive_data", "_backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

# Known LaTeX commands by starting letter
LATEX_BY_LETTER = {
    "f": [
        "frac", "frak", "forall", "fbox", "floor",
    ],
    "t": [
        "triangle", "theta", "times", "tan", "to", "top", "tau", "text",
        "textbf", "textit", "tfrac",
    ],
    "b": [
        "binom", "bigcap", "bigcup", "bigoplus", "boxed",
        "begin", "bf", "bullet",
    ],
    "n": [
        "ne", "neq", "neg", "not", "ngeq", "nleq", "nmid", "ni",
        "nsubseteq", "nsupseteq", "newline", "nabla", "natural",
    ],
    "r": [
        "rightarrow", "Rightarrow", "Re", "rho", "rfloor", "rceil",
    ],
}

# Build a regex that matches each control char followed by lowercase letters
# and tries to find the longest known command name.
def restore_command(letter: str, tail: str) -> tuple[str, int]:
    """Return (replacement_with_backslash, chars_consumed_from_tail)."""
    cmds = LATEX_BY_LETTER.get(letter, [])
    # Try longest match
    for name in sorted(cmds, key=len, reverse=True):
        body = name[1:]  # without first letter
        if tail.startswith(body):
            return ("\\" + name, len(body))
    # Default: at minimum restore the leading backslash, even if we don't
    # know the command (better than a control character).
    return ("\\" + letter, 0)


CONTROL_MAP = {
    "\x0c": "f",  # form feed
    "\x09": "t",  # tab
    "\x08": "b",  # backspace
}

def fix_text(text: str) -> tuple[str, int]:
    """Return (new_text, num_replacements)."""
    if not text:
        return text, 0
    out = []
    i = 0
    n = len(text)
    fixes = 0
    while i < n:
        ch = text[i]
        if ch in CONTROL_MAP:
            letter = CONTROL_MAP[ch]
            # Restore leading "\\" + match best command
            tail = text[i + 1:]
            replacement, used = restore_command(letter, tail)
            out.append(replacement)
            i += 1 + used
            fixes += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out), fixes


FIELDS = ["task_text", "solution", "criteria_1_point", "criteria_2_points",
          "correct_answer", "llm_suggested_solution", "llm_suggested_answer"]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute(f"SELECT id, {', '.join(FIELDS)} FROM adaptive_tasks")
rows = cur.fetchall()
print(f"Scanning {len(rows)} tasks...")

backup_rows = []
total_fixes = 0
affected_tasks = 0

updates = []
for r in rows:
    new = {}
    fixes_this_row = 0
    for f in FIELDS:
        val = r[f]
        new_val, fixes = fix_text(val)
        if fixes:
            new[f] = new_val
            fixes_this_row += fixes
    if fixes_this_row:
        backup_rows.append({"id": r["id"], **{f: r[f] for f in FIELDS}})
        affected_tasks += 1
        total_fixes += fixes_this_row
        updates.append((r["id"], new))

print(f"Tasks needing fix: {affected_tasks}; total replacements: {total_fixes}")

if updates:
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"before_latex_command_fix_{ts}.json")
    with open(backup_path, "w", encoding="utf-8") as fp:
        json.dump(backup_rows, fp, ensure_ascii=False, indent=2)
    print(f"Backup: {backup_path}")

    for tid, new in updates:
        sets = ", ".join([f"{k}=?" for k in new.keys()])
        params = list(new.values()) + [tid]
        cur.execute(f"UPDATE adaptive_tasks SET {sets} WHERE id=?", params)
    conn.commit()
    print(f"Updated rows: {len(updates)}")

# Re-check
cur.execute(
    "SELECT COUNT(*) FROM adaptive_tasks "
    "WHERE solution LIKE ? OR solution LIKE ? OR solution LIKE ? "
    "   OR task_text LIKE ? OR task_text LIKE ? OR task_text LIKE ?",
    ("%\x0c%", "%\x09%", "%\x08%", "%\x0c%", "%\x09%", "%\x08%"),
)
print(f"Tasks still containing control chars: {cur.fetchone()[0]}")
conn.close()

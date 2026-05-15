"""Wrap bare LaTeX fragments in adaptive_tasks with proper MathJax delimiters.

Strategy:
- Walk through each text field; preserve regions already inside $..$, \\(..\\), \\[..\\].
- In remaining "plain" regions, find runs of math-looking content (LaTeX
  commands, ^{...}, _{...}, sqrt-like expressions) and wrap each run in \\(..\\).
- Idempotent: re-running on already-fixed text changes nothing.
"""

from __future__ import annotations
import sqlite3
import re
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "instance", "formyla.db")
FIELDS = ("task_text", "solution",
          "criteria_1_point", "criteria_2_points", "correct_answer")

# Match anything already wrapped: $..$, \( .. \), \[ .. \]
PROTECTED_RE = re.compile(
    r"(\$\$[\s\S]*?\$\$|\$[^\$\n]*?\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\])"
)

# A bare-math token: \command{...}, \command, ^{..}, _{..}, ^digit, _digit
BARE_MATH_RE = re.compile(
    r"(?:\\[A-Za-z]+(?:\{[^{}]*\})*"          # \frac{a}{b}, \sqrt{x}, \pi
    r"|\\[(),.;])"                             # \, \(, \) etc. very rare in plain
    r"|\^\{[^{}]*\}|\_\{[^{}]*\}"             # ^{...}, _{...}
    r"|\^[0-9A-Za-z]|\_[0-9A-Za-z]"           # ^2, _i
)


def wrap_runs(plain: str) -> str:
    """Find bare math tokens in plain text and wrap each MAXIMAL run with \\(...\\).

    A run is a contiguous span of math tokens possibly glued by digits, single
    letters or simple operators (+ - = * / ^ _ { } ( ) , .). Whitespace ends a run
    only if it is followed by clearly non-math text.
    """
    if not plain:
        return plain
    matches = list(BARE_MATH_RE.finditer(plain))
    if not matches:
        return plain

    # Decide expansion characters: math glue
    glue_re = re.compile(r"[0-9A-Za-zА-Яа-я\^\_\{\}\(\)\+\-\=\*/,.\s]")

    out_parts: list[str] = []
    cursor = 0
    i = 0
    n = len(plain)

    while i < len(matches):
        m = matches[i]
        # Expand left while we see math-glue characters; stop at strong word boundary
        start = m.start()
        # back up over operands/symbols (e.g. "30" in "30^{\circ}")
        while start > cursor:
            ch = plain[start - 1]
            if re.match(r"[0-9A-Za-z\)\}]", ch):
                start -= 1
                continue
            break

        end = m.end()
        # Greedily merge subsequent matches if separated only by glue chars
        j = i + 1
        while j < len(matches):
            gap = plain[end:matches[j].start()]
            # gap must be only glue chars and not contain Russian word characters
            if gap and (re.search(r"[А-Яа-я]{2,}", gap) or re.search(r"[A-Za-z]{3,}", gap)):
                break
            if gap and not all(glue_re.match(c) for c in gap):
                break
            end = matches[j].end()
            j += 1

        # Expand right over trailing operands
        while end < n:
            ch = plain[end]
            if re.match(r"[0-9A-Za-z\(\{]", ch):
                end += 1
                continue
            break

        # Append the prefix unchanged
        out_parts.append(plain[cursor:start])
        # Wrap the math run
        run = plain[start:end].rstrip()
        # If run is just a single character or empty, skip wrapping
        if len(run.strip()) >= 2:
            out_parts.append(f"\\({run}\\)")
            # restore trailing whitespace dropped by rstrip
            out_parts.append(plain[start:end][len(run):])
        else:
            out_parts.append(plain[start:end])
        cursor = end
        i = j

    out_parts.append(plain[cursor:])
    return "".join(out_parts)


def fix_text(s: str) -> str:
    if not s:
        return s
    # Split on protected segments; only fix unprotected ones
    parts = PROTECTED_RE.split(s)
    for k in range(0, len(parts), 2):
        parts[k] = wrap_runs(parts[k])
    return "".join(parts)


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    total = cur.fetchone()[0]
    print(f"Total tasks: {total}")

    cur.execute(f"SELECT id, {', '.join(FIELDS)} FROM adaptive_tasks")
    rows = cur.fetchall()

    updates = []
    for row in rows:
        rid = row[0]
        original = row[1:]
        fixed = tuple(fix_text(v) if isinstance(v, str) else v for v in original)
        if fixed != original:
            updates.append((*fixed, rid))

    print(f"Rows changed: {len(updates)}")
    if updates:
        set_clause = ", ".join(f"{f}=?" for f in FIELDS)
        cur.executemany(
            f"UPDATE adaptive_tasks SET {set_clause} WHERE id=?",
            updates,
        )
        conn.commit()
        print(f"Committed {len(updates)} updates")

    conn.close()


if __name__ == "__main__":
    main()

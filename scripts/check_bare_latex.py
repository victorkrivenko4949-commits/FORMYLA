"""Count adaptive tasks where text contains LaTeX commands NOT inside math delimiters."""
import sqlite3, re, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "instance", "formyla.db")

PROTECTED = re.compile(r"(\$\$[\s\S]*?\$\$|\$[^\$\n]*?\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\])")
BARE = re.compile(r"\\[A-Za-z]+|\^\{|_\{|(?<![A-Za-z])\^[0-9]|(?<![A-Za-z])_[0-9]")
FIELDS = ("task_text", "solution",
          "criteria_1_point", "criteria_2_points", "correct_answer")

c = sqlite3.connect(DB).cursor()
rows = c.execute(
    f"SELECT id, {', '.join(FIELDS)} FROM adaptive_tasks"
).fetchall()
totals = {f: 0 for f in FIELDS}
samples: dict[str, list] = {f: [] for f in FIELDS}
for row in rows:
    rid = row[0]
    for fname, val in zip(FIELDS, row[1:]):
        if not val:
            continue
        parts = PROTECTED.split(val)
        plain = "".join(parts[i] for i in range(0, len(parts), 2))
        if BARE.search(plain):
            totals[fname] += 1
            if len(samples[fname]) < 5:
                samples[fname].append((rid, plain[:200]))

for fname in FIELDS:
    print(f"\n=== {fname}: {totals[fname]} rows with bare LaTeX ===")
    for rid, snippet in samples[fname]:
        print(f"  id={rid}: {snippet!r}")
print(f"\nTOTAL fields with leakage: {sum(totals.values())}")

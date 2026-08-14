import json
import re
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("Usage: python fix_latex_json.py paste.txt paste_fixed.txt")

source = Path(sys.argv[1])
target = Path(sys.argv[2])
problem_ids = {15, 18}
pattern = re.compile(r"\\\\(?=[A-Za-z]+|[()\[\]{}])")
changed = 0

text = source.read_text(encoding="utf-8-sig")
try:
    data = json.loads(text)
    jsonl_mode = False
except json.JSONDecodeError:
    jsonl_mode = True
    data = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if line.strip():
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Invalid JSON on line {line_no}: {exc}\nFirst characters: {line[:80]!r}") from exc

def fix_record(record):
    global changed
    if not isinstance(record, dict) or record.get("idx") not in problem_ids:
        return
    payload = record.get("result_json")
    if not isinstance(payload, dict):
        return
    for field in ("statement", "answer", "solution"):
        value = payload.get(field)
        if isinstance(value, str):
            fixed, count = pattern.subn(r"\\", value)
            payload[field] = fixed
            changed += count

if isinstance(data, list):
    for record in data:
        fix_record(record)
elif isinstance(data, dict):
    if isinstance(data.get("items"), list):
        for record in data["items"]:
            fix_record(record)
    else:
        fix_record(data)
else:
    raise SystemExit("The JSON root must be an object or an array.")

if jsonl_mode:
    output = "\n".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in data) + "\n"
else:
    output = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

target.write_text(output, encoding="utf-8")
print(f"Saved {target}; fixed {changed} over-escaped LaTeX sequences.")

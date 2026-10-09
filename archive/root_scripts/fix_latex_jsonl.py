import json
import re
from pathlib import Path
import sys

if len(sys.argv) != 3:
    raise SystemExit("Usage: python fix_latex_jsonl.py paste.txt paste_fixed.txt")

source = Path(sys.argv[1])
target = Path(sys.argv[2])
problem_ids = {15, 18}
pattern = re.compile(r"\\\\(?=[A-Za-z]+|[()\[\]{}])")
changed = 0
lines = []

for line_no, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip():
        lines.append(line)
        continue
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON on line {line_no}: {exc}") from exc

    if record.get("idx") in problem_ids:
        payload = record.get("result_json", {})
        for field in ("statement", "answer", "solution"):
            value = payload.get(field)
            if isinstance(value, str):
                fixed, count = pattern.subn(r"\\", value)
                payload[field] = fixed
                changed += count

    lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))

target.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Saved {target}; fixed {changed} over-escaped LaTeX sequences.")

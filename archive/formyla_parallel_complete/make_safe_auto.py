from pathlib import Path
import re, sys

workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
src = Path("auto_formyla_until_clean.py")
dst = Path("auto_formyla_until_clean_safe.py")

s = src.read_text(encoding="utf-8", errors="replace")
s = re.sub(r"--workers\s+\d+", f"--workers {workers}", s)
s = re.sub(
    r"([\"']--workers[\"']\s*,\s*)[\"']\d+[\"']",
    lambda m: m.group(1) + repr(str(workers)),
    s
)

dst.write_text(s, encoding="utf-8")
print(f"OK: created {dst} with workers={workers}")

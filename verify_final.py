#!/usr/bin/env python3
"""Final comprehensive verification."""
import json
import re
import sys

with open("all_methods_real_final.json", "r", encoding="utf-8") as f:
    methods = json.load(f)

errors = []

# 1. Count
if len(methods) != 102:
    errors.append(f"Method count: {len(methods)}, expected 102")
else:
    print(f"1. Method count: {len(methods)} -- OK")

# 2. No \\(...\\) or \\[...\\] paired delimiters
found = 0
for m in methods:
    code = m["method_code"]
    for key, val in m.items():
        if isinstance(val, str):
            if re.search(r'\\\(.*?\\\)', val):
                errors.append(f"\\(...\\) in {code}.{key}")
                found += 1
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, str) and re.search(r'\\\(.*?\\\)', item):
                    errors.append(f"\\(...\\) in {code}.{key}[{i}]")
                    found += 1
if found == 0:
    print("2. No \\(...\\) paired delimiters -- OK")
else:
    print(f"2. {found} \\(...\\) occurrences -- FAIL")

# 3. Broken refs
valid = {m["method_code"] for m in methods}
for m in methods:
    code = m["method_code"]
    for field in ["prerequisites", "leads_to"]:
        for ref in m.get(field, []):
            if ref not in valid:
                errors.append(f"BROKEN: {code}.{field} -> {ref}")
if not any("BROKEN" in e for e in errors):
    print("3. No broken refs -- OK")
else:
    print("3. Broken refs found -- FAIL")

# 4. Long methods
long = {"E8", "E12", "E14", "E15", "F3"}
for m in methods:
    if m["method_code"] in long:
        l = len(m.get("worked_example_md", ""))
        if l > 13000:
            errors.append(f"Still long: {m['method_code']} = {l} chars")
            print(f"4. {m['method_code']}: {l} chars -- FAIL")
        else:
            print(f"4. {m['method_code']}: {l} chars -- OK")

# 5. JSON validity
with open("all_methods_real_final.json", "rb") as f:
    raw = f.read()
try:
    json.loads(raw.decode("utf-8"))
    print("5. JSON valid -- OK")
except Exception as e:
    errors.append(f"JSON invalid: {e}")
    print(f"5. JSON INVALID: {e}")

print(f"\n{'='*50}")
if errors:
    print(f"FAILED with {len(errors)} error(s):")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    sys.exit(0)

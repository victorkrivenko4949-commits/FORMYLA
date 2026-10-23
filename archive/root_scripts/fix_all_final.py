#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive fix for all_methods_real_final.json.

Problem 1: Fix \\(...\\) --> $...$ in F3 worked_example_md (only actual LaTeX delimiters).
           The \\[2pt] and \\[4pt] are LaTeX spacing -- leave them alone.
Problem 2: Truncate 5 long methods to ~12000 chars.
Problem 3: Remove broken refs A3, A4, A5, D14 from prerequisites/leads_to.
"""
import json
import re
import sys

INPUT = "all_methods_real_final.json"

LONG_METHODS = {"E8", "E12", "E14", "E15", "F3"}
MAX_LEN = 12000

BROKEN_REFS = {
    "B6":   {"prerequisites": ["A3"]},
    "C9":   {"prerequisites": ["A5"]},
    "D13":  {"leads_to": ["D14"]},
    "E6c":  {"prerequisites": ["A3"]},
    "E10a": {"prerequisites": ["A3"]},
    "E14a": {"prerequisites": ["A3", "A4"]},
    "F16":  {"prerequisites": ["A4"]},
    "F17":  {"prerequisites": ["A4"]},
}

# ---------------------------------------------------------------------------
# Problem 1: Fix \\(...\\) --> $...$
# NOTE: \\[2pt], \\[4pt] etc are LaTeX spacing commands -- NOT display math!
# Only fix \\(...\\) paired inline delimiters.
# ---------------------------------------------------------------------------
def fix_latex_delimiters(methods):
    count = 0
    affected = set()

    for method in methods:
        code = method.get("method_code", "?")
        for key in list(method.keys()):
            val = method[key]
            if isinstance(val, str):
                new_val, n = re.subn(r'\\\((.*?)\\\)', r'$\1$', val)
                if n > 0:
                    method[key] = new_val
                    count += n
                    affected.add(code)
            elif isinstance(val, list):
                new_list = []
                changed = False
                for item in val:
                    if isinstance(item, str):
                        new_item, n = re.subn(r'\\\((.*?)\\\)', r'$\1$', item)
                        new_list.append(new_item)
                        if n > 0:
                            count += n
                            changed = True
                    else:
                        new_list.append(item)
                if changed:
                    method[key] = new_list
                    affected.add(code)

    print(f"Problem 1: Fixed {count} LaTeX delimiters "
          f"in {len(affected)} methods: {sorted(affected)}")
    return methods


# ---------------------------------------------------------------------------
# Problem 2: Truncate long worked_example_md
# Strategy: find "**Что было главным:**" markers, keep up to 4 complete tasks.
# A task ends at the next "\n### Задача" or end of text.
# ---------------------------------------------------------------------------
def truncate_long_examples(methods):
    marker = "**Что было главным:**"

    for method in methods:
        code = method.get("method_code", "")
        if code not in LONG_METHODS:
            continue

        text = method.get("worked_example_md", "")
        orig_len = len(text)
        print(f"  {code}: {orig_len} chars", end="")

        if orig_len <= MAX_LEN:
            print(" -- under limit, skip")
            continue

        # Find all marker positions
        positions = []
        p = 0
        while True:
            idx = text.find(marker, p)
            if idx == -1:
                break
            positions.append(idx)
            p = idx + len(marker)

        # Find end of each task block
        task_ends = []
        for pos in positions:
            next_task = text.find("\n### Задача", pos + len(marker))
            if next_task == -1:
                next_task = len(text)
            task_ends.append(next_task)

        # Try keeping N tasks (from 4 down to 1) to fit under MAX_LEN
        max_tasks = min(len(positions), 4)
        best_end = None
        best_tasks = 0

        for n in range(max_tasks, 0, -1):
            end_pos = task_ends[n - 1]
            truncated = text[:end_pos].rstrip()
            if len(truncated) <= MAX_LEN:
                best_end = end_pos
                best_tasks = n
                break

        if best_end is None:
            # Even 1 task is too long -- cut at MAX_LEN
            truncated = text[:MAX_LEN].rstrip()
            last_nl = truncated.rfind('\n')
            if last_nl > MAX_LEN * 0.8:
                truncated = truncated[:last_nl].rstrip()
            best_tasks = 1
            print(f" --> {len(truncated)} chars (1 task, hard cut)")
        else:
            truncated = text[:best_end].rstrip()
            print(f" --> {len(truncated)} chars ({best_tasks} tasks)")

        method["worked_example_md"] = truncated

    return methods


# ---------------------------------------------------------------------------
# Problem 3: Remove broken references
# ---------------------------------------------------------------------------
def fix_broken_refs(methods):
    valid_codes = {m["method_code"] for m in methods}
    print(f"\nProblem 3: {len(valid_codes)} valid method codes")

    all_broken = {"A3", "A4", "A5", "D14"}
    for bc in sorted(all_broken):
        status = "MISSING (will remove)" if bc not in valid_codes else "EXISTS (skip)"
        print(f"  {bc}: {status}")

    removed_total = 0

    for method in methods:
        code = method.get("method_code", "")
        if code not in BROKEN_REFS:
            continue

        spec = BROKEN_REFS[code]
        for field, bad_codes in spec.items():
            if field not in method:
                continue
            arr = method[field]
            if not isinstance(arr, list):
                continue

            bad_set = set(bad_codes)
            new_arr = [x for x in arr if x not in bad_set]
            diff = len(arr) - len(new_arr)
            if diff > 0:
                removed_total += diff
                method[field] = new_arr
                removed_items = sorted(set(arr) - set(new_arr))
                print(f"  {code}.{field}: removed {diff}: {removed_items} "
                      f"(was {len(arr)}, now {len(new_arr)})")

    print(f"  Total removed: {removed_total}")
    return methods


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def verify(methods):
    errors = []

    # Check: no \\(...\\) left
    for method in methods:
        code = method.get("method_code", "?")
        for key, val in method.items():
            if isinstance(val, str):
                if re.search(r'\\\(.*?\\\)', val):
                    errors.append(f"LEFT OVER \\(...\\) in {code}.{key}")
            elif isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, str) and re.search(r'\\\(.*?\\\)', item):
                        errors.append(f"LEFT OVER \\(...\\) in {code}.{key}[{i}]")

    # Check: 102 methods
    if len(methods) != 102:
        errors.append(f"Method count: {len(methods)}, expected 102")

    # Check: no broken refs
    valid_codes = {m["method_code"] for m in methods}
    for method in methods:
        code = method.get("method_code", "?")
        for field in ["prerequisites", "leads_to"]:
            for ref in method.get(field, []):
                if ref not in valid_codes:
                    errors.append(f"BROKEN REF: {code}.{field} -> '{ref}'")

    # Check: long methods truncated
    for method in methods:
        code = method.get("method_code", "")
        if code in LONG_METHODS:
            real_len = len(method.get("worked_example_md", ""))
            if real_len > MAX_LEN + 2000:
                errors.append(f"STILL LONG: {code} = {real_len} chars (max ~{MAX_LEN})")

    if errors:
        print(f"\n{'='*60}")
        print(f"VERIFICATION FAILED: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print(f"\n{'='*60}")
        print("VERIFICATION PASSED")
        return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"Loading {INPUT}...")
    with open(INPUT, "r", encoding="utf-8") as f:
        methods = json.load(f)
    print(f"Loaded {len(methods)} methods\n")

    # Problem 1
    print("--- Problem 1: Fix LaTeX \\(...\\) --> $...$ ---")
    methods = fix_latex_delimiters(methods)

    # Problem 2
    print("\n--- Problem 2: Truncate long worked_example_md ---")
    methods = truncate_long_examples(methods)

    # Problem 3
    print("\n--- Problem 3: Remove broken references ---")
    methods = fix_broken_refs(methods)

    # Write
    print(f"\nWriting to {INPUT}...")
    with open(INPUT, "w", encoding="utf-8") as f:
        json.dump(methods, f, ensure_ascii=False, indent=2)
    print("Done.")

    # Re-read and verify
    with open(INPUT, "r", encoding="utf-8") as f:
        methods2 = json.load(f)

    print("\n--- Verification ---")
    ok = verify(methods2)

    if ok:
        print("\nAll checks passed. File is clean.")
    else:
        print("\nIssues remain -- review manually.")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

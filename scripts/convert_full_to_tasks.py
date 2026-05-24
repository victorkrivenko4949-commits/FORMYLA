# -*- coding: utf-8 -*-
"""Convert vsosh9_2027_full_v3.json (delivery format) → vsosh_9_2027_tasks.json
(format expected by scripts/import_olympiad.py + schemas/olympiad.py:TaskSchema).

Source schema (full_v3.json):
    {
      "course": ..., "version": ..., "packs": [...],
      "problems": [
        {
          "id": "vsosh-9-2027-topic-1-001",
          "topic_pack": "vsosh-9-2027-topic-1",
          "problem_number": 1,
          "color": "green",
          "method_primary": "A1",
          "method_secondary": null|"B1",
          "statement_md": "...",
          "answer": "...",
          "solution_md": "...",
          "source_prototype": "...",
          ...  # other fields (tags, source_type, difficulty_level,
                #               topic_title, competition, grade) are dropped
        },
        ...
      ]
    }

Target schema (TaskSchema, extra='forbid'):
    {
      "probnik_code": "vsosh-9-2027-topic-1",
      "number":       "1.1",
      "sort_order":   1,
      "difficulty":   "green",
      "method_primary":   "A1",
      "method_secondary": null|"B1",
      "condition_md": "...",
      "idea_md":      "...",        ← REQUIRED, missing in source → stub
      "solution_md":  "...",
      "answer":       "...",
      "source_prototype": "...",
      "estimated_minutes": null|int,  (omitted)
      "max_score": 7                  (default)
    }

Per release decision "L+A":
- `idea_md` populated with a non-empty placeholder phrase (200/200 problems).
- `estimated_minutes`, `max_score` are NOT set (defaults are used).
- The target file is overwritten; previous version goes to .bak.<timestamp>.

Usage:
    python scripts/convert_full_to_tasks.py \\
        --input  data/courses/vsosh-9-2027/vsosh9_2027_full_v3.json \\
        --output data/olympiads/vsosh_9_2027_tasks.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import sys
from typing import Any, Dict, List

IDEA_STUB = (
    "Идея решения раскрывается в подробном разборе ниже — "
    "следите за ключевыми шагами в разделе «Решение»."
)


def _load_full(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Input file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "problems" not in data:
        raise ValueError(
            f"{path}: expected top-level object with 'problems' key, "
            f"got {type(data).__name__}"
        )
    return data


def _convert_one(p: Dict[str, Any], idx_in_pack: Dict[str, int]) -> Dict[str, Any]:
    """Map one problem dict → one TaskSchema-shaped dict."""
    probnik_code = p["topic_pack"]
    # number: "pack_n.problem_n" — e.g. topic-1 №3 → "1.3".
    # Pack number is parsed from the trailing integer of topic_pack.
    pack_suffix = probnik_code.rsplit("-", 1)[-1]
    try:
        pack_n = int(pack_suffix)
    except ValueError:
        raise ValueError(
            f"Cannot parse pack number from topic_pack={probnik_code!r}"
        )
    n = int(p["problem_number"])
    number_str = f"{pack_n}.{n}"

    # sort_order: monotonic 1..N within each probnik.
    idx_in_pack[probnik_code] = idx_in_pack.get(probnik_code, 0) + 1
    sort_order = idx_in_pack[probnik_code]

    # difficulty: TaskSchema.DifficultyLiteral = {green,yellow,orange,red}.
    color = p.get("color")
    if color not in ("green", "yellow", "orange", "red", None):
        raise ValueError(
            f"Problem {p.get('id')!r}: unexpected color={color!r}"
        )

    out = {
        "probnik_code": probnik_code,
        "number": number_str,
        "sort_order": sort_order,
        "difficulty": color,
        "method_primary": p["method_primary"],
        "method_secondary": p.get("method_secondary"),
        "condition_md": p["statement_md"],
        "idea_md": IDEA_STUB,
        "solution_md": p["solution_md"],
        "answer": p.get("answer"),
        "source_prototype": p.get("source_prototype"),
    }
    # Drop None-valued OPTIONAL fields if Pydantic forbids them as None.
    # (TaskSchema accepts None for method_secondary/answer/source_prototype
    # since they are Optional, so leaving them is fine.)
    return out


def convert(input_path: str, output_path: str) -> Dict[str, int]:
    full = _load_full(input_path)
    problems: List[Dict[str, Any]] = full["problems"]
    if not isinstance(problems, list):
        raise ValueError("'problems' must be a list")

    declared_total = full.get("total_problems")
    if declared_total is not None and declared_total != len(problems):
        print(
            f"⚠️  total_problems={declared_total} but len(problems)={len(problems)}",
            file=sys.stderr,
        )

    # Sort to ensure stable sort_order: by (topic_pack, problem_number).
    problems_sorted = sorted(
        problems,
        key=lambda x: (x["topic_pack"], int(x["problem_number"])),
    )

    idx_in_pack: Dict[str, int] = {}
    out_rows: List[Dict[str, Any]] = []
    pack_counts: Dict[str, int] = {}
    for p in problems_sorted:
        row = _convert_one(p, idx_in_pack)
        out_rows.append(row)
        pack_counts[row["probnik_code"]] = pack_counts.get(row["probnik_code"], 0) + 1

    # Backup existing output, if any.
    if os.path.isfile(output_path):
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = f"{output_path}.bak.{ts}"
        shutil.copy2(output_path, bak)
        print(f"📦 Backup: {output_path} → {bak}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out_rows, f, ensure_ascii=False, indent=2)

    print(f"✅ Wrote {len(out_rows)} tasks → {output_path}")
    print("📊 Per-probnik counts:")
    for code in sorted(pack_counts):
        print(f"   {code}: {pack_counts[code]}")

    return {"total": len(out_rows), "packs": len(pack_counts)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="convert_full_to_tasks")
    p.add_argument("--input", required=True, help="Path to full_v3.json")
    p.add_argument("--output", required=True, help="Path to tasks.json")
    args = p.parse_args(argv)
    try:
        convert(args.input, args.output)
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

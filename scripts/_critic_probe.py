# -*- coding: utf-8 -*-
"""
Direct probe of the Gemini critic — bypasses the full pipeline.
Reads a problem, a generated code file and a PNG, then asks Gemini what's
wrong with the drawing.  Used to sanity-check that the critic actually
reacts to imperfect drawings (and isn't just always returning []).
"""
import argparse
import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# Ensure critic is "enabled" so the constant resolves to True (not strictly
# required for _critique_with_gemini itself, but it keeps logging consistent).
os.environ.setdefault("DRAWING_CRITIC_ENABLED", "1")

from services.drawing_service import (  # noqa: E402
    _critique_with_gemini,
    MODEL_CRITIC,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--problem-file", required=True)
    p.add_argument("--code-file", required=True)
    p.add_argument("--png-file", required=True)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    with open(args.problem_file, "r", encoding="utf-8") as f:
        problem = f.read().strip()
    with open(args.code_file, "r", encoding="utf-8") as f:
        code = f.read()
    with open(args.png_file, "rb") as f:
        png = f.read()

    print("=" * 70)
    print(" Critic probe")
    print("=" * 70)
    print("  model       :", MODEL_CRITIC)
    print("  problem_file:", args.problem_file)
    print("  code_file   :", args.code_file, "(" + str(len(code)) + " chars)")
    print("  png_file    :", args.png_file, "(" + str(len(png)) + " bytes)")
    print("  calling gemini ...")
    sys.stdout.flush()

    findings, cost = _critique_with_gemini(problem, code, png)

    print("-" * 70)
    print("  cost_usd       :", cost)
    print("  findings_count :", len(findings))
    for i, f in enumerate(findings, 1):
        print()
        print("  [" + str(i) + "] " + f.id + " | " + f.severity)
        print("      title    :", f.title)
        print("      detail   :", f.detail)
        print("      fix_hint :", f.fix_hint)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({
                "model": MODEL_CRITIC,
                "cost_usd": cost,
                "findings": [dataclasses.asdict(f) for f in findings],
            }, fh, ensure_ascii=False, indent=2)
        print()
        print("  saved to:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

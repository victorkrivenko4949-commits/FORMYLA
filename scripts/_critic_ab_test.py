# -*- coding: utf-8 -*-
"""
A/B test harness for the drawing critic.

Runs `services.drawing_service.generate_drawing()` ONCE for a single problem
and dumps everything we need to compare with another run:
  - <out_dir>/<tag>.png            -- final rendered image
  - <out_dir>/<tag>.code.py        -- final matplotlib code
  - <out_dir>/<tag>.result.json    -- meta (render_ms, cost, findings, attempts)

This script is INTENTIONALLY single-shot.  Because
`services.drawing_service.CRITIC_ENABLED` is evaluated at module-import
time (it reads `DRAWING_CRITIC_ENABLED` once), enabling/disabling the
critic requires a fresh Python process for each leg of the A/B.

Usage (cmd.exe):
    set DRAWING_CRITIC_ENABLED=0
    python scripts/_critic_ab_test.py --tag baseline --problem-file scripts/_critic_ab_problem.txt

    set DRAWING_CRITIC_ENABLED=1
    python scripts/_critic_ab_test.py --tag with_critic --problem-file scripts/_critic_ab_problem.txt
"""
import argparse
import dataclasses
import json
import os
import sys
import time

# Make project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# IMPORTANT: import drawing_service AFTER load_dotenv() but the value of
# DRAWING_CRITIC_ENABLED must already be present in the environment when
# this module is imported (it's frozen into CRITIC_ENABLED at import time).
from services.drawing_service import (  # noqa: E402
    generate_drawing,
    CRITIC_ENABLED,
    MODEL_PRIMARY,
    MODEL_CRITIC,
    MAX_CRITIQUE_ROUNDS,
)


def _finding_to_dict(f) -> dict:
    # CritiqueFinding is a dataclass
    try:
        return dataclasses.asdict(f)
    except TypeError:
        return {
            "id": getattr(f, "id", None),
            "severity": getattr(f, "severity", None),
            "title": getattr(f, "title", None),
            "detail": getattr(f, "detail", None),
            "fix_hint": getattr(f, "fix_hint", None),
            "claude_decision": getattr(f, "claude_decision", None),
            "claude_reasoning": getattr(f, "claude_reasoning", None),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True,
                        help="prefix for output files, e.g. 'baseline'")
    parser.add_argument("--problem-file", required=True,
                        help="path to UTF-8 text file with the problem")
    parser.add_argument("--out-dir", default="scripts/_critic_ab_out",
                        help="directory for the artifacts")
    args = parser.parse_args()

    with open(args.problem_file, "r", encoding="utf-8") as fh:
        problem = fh.read().strip()
    if not problem:
        print("[error] problem file is empty", file=sys.stderr)
        return 2

    os.makedirs(args.out_dir, exist_ok=True)

    env_flag = os.environ.get("DRAWING_CRITIC_ENABLED", "<unset>")
    print("=" * 70)
    print(" FORMYLA -- drawing critic A/B harness")
    print("=" * 70)
    print("  tag                       :", args.tag)
    print("  DRAWING_CRITIC_ENABLED env:", env_flag)
    print("  CRITIC_ENABLED (frozen)   :", CRITIC_ENABLED)
    print("  MODEL_PRIMARY             :", MODEL_PRIMARY)
    print("  MODEL_CRITIC              :", MODEL_CRITIC)
    print("  MAX_CRITIQUE_ROUNDS       :", MAX_CRITIQUE_ROUNDS)
    print("  problem (first 200 chars) :")
    print("   ", problem[:200].replace("\n", " "))
    print("-" * 70)
    print("  generating ... (this can take 15-90 s)")
    sys.stdout.flush()

    started = time.time()
    try:
        result = generate_drawing(problem, app_root=os.getcwd(),
                                  use_cache=False)
    except Exception as e:
        wall_ms = int((time.time() - started) * 1000)
        err = {
            "tag": args.tag,
            "ok": False,
            "exception_type": type(e).__name__,
            "exception_msg": str(e)[:2000],
            "wall_ms": wall_ms,
            "critic_enabled_env": env_flag,
            "critic_enabled_frozen": CRITIC_ENABLED,
        }
        err_path = os.path.join(args.out_dir, args.tag + ".error.json")
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(err, f, ensure_ascii=False, indent=2)
        print("[FAILED] " + type(e).__name__ + ": " + str(e)[:300])
        print("        wrote " + err_path)
        return 1

    wall_ms = int((time.time() - started) * 1000)

    png_path = os.path.join(args.out_dir, args.tag + ".png")
    code_path = os.path.join(args.out_dir, args.tag + ".code.py")
    json_path = os.path.join(args.out_dir, args.tag + ".result.json")

    with open(png_path, "wb") as f:
        f.write(result.image_bytes)
    with open(code_path, "w", encoding="utf-8") as f:
        f.write(result.code or "")

    summary = {
        "tag": args.tag,
        "ok": True,
        "critic_enabled_env": env_flag,
        "critic_enabled_frozen": CRITIC_ENABLED,
        "model": result.model,
        "render_ms": result.render_ms,
        "wall_ms": wall_ms,
        "cost_usd": result.cost_usd,
        "cache_hit": result.cache_hit,
        "repair_iters": result.repair_iters,
        "image_bytes": len(result.image_bytes),
        "critique_rounds": getattr(result, "critique_rounds", 0),
        "critique_accepted": getattr(result, "critique_accepted", 0),
        "critique_rejected": getattr(result, "critique_rejected", 0),
        "critique_findings": [
            _finding_to_dict(f)
            for f in (getattr(result, "critique_findings", []) or [])
        ],
        "attempts": result.attempts,
        "problem_first_200": problem[:200],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("[OK]")
    print("  render_ms          :", result.render_ms)
    print("  wall_ms            :", wall_ms)
    print("  cost_usd           :", result.cost_usd)
    print("  repair_iters       :", result.repair_iters)
    print("  critique_rounds    :", getattr(result, "critique_rounds", 0))
    print("  critique_accepted  :", getattr(result, "critique_accepted", 0))
    print("  critique_rejected  :", getattr(result, "critique_rejected", 0))
    print("  findings_count     :",
          len(getattr(result, "critique_findings", []) or []))
    print("  image_bytes        :", len(result.image_bytes))
    print("  attempts:")
    for a in result.attempts:
        print("    -", a)
    print("  ---")
    print("  png  ->", png_path)
    print("  code ->", code_path)
    print("  json ->", json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

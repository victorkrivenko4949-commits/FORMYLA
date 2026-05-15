# -*- coding: utf-8 -*-
# Measure end-to-end drawing pipeline latency with critics ENABLED.
#
# Usage:
#     python scripts/_probe_critic_latency.py
#
# Env knobs:
#   PROBE_PROBLEM            - problem text (utf-8). Defaults to the
#                              hard-coded "ortocentre" problem below.
#   DRAWING_CRITIC_ENABLED   - forced ON inside this probe.
#   DRAWING_COSMETIC_CRITIC  - forced ON inside this probe.
#
# Reads OPENROUTER_API_KEY from .env. Bypasses the on-disk PNG cache
# (use_cache=False) so every run is a real LLM round trip.
from __future__ import annotations

import logging
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

# Force both critics ON for this probe regardless of shell env.
os.environ["DRAWING_CRITIC_ENABLED"] = "1"
os.environ.setdefault("DRAWING_COSMETIC_CRITIC", "1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Import AFTER env is set so module-level flags capture it.
from services import drawing_service as ds  # noqa: E402

assert ds.CRITIC_ENABLED is True, "geometric critic flag did not take effect"

_DEFAULT_PROBLEM = (
    "Дан остроугольный треугольник ABC. H - ортоцентр, O - центр описанной "
    "окружности, M - середина BC (медиана AM). Известно, что AH = 2 OM. "
    "Построить чертёж: треугольник ABC, описанную окружность, точки H, O, M, "
    "основание высоты H1 из A на BC, высоту AH1 и медиану AM."
)
PROBLEM = os.environ.get("PROBE_PROBLEM", _DEFAULT_PROBLEM)


def main():
    print("=" * 60)
    print("PROBE: drawing pipeline with critics ENABLED")
    print("CRITIC_ENABLED          =", ds.CRITIC_ENABLED)
    print("COSMETIC_CRITIC_ENABLED =", ds.COSMETIC_CRITIC_ENABLED)
    print("MODEL_PRIMARY  =", ds.MODEL_PRIMARY)
    print("MODEL_CRITIC   =", ds.MODEL_CRITIC)
    print("MAX_REPAIR_ITERS    =", ds.MAX_REPAIR_ITERS)
    print("MAX_CRITIQUE_ROUNDS =", ds.MAX_CRITIQUE_ROUNDS)
    print("=" * 60)
    print("PROBLEM:", PROBLEM)
    print("=" * 60)

    t0 = time.time()
    result = ds.generate_drawing(PROBLEM, app_root=ROOT, use_cache=False)
    total = time.time() - t0

    print()
    print("=" * 60)
    print("RESULT")
    print("  total wall time:    %.2fs" % total)
    print("  result.render_ms:   %dms" % result.render_ms)
    print("  cache_hit:          %s" % result.cache_hit)
    print("  model:              %s" % result.model)
    print("  repair_iters:       %d" % result.repair_iters)
    print("  critique_rounds:    %d" % result.critique_rounds)
    print("  critique_accepted:  %d" % result.critique_accepted)
    print("  critique_rejected:  %d" % result.critique_rejected)
    print("  cost_usd:           $%.6f" % result.cost_usd)
    print("  image_bytes:        %d bytes" % len(result.image_bytes))
    print()
    print("ATTEMPTS:")
    for a in result.attempts:
        print(" ", a)
    print()
    if result.critique_findings:
        print("FINDINGS:")
        for f in result.critique_findings:
            print("  [%s|%s] %s" % (f.id, f.severity, f.title))
            print("    detail:   ", f.detail[:200])
            print("    fix_hint: ", f.fix_hint[:200])
            print("    decision: ", f.claude_decision, "->",
                  (f.claude_reasoning or "")[:200])

    out_png = os.path.join(HERE, "_probe_critic_out.png")
    with open(out_png, "wb") as f:
        f.write(result.image_bytes)
    out_code = os.path.join(HERE, "_probe_critic_out.code.py")
    with open(out_code, "w", encoding="utf-8") as f:
        f.write(result.code)
    print()
    print("PNG  ->", out_png)
    print("Code ->", out_code)


if __name__ == "__main__":
    main()

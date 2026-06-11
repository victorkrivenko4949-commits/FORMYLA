# -*- coding: utf-8 -*-
"""Standalone runner for the additive VsOSH-10/11 seeder.

Usage on Render One-Off Shell (or any worker):
    python -m scripts.seed_vsosh_10_11

Reads data/olympiads/vsosh_10_11_full.json (committed in repo) and
idempotently inserts missing Probnik/OlympiadTask/MethodTask rows for
grade=10 and grade=11. Does NOT touch grade=9 records.

Exit code 0 on success (status in {ok, skipped, disabled}), 1 on error.
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    # Force-enable the flag in case env defaults differ on Render One-Off Job.
    os.environ.setdefault("VSOSH10_2027_FORCE_IMPORT", "1")

    # Import after env is set so the in-boot hook also sees the flag.
    from app import app, db  # noqa: E402
    from services.vsosh_10_11_additive_seed import run_vsosh_10_11_additive_seed  # noqa: E402

    result = run_vsosh_10_11_additive_seed(app, db)
    print("[seed_vsosh_10_11] result =", json.dumps(result, ensure_ascii=False, default=str))

    status = (result or {}).get("status")
    if status in ("ok", "skipped", "disabled"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
# Diagnostic endpoint for /drawing pipeline.
#
# GET /api/drawing/diag?token=<DRAWING_DIAG_TOKEN>
#
# Returns the runtime configuration that was loaded when the worker
# process started.  This is the single source of truth: if a flag is
# False here, the pipeline is running without that stage *regardless*
# of what the Render Dashboard shows -- it means the worker was started
# BEFORE that env var was set and never reloaded.
#
# Also returns metadata for the most recent DrawingGeneration rows so
# you can see exactly which stages fired for each request.

import json
import os

from flask import Blueprint, jsonify, request


drawing_diag_bp = Blueprint("drawing_diag", __name__)


def _token_ok() -> bool:
    expected = (os.environ.get("DRAWING_DIAG_TOKEN") or "").strip()
    if not expected:
        # If no token is configured, allow access ONLY from localhost.
        # Render's outbound IP is not localhost, so on prod this gate
        # is effectively closed until you set the env var.
        remote = (request.remote_addr or "").strip()
        return remote in ("127.0.0.1", "::1", "localhost")
    got = (request.args.get("token") or "").strip()
    return got == expected


@drawing_diag_bp.route("/api/drawing/diag", methods=["GET"])
def diag():
    if not _token_ok():
        return jsonify({"error": "forbidden"}), 403

    # Import lazily so a broken drawing_service module still lets us
    # see the failure mode.
    info: dict = {}
    try:
        from services import drawing_service as ds
        info["module_loaded"] = True
        info["MODEL_PRIMARY"] = getattr(ds, "MODEL_PRIMARY", None)
        info["MODEL_CRITIC"] = getattr(ds, "MODEL_CRITIC", None)
        info["MODEL_ARCHITECT"] = getattr(ds, "MODEL_ARCHITECT", None)
        info["CRITIC_ENABLED"] = bool(getattr(ds, "CRITIC_ENABLED", False))
        info["ARCHITECT_ENABLED"] = bool(getattr(ds, "ARCHITECT_ENABLED", False))
        info["COSMETIC_CRITIC_ENABLED"] = bool(
            getattr(ds, "COSMETIC_CRITIC_ENABLED", False)
        )
        info["MAX_REPAIR_ITERS"] = getattr(ds, "MAX_REPAIR_ITERS", None)
        info["MAX_CRITIQUE_ROUNDS"] = getattr(ds, "MAX_CRITIQUE_ROUNDS", None)
    except Exception as e:
        info["module_loaded"] = False
        info["import_error"] = repr(e)

    # Raw env (so you can compare what the OS actually exposes to the
    # worker against what the module captured at import time).
    info["env_seen"] = {
        "DRAWING_CRITIC_ENABLED": os.environ.get("DRAWING_CRITIC_ENABLED"),
        "DRAWING_ARCHITECT": os.environ.get("DRAWING_ARCHITECT"),
        "DRAWING_COSMETIC_CRITIC": os.environ.get("DRAWING_COSMETIC_CRITIC"),
    }

    # Last N rows of DrawingGeneration so you can see whether the
    # critique stage actually ran for recent requests.
    try:
        from models import db, DrawingGeneration
        rows = (
            DrawingGeneration.query
            .order_by(DrawingGeneration.id.desc())
            .limit(5)
            .all()
        )
        info["last_5"] = []
        for r in rows:
            findings = None
            try:
                findings = (
                    json.loads(r.critique_findings_json)
                    if r.critique_findings_json else None
                )
            except Exception:
                findings = None
            info["last_5"].append({
                "id": r.id,
                "status": r.status,
                "model": r.model,
                "cost_usd": r.cost_usd,
                "render_ms": r.render_ms,
                "repair_iters": r.repair_iters,
                "critique_rounds": r.critique_rounds,
                "critique_accepted": r.critique_accepted,
                "critique_rejected": r.critique_rejected,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "problem_preview": (r.problem or "")[:120],
                "error_preview": (r.error or "")[:200] if r.error else None,
                "critique_findings": findings,
            })
    except Exception as e:
        info["history_error"] = repr(e)

    return jsonify(info)

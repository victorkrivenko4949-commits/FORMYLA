# -*- coding: utf-8 -*-
"""Blueprint for /drawing history feature.

Endpoints:
    GET    /api/drawing/history?limit=N&offset=M
    DELETE /api/drawing/history/ROW_ID
    GET    /drawing/history

Only successful generations with an existing PNG file are returned.
Users only see their own rows. Anonymous users see an empty list.
"""

from __future__ import annotations

import logging
import os

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    url_for,
)

try:
    from flask_login import current_user, login_required
except Exception:  # pragma: no cover
    current_user = None

    def login_required(fn):
        return fn


logger = logging.getLogger(__name__)

drawing_history_bp = Blueprint("drawing_history", __name__)


# Max page size for /api/drawing/history (DoS guard).
MAX_LIMIT = 50
DEFAULT_LIMIT = 10


def _current_uid():
    try:
        if current_user is not None and getattr(current_user, "is_authenticated", False):
            return getattr(current_user, "id", None)
    except Exception:
        pass
    return None


def _image_url_from_path(image_path):
    """Convert an absolute path like /.../static/generated/foo.png to URL."""
    if not image_path:
        return None
    try:
        basename = os.path.basename(image_path)
        if not basename:
            return None
        # Confirm the file still exists on disk; if it was deleted, return
        # None so the frontend can hide the broken card.
        if not os.path.exists(image_path):
            return None
        return url_for("static", filename="generated/" + basename)
    except Exception:
        return None


def _row_to_dict(row):
    return {
        "id": row.id,
        "problem": row.problem or "",
        "model": row.model,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "render_ms": row.render_ms,
        "cost_usd": row.cost_usd,
        "repair_iters": row.repair_iters,
        "critique_rounds": row.critique_rounds,
        "image_url": _image_url_from_path(row.image_path),
    }


@drawing_history_bp.route("/api/drawing/history", methods=["GET"])
def api_history_list():
    uid = _current_uid()
    if uid is None:
        # Anonymous: empty list, not an error -- the UI can just hide.
        return jsonify({"items": [], "total": 0})

    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))

    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    offset = max(0, offset)

    try:
        from models import DrawingGeneration
        q = (
            DrawingGeneration.query
            .filter(DrawingGeneration.user_id == uid)
            .filter(DrawingGeneration.status.in_(("ok", "cache_hit")))
            .filter(DrawingGeneration.image_path.isnot(None))
            .order_by(DrawingGeneration.id.desc())
        )
        total = q.count()
        rows = q.offset(offset).limit(limit).all()
        items = [_row_to_dict(r) for r in rows]
        # Drop entries whose PNG was deleted from disk -- the frontend
        # should not show broken thumbnails.
        items = [it for it in items if it.get("image_url")]
        return jsonify({"items": items, "total": total})
    except Exception as e:
        logger.warning("[drawing_history] list failed: %s", e)
        return jsonify({"error": "internal", "detail": str(e)}), 500


@drawing_history_bp.route(
    "/api/drawing/history/<int:row_id>", methods=["DELETE"]
)
def api_history_delete(row_id: int):
    uid = _current_uid()
    if uid is None:
        return jsonify({"error": "forbidden"}), 403

    try:
        from models import db, DrawingGeneration
        row = DrawingGeneration.query.filter_by(id=row_id, user_id=uid).first()
        if row is None:
            return jsonify({"error": "not_found"}), 404

        # Best-effort: remove the PNG from disk too.
        path = row.image_path
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                logger.info(
                    "[drawing_history] could not unlink %s: %s", path, e
                )

        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True, "id": row_id})
    except Exception as e:
        logger.warning("[drawing_history] delete failed: %s", e)
        return jsonify({"error": "internal", "detail": str(e)}), 500


@drawing_history_bp.route("/drawing/history", methods=["GET"])
@login_required
def history_page():
    # Server-rendered page lists ALL the user's drawings, paginated.
    uid = _current_uid()
    if uid is None:
        abort(403)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    per_page = 24
    from models import DrawingGeneration
    q = (
        DrawingGeneration.query
        .filter(DrawingGeneration.user_id == uid)
        .filter(DrawingGeneration.status.in_(("ok", "cache_hit")))
        .filter(DrawingGeneration.image_path.isnot(None))
        .order_by(DrawingGeneration.id.desc())
    )
    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()
    items = [_row_to_dict(r) for r in rows]
    items = [it for it in items if it.get("image_url")]
    last_page = max(1, (total + per_page - 1) // per_page)
    return render_template(
        "drawing_history.html",
        items=items,
        page=page,
        last_page=last_page,
        total=total,
    )

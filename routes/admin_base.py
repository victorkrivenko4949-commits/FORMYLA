# -*- coding: utf-8 -*-
"""
routes/admin_base.py — раздел «База» в админ-статистике (ADMIN_BASE_V1, 06.10.2026).

Маршруты (только для админа, current_user.is_admin):
  GET /admin/base                      — сводка по ВСЕЙ базе: все задачи, решения,
                                         ответы, чертежи, чат, события + список
                                         пользователей (кликабельный) + лента.
  GET /admin/base?q=lavrik             — поиск пользователя по имени / email / id.
  GET /admin/base/user/<id>            — карточка конкретного пользователя: всё,
                                         что он сделал, по каждой таблице.
  GET /admin/base/api/summary          — JSON сводки.
  GET /admin/base/api/users?q=         — JSON списка пользователей.
  GET /admin/base/api/user/<id>        — JSON карточки пользователя.
  GET /admin/base/api/feed             — JSON ленты последних событий.

Регистрация: автоматически через routes/__init__.py (см. там), либо вручную:
    from routes.admin_base import admin_base_bp
    app.register_blueprint(admin_base_bp)
"""
from __future__ import annotations

import logging

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from services import admin_base_stats as _abs

logger = logging.getLogger(__name__)

admin_base_bp = Blueprint("admin_base", __name__)


def _is_admin() -> bool:
    return getattr(current_user, "is_admin", False) is True


def _guard():
    if not _is_admin():
        logger.warning("[admin_base] forbidden for user=%r path=%s",
                       getattr(current_user, "id", None), request.path)
        abort(403)


@admin_base_bp.route("/admin/base")
@login_required
def admin_base_index():
    _guard()
    q = (request.args.get("q") or "").strip()
    summary = _abs.collect_summary()
    users = _abs.list_users(q=q, limit=500 if q else 300)
    feed = _abs.recent_feed(limit_per_table=15, total_limit=200)
    return render_template(
        "admin/base_stats.html",
        summary=summary, users=users, feed=feed, q=q,
    )


@admin_base_bp.route("/admin/base/user/<int:user_id>")
@login_required
def admin_base_user(user_id: int):
    _guard()
    per_table = request.args.get("n", type=int) or 100
    per_table = max(10, min(per_table, 1000))
    data = _abs.user_detail(user_id, per_table=per_table)
    if data is None:
        abort(404)
    return render_template("admin/base_user.html", u=data, per_table=per_table)


# ── JSON API ────────────────────────────────────────────────────────────
@admin_base_bp.route("/admin/base/api/summary")
@login_required
def admin_base_api_summary():
    _guard()
    return jsonify(_abs.collect_summary())


@admin_base_bp.route("/admin/base/api/users")
@login_required
def admin_base_api_users():
    _guard()
    q = (request.args.get("q") or "").strip()
    return jsonify({"users": _abs.list_users(q=q, limit=1000)})


@admin_base_bp.route("/admin/base/api/user/<int:user_id>")
@login_required
def admin_base_api_user(user_id: int):
    _guard()
    data = _abs.user_detail(user_id, per_table=request.args.get("n", type=int) or 200)
    if data is None:
        abort(404)
    return jsonify(data)


@admin_base_bp.route("/admin/base/api/feed")
@login_required
def admin_base_api_feed():
    _guard()
    return jsonify({"feed": _abs.recent_feed(limit_per_table=30, total_limit=500)})

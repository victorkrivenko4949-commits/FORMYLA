# -*- coding: utf-8 -*-
"""LAUNCH_V1 — дашборд запуска (промпт 29).

Маршруты (только для админа, иначе 404; включается ADMIN_LAUNCH_ENABLED):
  GET /admin/launch        — сводка готовности к включению лимитов:
                             готовность / эксперимент / воронка родителя /
                             деньги / источники + текст правила для 11.11.
  GET /admin/launch.csv    — те же данные в CSV (защита от formula-injection).

Только чтение БД. Ничего не включает/не выключает. Даты — МСК.
Отсутствующее событие → «нет источника данных», не 0.
Регистрация: автоматически через routes/__init__.py (см. _install), либо:
    from routes.admin_launch import admin_launch_bp
    app.register_blueprint(admin_launch_bp)
"""
from __future__ import annotations

import csv
import io
import logging
import os

from flask import Blueprint, Response, abort, render_template
from flask_login import current_user

import services.launch_metrics as lm

logger = logging.getLogger(__name__)

admin_launch_bp = Blueprint("admin_launch", __name__)


def _is_admin() -> bool:
    return getattr(current_user, "is_admin", False) is True


def _guard():
    """404 для анонима, не-админа и при выключенном флаге — страницы нет.
    Требование промпта: «только для admin (иначе 404)» — без редиректа."""
    if os.environ.get("ADMIN_LAUNCH_ENABLED", "0") != "1":
        abort(404)
    if not current_user.is_authenticated or not _is_admin():
        logger.warning("[admin_launch] forbidden for user=%r", getattr(current_user, "id", None))
        abort(404)


@admin_launch_bp.route("/admin/launch")
def launch_index():
    _guard()
    try:
        data = lm.collect()
    except Exception:  # noqa: BLE001
        logger.exception("[admin_launch] collect failed")
        abort(500)
    return render_template("admin/launch.html", d=data)


@admin_launch_bp.route("/admin/launch.csv")
def launch_csv():
    _guard()
    try:
        data = lm.collect()
        rows = lm.to_csv_rows(data)
    except Exception:  # noqa: BLE001
        logger.exception("[admin_launch] csv failed")
        abort(500)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerows(rows)
    return Response(
        buf.getvalue(), mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="launch.csv"'})

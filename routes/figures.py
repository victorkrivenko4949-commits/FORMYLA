# -*- coding: utf-8 -*-
# Blueprint "/figures" — figure vitrine (D4 showcase).
#
# This module contains ONLY the vitrine routes:
#   - /figures (showcase page)
#   - /pricing (credit packages)
#   - /payment-stub (payment placeholder)
#   - API: balance, transactions, email subscription
#
# The generation pipeline has been moved to routes/figures_generator.py
# at /figures/generate/* to avoid route conflicts with /figures and /drawing.

from __future__ import annotations

import logging

from flask import (
    Blueprint,
    Response,
    jsonify,
    render_template,
    request,
)

try:
    from flask_login import current_user, login_required
except Exception:
    current_user = None

    def login_required(f):
        return f


logger = logging.getLogger(__name__)

figures_bp = Blueprint("figures", __name__)

# ── Payment packages (single source of truth — change here, not in code) ──

FIGURE_PACKAGES = [
    {"id": "p10", "amount": 10, "price_rub": 99, "label": "10 чертежей", "featured": False},
    {"id": "p30", "amount": 30, "price_rub": 249, "label": "30 чертежей", "featured": True},
    {"id": "p100", "amount": 100, "price_rub": 599, "label": "100 чертежей", "featured": False},
]

# ── Credit helpers ──────────────────────────────────────────────────────

def _get_figure_credits(user) -> int:
    """Get user's figure_credits, defaulting to 3 for new users."""
    if user is None:
        return 0
    val = getattr(user, "figure_credits", None)
    if val is None:
        try:
            from models import db
            user.figure_credits = 3
            db.session.commit()
            return 3
        except Exception:
            return 3
    return int(val)


def _credit_balance_response(user) -> dict:
    """Return credit balance for client."""
    if user is None or not getattr(user, "is_authenticated", False):
        return {"credits": 0, "authenticated": False}
    return {
        "credits": _get_figure_credits(user),
        "authenticated": True,
        "figures_built": getattr(user, "figures_built", 0) or 0,
    }


# ── Routes ──────────────────────────────────────────────────────────────

@figures_bp.route("/figures", methods=["GET"])
def figures_page():
    """Render the figure vitrine page."""
    balance = _credit_balance_response(current_user)
    return render_template(
        "figures.html",
        credits=balance.get("credits", 0),
        figures_built=balance.get("figures_built", 0),
    )


@figures_bp.route("/pricing", methods=["GET"])
def pricing_page():
    """Figure credit packages page."""
    balance = _credit_balance_response(current_user)
    return render_template(
        "pricing.html",
        packages=FIGURE_PACKAGES,
        credits=balance.get("credits", 0),
    )


@figures_bp.route("/payment-stub", methods=["GET"])
def payment_stub_page():
    """Payment stub — payment coming soon."""
    package_id = request.args.get("package", "p10")
    pkg = next((p for p in FIGURE_PACKAGES if p["id"] == package_id), FIGURE_PACKAGES[0])
    return render_template("payment_stub.html", package=pkg)


@figures_bp.route("/api/figures/balance", methods=["GET"])
def api_figures_balance():
    """Return current credit balance."""
    return jsonify(_credit_balance_response(current_user))


@figures_bp.route("/api/figures/transactions", methods=["GET"])
@login_required
def api_figure_transactions():
    """Return transaction journal for the current user."""
    try:
        from models import FigureCreditTransaction
        txns = (
            FigureCreditTransaction.query
            .filter_by(user_id=current_user.id)
            .order_by(FigureCreditTransaction.created_at.desc())
            .limit(50)
            .all()
        )
        return jsonify({
            "transactions": [
                {
                    "id": t.id,
                    "amount": t.amount,
                    "reason": t.reason,
                    "reference": t.reference,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in txns
            ]
        })
    except Exception as e:
        logger.error("[figures] failed to fetch transactions: %s", e)
        return jsonify({"transactions": []})


@figures_bp.route("/api/figures/subscribe-email", methods=["POST"])
def api_subscribe_email():
    """Save email from payment stub 'notify me when ready' form."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    if not email or "@" not in email or len(email) > 200:
        return jsonify({"error": "Некорректный email"}), 400
    try:
        from models import db, FigureEmailSubscription
        sub = FigureEmailSubscription(email=email)
        db.session.add(sub)
        db.session.commit()
        return jsonify({"ok": True, "message": "Спасибо! Мы сообщим вам, когда оплата заработает."})
    except Exception as e:
        logger.error("[figures] email subscription failed: %s", e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": "Ошибка сохранения. Попробуйте позже."}), 500


# ── C11: Protected aux figure serving ─────────────────────────────────────
# Aux (чертёж с построением) отдаётся только после ответа на задачу.
# Для среза и задач дня проверяется наличие SolutionAttempt.
# Для методов олимпиад aux отдаётся сразу без проверки ответа.


def _has_answered_probe(user_id: int, task_id: int) -> bool:
    """Проверить, что пользователь отправил ответ на задачу среза."""
    try:
        from models import SolutionAttempt
        attempt = SolutionAttempt.query.filter_by(
            user_id=user_id,
            task_id=task_id,
            attempt_type='probe',
        ).first()
        return attempt is not None
    except Exception:
        return False


def _has_answered_daily(user_id: int, item_id: int) -> bool:
    """Проверить, что пользователь отправил ответ на задачу дня."""
    try:
        from daily_tasks.models import DailyTaskItem
        item = DailyTaskItem.query.get(item_id)
        if item is None:
            return False
        return item.user_answer is not None
    except Exception:
        return False


@figures_bp.route("/figures/aux/probe/<int:task_id>", methods=["GET"])
@login_required
def aux_probe(task_id: int):
    """Отдать aux-SVG для задачи среза, только если ответ уже отправлен."""
    if not _has_answered_probe(int(current_user.id), task_id):
        return jsonify({"error": "Сначала отправьте ответ на задачу."}), 403

    try:
        from models import db
        from sqlalchemy import text
        row = db.session.execute(
            text("SELECT has_aux, aux_svg_path FROM adaptive_tasks WHERE id=:tid"),
            {"tid": task_id},
        ).fetchone()
        if row is None:
            return jsonify({"error": "Задача не найдена."}), 404
        if not row[0] or not row[1]:
            return jsonify({"error": "Дополнительное построение отсутствует."}), 404
        return Response(row[1], mimetype='image/svg+xml')
    except Exception as e:
        logger.error("[figures] aux_probe error task_id=%d: %s", task_id, e)
        return jsonify({"error": "Ошибка сервера."}), 500


@figures_bp.route("/figures/aux/daily/<int:item_id>", methods=["GET"])
@login_required
def aux_daily(item_id: int):
    """Отдать aux-SVG для задачи дня, только если ответ уже отправлен."""
    if not _has_answered_daily(int(current_user.id), item_id):
        return jsonify({"error": "Сначала отправьте ответ на задачу."}), 403

    try:
        from daily_tasks.models import DailyTaskItem
        item = DailyTaskItem.query.get(item_id)
        if item is None:
            return jsonify({"error": "Задача не найдена."}), 404
        if not item.has_aux or not item.aux_svg_path:
            return jsonify({"error": "Дополнительное построение отсутствует."}), 404
        return Response(item.aux_svg_path, mimetype='image/svg+xml')
    except Exception as e:
        logger.error("[figures] aux_daily error item_id=%d: %s", item_id, e)
        return jsonify({"error": "Ошибка сервера."}), 500


@figures_bp.route("/figures/aux/method/<int:method_task_id>", methods=["GET"])
def aux_method(method_task_id: int):
    """Отдать aux-SVG для метода олимпиад — без проверки ответа."""
    try:
        from models_olympiad import MethodTask
        t = MethodTask.query.get(method_task_id)
        if t is None:
            return jsonify({"error": "Задача не найдена."}), 404
        has_aux = getattr(t, 'has_aux', False)
        aux_svg = getattr(t, 'aux_svg_path', None)
        if not has_aux or not aux_svg:
            return jsonify({"error": "Дополнительное построение отсутствует."}), 404
        return Response(aux_svg, mimetype='image/svg+xml')
    except Exception as e:
        logger.error("[figures] aux_method error method_task_id=%d: %s", method_task_id, e)
        return jsonify({"error": "Ошибка сервера."}), 500

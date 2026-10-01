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
# at /figures/generate/* to avoid route conflicts with /figures.

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

# ── Payment packages (prices from services/cost_calculation.py) ──

from services.cost_calculation import (
    figure_pack_price_rub,
    FIGURES_FREE,
)

FIGURE_PACKAGES = [
    {"id": "p10", "amount": 10, "price_rub": int(figure_pack_price_rub(10)), "label": "10 чертежей", "featured": False},
    {"id": "p30", "amount": 30, "price_rub": int(figure_pack_price_rub(30)), "label": "30 чертежей", "featured": True},
    {"id": "p100", "amount": 100, "price_rub": int(figure_pack_price_rub(100)), "label": "100 чертежей", "featured": False},
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
    import os
    return render_template(
        "figures.html",
        credits=balance.get("credits", 0),
        figures_built=balance.get("figures_built", 0),
        max_problem_length=int(os.environ.get("FIGURE_MAX_LENGTH", "4000")),
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


@figures_bp.route("/api/figures/purchase", methods=["POST"])
@login_required
def api_figures_purchase():
    """Начислить пакет чертежей (бесплатно в бета-периоде, 0 руб.).

    Тело: {package: 'p10'|'p30'|'p100'}.
    Начисляет кредиты пользователю и пишет запись в журнал транзакций.
    """
    data = request.get_json(silent=True) or {}
    package_id = (data.get("package") or "p30").strip()
    pkg = next((p for p in FIGURE_PACKAGES if p["id"] == package_id), None)
    if pkg is None:
        return jsonify({"error": "Неизвестный пакет"}), 400

    try:
        from models import db, FigureCreditTransaction

        credits = _get_figure_credits(current_user)
        amount = int(pkg["amount"])

        current_user.figure_credits = credits + amount

        txn = FigureCreditTransaction(
            user_id=current_user.id,
            amount=amount,
            reason="purchase",
            reference=package_id,
        )
        db.session.add(txn)
        db.session.commit()

        return jsonify({
            "ok": True,
            "credits": current_user.figure_credits,
            "added": amount,
            "message": f"Начислено {amount} чертежей",
        })
    except Exception as e:
        logger.error("[figures] purchase failed: %s", e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": "Ошибка начисления. Попробуйте позже."}), 500


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


# ── CH5: Build + status routes (delegating to figures_generator) ─────────

@figures_bp.route("/api/figures/build", methods=["POST"])
@login_required
def api_figures_build():
    """Delegate to figures_generator.start_build()."""
    from routes.figures_generator import start_build as _start_build
    return _start_build()


@figures_bp.route("/api/figures/status/<int:job_id>", methods=["GET"])
@login_required
def api_figures_status(job_id: int):
    """Delegate to figures_generator.job_status()."""
    from routes.figures_generator import job_status as _job_status
    return _job_status(job_id)


@figures_bp.route("/api/figures/active", methods=["GET"])
@login_required
def api_figures_active():
    """Delegate to figures_generator.active_job().

    Позволяет фронтенду возобновить незавершённую генерацию после того, как
    пользователь ушёл со страницы и вернулся: задание живёт в БД, поэтому
    queued/thinking/drawing переживает навигацию и перезагрузку.
    """
    from routes.figures_generator import active_job as _active_job
    return _active_job()


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


@figures_bp.route("/figures/history", methods=["GET"])
@login_required
def figures_history():
    """History page — all completed figure builds for the current user."""
    from models import FigureBuildJob
    jobs = (
        FigureBuildJob.query
        .filter_by(user_id=current_user.id)
        .filter(FigureBuildJob.status.in_(['done', 'failed']))
        .order_by(FigureBuildJob.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("figures_history.html", jobs=jobs)


@figures_bp.route("/api/figures/recognize-photo", methods=["POST"])
@login_required
def fig_recognize_photo():
    """Recognize math text from photo.

    Primary: DeepSeek vision (DEEPSEEK_VISION_MODEL).
    Fallback: local Tesseract OCR (free, no network) if DeepSeek fails.

    Rate limit: at most 10 requests per user per hour.  The counter is
    stored in the DB (photo_recognize_requests table).
    """
    import base64
    from services.tesseract_ocr import recognize_bytes as _tesseract_ocr

    # ── Rate limit (DB counter, per user + hour bucket) ─────────────────
    try:
        from datetime import datetime, timedelta
        from models import db, PhotoRecognizeRequest
        uid = None
        try:
            if current_user is not None and getattr(current_user, "is_authenticated", False):
                uid = getattr(current_user, "id", None)
        except Exception:
            uid = None
        if uid is None:
            return jsonify({"error": "Требуется авторизация."}), 401
        hour_bucket = datetime.utcnow().strftime("%Y-%m-%dT%H")
        row = PhotoRecognizeRequest.query.filter_by(
            user_id=uid, hour_bucket=hour_bucket,
        ).first()
        if row is None:
            row = PhotoRecognizeRequest(
                user_id=uid, hour_bucket=hour_bucket, count=0,
            )
            db.session.add(row)
        if row.count >= 10:
            db.session.rollback()
            return jsonify({
                "error": "Превышен лимит распознавания фото: не более 10 запросов в час.",
            }), 429
        row.count += 1
        db.session.commit()
    except Exception as e:
        logger.error("[figures] rate limit check failed: %s", e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": "Ошибка сервера при проверке лимита."}), 500

    data = request.get_json(silent=True) or {}
    img_b64 = data.get('image', '')
    mime = data.get('mime', 'image/jpeg')
    if not img_b64:
        return jsonify({'error': 'No image'}), 400

    try:
        raw_bytes = base64.b64decode(img_b64)
    except Exception as e:
        return jsonify({'error': f'Bad base64: {e}'}), 400

    # ── Шаг 1: DeepSeek vision (основной распознаватель) ────────────────
    try:
        import os as _os
        import requests as _requests
        _ds_key = _os.environ.get('DEEPSEEK_API_KEY', '').strip()
        _ds_model = _os.getenv('DEEPSEEK_VISION_MODEL', 'deepseek-v4-flash-vision-exp').strip()
        if _ds_key:
            _ds_resp = _requests.post(
                'https://api.deepseek.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {_ds_key}', 'Content-Type': 'application/json'},
                json={
                    'model': _ds_model,
                    'messages': [
                        {'role': 'user', 'content': [
                            {'type': 'text', 'text': 'Верни текст с изображения, формулы в LaTeX.'},
                            {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{img_b64}'}},
                        ]},
                    ],
                    'temperature': 0.7,
                    'max_tokens': 8192,
                },
                timeout=(15, 60),
            )
            if _ds_resp.status_code == 200:
                _ds_body = _ds_resp.json()
                if _ds_body.get('choices'):
                    text = (_ds_body['choices'][0].get('message', {}) or {}).get('content') or ''
                    if text:
                        logger.info("[figures] photo recognized via DeepSeek vision (%d chars)", len(text))
                        return jsonify({'text': text, 'engine': 'deepseek_vision'})
    except Exception as e:
        logger.warning("[figures] deepseek vision OCR raised: %s", e)

    # ── Шаг 2: локальный Tesseract OCR (резерв) ────────────────────────
    try:
        text, t_err = _tesseract_ocr(raw_bytes, mime)
        if text:
            logger.info("[figures] photo recognized via Tesseract (%d chars)", len(text))
            return jsonify({'text': text, 'engine': 'tesseract'})
    except Exception as e:
        t_err = str(e)
        logger.warning("[figures] tesseract OCR raised: %s", e)

    err = t_err or 'Recognition failed'
    return jsonify({'error': err}), 422

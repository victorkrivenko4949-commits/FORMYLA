# -*- coding: utf-8 -*-
"""
daily_tasks/routes.py — Flask endpoints для раздела «Задачи дня».

Endpoints
---------
* ``GET    /daily_tasks``           — главная страница / данные сета
* ``POST   /daily_tasks/<item_id>/submit`` — отправить ответ
* ``GET    /daily_tasks/<item_id>/hint``    — получить подсказку
* ``POST   /daily_tasks/regenerate``        — перегенерировать сегодняшний сет
* ``GET    /daily_tasks/job_status``        — polling статуса генерации

TZ Section 5 (document lines 479–571).
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Any, Dict

from flask import jsonify, render_template, request
from flask_login import current_user, login_required

from models import db
from . import daily_tasks_bp
from .models import DailyTaskSet, DailyTaskItem, DailyGenerationJob
from . import services

# Единый сервис AI-проверки (общий с /api/check_adaptive_answer).
# Опциональный импорт — файла может не быть на проде.
try:
    from services.ai_tutor_review import review_attempt
except ModuleNotFoundError:
    review_attempt = None

# DeepSeek-клиент берём опционально — если AI недоступен, review_attempt
# вернёт fallback с эталонным ответом из БД.
try:  # pragma: no cover — best-effort import
    from ai.deepseek_client import DeepSeekClient  # type: ignore
    _DEEPSEEK_AVAILABLE = True
except ImportError:
    DeepSeekClient = None  # type: ignore[assignment]
    _DEEPSEEK_AVAILABLE = False

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# GET /daily_tasks
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("", methods=["GET"])
@login_required
def get_daily_tasks():
    """Получить сегодняшний набор задач или статус генерации.

    * Нет сета → 404 ``{"status": "no_set", "message": "..."}`` (JSON)
                 или рендер шаблона с теми же данными (HTML)
    * Генерация → 202 ``{"status": "generating", "progress_pct": ..., ...}``
    * Готов / частично → 200 с полным набором задач
    """
    user_id = current_user.id
    today = date.today()

    # ── всегда отдаём HTML (страница, а не API) ──────────────────────
    # Браузеры шлют Accept: */*, что совпадает с application/json,
    # поэтому accept_json ложно срабатывает. Фикс: всегда HTML.
    wants_html = True

    daily_set: DailyTaskSet | None = DailyTaskSet.query.filter_by(
        user_id=user_id,
        target_date=today,
    ).first()

    # ── нет сета ─────────────────────────────────────────────────────
    if not daily_set:
        data = {
            "status": "no_set",
            "daily_set_id": None,
            "target_date": today.isoformat(),
            "message": (
                "Пройди адаптивный тест, чтобы получить персональные задачи на день. "
                "Или нажми «Сгенерировать» вручную."
            ),
            "class_level": None,
            "summary": None,
            "generated_at": None,
            "total_cost_usd": None,
            "progress": {"completed": 0, "total": 0},
            "items": [],
        }
        if wants_html:
            return render_template("daily_tasks_dashboard.html", data=data)
        return jsonify({
            "status": "no_set",
            "message": data["message"],
        }), 404

    # ── генерация в процессе ─────────────────────────────────────────
    if daily_set.status == "generating":
        job = DailyGenerationJob.query.filter_by(
            user_id=user_id,
            target_date=today,
        ).first()

        # считаем примерное ETA (если знаем, когда начали)
        eta_seconds = None
        if job and job.started_at:
            elapsed = (datetime.utcnow() - job.started_at).total_seconds()
            eta_seconds = max(0, int(90 - elapsed))  # ~90 секунд в среднем

        data = {
            "status": "generating",
            "daily_set_id": daily_set.id,
            "target_date": today.isoformat(),
            "progress_pct": job.progress_pct if job else 0,
            "current_step": job.current_step if job else None,
            "eta_seconds": eta_seconds,
            "class_level": None,
            "summary": None,
            "generated_at": None,
            "total_cost_usd": None,
            "progress": {"completed": 0, "total": 0},
            "items": [],
        }
        if wants_html:
            return render_template("daily_tasks_dashboard.html", data=data)
        return jsonify({
            "status": "generating",
            "daily_set_id": daily_set.id,
            "progress_pct": job.progress_pct if job else 0,
            "current_step": job.current_step if job else None,
            "eta_seconds": eta_seconds,
        }), 202

    # ── готов / частично ─────────────────────────────────────────────
    # пользуемся сервисной функцией, которая уже умеет сериализовать
    svc_data = services.get_daily_tasks(user_id)

    # добавляем вычисляемое поле progress
    items = svc_data.get("items", [])
    completed = sum(
        1 for it in items if it.get("user_answer") is not None
    )

    data = {
        "date": today.isoformat(),
        "status": svc_data["status"],
        "daily_set_id": svc_data["daily_set_id"],
        "target_date": svc_data.get("target_date"),
        "class_level": daily_set.class_level,
        "summary": svc_data.get("reason_summary"),
        "generated_at": svc_data.get("generated_at"),
        "total_cost_usd": svc_data.get("total_cost_usd"),
        "progress": {
            "completed": completed,
            "total": len(items),
        },
        "items": items,
    }

    if wants_html:
        return render_template("daily_tasks_dashboard.html", data=data)
    return jsonify(data), 200


# ──────────────────────────────────────────────────────────────────────
# POST /daily_tasks/<item_id>/submit
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/<int:item_id>/submit", methods=["POST"])
@login_required
def submit_answer(item_id: int):
    """Отправить ответ на задачу.

    Request JSON:
        ``{"answer": "...", "time_spent_seconds": 320}``

    Response:
        ``is_correct``, ``correct_answer``, ``solution``,
        ``explanation``, ``set_progress``, ``weakness_update``
    """
    # ── загружаем задачу ─────────────────────────────────────────────
    item: DailyTaskItem | None = DailyTaskItem.query.get(item_id)
    if not item:
        return jsonify({"success": False, "message": "Задача не найдена"}), 404

    # ── проверяем принадлежность current_user ───────────────────────
    daily_set = DailyTaskSet.query.get(item.daily_set_id)
    if not daily_set or daily_set.user_id != current_user.id:
        return jsonify({"success": False, "message": "Задача не принадлежит текущему пользователю"}), 403

    # ── проверяем, что задача ещё не отвечена ───────────────────────
    if item.user_answer is not None:
        return jsonify({
            "success": False,
            "message": "Ответ на эту задачу уже был отправлен",
            "is_correct": item.is_correct,
            "correct_answer": item.correct_answer,
            "solution": item.solution,
        }), 409

    # ── парсим тело запроса ─────────────────────────────────────────
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    answer: str = data.get("answer", "")
    time_spent: int | None = data.get("time_spent_seconds")

    if not answer:
        return jsonify({"success": False, "message": "Поле 'answer' обязательно"}), 400

    # ── сохраняем ответ через сервис ────────────────────────────────
    result = services.submit_answer(
        item_id=item_id,
        answer=answer,
        time_spent=time_spent,
    )

    if not result.get("success"):
        return jsonify(result), 400

    # ── считаем прогресс сета ────────────────────────────────────────
    all_items = DailyTaskItem.query.filter_by(daily_set_id=item.daily_set_id).all()
    completed = sum(1 for it in all_items if it.user_answer is not None)
    total = len(all_items)

    # ── формируем пояснение ─────────────────────────────────────────
    is_correct = result.get("is_correct", False)
    explanation = (
        "Молодец, верно! 🎉"
        if is_correct
        else "Неверно. Попробуй ещё раз или посмотри решение."
    )

    # ── weakness_update (заглушка — в MVP обновляем через адаптивный тест) ─
    weakness_update = {
        "topic": item.topic,
        "new_score": None,
        "delta": None,
    }

    response = {
        "is_correct": is_correct,
        "correct_answer": result.get("correct_answer"),
        "solution": item.solution,
        "explanation": explanation,
        "set_progress": {
            "completed": completed,
            "total": total,
        },
        "weakness_update": weakness_update,
    }

    return jsonify(response), 200


# ──────────────────────────────────────────────────────────────────────
# GET /daily_tasks/<item_id>/hint
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/<int:item_id>/hint", methods=["GET"])
@login_required
def get_hint(item_id: int):
    """Получить подсказку для задачи.

    Query params:
        ``?index=0`` — индекс подсказки (по умолчанию 0)

    Возвращает:
        ``hint``, ``total_hints``, ``hint_index``
    """
    # ── проверяем, что задача принадлежит current_user ──────────────
    item: DailyTaskItem | None = DailyTaskItem.query.get(item_id)
    if not item:
        return jsonify({"success": False, "message": "Задача не найдена"}), 404

    daily_set = DailyTaskSet.query.get(item.daily_set_id)
    if not daily_set or daily_set.user_id != current_user.id:
        return jsonify({"success": False, "message": "Задача не принадлежит текущему пользователю"}), 403

    hint_index = request.args.get("index", 0, type=int)

    result = services.get_hint(item_id=item_id, hint_index=hint_index)

    if not result.get("success"):
        return jsonify(result), 404

    return jsonify(result), 200


# ──────────────────────────────────────────────────────────────────────
# POST /daily_tasks/regenerate
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/regenerate", methods=["POST"])
@login_required
def regenerate():
    """Перегенерировать сегодняшний набор задач.

    * Обычный пользователь — 1 раз в день.
    * Админ — без лимита.
    """
    user_id = current_user.id
    today = date.today()

    # ── проверяем лимит для обычных пользователей ───────────────────
    if not current_user.is_admin:
        existing_set = DailyTaskSet.query.filter_by(
            user_id=user_id,
            target_date=today,
        ).first()

        if existing_set and existing_set.status == "ready":
            # проверяем, не было ли уже регенерации сегодня
            generated_count = DailyTaskSet.query.filter(
                DailyTaskSet.user_id == user_id,
                DailyTaskSet.target_date == today,
                DailyTaskSet.generated_at.isnot(None),
            ).count()

            if generated_count >= 1:
                logger.warning(
                    "User %d пытается перегенерировать задачи, уже было %d генераций сегодня",
                    user_id,
                    generated_count,
                )
                return jsonify({
                    "success": False,
                    "message": "Перегенерация доступна 1 раз в день",
                }), 429

    # ── удаляем существующий сет (каскадно удалит items + jobs) ─────
    existing_set = DailyTaskSet.query.filter_by(
        user_id=user_id,
        target_date=today,
    ).first()

    if existing_set:
        # удаляем связанные jobs
        DailyGenerationJob.query.filter_by(
            user_id=user_id,
            target_date=today,
        ).delete()

        db.session.delete(existing_set)
        db.session.commit()
        logger.info("Удалён существующий сет #%s для перегенерации", existing_set.id)

    # ── запускаем новую генерацию ───────────────────────────────────
    result = services.enqueue_daily_generation(
        user_id=user_id,
        triggered_by="manual",
    )

    return jsonify(result), 202


# ──────────────────────────────────────────────────────────────────────
# GET /daily_tasks/job_status
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/job_status", methods=["GET"])
@login_required
def job_status():
    """Polling-эндпоинт для фронта во время генерации.

    Возвращает состояние ``DailyGenerationJob`` для сегодняшней даты.
    """
    result = services.get_job_status(current_user.id)

    if result.get("state") == "no_job":
        return jsonify({"state": "no_job", "message": "Нет активной генерации"}), 404

    return jsonify(result), 200


# ──────────────────────────────────────────────────────────────────────
# POST /daily_tasks/<item_id>/submit_ai
# ──────────────────────────────────────────────────────────────────────
#
# 1-в-1 с /api/check_adaptive_answer (раздел «Адаптивный тест»):
# принимает {user_answer, user_solution, solution_image_b64?,
# solution_images_b64?}, прогоняет через services.ai_tutor_review.
# Сохраняет в DailyTaskItem (user_answer, is_correct, answered_at).
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/<int:item_id>/submit_ai", methods=["POST"])
@login_required
def submit_answer_ai(item_id: int):
    """AI-проверка решения «Задач дня» — тот же pipeline, что в адаптивном тесте."""
    item = DailyTaskItem.query.get(item_id)
    if not item:
        return jsonify({"status": "error", "message": "Задача не найдена"}), 404

    daily_set = DailyTaskSet.query.get(item.daily_set_id)
    if not daily_set or daily_set.user_id != current_user.id:
        return jsonify({
            "status": "error",
            "message": "Задача не принадлежит текущему пользователю",
        }), 403

    if item.user_answer is not None:
        return jsonify({
            "status": "error",
            "message": "На эту задачу уже отвечено.",
            "already_answered": True,
            "is_correct": item.is_correct,
            "correct_answer": item.correct_answer,
            "solution": item.solution,
        }), 409

    data = request.get_json(silent=True) or {}
    user_answer = (data.get("user_answer") or data.get("answer") or "").strip()
    user_solution = (data.get("user_solution") or "").strip()
    if not user_answer:
        return jsonify({
            "status": "error",
            "message": "Не указан ответ",
        }), 400

    # Собираем фото (solution_image_b64 + solution_images_b64), режем data:
    raw_images = []
    single = data.get("solution_image_b64", "") or ""
    if single:
        raw_images.append(single)
    multi = data.get("solution_images_b64") or []
    if isinstance(multi, list):
        for it in multi:
            if isinstance(it, str) and it.strip():
                raw_images.append(it)

    def _strip_dataurl(b: str) -> str:
        return b.split(",", 1)[-1] if b.startswith("data:") else b

    images_b64 = [_strip_dataurl(b) for b in raw_images if b]

    # Если AI-проверка недоступна (нет файла services/ai_tutor_review.py на проде)
    if review_attempt is None:
        return jsonify({
            "status": "error",
            "message": "AI-проверка временно недоступна",
        }), 503

    # AI-проверка через общий сервис
    try:
        result = review_attempt(
            task_text=item.task_text or "",
            correct_answer=item.correct_answer or "",
            solution_ref=item.solution or "",
            user_answer=user_answer,
            user_solution=user_solution,
            images_b64=images_b64,
            deepseek_client_cls=DeepSeekClient if _DEEPSEEK_AVAILABLE else None,
            deepseek_available=_DEEPSEEK_AVAILABLE,
            max_tokens=4096,
        )
    except Exception as e:  # pragma: no cover
        logger.exception("submit_answer_ai: review_attempt failed: %s", e)
        return jsonify({
            "status": "error",
            "message": f"Ошибка AI-проверки: {e}",
        }), 500

    score = result.get("score", 0.0)
    feedback = str(result.get("feedback") or "")
    is_correct = bool(result.get("is_correct"))

    # Сохраняем ответ ученика в БД
    from datetime import datetime as _dt
    try:
        item.user_answer = user_answer[:4000]
        item.is_correct = is_correct
        item.answered_at = _dt.utcnow()
        try:
            item.time_spent_seconds = int(data.get("time_spent_seconds") or 0)
        except (TypeError, ValueError):
            item.time_spent_seconds = 0
        db.session.commit()
    except Exception as e:  # pragma: no cover
        db.session.rollback()
        logger.exception("submit_answer_ai: db commit failed: %s", e)

    # Прогресс сета
    try:
        all_items = DailyTaskItem.query.filter_by(daily_set_id=item.daily_set_id).all()
        completed = sum(1 for it in all_items if it.user_answer is not None)
        total = len(all_items)
    except Exception:
        completed = total = 0

    return jsonify({
        "status": "success",
        "score": score,
        "feedback": feedback,
        "is_correct": is_correct,
        "correct_answer": item.correct_answer or "",
        "solution": item.solution or "",
        "set_progress": {"completed": completed, "total": total},
    })

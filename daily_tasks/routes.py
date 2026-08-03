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
from datetime import datetime, date, timedelta
from calendar import monthrange
from typing import Any, Dict, Optional

from flask import jsonify, render_template, request, current_app
from flask_login import current_user, login_required

from models import db
from models_curator import CuratorState
from . import daily_tasks_bp
from .models import DailyTaskSet, DailyTaskItem, DailyGenerationJob, TaskPool
from . import services
from .services import today_in_user_tz
from .monthly_plan import get_or_build_plan, current_month_index, pick_day_subtopic, subtopic_title

# 24h TTL для сета «Задач дня»: после истечения сет автоматически
# помечается как expired при следующем GET /daily_tasks, и пользователю
# показывается чистое empty-state с кнопкой «Сгенерировать».
DAILY_SET_TTL = timedelta(hours=24)

# Российские темы для поля «Тема дня» — ротация по дню и классу.
_RU_THEMES = [
    "Теория чисел",
    "Геометрия",
    "Алгебра",
    "Комбинаторика",
    "Логика и игры",
]


def _theme_for_day(target_date, class_level=None) -> str:
    """Детерминированная тема дня: меняется ежедневно и зависит от класса."""
    try:
        doy = target_date.timetuple().tm_yday
    except Exception:
        doy = 0
    cls = int(class_level) if class_level else 0
    return _RU_THEMES[(doy + cls) % len(_RU_THEMES)]


def _set_expires_at(daily_set: DailyTaskSet) -> datetime | None:
    """Момент истечения 24h-окна сета (UTC). None — если ещё не готов."""
    anchor = daily_set.generated_at
    if anchor is None:
        return None
    return anchor + DAILY_SET_TTL


def _is_expired(daily_set: DailyTaskSet) -> bool:
    """True, если сет старше 24 часов и должен быть помечен expired."""
    exp = _set_expires_at(daily_set)
    if exp is None:
        return False
    return datetime.utcnow() >= exp

# Единый сервис AI-проверки (общий с /api/check_adaptive_answer).
# Опциональный импорт — файла может не быть на проде.
try:
    from services.ai_tutor_review import review_attempt, solve_task
except ModuleNotFoundError:
    review_attempt = None
    solve_task = None

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


@daily_tasks_bp.route("/", methods=["GET"])
@login_required
def get_daily_tasks():
    """Получить сегодняшний набор задач или статус генерации.

    * Нет сета → 404 ``{"status": "no_set", "message": "..."}`` (JSON)
                 или рендер шаблона с теми же данными (HTML)
    * Генерация → 202 ``{"status": "generating", "progress_pct": ..., ...}``
    * Готов / частично → 200 с полным набором задач
    """
    user_id = current_user.id
    today = today_in_user_tz()

    # ── всегда отдаём HTML (страница, а не API) ──────────────────────
    # Браузеры шлют Accept: */*, что совпадает с application/json,
    # поэтому accept_json ложно срабатывает. Фикс: всегда HTML.
    wants_html = True

    daily_set: DailyTaskSet | None = DailyTaskSet.query.filter_by(
        user_id=user_id,
        target_date=today,
    ).first()

    # ── P4 DEBT: при первом заходе ученика обновляем долг ────────────────
    try:
        from services.daily_debt import refresh_debt_for_user
        refresh_debt_for_user(user_id)
    except Exception as _debt_err:
        logger.warning("daily_debt refresh failed for user=%d: %s", user_id, _debt_err)

    # ── 24h-TTL: если сет старше 24 часов от generated_at — помечаем
    # expired «лениво» прямо в этом запросе.
    # P4: ПЕРЕД expire мигрируем нерешённые задачи в долг.
    if (
        daily_set
        and daily_set.status not in ("expired", "generating")
        and _is_expired(daily_set)
    ):
        # Мигрируем нерешённое этого сета в долг перед expire
        try:
            from services.daily_debt import migrate_to_debt
            migrate_to_debt(user_id, daily_set.target_date + __import__('datetime').timedelta(days=1))
        except Exception:
            pass
        try:
            daily_set.status = "expired"
            db.session.commit()
            logger.info(
                "DailyTaskSet #%s expired (>24h since generated_at=%s)",
                daily_set.id, daily_set.generated_at,
            )
        except Exception:  # pragma: no cover
            db.session.rollback()
        daily_set = None

    # ── BLOCKED: morning probe not done ─────────────────────────────────
    # Проверяем monthly cycle: если probe ещё не пройден — блокируем задачи дня
    blocked = False
    blocked_theme = None
    blocked_theme_title = None
    try:
        from curator.monthly_cycle import get_cycle_info
        cycle = get_cycle_info(user_id)
        if cycle.get('active') and cycle.get('blocked') and not cycle.get('finished'):
            blocked = True
            blocked_theme = cycle.get('current_theme', '')
            from daily_tasks.monthly_plan import subtopic_title
            blocked_theme_title = subtopic_title(blocked_theme) if blocked_theme else 'тема дня'
    except Exception:
        pass

    if blocked:
        data = {
            "status": "blocked",
            "daily_set_id": None,
            "target_date": today.isoformat(),
            "message": (
                f"Сначала утренний срез: «{blocked_theme_title}». "
                f"5 задач, примерно 15 минут."
            ),
            "class_level": None,
            "summary": None,
            "generated_at": None,
            "total_cost_usd": None,
            "progress": {"completed": 0, "total": 0},
            "items": [],
            "blocked": True,
            "blocked_theme": blocked_theme,
            "blocked_theme_title": blocked_theme_title,
            "probe_url": "/prep/probe",
        }
        if wants_html:
            return render_template("daily_tasks/daily_tasks_dashboard.html", data={**data, "theme_today": _theme_for_day(today, data.get("class_level"))})
        return jsonify({
            "status": "blocked",
            "message": data["message"],
            "probe_url": "/prep/probe",
        }), 200

    # ── нет сета (или только что протух) ─────────────────────────────
    if not daily_set:
        # Попытка создать набор через pick_daily_set
        # (анкета + level_engine). Если нет данных — классический empty-state.
        try:
            from services.daily_task_rotation import pick_daily_set
            pick_daily_set(user_id, force_regenerate=False)
            # Перезапрашиваем только что созданный сет
            daily_set = DailyTaskSet.query.filter_by(
                user_id=user_id, target_date=today,
            ).first()
            if daily_set and daily_set.status in ("ready", "partial"):
                logger.info(
                    "DailyTaskSet auto-created via pick_daily_set for user=%d", user_id,
                )
        except Exception as _pds_err:
            logger.warning(
                "pick_daily_set fallback failed for user=%d: %s", user_id, _pds_err,
            )

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
            return render_template("daily_tasks/daily_tasks_dashboard.html", data={**data, "theme_today": _theme_for_day(today, data.get("class_level"))})
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
        elapsed_seconds = None
        started_at_iso = None
        if job and job.started_at:
            elapsed = (datetime.utcnow() - job.started_at).total_seconds()
            eta_seconds = max(0, int(90 - elapsed))  # ~90 секунд в среднем
            elapsed_seconds = max(0, int(elapsed))
            # started_at в БД хранится как datetime.utcnow() (naive UTC).
            # Отдаём ISO-строку с явным суффиксом 'Z', чтобы JS
            # Date.parse(...) корректно интерпретировал её как UTC.
            started_at_iso = job.started_at.isoformat() + "Z"

        data = {
            "status": "generating",
            "daily_set_id": daily_set.id,
            "target_date": today.isoformat(),
            "progress_pct": job.progress_pct if job else 0,
            "current_step": job.current_step if job else None,
            "eta_seconds": eta_seconds,
            # Fix «прошло X:XX» сбрасывается при F5: отдаём серверное
            # время старта (UTC, ISO с 'Z') + уже посчитанное elapsed,
            # чтобы JS-таймер мог восстановиться с правильной отметки.
            "started_at": started_at_iso,
            "elapsed_seconds": elapsed_seconds,
            "class_level": None,
            "summary": None,
            "generated_at": None,
            "total_cost_usd": None,
            "progress": {"completed": 0, "total": 0},
            "items": [],
        }
        if wants_html:
            return render_template("daily_tasks/daily_tasks_dashboard.html", data={**data, "theme_today": _theme_for_day(today, data.get("class_level"))})
        return jsonify({
            "status": "generating",
            "daily_set_id": daily_set.id,
            "progress_pct": job.progress_pct if job else 0,
            "current_step": job.current_step if job else None,
            "eta_seconds": eta_seconds,
            "started_at": started_at_iso,
            "elapsed_seconds": elapsed_seconds,
        }), 202

    # ── failed / ready / partial ─────────────────────────────────────
    # пользуемся сервисной функцией, которая уже умеет сериализовать
    svc_data = services.get_daily_tasks(user_id)

    # добавляем вычисляемое поле progress
    items = svc_data.get("items", [])
    completed = sum(
        1 for it in items if it.get("user_answer") is not None
    )

    # Для failed-сета подтягиваем error_message из джоба — фронт покажет его
    # в understandable виде, плюс кнопку «Попробовать снова».
    error_message = None
    if svc_data.get("status") == "failed":
        job = DailyGenerationJob.query.filter_by(
            user_id=user_id, target_date=today,
        ).first()
        if job and job.error_message:
            error_message = job.error_message

    # ── Completeness-баннер: считаем сколько задач калибровочные ─────
    # (для UI достаточно: число калибровочных / общее число задач).
    calibration_items_count = sum(
        1 for it in items if it.get("is_calibration")
    )
    has_calibration = calibration_items_count > 0

    expires_at_dt = _set_expires_at(daily_set)
    data = {
        "date": today.isoformat(),
        "status": svc_data["status"],
        "daily_set_id": svc_data["daily_set_id"],
        "target_date": svc_data.get("target_date"),
        "class_level": daily_set.class_level,
        "summary": svc_data.get("reason_summary"),
        "generated_at": svc_data.get("generated_at"),
        # 24h-окно: ISO-строка момента, когда задачи протухнут.
        # Фронт использует это значение для обратного отсчёта вверху страницы.
        "expires_at": expires_at_dt.isoformat() + "Z" if expires_at_dt else None,
        "ttl_seconds": int(DAILY_SET_TTL.total_seconds()),
        "total_cost_usd": svc_data.get("total_cost_usd"),
        "error_message": error_message,
        "progress": {
            "completed": completed,
            "total": len(items),
        },
        "items": items,
        # PR percent_to_level + calibration
        "calibration_items_count": calibration_items_count,
        "has_calibration": has_calibration,
        # подсказка на которой страницу идти за тестами (для баннера)
        "adaptive_tests_url": "/adaptive_test_simple",
    }

    # ── P4 DEBT: добавляем долг в data ──────────────────────────────────
    try:
        from services.daily_debt import get_debt_items, get_debt_count
        debt_items = get_debt_items(user_id)
        if debt_items:
            # Группируем по дате выдачи
            from collections import defaultdict
            by_date: dict = defaultdict(list)
            for di in debt_items:
                by_date[di['issued_date'] or '?'].append(di)
            debt_summary = {
                'total': len(debt_items),
                'by_date': [
                    {'date': d, 'count': len(tasks), 'tasks': tasks}
                    for d, tasks in sorted(by_date.items(), reverse=True)
                ],
            }
            data['debt'] = debt_summary
        # debt=None означает «долга нет» — шаблон его не отрисует
    except Exception as _debt_err:
        logger.warning("get_debt_items failed: %s", _debt_err)

    # ── 🗓  Monthly plan (prep_plan from CuratorState) ────────────
    plan_data = _build_monthly_plan_data(user_id, today)
    if plan_data:
        data["plan_data"] = plan_data

    if wants_html:
        return render_template("daily_tasks/daily_tasks_dashboard.html", data={**data, "theme_today": _theme_for_day(today, data.get("class_level"))})
    return jsonify(data), 200


def _build_monthly_plan_data(user_id: int, today: date) -> Optional[Dict[str, Any]]:
    """Построить plan_data для календаря подтем из CuratorState.prep_plan.

    Возвращает dict с ключами:
        current_month (int) — 1-based номер текущего месяца
        today_subtopic (str) — русское название подтемы дня
        today_subtopic_slug (str) — slug подтемы дня
        months (list) — список месяцев с подтемами
        anchor_date (str) — дата якоря
        grade (int) — класс
    или None, если у пользователя нет curator_state или плана.
    """
    from models_curator import CuratorState as _CS
    try:
        cs: Optional[_CS] = _CS.query.filter_by(user_id=user_id).first()
        if not cs or not cs.grade:
            return None
        grade = cs.grade
        plan = get_or_build_plan(cs, grade, today)
        if not plan or not plan.get("months"):
            return None

        current_month = current_month_index(plan, today)
        today_subtopic_slug = pick_day_subtopic(plan, today)
        today_subtopic_title = subtopic_title(today_subtopic_slug) if today_subtopic_slug else None

        months_data = []
        for m in plan.get("months", []):
            subs = []
            for slug in m.get("subtopics", []):
                subs.append({
                    "slug": str(slug),
                    "title": subtopic_title(str(slug)),
                })
            months_data.append({
                "index": m["index"],
                "subtopics": subs,
            })

        return {
            "current_month": current_month,
            "today_subtopic": today_subtopic_title,
            "today_subtopic_slug": today_subtopic_slug,
            "months": months_data,
            "anchor_date": plan.get("anchor_date"),
            "grade": grade,
        }
    except Exception as exc:
        logger.warning("[monthly_plan] _build_monthly_plan_data failed: %s", exc, exc_info=True)
        return None


# ──────────────────────────────────────────────────────────────────────
# POST /daily_tasks/<item_id>/submit
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/<int:item_id>/submit", methods=["POST"])
@login_required
def submit_answer(item_id: int):
    """Отправить ответ на задачу.

    Request JSON:
        ``{"answer": "...", "solution_method": "text"|"photo",
          "solution_text": "...", "time_spent_seconds": 320}``
    Or multipart form with ``solution_photo`` file.

    D1: решение необязательно. Если решение прислано (текст или файл) -
    сохраняется в solution_attempts с attempt_type='daily'.
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

    # ── парсим тело запроса (JSON или multipart) ────────────────────
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    if request.form:
        data = {**data, **request.form.to_dict()}
    answer: str = data.get("answer", "")
    time_spent: int | None = data.get("time_spent_seconds")
    solution_method: str = (data.get("solution_method") or "").strip().lower()
    solution_text: str = (data.get("solution_text") or "").strip()

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

    # ── D1: сохраняем SolutionAttempt если решение прислано ─────────
    file_path_rel = None
    file_size = None
    if solution_method == 'photo' and 'solution_photo' in request.files:
        photo_file = request.files['solution_photo']
        if photo_file and photo_file.filename:
            photo_bytes = photo_file.read()
            if len(photo_bytes) > 12 * 1024 * 1024:
                pass  # Too large, skip - not blocking
            elif len(photo_bytes) > 0:
                content_type = photo_file.content_type or 'application/octet-stream'
                # Convert HEIC to JPEG
                if content_type in ('image/heic', 'image/heif') or photo_file.filename.lower().endswith(('.heic', '.heif')):
                    try:
                        from routes.prep import _convert_heic_to_jpeg
                        photo_bytes, content_type = _convert_heic_to_jpeg(photo_bytes)
                    except Exception:
                        pass  # Keep original
                # Compress: max 1500px, quality 0.8
                try:
                    from PIL import Image
                    import io as _io
                    img = Image.open(_io.BytesIO(photo_bytes))
                    img = img.convert('RGB')
                    w, h = img.size
                    max_side = 1500
                    if max(w, h) > max_side:
                        ratio = max_side / max(w, h)
                        w = int(w * ratio)
                        h = int(h * ratio)
                        img = img.resize((w, h), Image.LANCZOS)
                    out_buf = _io.BytesIO()
                    img.save(out_buf, format='JPEG', quality=80)
                    photo_bytes = out_buf.getvalue()
                    content_type = 'image/jpeg'
                except Exception:
                    pass  # Keep original
                # Save file
                import os as _os
                from datetime import datetime as _dt
                year_month = _dt.utcnow().strftime('%Y-%m')
                upload_dir = _os.path.join(current_app.static_folder, 'uploads', 'solutions', year_month)
                _os.makedirs(upload_dir, exist_ok=True)
                import uuid as _uuid
                filename = f'{_uuid.uuid4().hex[:16]}.jpg'
                file_path_rel = f'uploads/solutions/{year_month}/{filename}'
                file_path_abs = _os.path.join(current_app.static_folder, file_path_rel)
                with open(file_path_abs, 'wb') as f:
                    f.write(photo_bytes)
                file_size = len(photo_bytes)

    # D1: запись в solution_attempts только если решение присутствует
    if solution_method in ('text', 'photo'):
        has_solution = (solution_method == 'text' and len(solution_text) > 0) or \
                       (solution_method == 'photo' and file_path_rel is not None)
        if has_solution:
            try:
                from models import SolutionAttempt
                # DailyTaskItem has no FK to adaptive_tasks, use item.id as task_id
                attempt = SolutionAttempt(
                    user_id=current_user.id,
                    task_id=item_id,
                    probe_id=None,
                    attempt_type='daily',
                    solution_text=solution_text if solution_method == 'text' else None,
                    file_path=file_path_rel if solution_method == 'photo' else None,
                    file_size=file_size if solution_method == 'photo' else None,
                )
                db.session.add(attempt)
                db.session.commit()
            except Exception:
                pass  # SolutionAttempt save failure must not block answer

    # ── считаем прогресс сета ────────────────────────────────────────
    all_items = DailyTaskItem.query.filter_by(daily_set_id=item.daily_set_id).all()
    completed = sum(1 for it in all_items if it.user_answer is not None)
    total = len(all_items)

    # ── формируем пояснение ─────────────────────────────────────────
    is_correct = result.get("is_correct", False)
    explanation = (
        "Молодец, верно!"
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
        "has_aux": bool(item.has_aux),
        "aux_svg_path": item.aux_svg_path if item.has_aux else None,
        "aux_reason": item.aux_reason if item.has_aux else None,
    }

    # CH10: Kimi review
    try:
        from services.kimi_review import review_text as _kimi_text
        kimi = _kimi_text(
            task_text=(item.question or ""),
            correct_answer=(item.correct_answer or ""),
            solution_text=answer,
            surface="daily_task",
        )
        if kimi and not kimi.get("error"):
            response["kimi_review"] = {
                "label": kimi.get("label"),
                "raw_response": kimi.get("raw_response", ""),
            }
    except Exception:
        pass

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

    Правила лимита:
    * Обычный пользователь — 1 успешная генерация в день
      (``status == 'ready'`` или ``'partial'``).
    * **Failed-сеты НЕ считаются** израсходованной попыткой —
      пользователь может повторить, если генерация сломалась
      (например, исчерпался баланс OpenRouter, упал LLM-провайдер).
    * Админ — без лимита.
    """
    user_id = current_user.id
    today = today_in_user_tz()

    # ── проверяем лимит для обычных пользователей ───────────────────
    if not current_user.is_admin:
        existing_set = DailyTaskSet.query.filter_by(
            user_id=user_id,
            target_date=today,
        ).first()

        # Лимит срабатывает ТОЛЬКО когда сегодня уже есть УСПЕШНЫЙ сет.
        # Failed / generating / отсутствие сета — повторная попытка разрешена.
        if existing_set and existing_set.status in ("ready", "partial"):
            logger.warning(
                "User %d пытается перегенерировать задачи, "
                "но сегодня уже есть готовый сет #%d (status=%s)",
                user_id, existing_set.id, existing_set.status,
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
        triggered_by="manual",         forced_topic=((request.get_json(silent=True) or {}).get("topic") or "").strip() or None,
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
# Fix 6: GET /daily-tasks/status — статус пула для фронта (polling 2 с)
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/status", methods=["GET"])
@login_required
def daily_tasks_pool_status():
    """Вернуть статус ``task_pool``'а (предгенерация после адаптивного теста).

    Фронт делает GET /daily-tasks/status каждые 2 с, пока status = ``generating``.
    Как только статус сменится на ``ready`` / ``partial`` — фронт переходит к
    GET /daily_tasks.
    """
    from daily_tasks.profile import build_profile
    from daily_tasks.services import compute_cache_key

    profile = build_profile(current_user.id)
    cache_key = compute_cache_key(profile)

    pool = TaskPool.query.filter_by(cache_key=cache_key).first()
    if not pool:
        return jsonify({
            "status": "no_pool",
            "pool_id": None,
            "message": "Пул ещё не создан",
        }), 404

    return jsonify({
        "status": pool.status,
        "pool_id": pool.id,
        "expires_at": pool.expires_at.isoformat() if pool.expires_at else None,
        "message": {
            "generating": "Задачи генерируются",
            "ready": "Пул готов",
            "partial": "Пул готов (частично)",
            "failed": "Генерация не удалась",
        }.get(pool.status, "Неизвестный статус"),
        "valid_count": pool.valid_count,
    }), 200


# ──────────────────────────────────────────────────────────────────────
# POST /daily_tasks/<item_id>/submit_ai
# ──────────────────────────────────────────────────────────────────────
#
# 1-в-1 с /api/check_adaptive_answer (раздел «Адаптивный тест»):
# принимает {user_answer, user_solution, solution_image_b64?,
# solution_images_b64?}, прогоняет через services.ai_tutor_review.
# Сохраняет в DailyTaskItem (user_answer, is_correct, answered_at).
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/<int:item_id>/solve", methods=["POST"])
@login_required
def solve_task_preview(item_id: int):
    """AI решает задачу с нуля (превью) — вызывается при открытии задачи до того,
    как ученик написал свой ответ."""
    item = DailyTaskItem.query.get(item_id)
    if not item:
        return jsonify({"status": "error", "message": "Задача не найдена"}), 404

    daily_set = DailyTaskSet.query.get(item.daily_set_id)
    if not daily_set or daily_set.user_id != current_user.id:
        return jsonify({
            "status": "error",
            "message": "Задача не принадлежит текущему пользователю",
        }), 403

    if solve_task is None:
        # Fallback: отдаём эталонное решение из БД
        return jsonify({
            "status": "success",
            "solution": item.solution or "Решение временно недоступно.",
        })

    import concurrent.futures as _cf
    _result = None
    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as _executor:
            _future = _executor.submit(
                solve_task,
                task_text=item.task_text or "",
                correct_answer=item.correct_answer or "",
                solution_ref=item.solution or "",
                deepseek_client_cls=DeepSeekClient if _DEEPSEEK_AVAILABLE else None,
                deepseek_available=_DEEPSEEK_AVAILABLE,
                max_tokens=4096,
            )
            try:
                _result = _future.result(timeout=20)
            except _cf.TimeoutError:
                logger.warning("solve_task_preview: solve_task timed out after 20s — fallback")
    except Exception as e:
        logger.exception("solve_task_preview: solve_task failed: %s", e)

    if _result and _result.get("success"):
        return jsonify({
            "status": "success",
            "solution": _result.get("solution", ""),
        })

    # Fallback: эталонное решение из БД
    return jsonify({
        "status": "success",
        "solution": item.solution or "Решение временно недоступно.",
    })


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

    if item.user_answer is not None and item.is_correct:
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

    # AI-проверка через общий сервис с жёстким таймаутом 20 секунд
    # (DeepSeekClient.timeout=90с, но Render LB отбивает через ~30с)
    import concurrent.futures as _cf
    _result = None
    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as _executor:
            _future = _executor.submit(
                review_attempt,
                task_text=item.task_text or "",
                correct_answer=item.correct_answer or "",
                solution_ref=item.solution or "",
                user_answer=user_answer,
                user_solution=user_solution,
                images_b64=images_b64,
                deepseek_client_cls=DeepSeekClient if _DEEPSEEK_AVAILABLE else None,
                deepseek_available=_DEEPSEEK_AVAILABLE,
                max_tokens=4096,
                sanitize_latex=False,
            )
            try:
                _result = _future.result(timeout=20)
            except _cf.TimeoutError:
                logger.warning("submit_answer_ai: review_attempt timed out after 20s — fallback")
    except Exception as e:  # pragma: no cover
        logger.exception("submit_answer_ai: review_attempt failed: %s", e)

    if _result is None:
        # Таймаут или ошибка — сохраняем ответ без AI-проверки
        score = 0.0
        feedback = "AI-проверка временно недоступна. Ответ сохранён."
        is_correct = False
    else:
        score = _result.get("score", 0.0)
        feedback = str(_result.get("feedback") or "")
        is_correct = bool(_result.get("is_correct"))

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

        # ── Записать результат в level_engine ──────────────────────────
        try:
            from services.daily_task_rotation import record_daily_answer
            record_daily_answer(current_user.id, item.id, is_correct)
            logger.info(
                "submit_answer_ai: level_engine updated user=%d item=%d correct=%s",
                current_user.id, item.id, is_correct,
            )
        except Exception as _le_err:
            logger.warning("submit_answer_ai: level_engine update failed: %s", _le_err)
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


# ──────────────────────────────────────────────────────────────────────
# GET /daily_tasks/calendar?year=YYYY&month=MM
# ──────────────────────────────────────────────────────────────────────
#
# Возвращает агрегированную статистику по решённым задачам за каждый день
# указанного месяца (по умолчанию — текущий месяц). Используется для
# вертикального календаря справа от блока «Задачи дня».
#
# Цвета подсветки на фронте:
#   0          → серая
#   1–3        → бледно-зелёная
#   4–6        → зелёная
#   7–9        → яркая зелёная
#   10 (или больше) → золотая (с короной)
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/calendar", methods=["GET"])
@login_required
def calendar_stats():
    """Статистика по решённым задачам за каждый день месяца."""
    today = today_in_user_tz()
    try:
        year = int(request.args.get("year") or today.year)
        month = int(request.args.get("month") or today.month)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Неверный year/month"}), 400

    if month < 1 or month > 12:
        return jsonify({"success": False, "message": "Неверный month"}), 400

    last_day = monthrange(year, month)[1]
    first_dt = date(year, month, 1)
    last_dt = date(year, month, last_day)

    # Берём ВСЕ сеты пользователя за этот месяц (включая expired).
    # expired-сеты тоже видны на календаре — их данные сохраняются,
    # пользователь видит свою историю.
    sets = (
        DailyTaskSet.query
        .filter(
            DailyTaskSet.user_id == current_user.id,
            DailyTaskSet.target_date >= first_dt,
            DailyTaskSet.target_date <= last_dt,
        )
        .all()
    )
    set_ids = [s.id for s in sets]
    set_by_id = {s.id: s for s in sets}

    # Подтягиваем items одним запросом (избегаем N+1).
    items_by_set: Dict[int, list] = {sid: [] for sid in set_ids}
    if set_ids:
        items = (
            DailyTaskItem.query
            .filter(DailyTaskItem.daily_set_id.in_(set_ids))
            .all()
        )
        for it in items:
            items_by_set.setdefault(it.daily_set_id, []).append(it)

    # Собираем массив с статистикой по каждому дню месяца.
    days = []
    for d in range(1, last_day + 1):
        the_date = date(year, month, d)
        ds = next(
            (s for s in sets if s.target_date == the_date),
            None,
        )
        solved = 0
        total = 0
        status = None
        if ds is not None:
            ds_items = items_by_set.get(ds.id, [])
            total = len(ds_items)
            solved = sum(1 for it in ds_items if it.is_correct)
            status = ds.status

        # Категория для подсветки на фронте (информативно — фронт может
        # сам пересчитать, но сервер тоже отдаёт для удобства).
        if total == 0:
            tier = "empty"
        elif solved == 0:
            tier = "gray"
        elif solved <= 3:
            tier = "pale"
        elif solved <= 6:
            tier = "green"
        elif solved <= 9:
            tier = "bright"
        else:  # >= 10
            tier = "gold"

        days.append({
            "date": the_date.isoformat(),
            "day": d,
            "solved": solved,
            "total": total,
            "status": status,
            "tier": tier,
            "is_today": (the_date == today),
            "is_future": (the_date > today),
        })

    return jsonify({
        "success": True,
        "year": year,
        "month": month,
        "today": today.isoformat(),
        "days": days,
    }), 200


# ──────────────────────────────────────────────────────────────────────
# GET /daily_tasks/day_history/<date>
# ──────────────────────────────────────────────────────────────────────
#
# Возвращает список задач (и их статусы) за указанный день.
# Используется для модалки/панели, которая открывается по клику на
# дату в календаре.
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/day_history/<date_iso>", methods=["GET"])
@login_required
def day_history(date_iso: str):
    """Список задач, решённых пользователем в указанную дату."""
    try:
        target = date.fromisoformat(date_iso)
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Неверный формат даты (ожидается YYYY-MM-DD)",
        }), 400

    daily_set = DailyTaskSet.query.filter_by(
        user_id=current_user.id,
        target_date=target,
    ).first()

    if not daily_set:
        return jsonify({
            "success": True,
            "date": date_iso,
            "has_set": False,
            "solved": 0,
            "total": 0,
            "status": None,
            "items": [],
        }), 200

    items = (
        DailyTaskItem.query
        .filter_by(daily_set_id=daily_set.id)
        .order_by(DailyTaskItem.position.asc())
        .all()
    )

    items_payload = []
    for it in items:
        # Краткий превью текста задачи (для модалки).
        preview = (it.task_text or "").strip()
        if len(preview) > 220:
            preview = preview[:220].rstrip() + "…"
        items_payload.append({
            "id": it.id,
            "position": it.position,
            "topic": it.topic,
            "subject": it.subject,
            "difficulty_level": it.difficulty_level,
            "preview": preview,
            "is_correct": it.is_correct,
            "is_answered": it.user_answer is not None,
            "answered_at": it.answered_at.isoformat() + "Z" if it.answered_at else None,
        })

    solved = sum(1 for it in items if it.is_correct)
    total = len(items)

    return jsonify({
        "success": True,
        "date": date_iso,
        "has_set": True,
        "daily_set_id": daily_set.id,
        "status": daily_set.status,
        "solved": solved,
        "total": total,
        "items": items_payload,
    }), 200

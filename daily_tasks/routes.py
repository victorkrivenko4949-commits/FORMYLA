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
from utils.math_text_fixer import wrap_bare_math
from services.streak_service import (
    get_or_create_streak, check_streak_on_open, complete_day,
    take_day_off, set_is_fully_answered, compute_all_correct,
)

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

    * Нет сета -> 404 ``{"status": "no_set", "message": "..."}`` (JSON)
                 или рендер шаблона с теми же данными (HTML)
    * Генерация -> 202 ``{"status": "generating", "progress_pct": ..., ...}``
    * Готов / частично -> 200 с полным набором задач
    """
    if not current_user.has_access():
        return render_template('trial_expired.html'), 402
    user_id = current_user.id
    today = today_in_user_tz()

    # ── T8 streak: check on open ────────────────────────────────────
    streak = check_streak_on_open(user_id, today)

    # ── Цикл месяца: реальная тема дня + блокировка срезом ──────────
    cycle_info = {}
    blocked = False
    blocked_theme_title = None
    try:
        from curator.monthly_cycle import get_cycle_info
        cycle_info = get_cycle_info(user_id)
        if cycle_info.get('active') and cycle_info.get('blocked') and not cycle_info.get('finished'):
            blocked = True
            _ct = cycle_info.get('current_theme', '')
            from daily_tasks.monthly_plan import subtopic_title as _stt
            blocked_theme_title = _stt(_ct) if _ct else 'тема дня'
    except Exception:
        pass

    # ── Реальная тема дня из цикла (fallback на ротацию) ────────────
    real_theme_title = None
    if cycle_info.get('current_theme'):
        try:
            from daily_tasks.monthly_plan import subtopic_title as _stt2
            real_theme_title = _stt2(cycle_info['current_theme'])
        except Exception:
            pass
    if not real_theme_title:
        real_theme_title = _theme_for_day(today, None)

    # ── BLOCKED: если в первую неделю срез не пройден — блокируем
    # выдачу задач дня ДО обращения к банку (иначе банк вернёт
    # plan_missing/empty и пользователь не увидит требование среза). ──
    if blocked:
        data = {
            "status": "blocked",
            "daily_set_id": None,
            "target_date": today.isoformat(),
            "message": (
                f"До получения задач дня нужно выполнить утренний срез: "
                f"«{blocked_theme_title}». 5 задач, примерно 15 минут."
            ),
            "class_level": None,
            "summary": None,
            "generated_at": None,
            "total_cost_usd": None,
            "progress": {"completed": 0, "total": 0},
            "items": [],
            "blocked": True,
            "blocked_theme": cycle_info.get('current_theme'),
            "blocked_theme_title": blocked_theme_title,
            "probe_url": "/prep/probe",
        }
        return render_template(
            "daily_tasks/daily_tasks_dashboard.html",
            data={**data, "theme_today": real_theme_title},
        )

    # ── BANK: задачи дня выдаются из предзаполненного банка ─────────
    # build_daily_set сам пишет выданное в bank_issues и идемпотентен
    # по (user_id, issued_date). Флаги plan_missing/bank_exhausted/
    # bank_empty дают код 200 с русским текстом.
    # ── BANK: предзаполненный daily_task_bank (заливает человек). ──────
    # Если банк пуст (bank_empty) или план месяца не задан в
    # UserSubtopicAssignment (plan_missing), НЕ показываем empty-state:
    # проваливаемся ниже к pick_daily_set — ротации по monthly_cycle +
    # FORMYLA_BANK.jsonl, которая умеет выдать задачи дня.
    try:
        from services.bank_daily import build_daily_set as _build_bank_set
        _bank = _build_bank_set(user_id, today)
        if _bank.get("bank_empty"):
            logger.info(
                "daily_tasks: bank_empty для user=%d — fallback на pick_daily_set",
                user_id,
            )
        elif _bank.get("plan_missing"):
            logger.info(
                "daily_tasks: plan_missing для user=%d — fallback на pick_daily_set",
                user_id,
            )
        else:
            if _bank.get("bank_exhausted"):
                logger.warning(
                    "daily_tasks: bank_exhausted для user=%d date=%s, выдано %d задач",
                    user_id, today, len(_bank.get("items", [])),
                )
            _bank_items = _bank.get("items", [])
            if _bank_items:
                _bank_data = {
                    "status": "ready" if _bank_items else "partial",
                    "daily_set_id": None,
                    "target_date": today.isoformat(),
                    "class_level": None,
                    "summary": None,
                    "generated_at": None,
                    "total_cost_usd": None,
                    "bank_exhausted": bool(_bank.get("bank_exhausted")),
                    "progress": {"completed": 0, "total": len(_bank_items)},
                    "items": [
                        {
                            "id": t.id,
                            "position": getattr(t, "position", None) or (i + 1),
                            "task_text": wrap_bare_math(t.statement or ""),
                            "correct_answer": t.answer or "",
                            "solution": t.solution or "",
                            "subtopic": t.subtopic or "",
                            "topic": t.section or "",
                            "difficulty": t.level or 1,
                            "difficulty_level": t.level or 1,
                            "user_answer": None,
                            "is_correct": None,
                            "is_flagged": False,
                            "is_calibration": False,
                            "figure_url": None,
                        }
                        for i, t in enumerate(_bank_items)
                    ],
                }
                return render_template(
                    "daily_tasks/daily_tasks_dashboard.html",
                    data={**_bank_data, "theme_today": real_theme_title},
                )
    except Exception as _bank_err:
        logger.exception("daily_tasks: build_daily_set failed for user=%d: %s", user_id, _bank_err)

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

    # ──   Monthly plan (prep_plan from CuratorState) ────────────
    plan_data = _build_monthly_plan_data(user_id, today)
    if plan_data:
        data["plan_data"] = plan_data

    # ── T8 streak data for template ──────────────────────────────────
    streak_rec = get_or_create_streak(user_id)
    data["streak"] = {
        "current_streak": streak_rec.current_streak or 0,
        "max_streak": streak_rec.max_streak or 0,
        "days_off_available": streak_rec.days_off_available or 0,
    }

    if wants_html:
        return render_template("daily_tasks/daily_tasks_dashboard.html", data={**data, "theme_today": real_theme_title})
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
            content_type = photo_file.content_type or 'application/octet-stream'

            from services.photo_upload import prepare_photo, PhotoError
            try:
                photo_bytes, content_type = prepare_photo(
                    photo_bytes, content_type, photo_file.filename or '',
                )
            except PhotoError as pe:
                return jsonify(error=pe.message), pe.status

            from services.storage import upload_photo, StorageError
            try:
                file_path_rel, _ = upload_photo(photo_bytes, current_user.id, content_type)
            except StorageError as se:
                return jsonify(error=str(se)), 500
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

    # ── T8 streak: if set is fully answered, update streak ────────────
    if completed == total and total > 0:
        all_correct = compute_all_correct(item.daily_set_id)
        complete_day(current_user.id, today_in_user_tz(), all_correct)

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
# POST /daily_tasks/take-day-off — T8 streak
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/take-day-off", methods=["POST"])
@login_required
def take_day_off_route():
    """Взять выходной: сохранить серию, не менять mu/sigma."""
    user_id = current_user.id
    today = today_in_user_tz()
    ok = take_day_off(user_id, today)
    if not ok:
        return jsonify({"success": False, "message": "Нет доступных выходных"}), 400
    return jsonify({"success": True}), 200


# ──────────────────────────────────────────────────────────────────────
# POST /daily_tasks/regenerate
# ──────────────────────────────────────────────────────────────────────


@daily_tasks_bp.route("/regenerate", methods=["POST"])
@login_required
def regenerate():
    """Перегенерировать сегодняшний набор задач.

    AI-генерация «Задач дня» отключена (см. AI_GENERATION_ENABLED в
    daily_tasks/services.py). Выдача задач дня идёт только из банка
    daily_task_bank, поэтому ручная перегенерация LLM недоступна.
    """
    return jsonify({
        "status": "disabled",
        "message": "AI-генерация задач дня отключена. Задачи выдаются из банка.",
    }), 200


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

    # D2: серверная проверка наличия решения перед AI-вызовом
    has_solution_text = len(user_solution.strip()) > 0
    has_solution_photo = len(images_b64) > 0
    if not has_solution_text and not has_solution_photo:
        return jsonify({
            "status": "error",
            "error": "Опиши решение или прикрепи фото.",
        }), 400

    # Если AI-проверка недоступна (нет файла services/ai_tutor_review.py на проде)
    if review_attempt is None:
        return jsonify({
            "status": "error",
            "message": "AI-проверка временно недоступна",
        }), 503

    # Единый pipeline проверки (OCR + checker) с жёстким таймаутом 60 секунд.
    import concurrent.futures as _cf
    _verdict = None
    try:
        from services.solution_check_pipeline import check_solution
        with _cf.ThreadPoolExecutor(max_workers=1) as _executor:
            _future = _executor.submit(
                check_solution,
                entity_type="daily_task",
                task_text=item.task_text or "",
                correct_answer=item.correct_answer or "",
                solution_ref=item.solution or "",
                user_answer=user_answer,
                user_solution=user_solution,
                images_b64=images_b64,
                difficulty_level=getattr(item, "difficulty_level", 4) or 4,
            )
            try:
                _verdict = _future.result(timeout=60)
            except _cf.TimeoutError:
                logger.warning("submit_answer_ai: pipeline timed out after 60s — fallback")
    except Exception as e:  # pragma: no cover
        logger.exception("submit_answer_ai: pipeline failed: %s", e)

    from services.md_render import md_render
    from utils.math_text_fixer import wrap_bare_math

    if _verdict is None:
        # Таймаут или ошибка — сохраняем ответ без AI-проверки
        score = 0.0
        feedback = "AI-проверка временно недоступна. Ответ сохранён."
        is_correct = False
    else:
        score = float(_verdict.get("score", 0.0))
        feedback = str(md_render(wrap_bare_math(_verdict.get("feedback") or "")))
        is_correct = bool(_verdict.get("is_correct"))
        # Низкое доверие OCR — предупреждаем ученика
        if _verdict.get("ocr") and _verdict["ocr"].get("low_confidence"):
            warn = _verdict["ocr"].get("warning") or "Распознавание фото ненадёжно."
            feedback = f"⚠️ {warn}<br><br>{feedback}"

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

    # «Банк неточностей»: ставим решение в очередь на скрининг (фоновый анализ).
    try:
        from services.insight_queue import enqueue_screen
        enqueue_screen(
            user_id=current_user.id,
            task_text=item.task_text or "",
            correct_answer=item.correct_answer or "",
            solution_ref=item.solution or "",
            user_solution=user_solution or user_answer,
            topic=getattr(item, "topic", "") or "",
            difficulty_level=getattr(item, "difficulty_level", 4) or 4,
            time_spent_sec=int(data.get("time_spent_seconds") or 0) or None,
            source="daily_task",
            source_task_id=item.id,
        )
    except Exception:
        pass  # анализ неточностей никогда не должен ронять основной поток

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
        "solution": str(md_render(wrap_bare_math(item.solution or ""))),
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
#   0          -> серая
#   1–3        -> бледно-зелёная
#   4–6        -> зелёная
#   7–9        -> яркая зелёная
#   10 (или больше) -> золотая (с короной)
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
        preview = wrap_bare_math((it.task_text or "").strip())
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

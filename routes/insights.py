# -*- coding: utf-8 -*-
"""Blueprint «Банк неточностей» — API + админ-статистика (разделы 9–10 ТЗ).

Endpoints:
  GET  /api/insights?status=&type=&tag=      — список неточностей.
  GET  /api/insights/:id                     — деталь с задачами.
  POST /api/insights/:id/practice/:taskId/answer — проверка ответа.
  POST /api/insights/:id/practice/regenerate — ещё 3 задачи (в фоне).
  POST /api/insights/:id/dismiss             — «описка» / «не моя ошибка».
  GET  /api/insights/notifications/pending   — pending, suppressed при срезе.
  POST /api/insights/notifications/:id/seen  — пометить просмотренным.
  GET  /api/admin/insights/stats             — админ-метрики.

Плюс страница банка:
  GET  /insights                              — HTML-страница раздела.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from models import db
from models_insights import (
    Insight,
    InsightNotification,
    InsightPracticeTask,
    normalize_title,
)

logger = logging.getLogger(__name__)

insights_bp = Blueprint("insights", __name__, url_prefix="")


# ─── Вспомогательные ─────────────────────────────────────────────────────

def _active_review_session(user_id: int) -> bool:
    """True, если у пользователя активная сессия «Среза»."""
    try:
        from services.theme_probe import has_active_probe
        return bool(has_active_probe(user_id))
    except Exception:  # noqa: BLE001
        return False


def _own_or_404(insight_id: int) -> Insight:
    insight = Insight.query.filter_by(
        id=insight_id, user_id=current_user.id
    ).first_or_404()
    return insight


def _parse_tags(raw) -> list:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


# ─── Список ──────────────────────────────────────────────────────────────

@insights_bp.route("/api/insights")
@login_required
def api_insights_list():
    q = Insight.query.filter_by(user_id=current_user.id)

    status = request.args.get("status")
    if status:
        q = q.filter(Insight.status == status)

    itype = request.args.get("type")
    if itype:
        q = q.filter(Insight.type == itype)

    tag = request.args.get("tag")
    if tag:
        q = q.filter(Insight.tags.like(f'%"{tag}"%'))

    sort = request.args.get("sort", "date")
    if sort == "severity":
        q = q.order_by(Insight.severity.desc(), Insight.created_at.desc())
    else:
        q = q.order_by(Insight.created_at.desc())

    rows = q.all()
    return jsonify([r.to_dict() for r in rows])


# ─── Деталь с задачами ───────────────────────────────────────────────────

@insights_bp.route("/api/insights/<int:insight_id>")
@login_required
def api_insight_detail(insight_id: int):
    insight = _own_or_404(insight_id)
    data = insight.to_dict()
    data["practice"] = [p.to_dict(reveal=True) for p in insight.practice_tasks]
    return jsonify(data)


# ─── Проверка ответа ─────────────────────────────────────────────────────

@insights_bp.route("/api/insights/<int:insight_id>/practice/<int:task_id>/answer",
                   methods=["POST"])
@login_required
def api_practice_answer(insight_id: int, task_id: int):
    from utils.math_answer_utils import compare_math_answers

    insight = _own_or_404(insight_id)
    task = InsightPracticeTask.query.filter_by(
        id=task_id, insight_id=insight.id
    ).first_or_404()

    data = request.get_json(silent=True) or {}
    user_answer = (data.get("answer") or "").strip()
    correct = compare_math_answers(user_answer, task.answer or "")

    was_correct = bool(task.is_correct)

    task.user_answer = user_answer
    task.is_correct = bool(correct)
    if correct and task.solved_at is None:
        task.solved_at = datetime.utcnow()

    # Обновить прогресс неточности.
    solved = insight.practice_tasks.filter_by(is_correct=True).count()
    total = insight.practice_tasks.count() or insight.progress_total or 3
    insight.progress_done = solved
    if solved >= 3:
        insight.status = "mastered"
    elif solved > 0:
        insight.status = "in_progress"

    # ── XP за отработку (связь с лидербордом), одна транзакция ─────
    # +5 XP за каждую верно решённую задачу на отработку (один раз
    # на задачу), +15 XP бонусом, когда неточность закрыта полностью.
    xp_gained = 0
    if correct and not was_correct:
        from models import User as _User
        _u = db.session.get(_User, current_user.id)
        if _u is not None:
            _u.experience_points = (_u.experience_points or 0) + 5
            _u.total_problems_solved = (_u.total_problems_solved or 0) + 1
            xp_gained += 5
    if insight.status == "mastered" and not getattr(insight, "mastered_xp_awarded", False):
        from models import User as _User2
        _u2 = db.session.get(_User2, current_user.id)
        if _u2 is not None:
            _u2.experience_points = (_u2.experience_points or 0) + 15
            xp_gained += 15
        insight.mastered_xp_awarded = True
    db.session.commit()

    return jsonify({
        "correct": bool(correct),
        "correct_answer": task.answer,
        "progress_done": insight.progress_done,
        "progress_total": total,
        "xp_gained": xp_gained,
        "status": insight.status,
    })


# ─── Ещё 3 задачи (в фоне) ───────────────────────────────────────────────

@insights_bp.route("/api/insights/<int:insight_id>/practice/regenerate",
                   methods=["POST"])
@login_required
def api_practice_regenerate(insight_id: int):
    insight = _own_or_404(insight_id)
    from services.insight_queue import enqueue_regenerate

    job_id = enqueue_regenerate(insight)
    return jsonify({"status": "queued", "job_id": job_id})


# ─── Обратная связь (dismiss) ────────────────────────────────────────────

@insights_bp.route("/api/insights/<int:insight_id>/dismiss", methods=["POST"])
@login_required
def api_insight_dismiss(insight_id: int):
    insight = _own_or_404(insight_id)
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if reason not in ("slip", "not_mine"):
        return jsonify({"error": "reason must be 'slip' or 'not_mine'"}), 400

    insight.status = "dismissed"
    insight.dismiss_reason = reason
    db.session.commit()

    logger.info(
        "[insight] dismissed id=%s user=%s reason=%s",
        insight.id, current_user.id, reason,
    )
    return jsonify({"status": "dismissed", "reason": reason})


# ─── Уведомления ─────────────────────────────────────────────────────────

@insights_bp.route("/api/insights/notifications/pending")
@login_required
def api_notifications_pending():
    suppressed = _active_review_session(current_user.id)
    pending = (
        InsightNotification.query
        .filter_by(user_id=current_user.id, status="pending")
        .order_by(InsightNotification.created_at.desc())
        .all()
    )
    total = sum(n.insights_count or 1 for n in pending)
    tasks = sum(n.tasks_count or 0 for n in pending)
    payload = {
        "suppressed": suppressed,
        "count": len(pending),
        "insights_count": total,
        "tasks_count": tasks,
        "notifications": [
            {
                "id": n.id,
                "kind": n.kind,
                "insight_id": n.insight_id,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in pending
        ],
    }
    return jsonify(payload)


@insights_bp.route("/api/insights/notifications/<int:notification_id>/seen",
                   methods=["POST"])
@login_required
def api_notification_seen(notification_id: int):
    n = InsightNotification.query.filter_by(
        id=notification_id, user_id=current_user.id
    ).first_or_404()
    if n.status != "seen":
        n.status = "seen"
        n.seen_at = datetime.utcnow()
        db.session.commit()
    return jsonify({"status": "seen"})


# ─── Админ-статистика ────────────────────────────────────────────────────

@insights_bp.route("/api/admin/insights/stats")
@login_required
def api_admin_insights_stats():
    if current_user.id != 1:
        return jsonify({"error": "forbidden"}), 403

    from models_insights import InsightJob

    jobs = InsightJob.query.all()
    total_screen = sum(1 for j in jobs if j.stage == "screen")
    skipped_screen = sum(
        1 for j in jobs if j.stage == "screen" and j.status == "skipped"
    )
    screen_rejection_rate = (
        (skipped_screen / total_screen) if total_screen else 0.0
    )

    deep_jobs = [j for j in jobs if j.stage == "deep"]
    reasoning_values = sorted(
        j.reasoning_tokens for j in deep_jobs if j.reasoning_tokens is not None
    )

    insights = Insight.query.all()
    dismissed = sum(1 for i in insights if i.status == "dismissed")
    dismissed_rate = (dismissed / len(insights)) if insights else 0.0
    # Разбивка отклонений по причинам: not_mine — показатель ложных
    # срабатываний анализа, slip — ученик считает это опиской.
    dismissed_slip = sum(
        1 for i in insights if i.status == "dismissed" and i.dismiss_reason == "slip"
    )
    dismissed_not_mine = sum(
        1 for i in insights if i.status == "dismissed" and i.dismiss_reason == "not_mine"
    )

    practice_tasks = InsightPracticeTask.query.all()
    from_bank = sum(1 for p in practice_tasks if p.source == "bank")
    from_generated = sum(1 for p in practice_tasks if p.source == "generated")
    total_practice = len(practice_tasks)

    return jsonify({
        "screen": {
            "total": total_screen,
            "skipped": skipped_screen,
            "rejection_rate": round(screen_rejection_rate, 4),
        },
        "deep": {
            "total": len(deep_jobs),
            "reasoning_tokens_distribution": {
                "min": reasoning_values[0] if reasoning_values else None,
                "p50": reasoning_values[len(reasoning_values) // 2] if reasoning_values else None,
                "p90": reasoning_values[int(len(reasoning_values) * 0.9)] if reasoning_values else None,
                "max": reasoning_values[-1] if reasoning_values else None,
            },
        },
        "quality": {
            "total_insights": len(insights),
            "dismissed": dismissed,
            "dismissed_rate": round(dismissed_rate, 4),
            # precision = 1 - not_mine_rate: доля реальных неточностей
            "dismissed_slip": dismissed_slip,
            "dismissed_not_mine": dismissed_not_mine,
            "not_mine_rate": round(
                (dismissed_not_mine / len(insights)) if insights else 0.0, 4
            ),
        },
        "practice_sources": {
            "bank": from_bank,
            "generated": from_generated,
            "total": total_practice,
            "bank_rate": round((from_bank / total_practice), 4) if total_practice else 0.0,
        },
    })


# ─── HTML-страница ───────────────────────────────────────────────────────

@insights_bp.route("/insights")
@login_required
def insights_page():
    analyzed_count = 0
    try:
        from models_insights import InsightJob
        analyzed_count = InsightJob.query.filter_by(user_id=current_user.id).count()
    except Exception:  # noqa: BLE001
        pass
    return render_template("insights.html", analyzed_count=analyzed_count)

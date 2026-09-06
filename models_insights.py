# -*- coding: utf-8 -*-
"""Модели «Банка неточностей» (Insights).

4 таблицы Этапа 1 + Этапа 2 ТЗ `roo_etap2_analiz_promty_ui.md`:

1. insight_jobs           — очередь фонового анализа решения (screen/deep).
2. insights               — найденная «неточность» (недостаток метода).
3. insight_practice_tasks — 3 задачи на отработку ровно этого места.
4. insight_notifications  — отложенное уведомление «банк пополнился».

Импортируется в app.py до auto_migrate, чтобы SQLAlchemy зарегистрировал
таблицы и они создались/долились идемпотентно.
"""

from datetime import datetime

from models import db

# ─── Допустимые значения ────────────────────────────────────────────────

INSIGHT_TYPES = (
    "wrong_approach",   # неверный подход
    "time_loss",        # потеря времени
    "missing_fact",     # незнание/неприменение факта
    "proof_gap",        # пробел в доказательстве
    "bad_form",         # неудобная форма
)

VISIBILITIES = ("obvious", "medium", "hidden")

SKIP_REASONS = ("no_issue", "arithmetic_slip", "bad_luck", "too_generic")

JOB_STAGES = ("screen", "deep")


def normalize_title(title: str) -> str:
    """Нормализация title для дедупликации (lowercase, без знаков препинания)."""
    import re
    s = (title or "").lower()
    s = re.sub(r"[^0-9a-zа-яё ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class InsightJob(db.Model):
    """Очередь фонового разбора решения пользователя.

    stage=screen — дешёвый скрининг (effort=low) для каждого решения.
    stage=deep   — дорогой глубокий разбор (effort=max), только если скрининг
                   вернул needs_deep_analysis=true.
    """

    __tablename__ = "insight_jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    stage = db.Column(db.String(16), nullable=False, default="screen", index=True)
    status = db.Column(db.String(16), nullable=False, default="queued", index=True)
    # status: queued | processing | done | skipped | failed

    skip_reason = db.Column(db.String(32), nullable=True)
    preliminary_type = db.Column(db.String(32), nullable=True)

    # Источник решения и ссылка на исходную задачу/попытку.
    source = db.Column(db.String(32), nullable=False, default="regular", index=True)
    # source: daily_task | srez | regular | regenerate
    source_task_id = db.Column(db.Integer, nullable=True)
    source_attempt_id = db.Column(db.Integer, nullable=True, index=True)

    # Снапшот данных для промта (переживает удаление исходной записи).
    task_text = db.Column(db.Text, nullable=True)
    correct_answer = db.Column(db.Text, nullable=True)
    solution_ref = db.Column(db.Text, nullable=True)
    user_solution = db.Column(db.Text, nullable=True)
    topic = db.Column(db.String(200), nullable=True)
    difficulty_level = db.Column(db.Integer, nullable=True)

    # Временные метки (для промта «потеря времени»).
    time_spent_sec = db.Column(db.Integer, nullable=True)
    etalon_time_sec = db.Column(db.Integer, nullable=True)

    # Телеметрия (см. раздел 6 ТЗ: reasoning_tokens обязательны).
    reasoning_tokens = db.Column(db.Integer, nullable=True)
    attempts_count = db.Column(db.Integer, nullable=False, default=0)
    cost_usd = db.Column(db.Float, nullable=False, default=0.0)
    error = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("insight_jobs", lazy="dynamic"))

    def __repr__(self):
        return (
            f"<InsightJob id={self.id} user={self.user_id} "
            f"stage={self.stage} status={self.status}>"
        )


class Insight(db.Model):
    """Найденная «неточность» — грубый содержательный недостаток метода."""

    __tablename__ = "insights"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    job_id = db.Column(db.Integer, nullable=True, index=True)

    title = db.Column(db.String(200), nullable=False)
    title_normalized = db.Column(db.String(200), nullable=False, index=True)
    type = db.Column(db.String(32), nullable=False, index=True)
    severity = db.Column(db.Integer, nullable=False, default=1)  # 1..3

    location_text = db.Column(db.Text, nullable=True)   # «где» в решении ученика
    what_went_wrong = db.Column(db.Text, nullable=True)
    better_way = db.Column(db.Text, nullable=True)
    time_lost_estimate_min = db.Column(db.Integer, nullable=True)
    canonical_fact = db.Column(db.Text, nullable=True)  # что выучить

    tags = db.Column(db.Text, nullable=True)  # JSON-массив ["topic:...", "method:..."]

    # Состояние отработки.
    status = db.Column(db.String(32), nullable=False, default="active", index=True)
    # status: active | in_progress | mastered | dismissed
    dismiss_reason = db.Column(db.String(32), nullable=True)  # slip | not_mine

    occurrences = db.Column(db.Integer, nullable=False, default=1)

    # Источник и ссылка на исходную задачу.
    source = db.Column(db.String(32), nullable=False, default="regular", index=True)
    source_task_id = db.Column(db.Integer, nullable=True)

    progress_done = db.Column(db.Integer, nullable=False, default=0)
    progress_total = db.Column(db.Integer, nullable=False, default=3)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("insights", lazy="dynamic"))
    practice_tasks = db.relationship(
        "InsightPracticeTask",
        backref="insight",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="InsightPracticeTask.position",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "severity": self.severity,
            "what_went_wrong": self.what_went_wrong,
            "better_way": self.better_way,
            "canonical_fact": self.canonical_fact,
            "time_lost_estimate_min": self.time_lost_estimate_min,
            "tags": _parse_tags(self.tags),
            "status": self.status,
            "dismiss_reason": self.dismiss_reason,
            "occurrences": self.occurrences,
            "source": self.source,
            "source_task_id": self.source_task_id,
            "progress_done": self.progress_done,
            "progress_total": self.progress_total,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Insight id={self.id} user={self.user_id} type={self.type}>"


def _parse_tags(raw):
    import json
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


class InsightPracticeTask(db.Model):
    """Задача на отработку конкретной неточности (ровно 3 на неточность)."""

    __tablename__ = "insight_practice_tasks"

    id = db.Column(db.Integer, primary_key=True)
    insight_id = db.Column(
        db.Integer, db.ForeignKey("insights.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    position = db.Column(db.Integer, nullable=False, default=1)  # 1..3
    statement = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=True)
    hint = db.Column(db.Text, nullable=True)
    solution_sketch = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.Integer, nullable=False, default=1)  # 1..5
    visibility = db.Column(db.String(16), nullable=False, default="medium")  # obvious|medium|hidden
    why_this_task = db.Column(db.Text, nullable=True)
    naive_path_cost = db.Column(db.Text, nullable=True)

    source = db.Column(db.String(16), nullable=False, default="generated")  # bank | generated
    bank_task_id = db.Column(db.Integer, nullable=True)

    # Проверка ответа.
    user_answer = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    solved_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self, reveal=False):
        d = {
            "id": self.id,
            "position": self.position,
            "statement": self.statement,
            "difficulty": self.difficulty,
            "visibility": self.visibility,
            "source": self.source,
            "is_correct": self.is_correct,
            "solved_at": self.solved_at.isoformat() if self.solved_at else None,
        }
        if reveal:
            d["answer"] = self.answer
            d["hint"] = self.hint
            d["solution_sketch"] = self.solution_sketch
            d["why_this_task"] = self.why_this_task
            d["naive_path_cost"] = self.naive_path_cost
        return d

    def __repr__(self):
        return f"<InsightPracticeTask id={self.id} insight={self.insight_id} pos={self.position}>"


class InsightNotification(db.Model):
    """Отложенное уведомление «Твой банк неточностей пополнился»."""

    __tablename__ = "insight_notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    kind = db.Column(db.String(16), nullable=False, default="new")  # new | repeat
    insight_id = db.Column(db.Integer, nullable=True, index=True)

    insights_count = db.Column(db.Integer, nullable=False, default=1)
    tasks_count = db.Column(db.Integer, nullable=False, default=3)

    status = db.Column(db.String(16), nullable=False, default="pending", index=True)
    # status: pending | seen
    suppressed = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    seen_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", backref=db.backref("insight_notifications", lazy="dynamic"))

    def __repr__(self):
        return (
            f"<InsightNotification id={self.id} user={self.user_id} "
            f"kind={self.kind} status={self.status}>"
        )

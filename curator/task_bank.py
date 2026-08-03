# -*- coding: utf-8 -*-
"""
task_bank.py — Банк задач для модуля «Куратор».

Модель TaskBank хранит верифицированные задачи для диагностики,
учебных планов и AI-тьютора. Задачи разбиты по 5 темам, уровням
сложности 1–10, содержат готовые подсказки (hints) и теги.

Используется вместо AdaptiveTask в модулях diagnostics, planner, tutor.
"""

import json
from datetime import datetime

from models import db


class TaskBank(db.Model):
    """Банк задач Куратора.

    Поля:
        id          — первичный ключ
        topic       — тема (algebra, geometry, combinatorics, number_theory, logic)
        subtopic    — подтема (например, "quadratic_equations", "triangles")
        difficulty  — уровень сложности (1–10)
        statement   — условие задачи (с LaTeX-разметкой $...$)
        answer      — правильный ответ (строка)
        solution    — эталонное решение (с пояснением)
        hints       — JSON-массив подсказок (3 уровня: общая -> ключевой шаг -> детальная)
        source      — источник задачи (например, "vsosh_2024", "formyla", "manual")
        tags        — JSON-массив тегов (например, ["divisibility", "modulo"])
        created_at  — дата создания записи
    """

    __tablename__ = "task_bank"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    topic = db.Column(db.String(64), nullable=False, index=True)
    subtopic = db.Column(db.String(128), nullable=True, index=True)
    difficulty = db.Column(db.Integer, nullable=False, default=5)
    statement = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    solution = db.Column(db.Text, nullable=True)
    hints = db.Column(db.Text, nullable=True)  # JSON-массив строк
    source = db.Column(db.String(128), nullable=True)
    tags = db.Column(db.Text, nullable=True)  # JSON-массив строк
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )

    # ─── JSON-геттеры/сеттеры ──────────────────────────────────────────────

    @property
    def hints_list(self) -> list:
        """Вернуть hints как list[str]."""
        if not self.hints:
            return []
        try:
            return json.loads(self.hints)
        except (json.JSONDecodeError, TypeError):
            return []

    @hints_list.setter
    def hints_list(self, value: list):
        self.hints = json.dumps(value, ensure_ascii=False)

    @property
    def tags_list(self) -> list:
        """Вернуть tags как list[str]."""
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)
        except (json.JSONDecodeError, TypeError):
            return []

    @tags_list.setter
    def tags_list(self, value: list):
        self.tags = json.dumps(value, ensure_ascii=False)

    def to_dict(self) -> dict:
        """Сериализовать в dict для API."""
        return {
            "id": self.id,
            "topic": self.topic,
            "subtopic": self.subtopic,
            "difficulty": self.difficulty,
            "statement": self.statement,
            "answer": self.answer,
            "solution": self.solution,
            "hints": self.hints_list,
            "source": self.source,
            "tags": self.tags_list,
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
        }

    def __repr__(self):
        return (
            f"<TaskBank #{self.id} {self.topic} "
            f"diff={self.difficulty}>"
        )

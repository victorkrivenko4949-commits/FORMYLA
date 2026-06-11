# -*- coding: utf-8 -*-
"""
Модели раздела «Олимпиады» (`/olympiads/*`).

Содержит 6 моделей под URL-префикс `/olympiads`:

  * Probnik         — пробник (тематический или этапный).
  * Task            — задача пробника.
  * TheoryBlock     — теоретический блок (метод/раздел).
  * ProbnikTheory   — связка пробник ↔ теоретический блок.
  * TaskAttempt     — попытка пользователя решить отдельную задачу.
  * StageAttempt    — попытка прохождения этапного пробника целиком.

Названия таблиц подобраны с префиксом `olympiad_*`, чтобы не конфликтовать
с уже существующими в проекте таблицами (`olympiad_prep`, `olympiad_secrets`,
`olympiad_generation_log`).

Импорт `db` идёт из общего `models.py`, поэтому все модели регистрируются в
едином `SQLAlchemy()`-экземпляре приложения.  Для удобства использования
снаружи (миграции, импортёр, маршруты) модели также реэкспортируются из
`models.py` через `from models_olympiad import *`.

ВНИМАНИЕ: класс назван `OlympiadTask` (не просто `Task`), чтобы избежать
коллизий с возможными будущими моделями `Task` и для прозрачного импорта
из всего проекта (`from models import OlympiadTask`).
"""

from datetime import datetime

from sqlalchemy import UniqueConstraint

from models import db


# ──────────────────────────────────────────────────────────────────────────────
# Допустимые значения для перечислений.
#
# Мы намеренно используем `db.String` + CHECK-ограничение (через
# `sqlalchemy.Enum` без `native_enum=True`), чтобы не плодить PostgreSQL-енумы
# и не блокировать миграции при добавлении новых значений.
# ──────────────────────────────────────────────────────────────────────────────

PROBNIK_TYPES = ('topic', 'stage')
DIFFICULTY_LEVELS = ('green', 'yellow', 'orange', 'red')
THEORY_SECTIONS = ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')
ATTEMPT_STATUSES = ('viewed', 'attempted', 'solved', 'revealed')
STAGE_RESULTS = ('participant', 'prize', 'winner')


# ──────────────────────────────────────────────────────────────────────────────
# Probnik
# ──────────────────────────────────────────────────────────────────────────────

class Probnik(db.Model):
    """Пробник: тематический (`topic`) или этапный (`stage`).

    Один пробник принадлежит одной комбинации (competition, grade, season_year).
    Этапные пробники имеют ограничение по времени и пороги для статусов
    «призёр» / «победитель».
    """

    __tablename__ = 'olympiad_probniks'

    id = db.Column(db.Integer, primary_key=True)

    # Стабильный человекочитаемый ключ. Используется в URL `/olympiads/probnik/<code>`.
    # Пример: 'vsosh-9-2027-topic-1', 'vsosh-9-2027-stage-3'.
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)

    type = db.Column(
        db.Enum(*PROBNIK_TYPES, name='probnik_type', native_enum=False),
        nullable=False,
    )
    number = db.Column(db.Integer, nullable=False)  # 1..9 для topic, 1..5 для stage

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    competition = db.Column(db.String(50), nullable=False, default='ВсОШ',
                            server_default='ВсОШ')
    grade = db.Column(db.Integer, nullable=False, default=9, server_default='9')
    season_year = db.Column(db.Integer, nullable=False, default=2027,
                            server_default='2027')

    # Только для этапных пробников.
    duration_minutes = db.Column(db.Integer, nullable=True)
    max_score = db.Column(db.Integer, nullable=True)
    threshold_prize = db.Column(db.Integer, nullable=True)
    threshold_winner = db.Column(db.Integer, nullable=True)

    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    is_published = db.Column(db.Boolean, nullable=False, default=True,
                             server_default='1')

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    tasks = db.relationship(
        'OlympiadTask',
        back_populates='probnik',
        order_by='OlympiadTask.sort_order',
        cascade='all, delete-orphan',
    )
    theory_links = db.relationship(
        'ProbnikTheory',
        back_populates='probnik',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        # Уникальная пара (competition, grade, season_year, type, number).
        # Гарантирует, что у одной олимпиады нет двух «тематических №3».
        UniqueConstraint(
            'competition', 'grade', 'season_year', 'type', 'number',
            name='uq_probnik_slot',
        ),
    )

    def __repr__(self):
        return f"<Probnik {self.code!r} type={self.type} #{self.number}>"


# ──────────────────────────────────────────────────────────────────────────────
# OlympiadTask (внутренний rename из ТЗ-шного `Task` → `OlympiadTask`)
# ──────────────────────────────────────────────────────────────────────────────

class OlympiadTask(db.Model):
    """Задача внутри одного пробника.

    Содержит условие, идею решения, полное решение и короткий ответ.
    Поле `number` — это пользовательская нумерация ('1.1', 'Э3.5'),
    а `sort_order` — машинный порядок отображения.
    """

    __tablename__ = 'olympiad_tasks'

    id = db.Column(db.Integer, primary_key=True)
    probnik_id = db.Column(
        db.Integer,
        db.ForeignKey('olympiad_probniks.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    number = db.Column(db.String(10), nullable=False)   # '1.1', 'Э3.5'
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    difficulty = db.Column(
        db.Enum(*DIFFICULTY_LEVELS, name='olympiad_difficulty', native_enum=False),
        nullable=True,
    )

    method_primary = db.Column(db.String(10), nullable=False)
    method_secondary = db.Column(db.String(10), nullable=True)

    condition_md = db.Column(db.Text, nullable=False)
    idea_md = db.Column(db.Text, nullable=False)
    solution_md = db.Column(db.Text, nullable=False)
    answer = db.Column(db.String(500), nullable=True)

    source_prototype = db.Column(db.String(200), nullable=True)

    estimated_minutes = db.Column(db.Integer, nullable=True)
    max_score = db.Column(db.Integer, nullable=False, default=7, server_default='7')

    # ── ВсОШ-9 импортные поля (xlsx → idempotent) ────────────────────────────
    # Все коды методов, использованных в задаче (primary + secondary, и шире).
    # Хранится как JSON-массив строк: ["E14", "F3"].
    # Включён в дополнение к method_primary/method_secondary, чтобы новый /methods
    # UI мог фильтровать «есть ли вообще такой код» одним запросом.
    method_codes = db.Column(db.JSON, nullable=True)
    # Год тура (2010..2026 для архива ВсОШ-9).
    year = db.Column(db.Integer, nullable=True, index=True)
    # Этап олимпиады: 'school' | 'municipal' | 'regional' | 'final'.
    stage = db.Column(db.String(20), nullable=True, index=True)

    probnik = db.relationship('Probnik', back_populates='tasks')
    attempts = db.relationship(
        'TaskAttempt',
        back_populates='task',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        # Внутри пробника номер задачи должен быть уникален.
        UniqueConstraint('probnik_id', 'number', name='uq_task_probnik_number'),
    )

    def __repr__(self):
        return f"<OlympiadTask #{self.number} probnik_id={self.probnik_id}>"


# ──────────────────────────────────────────────────────────────────────────────
# TheoryBlock
# ──────────────────────────────────────────────────────────────────────────────

class TheoryBlock(db.Model):
    """Один теоретический блок: метод/приём (например, `E14` — индукция).

    `related_methods` хранится как JSON-массив строк-кодов, чтобы можно было
    рендерить ссылки на связанные методы без отдельной таблицы.
    """

    __tablename__ = 'olympiad_theory'

    id = db.Column(db.Integer, primary_key=True)
    method_code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    method_name = db.Column(db.String(200), nullable=False)
    section = db.Column(
        db.Enum(*THEORY_SECTIONS, name='theory_section', native_enum=False),
        nullable=True,
    )

    definition_md = db.Column(db.Text, nullable=True)
    main_theorems_md = db.Column(db.Text, nullable=True)
    typical_techniques_md = db.Column(db.Text, nullable=True)
    triggers_md = db.Column(db.Text, nullable=True)
    worked_example_md = db.Column(db.Text, nullable=True)
    pitfalls_md = db.Column(db.Text, nullable=True)
    why_it_works_md = db.Column(db.Text, nullable=True)

    # JSON-массив строк-кодов: ["F4a","F3"]. Используем `db.JSON` —
    # это совместимый кросс-БД тип (PostgreSQL → JSONB, SQLite → TEXT).
    related_methods = db.Column(db.JSON, nullable=True)

    # Дополнительные поля из methods_final.json (ТЗ 102 методов)
    signal_phrases = db.Column(db.JSON, nullable=True)  # фразы-сигналы в условии
    first_moves = db.Column(db.JSON, nullable=True)     # первые ходы решения
    prerequisites = db.Column(db.JSON, nullable=True)   # method_codes, которые нужно знать
    leads_to = db.Column(db.JSON, nullable=True)        # method_codes, для которых этот — фундамент

    # ── Каталог методов (добавлены миграцией add_methods_catalog_fields.py) ──
    # Список классов, для которых актуален метод (например, [5,6,7,8,9]).
    grades = db.Column(db.JSON, nullable=True)
    # Список олимпиад, где этот метод чаще встречается ("ВсОШ", "Ломоносов"…).
    recommended_competitions = db.Column(db.JSON, nullable=True)
    # Уровень сложности 1..5.
    difficulty_level = db.Column(db.Integer, nullable=True, index=True)
    # Частота встречаемости на ВсОШ-9 (0..10).
    frequency_vsosh_9 = db.Column(db.Integer, nullable=True, index=True)
    # Точное число задач ВсОШ-9, использующих этот метод (по xlsx-аналитике).
    total_count = db.Column(db.Integer, nullable=True, index=True)
    # Доля задач 0..1 (например 0.1356 = метод встречается в 13.56% задач).
    share_percent = db.Column(db.Float, nullable=True)
    # Порядок отображения в каталоге.
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<TheoryBlock {self.method_code!r} {self.method_name!r}>"


# ──────────────────────────────────────────────────────────────────────────────
# ProbnikTheory (связка)
# ──────────────────────────────────────────────────────────────────────────────

class ProbnikTheory(db.Model):
    """Связь Probnik ↔ TheoryBlock с порядком отображения.

    Используется для тематических пробников: к каждому привязан список
    рекомендуемых для повторения теоретических блоков.
    """

    __tablename__ = 'olympiad_probnik_theory'

    probnik_id = db.Column(
        db.Integer,
        db.ForeignKey('olympiad_probniks.id', ondelete='CASCADE'),
        primary_key=True,
    )
    theory_block_id = db.Column(
        db.Integer,
        db.ForeignKey('olympiad_theory.id', ondelete='CASCADE'),
        primary_key=True,
    )
    # Поле `order` зарезервировано в SQL — называем колонку `display_order`,
    # сохраняя «order» как Python-имя нельзя (это keyword).  Используем
    # имя атрибута `display_order` и колонку `display_order` тоже.
    display_order = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    probnik = db.relationship('Probnik', back_populates='theory_links')
    theory_block = db.relationship('TheoryBlock')

    def __repr__(self):
        return (
            f"<ProbnikTheory probnik_id={self.probnik_id} "
            f"theory_block_id={self.theory_block_id} order={self.display_order}>"
        )


# ──────────────────────────────────────────────────────────────────────────────
# TaskAttempt
# ──────────────────────────────────────────────────────────────────────────────

class TaskAttempt(db.Model):
    """Запись о работе пользователя над одной задачей.

    На пару (user, task) хранится одна запись (UNIQUE).  При повторном
    открытии задачи мы обновляем статус и таймер, а не плодим строки.
    """

    __tablename__ = 'olympiad_task_attempts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    task_id = db.Column(
        db.Integer,
        db.ForeignKey('olympiad_tasks.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(*ATTEMPT_STATUSES, name='task_attempt_status', native_enum=False),
        nullable=False,
        default='viewed',
        server_default='viewed',
    )
    self_score = db.Column(db.Integer, nullable=True)          # 0..7
    time_spent_seconds = db.Column(db.Integer, nullable=False,
                                   default=0, server_default='0')
    note = db.Column(db.Text, nullable=True)

    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    task = db.relationship('OlympiadTask', back_populates='attempts')

    __table_args__ = (
        UniqueConstraint('user_id', 'task_id', name='uq_user_task'),
    )

    def __repr__(self):
        return (
            f"<TaskAttempt user_id={self.user_id} task_id={self.task_id} "
            f"status={self.status}>"
        )


# ──────────────────────────────────────────────────────────────────────────────
# StageAttempt
# ──────────────────────────────────────────────────────────────────────────────

class StageAttempt(db.Model):
    """Попытка пройти этапный пробник целиком (с таймером + автосдачей).

    `task_scores` — JSON-словарь вида ``{"5.1": 7, "5.2": 4, ...}``, где ключ
    совпадает с `OlympiadTask.number`.  Хранится отдельно от `TaskAttempt`,
    потому что этапный режим — это снимок результата на момент сдачи, а
    отдельные `TaskAttempt`-ы продолжают жить независимо.
    """

    __tablename__ = 'olympiad_stage_attempts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    probnik_id = db.Column(
        db.Integer,
        db.ForeignKey('olympiad_probniks.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )

    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    total_score = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    result = db.Column(
        db.Enum(*STAGE_RESULTS, name='stage_result', native_enum=False),
        nullable=True,
    )

    task_scores = db.Column(db.JSON, nullable=True)
    report_md = db.Column(db.Text, nullable=True)

    probnik = db.relationship('Probnik')

    def __repr__(self):
        return (
            f"<StageAttempt user_id={self.user_id} probnik_id={self.probnik_id} "
            f"score={self.total_score}>"
        )




# ------------------------------------------------------------------------------
# MethodTask  - standalone task bank (VsOSh 9/10/11, 2027)
# ------------------------------------------------------------------------------

METHOD_TASK_PROBABILITY_TIERS = ('CORE', 'LIKELY', 'POSSIBLE', 'RARE')


class MethodTask(db.Model):
    """Standalone task from VsOSh bank (not linked to Probnik).
    Primary key is string id like 10-1, 11-42, 9-7.
    Table method_tasks is created by auto-migration on app start.
    """

    __tablename__ = 'method_tasks'

    id = db.Column(db.String(20), primary_key=True)
    grade = db.Column(db.Integer, nullable=False, index=True)
    olympiad = db.Column(db.String(50), nullable=False, default='VsOSh', server_default='VsOSh')
    subject = db.Column(db.String(20), nullable=False, default='math', server_default='math')
    year = db.Column(db.Integer, nullable=True, index=True)
    num = db.Column(db.Integer, nullable=True)
    stage = db.Column(db.String(50), nullable=True, index=True)
    method_code = db.Column(db.String(20), nullable=False, index=True)
    method_name = db.Column(db.String(300), nullable=True)
    section = db.Column(db.String(100), nullable=True)
    difficulty = db.Column(db.Integer, nullable=True, index=True)
    difficulty_label = db.Column(db.String(100), nullable=True)
    difficulty_color = db.Column(db.String(20), nullable=True)
    method_probability = db.Column(db.String(200), nullable=True)
    method_probability_tier = db.Column(
        db.Enum(*METHOD_TASK_PROBABILITY_TIERS, name='method_probability_tier', native_enum=False),
        nullable=True,
        index=True,
    )
    method_probability_color = db.Column(db.String(20), nullable=True)
    text = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=True)
    solution_idea = db.Column(db.Text, nullable=True)
    task_type = db.Column(db.String(50), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return '<MethodTask id=%r grade=%r method=%r>' % (self.id, self.grade, self.method_code)
__all__ = [
    'Probnik',
    'OlympiadTask',
    'TheoryBlock',
    'ProbnikTheory',
    'TaskAttempt',
    'StageAttempt',
    'PROBNIK_TYPES',
    'DIFFICULTY_LEVELS',
    'THEORY_SECTIONS',
    'ATTEMPT_STATUSES',
    'STAGE_RESULTS',
    'MethodTask',
    'METHOD_TASK_PROBABILITY_TIERS',
]

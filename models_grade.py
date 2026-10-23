# -*- coding: utf-8 -*-
"""GradeTask model + per-grade domain registry.

Этот модуль содержит:
- ``GRADE_SUBJECTS`` — кортеж поддерживаемых предметов.
- ``GRADE_DOMAINS`` — словарь {класс (int) -> кортеж доменных ключей}.
- ``DOMAIN_LABELS`` — словарь {доменный ключ -> человекочитаемое имя на русском}.
- Класс :class:`GradeTask` — ORM-модель задачи, разбитой по классу/домену.

Используется в:
- ``app.py`` (роуты адаптивного теста ``/adaptive_test/select_topic`` и
  ``/adaptive_test/start_grade``);
- ``routes/grade.py`` (страницы тренировки по классам 5–11);
- ``scripts/import_grade_tasks.py`` (импорт банка задач).
"""
from datetime import datetime
from sqlalchemy import UniqueConstraint
from models import db

GRADE_SUBJECTS = ('math',)

# Домены по классам. Ключи должны совпадать с теми, что уложены в БД
# в столбце ``grade_tasks.domain``.
GRADE_DOMAINS = dict()
GRADE_DOMAINS[5] = (
    'natural_numbers',
    'fractions_decimals_percent',
    'geometry_measurement',
    'combinatorics_school',
    'logic_olympiad_intro',
)
GRADE_DOMAINS[6] = (
    'divisibility',
    'fractions_ratio_percent',
    'integers_coordinates',
    'geometry_6',
    'olympiad_logic_combinatorics',
)
GRADE_DOMAINS[7] = (
    'algebra_expressions_equations',
    'linear_functions_intro',
    'geometry_7_lines_triangles',
    'number_theory_combinatorics_7',
    'olympiad_logic_7',
)
GRADE_DOMAINS[8] = (
    'algebra_roots_quadratics_intro',
    'geometry_8_quadrilaterals_pythagoras',
    'functions_inequalities_8',
    'counting_probability_8',
    'olympiad_logic_8',
)
GRADE_DOMAINS[9] = (
    'algebra', 'geometry', 'combinatorics',
    'number_theory', 'logic', 'set_theory',
)
GRADE_DOMAINS[10] = (
    'algebra', 'geometry', 'combinatorics',
    'number_theory', 'logic', 'set_theory',
)
GRADE_DOMAINS[11] = (
    'algebra', 'geometry', 'combinatorics',
    'number_theory', 'logic', 'set_theory',
)

# Человекочитаемые имена доменов (RU). Используются в UI выбора темы.
DOMAIN_LABELS = {
    # 5 класс
    'natural_numbers':              'Натуральные числа',
    'fractions_decimals_percent':   'Дроби и проценты',
    'geometry_measurement':         'Геометрия и измерения',
    'combinatorics_school':         'Школьная комбинаторика',
    'logic_olympiad_intro':         'Вводная олимпиадная логика',
    # 6 класс
    'divisibility':                 'Делимость',
    'fractions_ratio_percent':      'Дроби, отношения, проценты',
    'integers_coordinates':         'Целые числа и координаты',
    'geometry_6':                   'Геометрия 6 класса',
    'olympiad_logic_combinatorics': 'Олимпиадная логика и комбинаторика',
    # 7 класс
    'algebra_expressions_equations':  'Выражения и уравнения',
    'linear_functions_intro':         'Линейные функции',
    'geometry_7_lines_triangles':     'Геометрия 7: прямые и треугольники',
    'number_theory_combinatorics_7':  'Теория чисел и комбинаторика 7',
    'olympiad_logic_7':               'Олимпиадная логика 7',
    # 8 класс
    'algebra_roots_quadratics_intro':       'Корни и квадратные уравнения',
    'geometry_8_quadrilaterals_pythagoras': 'Геометрия 8: четырёхугольники и Пифагор',
    'functions_inequalities_8':             'Функции и неравенства 8',
    'counting_probability_8':               'Перечисление и вероятность 8',
    'olympiad_logic_8':                     'Олимпиадная логика 8',
    # 9–11 классы (общие категории)
    'algebra':       'Алгебра',
    'geometry':      'Геометрия',
    'combinatorics': 'Комбинаторика',
    'number_theory': 'Теория чисел',
    'logic':         'Логика',
    'set_theory':    'Теория множеств',
}


class GradeTask(db.Model):
    """Задача, отнесённая к конкретному классу и домену.

    Источник: банк ~1600 задач, разложенных по школьной программе 5–11 классов.
    Каждая запись хранит формулировку, ответ, решение и теги; ``source_id``
    уникален и позволяет идемпотентно переимпортировать данные.
    """
    __tablename__ = 'grade_tasks'

    id         = db.Column(db.Integer, primary_key=True)
    source_id  = db.Column(db.String(120), unique=True, nullable=False, index=True)
    grade      = db.Column(db.Integer, nullable=False, index=True)
    domain     = db.Column(db.String(50), nullable=False, index=True)
    subject    = db.Column(db.String(20), nullable=False,
                           default='math', server_default='math')
    level      = db.Column(db.Integer, nullable=True, index=True)
    topic      = db.Column(db.String(300), nullable=True)
    statement  = db.Column(db.Text, nullable=False)
    answer     = db.Column(db.Text, nullable=True)
    solution   = db.Column(db.Text, nullable=True)
    status     = db.Column(db.String(50), nullable=True)
    tags       = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('source_id', name='uq_grade_tasks_source_id'),
    )

    def __repr__(self):
        return '<GradeTask %s g%d %s>' % (self.source_id, self.grade, self.domain)


__all__ = [
    'GradeTask',
    'GRADE_DOMAINS',
    'DOMAIN_LABELS',
    'GRADE_SUBJECTS',
]

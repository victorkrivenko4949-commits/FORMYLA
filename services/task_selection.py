# -*- coding: utf-8 -*-
"""Centralised, subject-safe task selection for the adaptive test.

Все маршруты адаптивного теста (`/adaptive_test/...`) и сервис
`prep_planner` ОБЯЗАНЫ использовать функции из этого модуля при выборке
задач из таблицы `adaptive_tasks`.

Ключевые правила (см. ТЗ):

1.  Если пользователь выбрал предмет (algebra/geometry/...), фильтр по
    `subject` применяется ПЕРЕД фильтром по классу/уровню и ПЕРЕД любым
    random/adaptive выбором.
2.  Никаких fallback'ов между предметами. Если для выбранной комбинации
    нет задач — возвращается пустой список (вызывающий код показывает
    «нет задач для выбранного фильтра»).
3.  Fallback допустим ТОЛЬКО внутри того же предмета и класса — на
    соседние уровни сложности.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from models import AdaptiveTask
from services.subject_classifier import ALL_SUBJECTS


def _subject_filter(query, subject: Optional[str]):
    """Применить субъект-фильтр, если subject ∈ ALL_SUBJECTS.

    Для не-канонических ключей (None, 'movement', 'knights_liars', …)
    фильтр НЕ применяется — для таких тем используется внешний
    keyword-фильтр по `topic`, но НИКОГДА не разрешается перепрыгнуть
    в другой канонический предмет.
    """
    if subject in ALL_SUBJECTS:
        return query.filter(AdaptiveTask.subject == subject)
    return query


def base_query(
    *,
    subject: Optional[str] = None,
    grade: Optional[int] = None,
    include_flagged: bool = False,
):
    """Базовый запрос: subject -> grade -> (не помечена)."""
    q = AdaptiveTask.query
    q = _subject_filter(q, subject)
    if grade is not None:
        q = q.filter(AdaptiveTask.class_level == int(grade))
    if not include_flagged:
        q = q.filter(AdaptiveTask.is_flagged == False)  # noqa: E712
    return q


def select_tasks(
    *,
    subject: Optional[str],
    grade: Optional[int],
    level: Optional[int] = None,
    exclude_ids: Optional[Iterable[int]] = None,
    nearby_levels: Sequence[int] = (1, -1, 2, -2, 3, -3),
    include_flagged: bool = False,
) -> List[AdaptiveTask]:
    """Вернуть список задач для адаптивного теста.

    Порядок и правила фильтрации:
        1) subject (если каноничен) — иначе фильтр не применяется, но
           возвращаемый список всё равно ограничен другими фильтрами.
        2) grade
        3) is_flagged == False (если не include_flagged)
        4) level — если задан, сначала точный, затем nearby_levels
           (внутри уже отфильтрованного по subject/grade набора!).

    Никаких fallback'ов на другие предметы НЕТ.  Если внутри (subject,
    grade) задач нет — функция возвращает пустой список.
    """
    excluded = set(exclude_ids or [])

    q_all = base_query(subject=subject, grade=grade, include_flagged=include_flagged)
    if excluded:
        q_all = q_all.filter(~AdaptiveTask.id.in_(list(excluded)))

    if level is None:
        return q_all.order_by(AdaptiveTask.id.asc()).all()

    # Точный уровень
    primary = q_all.filter(AdaptiveTask.difficulty_level == int(level)) \
                   .order_by(AdaptiveTask.id.asc()).all()
    if primary:
        return primary

    # Только соседние уровни внутри ТОГО ЖЕ предмета и класса.
    # ВАЖНО: разрешено расширять уровень — НЕЛЬЗЯ менять subject.
    for offset in nearby_levels:
        l = int(level) + offset
        if l < 1 or l > 5:
            continue
        widened = q_all.filter(AdaptiveTask.difficulty_level == l) \
                       .order_by(AdaptiveTask.id.asc()).all()
        if widened:
            return widened
    if grade is not None and subject:
        for g_offset in (1, -1, 2, -2):
            g = int(grade) + g_offset
            if g < 5 or g > 11:
                continue
            q_grade = base_query(subject=subject, grade=g, include_flagged=include_flagged)
            if excluded:
                q_grade = q_grade.filter(~AdaptiveTask.id.in_(list(excluded)))
            hit = q_grade.filter(AdaptiveTask.difficulty_level == int(level)).order_by(AdaptiveTask.id.asc()).all()
            if not hit:
                hit = q_grade.order_by(AdaptiveTask.id.asc()).all()
            if hit:
                return hit
            

    # Совсем нет задач — возвращаем пусто, чтобы вызывающий код показал
    # понятное сообщение.
    return []


def count_tasks(
    *,
    subject: Optional[str],
    grade: Optional[int],
    include_flagged: bool = False,
) -> int:
    """Кол-во задач в (subject, grade) — без учёта level/exclude."""
    return base_query(
        subject=subject, grade=grade, include_flagged=include_flagged
    ).count()


__all__ = [
    "base_query",
    "select_tasks",
    "count_tasks",
]

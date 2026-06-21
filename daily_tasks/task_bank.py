# -*- coding: utf-8 -*-
"""
FORMYLA Task Bank — банк готовых задач для «Задачи дня».

Читает pre-made JSON-файлы (grades 5–11) из ``daily_tasks/data/task_bank/``
и предоставляет детерминированный доступ к задачам по (grade, level, day).

Использование
-------------
    >>> from daily_tasks.task_bank import get_tasks, available_cells
    >>> tasks = get_tasks(grade=6, level=4, day=1)
    >>> if tasks:
    ...     for t in tasks:
    ...         print(t["text"])
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
#  Конфигурация
# ──────────────────────────────────────────────────────────────────────────
_DATA_DIR: Path = Path(__file__).resolve().parent / "data" / "task_bank"

# Имена файлов по классам (grade → filename)
_GRADE_FILES: Dict[int, str] = {
    5: "formyla_grade5.json",
    6: "formyla_grade6.json",
    7: "formyla_grade7.json",
    8: "formyla_grade8.json",
    9: "formyla_grade9.json",
    10: "formyla_grade10.json",
    11: "formyla_grade11.json",
}

# In-memory cache: grade → List[probe_dict]
_bank_cache: Dict[int, List[Dict[str, Any]]] = {}

# Валидные уровни в банке
BANK_LEVELS: Tuple[int, ...] = (4, 5, 6, 7, 8)
MIN_BANK_LEVEL = 4
MAX_BANK_LEVEL = 8
DAYS_PER_CELL = 100
TASKS_PER_PROBE = 10


# ──────────────────────────────────────────────────────────────────────────
#  Загрузка / кэширование
# ──────────────────────────────────────────────────────────────────────────
def _grade_file_path(grade: int) -> Path:
    """Путь к JSON-файлу банка для указанного класса."""
    fname = _GRADE_FILES.get(grade)
    if not fname:
        raise ValueError(f"Банк задач не поддерживает класс {grade} (доступны: {list(_GRADE_FILES.keys())})")
    return _DATA_DIR / fname


def load_bank(grade: int) -> List[Dict[str, Any]]:
    """Загрузить и закэшировать банк задач для указанного класса.

    Parameters
    ----------
    grade : int
        Класс (5–11).

    Returns
    -------
    List[Dict[str, Any]]
        Список пробников (probes) для данного класса.

    Raises
    ------
    FileNotFoundError
        Если файл банка не найден.
    json.JSONDecodeError
        Если файл повреждён.
    """
    if grade in _bank_cache:
        return _bank_cache[grade]

    path = _grade_file_path(grade)
    if not path.exists():
        raise FileNotFoundError(
            f"Файл банка задач не найден: {path}. "
            f"Убедитесь, что файл присутствует в {_DATA_DIR}"
        )

    logger.info("Загрузка банка задач: %s", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    probes: List[Dict[str, Any]] = data.get("probes", [])
    if not probes:
        logger.warning("Банк для %d-го класса пуст (probes=[])", grade)

    _bank_cache[grade] = probes
    logger.info(
        "Банк для %d-го класса загружен: %d пробников",
        grade, len(probes),
    )
    return probes


def clear_cache(grade: Optional[int] = None) -> None:
    """Очистить in-memory кэш банка.

    Parameters
    ----------
    grade : int, optional
        Если указан — очистить только кэш для этого класса.
        Если None — очистить весь кэш.
    """
    if grade is not None:
        _bank_cache.pop(grade, None)
    else:
        _bank_cache.clear()


# ──────────────────────────────────────────────────────────────────────────
#  Поиск задач
# ──────────────────────────────────────────────────────────────────────────
def get_tasks(
    grade: int,
    level: int,
    day: int,
    theme_hint: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Найти пробник по (grade, level, day) и вернуть его задачи.

    Parameters
    ----------
    grade : int
        Класс (5–11).
    level : int
        Уровень сложности (4–8).
    day : int
        День (1–100).
    theme_hint : str, optional
        Подсказка темы: если указана, предпочитаем пробник с такой темой.
        Если не указана — возвращаем первый подходящий.

    Returns
    -------
    Optional[List[Dict[str, Any]]]
        Список из 10 задач (каждая с ключами n, text, answer, solution, method)
        или None, если подходящий пробник не найден.
    """
    probes = load_bank(grade)

    # Собираем все подходящие пробники
    candidates: List[Dict[str, Any]] = []
    for p in probes:
        if p.get("level") == level and p.get("day") == day:
            candidates.append(p)

    if not candidates:
        logger.info(
            "Банк: нет пробника для grade=%d level=%d day=%d",
            grade, level, day,
        )
        return None

    # Если есть подсказка темы — ищем точное совпадение
    if theme_hint:
        hint_lower = theme_hint.strip().lower()
        for p in candidates:
            probe_theme = (p.get("theme") or "").strip().lower()
            if probe_theme == hint_lower:
                logger.info(
                    "Банк: найден пробник по теме '%s' для grade=%d level=%d day=%d",
                    p.get("theme"), grade, level, day,
                )
                tasks = p.get("tasks", [])
                if validate_tasks(tasks):
                    return tasks
                logger.warning(
                    "Банк: пробник '%s' не прошёл валидацию, ищу дальше",
                    p.get("probe_id"),
                )

    # Берём первый валидный пробник
    for p in candidates:
        tasks = p.get("tasks", [])
        if validate_tasks(tasks):
            logger.info(
                "Банк: выбран пробник '%s' для grade=%d level=%d day=%d",
                p.get("probe_id"), grade, level, day,
            )
            return tasks

    # Все кандидаты не прошли валидацию
    logger.warning(
        "Банк: все %d пробников для grade=%d level=%d day=%d не прошли валидацию",
        len(candidates), grade, level, day,
    )
    return None


def get_probe_meta(
    grade: int,
    level: int,
    day: int,
) -> Optional[Dict[str, Any]]:
    """Найти пробник по (grade, level, day) и вернуть его мета-данные (без задач).

    Полезно, когда нужно узнать тему пробника, чтобы сопоставить с planned_slots.
    """
    probes = load_bank(grade)
    for p in probes:
        if p.get("level") == level and p.get("day") == day:
            return {
                "probe_id": p.get("probe_id"),
                "grade": p.get("grade"),
                "theme": p.get("theme"),
                "level": p.get("level"),
                "day": p.get("day"),
                "num_tasks": len(p.get("tasks", [])),
            }
    return None


# ──────────────────────────────────────────────────────────────────────────
#  Валидация
# ──────────────────────────────────────────────────────────────────────────
def validate_tasks(tasks: List[Dict[str, Any]]) -> bool:
    """Проверить, что список задач корректен.

    Критерии:
    * Ровно 10 задач (TASKS_PER_PROBE).
    * У каждой задачи непустые поля ``text``, ``answer``, ``solution``.
    * Поле ``n`` (номер) от 1 до 10 (если присутствует).

    Parameters
    ----------
    tasks : List[Dict[str, Any]]
        Список задач из пробника.

    Returns
    -------
    bool
        True, если задачи валидны.
    """
    if not tasks:
        return False
    if len(tasks) != TASKS_PER_PROBE:
        logger.warning(
            "Валидация: ожидалось %d задач, получено %d",
            TASKS_PER_PROBE, len(tasks),
        )
        return False

    for i, t in enumerate(tasks):
        if not (t.get("text") or "").strip():
            logger.warning("Валидация: задача #%d: пустой text", i + 1)
            return False
        if not (t.get("answer") or "").strip():
            logger.warning("Валидация: задача #%d: пустой answer", i + 1)
            return False
        if not (t.get("solution") or "").strip():
            logger.warning("Валидация: задача #%d: пустой solution", i + 1)
            return False

    return True


# ──────────────────────────────────────────────────────────────────────────
#  Доступные ячейки
# ──────────────────────────────────────────────────────────────────────────
def available_cells(grade: int) -> Set[Tuple[int, int]]:
    """Множество доступных (level, day) для указанного класса.

    Parameters
    ----------
    grade : int
        Класс (5–11).

    Returns
    -------
    Set[Tuple[int, int]]
        Множество пар (level, day), для которых есть задачи.
    """
    probes = load_bank(grade)
    cells: Set[Tuple[int, int]] = set()
    for p in probes:
        cells.add((p["level"], p["day"]))
    return cells


def count_probes(grade: int) -> int:
    """Количество пробников в банке для указанного класса."""
    return len(load_bank(grade))


def grade_is_available(grade: int) -> bool:
    """Проверить, есть ли банк задач для указанного класса."""
    return grade in _GRADE_FILES


# ──────────────────────────────────────────────────────────────────────────
#  Расчёт номера дня
# ──────────────────────────────────────────────────────────────────────────
def compute_day_number(
    start_date: date,
    today: Optional[date] = None,
) -> int:
    """Детерминированный номер дня для банка задач.

    Вычисляется как ``(today - start_date).days % 100 + 1``,
    что даёт число от 1 до 100 включительно.

    Parameters
    ----------
    start_date : date
        Дата начала отсчёта (например, дата регистрации пользователя).
    today : date, optional
        Текущая дата. Если не указана — используется ``date.today()``.

    Returns
    -------
    int
        Номер дня (1–100).
    """
    if today is None:
        today = date.today()
    delta = (today - start_date).days
    if delta < 0:
        # Если start_date в будущем — возвращаем 1
        return 1
    return (delta % DAYS_PER_CELL) + 1


# ──────────────────────────────────────────────────────────────────────────
#  Определение уровня ученика из профиля
# ──────────────────────────────────────────────────────────────────────────
def pick_bank_level(
    profile: Dict[str, Any],
    default_level: int = 5,
) -> int:
    """Выбрать уровень для поиска в банке на основе профиля.

    .. important::
       Функция возвращает **уровень сложности банка** (4–8), а **не класс**
       (5–11). Класс (grade) берётся из ``profile.class_level`` и передаётся
       в ``get_tasks(grade=..., level=...)`` отдельно.

    Стратегия:
    1. Если у пользователя есть измеренные темы (measured topics),
       берём их средний ``target_level``, округлённый до целого.
    2. Иначе используем ``class_expected_level`` (но не ниже MIN_BANK_LEVEL).
    3. Если и это недоступно — ``default_level``.

    Результат принудительно зажимается в диапазон [MIN_BANK_LEVEL, MAX_BANK_LEVEL].

    Parameters
    ----------
    profile : Dict[str, Any]
        Профиль пользователя (из ``build_profile``).
    default_level : int
        Уровень по умолчанию, если ничего не удалось определить.

    Returns
    -------
    int
        Уровень сложности банка (4–8), **не** класс (5–11).
        Используется как ``level`` при вызове ``get_tasks(grade, level, day)``.
    """
    topics_full = profile.get("topics_full", []) or []
    measured_levels = [
        t.get("target_level", default_level)
        for t in topics_full
        if not t.get("calibration", False)
    ]

    if measured_levels:
        # Среднее среди измеренных тем
        avg = sum(measured_levels) / len(measured_levels)
        bank_level = round(avg)
    else:
        bank_level = profile.get("class_expected_level", default_level)

    # Зажимаем в доступный диапазон банка
    bank_level = max(MIN_BANK_LEVEL, min(MAX_BANK_LEVEL, bank_level))
    return bank_level

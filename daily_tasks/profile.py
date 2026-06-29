# -*- coding: utf-8 -*-
"""
daily_tasks/profile.py — Step 1: построение профиля пользователя.

Архитектура (PR «percent_to_level + calibration», ТЗ от 2026-06-08):

1. У каждой темы класса (7 шт. для 7–11 кл., 10 шт. для 5–6 кл.) есть состояние
   ``measured`` — пройден ли по ней адаптивный диагностический тест.
   * ``measured=True`` — есть ``AdaptiveTestResult`` → процент знания темы
     известен как ``100 * tasks_correct / tasks_total``.
   * ``measured=False`` — теста не было → тема **калибровочная**: задачи дня
     по ней даются на безопасном стартовом уровне, а ответы ученика по этим
     задачам со временем превращаются в собственный «running_pct» (см.
     ``update_topic_running_pct``).

2. Процент знания темы → уровень сложности задачи (1–5) через
   :func:`percent_to_level`. Пороги вынесены в
   :data:`PERCENT_LEVEL_THRESHOLDS` для удобного тюнинга.

3. Слабые темы (низкий %) идут в ``weak_topics`` с **пониженным**
   ``floor_level`` (``pct_level − 1``), чтобы Gemini-плэннер выбирал задачи
   «чуть ниже измеренного уровня» (подтянуть пробел). Доля
   «stretch»-задач — 20% — пойдёт на ``pct_level + 1`` (рост).

4. Сильные темы (высокий %) — в ``strong_topics`` для повторения.

5. Калибровочные темы (без теста) тоже попадают в ``weak_topics`` (приоритет
   ниже измеренных), но с явным флагом ``calibration=True`` и стартовым
   ``target_level = CALIBRATION_START_LEVEL``. По дням недели темы ротируются,
   чтобы за 6–7 дней закрыть профиль (см. ``_select_calibration_topics``).

6. **Никакого silent-fallback `class_level=9`**. Если у пользователя пустой
   ``preferred_grade`` — функция бросает :class:`ProfileBuildError` с ясной
   причиной, оркестратор пишет её в ``reason_summary`` (см. ТЗ п.6).

Совместимость
-------------
Возвращаемый профиль сохраняет старые ключи (``weak_topics``,
``strong_topics``, ``class_level``, ``class_expected_level``,
``adaptive_summary``) — Gemini-промпт и кэш ``task_pool`` продолжают работать.
Добавлены новые ключи (``profile_completeness``, ``measured_topics_count``,
``calibration_topics``, ``topics_full``).
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from models import (
    db, User, AdaptiveTestResult, TaskSolution, AdaptiveTask
)
from services.topic_taxonomy import (
    SUBTOPICS, TOPIC_NAMES_RU, SUBTOPIC_NAMES_RU
)
from services.adaptive_topics_registry import (
    ADAPTIVE_TOPICS_BY_GRADE, get_db_topic, is_registered
)
from .running_pct import (
    compute_topic_running_pct,
    MIN_ANSWERS_FOR_MEASURED,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Константы — все пороги и веса ВЫНЕСЕНЫ сюда, чтобы тюнить без правки логики
# ══════════════════════════════════════════════════════════════════════

# ── Маппинг процент → уровень сложности 1–5 (см. ТЗ п.1) ──────────────
# Формат: список (верхняя граница включительно, уровень).
# Низкий % → низкий уровень (ученик слаб → задаём проще).
# Высокий % → высокий уровень (ученик силён → задаём челлендж).
PERCENT_LEVEL_THRESHOLDS: List[Tuple[int, int]] = [
    (20, 1),   #   0–20% → lvl 1 (база)
    (40, 2),   #  21–40% → lvl 2
    (60, 3),   #  41–60% → lvl 3
    (80, 4),   #  61–80% → lvl 4
    (100, 5),  # 81–100% → lvl 5 (челлендж)
]

# ── Поведение для измеренных слабых тем ───────────────────────────────
# Сколько уровней «вниз» от измеренного даём как target (подтянуть пробелы).
LEVEL_PULL_DOWN: int = 1
# Сколько уровней «вверх» даём для растяжки (часть задач для роста).
LEVEL_STRETCH_UP: int = 1
# Доля растяжки от всех задач по теме (для подсказки Gemini-плэннеру).
LEVEL_STRETCH_PROB: float = 0.2

# ── Калибровочные темы (без теста) ────────────────────────────────────
# Стартовый уровень для калибровочных задач — середина шкалы, безопасно.
CALIBRATION_START_LEVEL: int = 2
# Максимум калибровочных тем в день при наличии хоть одного measured-теста
# (чтобы не размывать фокус — основные задачи идут по measured).
# При completeness=0 (0 из N тестов) лимит снимается: даём ВСЕ темы в
# калибровку (см. build_profile).
CALIBRATION_TOPICS_PER_DAY: int = 2
CALIBRATION_TOPICS_PER_DAY_WHEN_EMPTY: int = 10  # фактически = total_topics

# ── Старая логика (оставлена для совместимости с существующим Gemini) ─
_SUBJECT_PREFIX_MAP: Dict[str, str] = {
    'Алгебра': 'algebra',
    'Геометрия': 'geometry',
    'Комбинаторика': 'combinatorics',
    'Теория чисел': 'number_theory',
    'Логика': 'logic',
}
_WEAK_THRESHOLD = 35
_MAX_WEAK_PER_SUBJECT = 2
_TOP_WEAK_COUNT = 7
# Когда у ученика 0 тестов, все темы класса попадают в weak_topics
# как калибровочные. Лимит снимаем до общего числа тем класса (5..10).
_TOP_WEAK_COUNT_WHEN_EMPTY = 10
_TOP_STRONG_COUNT = 3
_MIN_STRONG_ATTEMPTS = 5

# ── Минимально допустимый уровень сложности (1–8 в БД) ────────────────
MIN_TASK_LEVEL = 1
MAX_TASK_LEVEL = 8  # шкала AdaptiveTask.difficulty_level в БД (1..8)


# ══════════════════════════════════════════════════════════════════════
# Исключения
# ══════════════════════════════════════════════════════════════════════


class ProfileBuildError(Exception):
    """Профиль построить нельзя по бизнес-причине (отсутствие grade и т.п.).

    Оркестратор ловит и пишет ``str(exc)`` в ``DailyTaskSet.reason_summary``
    + ``DailyGenerationJob.error_message``. Никакого silent-fallback.
    """


# ══════════════════════════════════════════════════════════════════════
# Чистые функции (без БД, легко тестируются)
# ══════════════════════════════════════════════════════════════════════


def percent_to_level(pct: Optional[float]) -> Optional[int]:
    """Конвертация процента знания темы (0–100) в уровень сложности (1–5).

    Параметры
    ---------
    pct : float | None
        Процент 0..100. Значения вне диапазона clamp'ятся.
        ``None`` → ``None`` (тест не пройден, уровень неизвестен).

    Возвращает
    ----------
    int | None
        Уровень из :data:`PERCENT_LEVEL_THRESHOLDS` (1..5) или ``None``.

    Примеры
    -------
    >>> percent_to_level(None)
    >>> percent_to_level(0)
    1
    >>> percent_to_level(20)
    1
    >>> percent_to_level(21)
    2
    >>> percent_to_level(100)
    5
    >>> percent_to_level(150)  # clamp
    5
    """
    if pct is None:
        return None
    try:
        pct_f = float(pct)
    except (TypeError, ValueError):
        return None
    # clamp в [0, 100]
    pct_f = max(0.0, min(100.0, pct_f))
    for upper, lvl in PERCENT_LEVEL_THRESHOLDS:
        if pct_f <= upper:
            return lvl
    # safety fallback — не должно случиться при корректной таблице
    return PERCENT_LEVEL_THRESHOLDS[-1][1]


def compute_profile_completeness(
    measured_count: int, total_topics: int = 7
) -> float:
    """Доля пройденных тестов от общего числа тем в каталоге класса.

    Возвращает 0.0..1.0; деление на 0 защищено.
    """
    if total_topics <= 0:
        return 0.0
    return round(max(0, min(measured_count, total_topics)) / total_topics, 4)


def compute_target_level_from_pct(
    pct: Optional[float],
    pull_down: int = LEVEL_PULL_DOWN,
    floor: int = MIN_TASK_LEVEL,
    ceil: int = MAX_TASK_LEVEL,
) -> Optional[int]:
    """[DEPRECATED] Target-уровень из pct в сжатой шкале 1..5.

    Сохранена для обратной совместимости. Новый код должен использовать
    :func:`score_to_target_level` (полная шкала 1..8 на основе
    ``final_level`` адаптивного теста + ratio correct/total).
    """
    lvl = percent_to_level(pct)
    if lvl is None:
        return None
    return max(floor, min(ceil, lvl - pull_down))


def compute_stretch_level_from_pct(
    pct: Optional[float],
    stretch_up: int = LEVEL_STRETCH_UP,
    floor: int = MIN_TASK_LEVEL,
    ceil: int = MAX_TASK_LEVEL,
) -> Optional[int]:
    """[DEPRECATED] Stretch-уровень в сжатой шкале 1..5."""
    lvl = percent_to_level(pct)
    if lvl is None:
        return None
    return max(floor, min(ceil, lvl + stretch_up))


# ══════════════════════════════════════════════════════════════════════
# Per-topic difficulty matching (PR per-topic difficulty matching)
# ══════════════════════════════════════════════════════════════════════
#
# КЛЮЧЕВАЯ ИДЕЯ:
# Адаптивный тест по теме даёт пару (correct, total) и ``final_level`` (1..8).
# Эти данные мы используем НАПРЯМУЮ, без потери верхней части шкалы:
#
#   8/8, final_level=8  →  target=L8, окно [L7, L8]   ← раньше тут было L5!
#   7/8, final_level=7  →  target=L7, окно [L6, L8]
#   4/8, final_level=4  →  target=L3, окно [L2, L4]
#   1/8, final_level=2  →  target=L1, окно [L1, L3]   ← бери ниже измеренного
#
# В отличие от старой логики `percent_to_level` (сжимала всё в L1..L5),
# здесь используется ПОЛНАЯ шкала 1..8 — соответствует AdaptiveTask.difficulty_level
# и VALID_DIFFICULTY_RANGE в validators.py.
# ══════════════════════════════════════════════════════════════════════


def score_to_target_level(
    correct: Optional[int],
    total: Optional[int],
    final_level: Optional[int],
    floor: int = MIN_TASK_LEVEL,
    ceil: int = MAX_TASK_LEVEL,
) -> Optional[int]:
    """Per-topic target_level в полной шкале 1..8 из результата адаптивного теста.

    Логика:
    * базовый уровень — то, что измерил адаптивный движок (``final_level``);
    * для **слабых** тем (ratio низкий) опускаем НИЖЕ измеренного — нужно
      добрать фундамент:
        - ratio ≤ 0.25 (1/8)  →  base − 2
        - ratio ≤ 0.50 (4/8)  →  base − 1
        - ratio ≤ 0.75 (6/8)  →  base
        - ratio > 0.75 (≥7/8) →  base   (держим высокий уровень)
    * clamp в диапазон [floor, ceil] = [1, 8].

    Параметры
    ---------
    correct, total : int | None
        Количество правильных / всего задач в тесте по теме.
    final_level : int | None
        Финальный уровень IRT-движка адаптивного теста (1..8).
    floor, ceil : int
        Границы шкалы (по умолчанию 1..8).

    Возвращает
    ----------
    int | None
        Целевой уровень 1..8 либо ``None``, если данных недостаточно.

    Примеры
    -------
    >>> score_to_target_level(8, 8, 8)
    8
    >>> score_to_target_level(7, 8, 7)
    7
    >>> score_to_target_level(4, 8, 4)
    3
    >>> score_to_target_level(1, 8, 2)
    1
    >>> score_to_target_level(0, 8, 1)
    1
    """
    if final_level is None:
        return None
    try:
        base = int(final_level)
    except (TypeError, ValueError):
        return None
    base = max(floor, min(ceil, base))

    # Без статистики ratio — отдаём чистый final_level
    if not total or total <= 0:
        return base

    try:
        ratio = float(correct or 0) / float(total)
    except (TypeError, ValueError, ZeroDivisionError):
        return base

    if ratio <= 0.25:
        return max(floor, base - 2)
    if ratio <= 0.50:
        return max(floor, base - 1)
    if ratio <= 0.75:
        return base
    # ratio > 0.75 — сильная тема, держим базовый (высокий)
    return min(ceil, base)


def compute_level_window(
    target_level: Optional[int],
    floor: int = MIN_TASK_LEVEL,
    ceil: int = MAX_TASK_LEVEL,
) -> Tuple[int, int]:
    """Окно уровней [low, high] для генерации задач вокруг target_level.

    Правила:
    * **Слабая тема** (target ≤ 3): окно [target, target+2] — даём
      фундамент + лёгкий рост (например, 1/8 → L1..L3).
    * **Средняя тема** (target == 4 или 5): [target−1, target+1].
    * **Сильная тема** (target ≥ 6): [max(target−1, 6), 8] — приоритет
      верхней части шкалы; при target=8 окно [7, 8], при 8/8 = L7..L8.
    * Если target=None — возвращаем (floor, ceil), полный диапазон.

    Результат clamp'ится в [floor, ceil] и гарантированно low ≤ high.
    """
    if target_level is None:
        return (floor, ceil)
    try:
        t = int(target_level)
    except (TypeError, ValueError):
        return (floor, ceil)
    t = max(floor, min(ceil, t))

    if t <= 3:
        # слабая — фундамент + 2 ступеньки вверх
        lo, hi = t, t + 2
    elif t >= 6:
        # сильная — приоритет верха, нижняя граница не ниже 6
        lo, hi = max(t - 1, 6), ceil
    else:
        # средняя
        lo, hi = t - 1, t + 1

    lo = max(floor, min(ceil, lo))
    hi = max(floor, min(ceil, hi))
    if lo > hi:
        lo, hi = hi, lo
    return (lo, hi)


def calibration_target_level(class_expected_level: int) -> int:
    """Target_level для калибровочной темы (нет AdaptiveTestResult).

    Берём середину по классу — это безопасный «нащупывающий» уровень.
    Для 7-8 кл это L4, для 10-11 — L6.
    """
    return max(MIN_TASK_LEVEL, min(MAX_TASK_LEVEL, int(class_expected_level or 3)))


def compute_slot_allocation(
    measured_count: int,
    total_topics: int = 7,
    total_slots: int = 10,
    min_measured_slots: int = 0,
) -> Tuple[int, int]:
    """Сколько задач выделить под measured-темы и под calibration-темы.

    Логика (ТЗ п.3, «1/7 пройдено → ~3–4 measured + ~6 калибровочных»):

    Если measured_count = 0 → (0, total_slots) — все 10 калибровочных.
    Если measured_count = total_topics (7/7) → (total_slots, 0).
    Между ними — линейная интерполяция с округлением.

    Формула:
        measured_slots ≈ round(total_slots * (measured_count / total_topics))

    + гарантия минимум 3 measured_slots, если есть хоть один тест (иначе
    «1 тест ничего не меняет» — нарушение требования «приоритет слабым»).
    """
    if total_topics <= 0:
        return (total_slots, 0)
    if measured_count <= 0:
        return (max(0, min_measured_slots), total_slots - max(0, min_measured_slots))
    if measured_count >= total_topics:
        return (total_slots, 0)

    # propor + базовый запас 3 на измеренные
    ratio = measured_count / total_topics
    measured_slots = max(3, round(total_slots * ratio))
    measured_slots = min(total_slots, measured_slots)
    calibration_slots = total_slots - measured_slots
    return (measured_slots, calibration_slots)


def select_calibration_topics(
    candidate_topics: List[str],
    n: int,
    rotation_seed: int,
) -> List[str]:
    """Детерминированно выбрать ``n`` калибровочных тем из ``candidate_topics``.

    Ротация: сдвиг = ``rotation_seed % len(candidate_topics)``.
    За 6–7 дней при стабильном seed=weekday темы перебираются равномерно.

    Параметры
    ---------
    candidate_topics : list[str]
        Список ``db_topic`` тем без теста.
    n : int
        Сколько вернуть (≤ len(candidate_topics)).
    rotation_seed : int
        Обычно ``date.weekday()`` (0..6).
    """
    if not candidate_topics or n <= 0:
        return []
    # копия отсортированная — чтобы результат был детерминирован, а не
    # зависел от порядка в БД/каталоге
    sorted_topics = sorted(candidate_topics)
    k = len(sorted_topics)
    offset = max(0, rotation_seed) % k
    rotated = sorted_topics[offset:] + sorted_topics[:offset]
    return rotated[:min(n, k)]


# ══════════════════════════════════════════════════════════════════════
# Вспомогательные функции (с обращением к БД)
# ══════════════════════════════════════════════════════════════════════


def _class_expected_level(class_level: int) -> int:
    """Ожидаемый уровень подготовки для класса (ТЗ строка 96)."""
    if class_level <= 6:
        return 3
    if class_level <= 8:
        return 4
    if class_level <= 9:
        return 5
    return 6  # 10-11


def _extract_subject(db_topic: str, class_level: int) -> str:
    """Извлечь subject из названия темы."""
    if class_level >= 7:
        for prefix, subject in _SUBJECT_PREFIX_MAP.items():
            if db_topic.startswith(prefix):
                return subject
        return 'unknown'
    entry = SUBTOPICS.get(db_topic)
    if isinstance(entry, dict) and entry.get('subjects'):
        return entry['subjects'][0]
    short = TOPIC_NAMES_RU.get(db_topic, db_topic)
    for prefix, subject in _SUBJECT_PREFIX_MAP.items():
        if short.startswith(prefix) or db_topic.startswith(prefix):
            return subject
    return 'unknown'


def _get_topic_catalog(class_level: int) -> List[Dict]:
    """Получить каталог тем для класса.

    Grade 5-6 → SUBTOPICS (topic_taxonomy).
    Grade 7-11 → ADAPTIVE_TOPICS_BY_GRADE, 7 тем.
    """
    if class_level >= 7:
        grade_data = ADAPTIVE_TOPICS_BY_GRADE.get(class_level, [])
        if not grade_data:
            return []
        return [
            {
                'topic_key': entry['key'],
                'db_topic': entry.get('db_topic', ''),
                'topic_name': entry.get('name', ''),
            }
            for entry in grade_data
        ]
    result = []
    for db_topic, entry in SUBTOPICS.items():
        if isinstance(entry, dict):
            grades = entry.get('grades') or [5, 6]
        else:
            grades = [5, 6]
        if class_level in grades:
            result.append({
                'topic_key': db_topic,
                'db_topic': db_topic,
                'topic_name': TOPIC_NAMES_RU.get(db_topic, db_topic),
            })
    return result


def _calc_weakness_score(
    accuracy: float,
    attempts: int,
    class_expected_level: int,
    avg_level_solved: float,
) -> float:
    """Старая формула weakness_score для совместимости со strong-отбором."""
    term1 = 100.0 * (1.0 - accuracy) * min(1.0, attempts / 5.0)
    term2 = max(0.0, 10.0 * (class_expected_level - avg_level_solved))
    return round(term1 + term2, 1)


def _floor_level(class_expected_level: int, avg_level_solved: float) -> int:
    """Минимальный уровень сложности (старая формула, дефолт для калибровки)."""
    return max(2, int(avg_level_solved) - 1, class_expected_level - 2)


def _get_subtopic_hints(db_topic: str, class_level: int, topic_key: str = '') -> List[str]:
    """Получить список подтем (hints) для темы — не более 5."""
    hints: List[str] = []
    if class_level <= 6:
        entry = SUBTOPICS.get(db_topic)
        if isinstance(entry, dict):
            subs = entry.get('topics', {}) or {}
            hints = [
                v.get('name_ru', k) if isinstance(v, dict) else str(k)
                for k, v in subs.items()
            ]
        elif isinstance(entry, list):
            hints = [str(s) for s in entry]
    else:
        grade_data = ADAPTIVE_TOPICS_BY_GRADE.get(class_level, [])
        entry = {}
        if isinstance(grade_data, list):
            for item in grade_data:
                if isinstance(item, dict) and item.get('key') == topic_key:
                    entry = item
                    break
        elif isinstance(grade_data, dict):
            entry = grade_data.get(topic_key, {})
        subs = entry.get('subtopics', []) if isinstance(entry, dict) else []
        if subs and isinstance(subs, list):
            hints = [str(s) for s in subs]
    return hints[:5]


def _resolve_class_level(user: User) -> int:
    """Явный, не-молчаливый резолв класса.

    Если ``preferred_grade`` пуст или не парсится — бросаем ProfileBuildError.
    Никакого silent ``class_level=9`` (ТЗ п.6).
    """
    raw_grade = getattr(user, 'preferred_grade', None)
    if raw_grade in (None, '', 0, '0'):
        msg = (
            "Не указан класс ученика (preferred_grade пуст). "
            "Без класса невозможно выбрать тематический каталог. "
            "Зайди в Профиль → укажи класс."
        )
        logger.error(
            "build_profile: user_id=%s missing preferred_grade — refuse silent fallback",
            getattr(user, 'id', '?'),
        )
        raise ProfileBuildError(msg)
    try:
        class_level = int(raw_grade)
    except (TypeError, ValueError):
        msg = (
            f"preferred_grade='{raw_grade}' не число. "
            "Зайди в Профиль и выбери класс из списка."
        )
        logger.error(
            "build_profile: user_id=%s preferred_grade=%r is not int",
            getattr(user, 'id', '?'), raw_grade,
        )
        raise ProfileBuildError(msg)
    if class_level < 5 or class_level > 11:
        msg = f"Класс {class_level} вне поддерживаемого диапазона (5–11)."
        raise ProfileBuildError(msg)
    return class_level


def _load_topic_test_pct(
    user_id: int, class_level: int
) -> Dict[str, float]:
    """Достать карту ``db_topic → pct (0..100)`` из AdaptiveTestResult.

    Берём **последний** тест на каждую (topic, class_level). Если у одной
    темы несколько записей — побеждает самая свежая (по completed_at, иначе
    по id).

    NB: для per-topic difficulty matching мы теперь дополнительно используем
    :func:`_load_topic_test_results` — он отдаёт (correct, total, final_level)
    отдельно для каждой темы. Эта функция оставлена для совместимости
    (running_pct, weakness_score).
    """
    return {
        topic: data["pct"]
        for topic, data in _load_topic_test_results(user_id, class_level).items()
    }


def _load_topic_test_results(
    user_id: int, class_level: int
) -> Dict[str, Dict[str, Any]]:
    """db_topic → {correct, total, final_level, pct, completed_at}.

    Нужна для :func:`score_to_target_level`, чтобы получить target_level
    в полной шкале 1..8 на основе ``final_level`` адаптивного теста и
    точного ratio. Берём только последний тест на каждую тему.
    """
    results = (
        db.session.query(AdaptiveTestResult)
        .filter(
            AdaptiveTestResult.user_id == user_id,
            AdaptiveTestResult.class_level == class_level,
        )
        .order_by(
            AdaptiveTestResult.completed_at.desc().nullslast()
            if hasattr(AdaptiveTestResult.completed_at.desc(), 'nullslast')
            else AdaptiveTestResult.completed_at.desc(),
            AdaptiveTestResult.id.desc(),
        )
        .all()
    )
    out: Dict[str, Dict[str, Any]] = {}
    for tr in results:
        if not tr.topic or tr.topic in out:
            continue
        total = int(tr.tasks_total or 0)
        correct = int(tr.tasks_correct or 0)
        if total <= 0:
            continue
        out[tr.topic] = {
            "correct": correct,
            "total": total,
            "final_level": int(tr.final_level) if tr.final_level is not None else None,
            "pct": round(100.0 * correct / total, 2),
            "completed_at": tr.completed_at,
        }
    return out


def _load_topic_final_level(
    user_id: int, class_level: int
) -> Dict[str, int]:
    """``db_topic → final_level (IRT 1..8)`` (для совместимости со старым кодом)."""
    rows = (
        db.session.query(AdaptiveTestResult.topic, AdaptiveTestResult.final_level)
        .filter(
            AdaptiveTestResult.user_id == user_id,
            AdaptiveTestResult.class_level == class_level,
        )
        .all()
    )
    out: Dict[str, int] = {}
    for topic, lvl in rows:
        if topic and lvl is not None and topic not in out:
            out[topic] = int(lvl)
    return out


# ══════════════════════════════════════════════════════════════════════
# Основная функция — build_profile()
# ══════════════════════════════════════════════════════════════════════


def build_profile(
    user_id: int,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Построить профиль пользователя для генерации «Задач дня».

    Параметры
    ---------
    user_id : int
    today : date | None
        Дата сегодня — нужна для ротации калибровочных тем по дням.
        По умолчанию ``date.today()``.

    Возвращает
    ----------
    dict со следующими ключами:

    * ``user_id``
    * ``class_level``                   — int 5..11
    * ``class_expected_level``          — int (из _class_expected_level)
    * ``profile_completeness``          — float 0..1 (N тестов / 7)
    * ``measured_topics_count``         — int
    * ``calibration_topics_count``      — int
    * ``slot_allocation``               — {'measured': int, 'calibration': int}
    * ``adaptive_summary``              — старая агрегация (по TaskSolution)
    * ``weak_topics``                   — list[dict] (измеренные слабые +
      калибровочные) — Gemini его и так читает
    * ``strong_topics``                 — list[dict]
    * ``calibration_topics``            — list[db_topic] (для маркировки items)
    * ``topics_full``                   — полный список с полями
      {'db_topic', 'subject', 'topic_key', 'measured', 'calibration',
      'pct', 'level_from_pct', 'target_level', 'stretch_level',
      'floor_level', 'subtopic_hints', ...}

    Raises
    ------
    ProfileBuildError
        Если у пользователя нет валидного ``preferred_grade``. Это
        бизнес-ошибка, не баг — оркестратор пишет её в reason_summary.
    """
    # ── 1. Пользователь ──────────────────────────────────────────────
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    class_level = _resolve_class_level(user)  # может бросить ProfileBuildError
    expected_level = _class_expected_level(class_level)

    # ── 2. Каталог тем класса ────────────────────────────────────────
    topic_catalog = _get_topic_catalog(class_level)
    if not topic_catalog:
        raise ProfileBuildError(
            f"Для класса {class_level} не найден каталог тем "
            "(ADAPTIVE_TOPICS_BY_GRADE / SUBTOPICS пуст)."
        )

    total_topics = len(topic_catalog)

    # ── 3. Map db_topic → результат адаптивного теста ────────────────
    # test_results: {topic: {correct, total, final_level, pct, completed_at}}
    # Используется напрямую в score_to_target_level → полная шкала 1..8.
    test_results = _load_topic_test_results(user_id, class_level)
    pct_by_topic = {t: r["pct"] for t, r in test_results.items()}
    final_level_by_topic = {
        t: r["final_level"] for t, r in test_results.items()
        if r.get("final_level") is not None
    }

    # ── 4. Статистика TaskSolution (для совместимости, weakness_score) ─
    solutions_query = (
        db.session.query(TaskSolution, AdaptiveTask)
        .join(AdaptiveTask, TaskSolution.task_id == AdaptiveTask.id)
        .filter(TaskSolution.user_id == user_id)
        .all()
    )
    topic_stats: Dict[str, Dict[str, Any]] = {}
    for sol, task in solutions_query:
        topic = task.topic
        if topic not in topic_stats:
            topic_stats[topic] = {
                'attempts': 0,
                'correct': 0,
                'level_sum': 0,
                'subject': task.subject or _extract_subject(topic, class_level),
            }
        ts = topic_stats[topic]
        ts['attempts'] += 1
        if sol.is_correct is True:
            ts['correct'] += 1
        ts['level_sum'] += task.difficulty_level

    # ── 5. Построить полный список тем с новыми полями ──────────────
    if today is None:
        today = date.today()
    weekday_seed = today.weekday()  # 0..6

    topics_full: List[Dict[str, Any]] = []
    measured_count = 0
    calibration_candidate_topics: List[str] = []

    for entry in topic_catalog:
        db_topic = entry['db_topic']
        subj = _extract_subject(db_topic, class_level)

        # — статистика по решённым задачам (для floor_level и weakness) —
        stats = topic_stats.get(db_topic, {
            'attempts': 0, 'correct': 0, 'level_sum': 0, 'subject': subj,
        })
        attempts = stats['attempts']
        correct = stats['correct']
        accuracy_solutions = round(correct / attempts, 4) if attempts > 0 else 0.0
        avg_level = round(stats['level_sum'] / attempts, 2) if attempts > 0 else 0.0

        # — главное: процент из адаптивного теста, если есть —
        pct = pct_by_topic.get(db_topic)
        measured = pct is not None
        running_pct_value: Optional[float] = None
        running_pct_count = 0

        if not measured:
            # Достройка профиля по истории решений (вариант B, см.
            # daily_tasks/running_pct.py). Когда ученик нарешал
            # MIN_ANSWERS_FOR_MEASURED калибровочных задач по теме —
            # тема становится measured без формального теста.
            try:
                running_pct_value, running_pct_count, running_measured = (
                    compute_topic_running_pct(user_id, db_topic)
                )
            except Exception:
                logger.exception(
                    "running_pct calc failed for user=%s topic=%r — skip",
                    user_id, db_topic,
                )
                running_pct_value, running_pct_count, running_measured = (
                    None, 0, False,
                )
            if running_measured and running_pct_value is not None:
                pct = running_pct_value
                measured = True

        if measured:
            measured_count += 1
        else:
            calibration_candidate_topics.append(db_topic)

        # — конвертация в уровни (PER-TOPIC DIFFICULTY MATCHING) ──────
        # target_level и окно [low, high] берутся ИЗ результата
        # адаптивного теста по этой теме (не из общего % ученика).
        # 8/8 алгебры → target=L8, окно [L7, L8]; геометрия независимо.
        pct_level = percent_to_level(pct)  # legacy 1..5 — для совместимости
        if measured:
            tr = test_results.get(db_topic, {})
            target_level = score_to_target_level(
                correct=tr.get("correct"),
                total=tr.get("total"),
                final_level=tr.get("final_level"),
            )
            # Если в БД нет final_level (старая запись теста или running_pct)
            # — фолбэк: оцениваем по pct через старую сжатую шкалу + растяжка
            # в шкалу 1..8 (умножаем на 8/5).
            if target_level is None:
                legacy = compute_target_level_from_pct(pct) or MIN_TASK_LEVEL
                target_level = max(MIN_TASK_LEVEL, min(MAX_TASK_LEVEL,
                    round(legacy * (MAX_TASK_LEVEL / 5.0))))
            level_lo, level_hi = compute_level_window(target_level)
            stretch_level = level_hi  # для совместимости с Gemini-промптом
            calibration = False
        else:
            # Калибровочная тема — нет теста. Берём середину по классу.
            target_level = calibration_target_level(expected_level)
            level_lo, level_hi = compute_level_window(target_level)
            stretch_level = level_hi
            calibration = True
        # floor_level = low окна (под старый промпт Gemini, который запрещает
        # опускаться ниже floor_level). Совпадает с low окна.
        floor = level_lo

        weakness = _calc_weakness_score(
            accuracy_solutions, attempts, expected_level, avg_level,
        )

        topic_data: Dict[str, Any] = {
            # старые поля (нужны существующему Gemini-промпту)
            'subject': subj,
            'topic': db_topic,
            'topic_key': entry.get('topic_key', db_topic),
            'weakness_score': weakness,
            'accuracy': accuracy_solutions,
            'attempts': attempts,
            'avg_level_solved': avg_level,
            'final_level': final_level_by_topic.get(db_topic),
            'floor_level': floor,
            'subtopic_hints': _get_subtopic_hints(
                db_topic, class_level, entry.get('topic_key', '')
            ),
            # новые поля (PR percent_to_level + calibration)
            'measured': measured,
            'calibration': calibration,
            'pct': pct,
            'level_from_pct': pct_level,
            'target_level': target_level,
            'stretch_level': stretch_level,
            # ── PER-TOPIC DIFFICULTY MATCHING ──────────────────────────
            # Окно уровней [low, high] для этой темы — жёстко из теста.
            # Step 1 (Gemini) получит готовые difficulty_level для каждого
            # слота, выбранные ВНУТРИ этого окна (см. step1_gemini.py).
            'level_window': [int(level_lo), int(level_hi)],
            'level_low': int(level_lo),
            'level_high': int(level_hi),
            # сырые данные теста (для аудита и UI)
            'test_correct': test_results.get(db_topic, {}).get('correct'),
            'test_total': test_results.get(db_topic, {}).get('total'),
            # история калибровки (для UI/логов; если measured=True
            # из running_pct — будет видно, что % набран без теста)
            'running_pct': running_pct_value,
            'running_pct_count': running_pct_count,
            # приоритет в задачах дня: чем ниже %, тем выше приоритет (для
            # measured); у calibration — фиксированный средний приоритет
            'priority': (
                round(100.0 - (pct if pct is not None else 50.0), 2)
            ),
        }
        topics_full.append(topic_data)

    # ── 6. Калибровочные темы дня — ротация по weekday ───────────────
    # min_measured_slots: гарантируем ≥3 измеренных слота, если есть
    # хоть один тест (чтобы 1/7 действительно отличался от 0/7).
    # При 0/7 это 0, иначе 3.
    slot_allocation = compute_slot_allocation(
        measured_count=measured_count,
        total_topics=total_topics,
        total_slots=10,
        min_measured_slots=(3 if measured_count > 0 else 0),
    )
    measured_slots, calibration_slots = slot_allocation

    # Сколько тем под калибровку оставляем в weak_topics.
    # PR per-topic difficulty matching (фикс 0/7):
    #   * При measured_count == 0 (ни одного теста) лимит снимается:
    #     берём ВСЕ темы каталога — все 10 задач должны быть калибровочными.
    #   * При measured_count > 0 действует обычный лимит
    #     CALIBRATION_TOPICS_PER_DAY=2, чтобы не размывать фокус.
    if measured_count == 0:
        n_cal_topics = min(
            CALIBRATION_TOPICS_PER_DAY_WHEN_EMPTY,
            len(calibration_candidate_topics),
            total_topics,  # сколько вообще тем у класса
        )
    else:
        n_cal_topics = min(
            CALIBRATION_TOPICS_PER_DAY,
            len(calibration_candidate_topics),
            # если нет калибровочных слотов, темы тоже не выбираем
            max(1, calibration_slots) if calibration_slots > 0 else 0,
        )
    chosen_calibration = select_calibration_topics(
        calibration_candidate_topics,
        n=n_cal_topics,
        rotation_seed=today.toordinal(),
    )
    chosen_calibration_set = set(chosen_calibration)

    # ── 7. Глобальный adaptive_summary (для совместимости) ───────────
    total_attempts = sum(t['attempts'] for t in topics_full)
    total_correct = sum(
        int(round(t['accuracy'] * t['attempts'])) for t in topics_full
    )
    total_level_sum = sum(
        int(round(t['avg_level_solved'] * t['attempts'])) for t in topics_full
    )
    overall_accuracy = (
        round(total_correct / total_attempts, 4) if total_attempts > 0 else 0.0
    )
    overall_avg_level = (
        round(total_level_sum / total_attempts, 2) if total_attempts > 0 else 0.0
    )
    adaptive_summary = {
        'total_attempts': total_attempts,
        'overall_accuracy': overall_accuracy,
        'avg_level_solved': overall_avg_level,
    }

    # ── 8. Отбор weak_topics ─────────────────────────────────────────
    # Стратегия:
    # (a) MEASURED-слабые: берём measured-темы, сортируем по priority desc
    #     (то есть по pct asc — самые слабые в первую очередь).
    # (b) CALIBRATION-темы: добавляем chosen_calibration (ротация дня)
    #     с явным флагом calibration=True. Они идут после (a) — приоритет
    #     ниже, но без них набор будет однообразным при completeness<100%.
    # (c) Итого <= 7 weak-тем. Лимит per-subject (max 2) применяется
    #     только к measured-слабым; калибровочные — без лимита (их и так
    #     максимум CALIBRATION_TOPICS_PER_DAY).
    measured_topics_sorted = sorted(
        [t for t in topics_full if t['measured']],
        key=lambda t: (-t['priority'], -t['weakness_score']),
    )
    weak_topics: List[Dict[str, Any]] = []
    subject_count: Dict[str, int] = {}

    # PR per-topic difficulty matching: при 0 тестов поднимаем лимит,
    # чтобы все 7-10 калибровочных тем попали в weak_topics → slot_planner
    # распределит между ними 10 слотов (вместо урезания до 7).
    weak_limit = (
        _TOP_WEAK_COUNT_WHEN_EMPTY if measured_count == 0 else _TOP_WEAK_COUNT
    )

    for t in measured_topics_sorted:
        if len(weak_topics) >= weak_limit:
            break
        if subject_count.get(t['subject'], 0) >= _MAX_WEAK_PER_SUBJECT:
            continue
        weak_topics.append(_pick_topic_fields(t))
        subject_count[t['subject']] = subject_count.get(t['subject'], 0) + 1

    # Добавляем калибровочные (без per-subject лимита — их максимум
    # CALIBRATION_TOPICS_PER_DAY при measured>0, или ВСЕ темы при 0/N).
    used_topic_set = {t['topic'] for t in weak_topics}
    for t in topics_full:
        if len(weak_topics) >= weak_limit:
            break
        if t['topic'] in used_topic_set:
            continue
        if t['topic'] not in chosen_calibration_set:
            continue
        weak_topics.append(_pick_topic_fields(t))
        used_topic_set.add(t['topic'])

    # ── 9. Strong topics (по высокому pct/accuracy) ──────────────────
    # Кандидаты: measured-темы с pct >= 60 (lvl 3+ по нашей шкале) ИЛИ
    # темы с большим количеством попыток и высокой accuracy.
    used_in_weak = {t['topic'] for t in weak_topics}
    strong_candidates = []
    for t in topics_full:
        if t['topic'] in used_in_weak:
            continue
        if not t['measured']:
            # калибровочную в strong не берём
            continue
        if (t['pct'] or 0) >= 60 or (
            t['attempts'] >= _MIN_STRONG_ATTEMPTS and t['accuracy'] >= 0.7
        ):
            strong_candidates.append(t)
    strong_candidates.sort(
        key=lambda t: (t['pct'] or 0, t['accuracy'], t['attempts']),
        reverse=True,
    )
    strong_topics: List[Dict[str, Any]] = []
    for t in strong_candidates[:_TOP_STRONG_COUNT]:
        strong_topics.append({
            'subject': t['subject'],
            'topic': t['topic'],
            'accuracy': t['accuracy'],
            'attempts': t['attempts'],
            'avg_level_solved': t['avg_level_solved'],
            'subtopic_hints': t['subtopic_hints'],
            'pct': t['pct'],
            'measured': True,
            'calibration': False,
            'target_level': t['target_level'],
            # PER-TOPIC DIFFICULTY MATCHING
            'level_window': t['level_window'],
            'level_low': t['level_low'],
            'level_high': t['level_high'],
            'floor_level': t['floor_level'],
            'stretch_level': t['stretch_level'],
            'test_correct': t.get('test_correct'),
            'test_total': t.get('test_total'),
            'final_level': t.get('final_level'),
        })

    # Если сильных меньше 3 — добираем фолбэк-кандидатами, как раньше
    if len(strong_topics) < _TOP_STRONG_COUNT:
        used = used_in_weak | {st['topic'] for st in strong_topics}
        for t in topics_full:
            if len(strong_topics) >= _TOP_STRONG_COUNT:
                break
            if t['topic'] in used:
                continue
            strong_topics.append({
                'subject': t['subject'],
                'topic': t['topic'],
                'accuracy': t['accuracy'],
                'attempts': t['attempts'],
                'avg_level_solved': t['avg_level_solved'],
                'subtopic_hints': t['subtopic_hints'],
                'pct': t['pct'],
                'measured': t['measured'],
                'calibration': t['calibration'],
                'target_level': t['target_level'],
                'level_window': t['level_window'],
                'level_low': t['level_low'],
                'level_high': t['level_high'],
                'floor_level': t['floor_level'],
                'stretch_level': t['stretch_level'],
                'test_correct': t.get('test_correct'),
                'test_total': t.get('test_total'),
                'final_level': t.get('final_level'),
            })
            used.add(t['topic'])

    # ── 10. Финальный профиль ────────────────────────────────────────
    completeness = compute_profile_completeness(measured_count, total_topics)
    profile: Dict[str, Any] = {
        'user_id': user_id,
        'class_level': class_level,
        'class_expected_level': expected_level,
        'profile_completeness': completeness,
        'measured_topics_count': measured_count,
        'calibration_topics_count': len(calibration_candidate_topics),
        'slot_allocation': {
            'measured': measured_slots,
            'calibration': calibration_slots,
        },
        'adaptive_summary': adaptive_summary,
        'weak_topics': weak_topics,
        'strong_topics': strong_topics,
        'calibration_topics': chosen_calibration,
        # полный «сырьевой» список — полезен для тестов и UI-баннера
        'topics_full': topics_full,
    }

    logger.info(
        "build_profile: user=%s grade=%s completeness=%.2f measured=%d/%d "
        "weak=%d (cal=%d) strong=%d slots=(m=%d,c=%d)",
        user_id, class_level, completeness, measured_count, total_topics,
        len(weak_topics), len(chosen_calibration), len(strong_topics),
        measured_slots, calibration_slots,
    )
    # CURATOR (sub-theme system): inject today's locked subtopic
    profile['curator_subtopic'] = None
    try:
        from models import CuratorState
        from .monthly_plan import (
            get_or_build_plan,
            pick_day_subtopic,
            subtopic_title,
            parent_topic_for_subtopic,
        )
        _cs = CuratorState.query.filter_by(user_id=user_id).first()
        if _cs is not None and getattr(_cs, 'enabled', True):
            _today = today or date.today()
            _plan = get_or_build_plan(_cs, class_level, _today)
            _slug = pick_day_subtopic(_plan, _today)
            if _slug:
                _parent = parent_topic_for_subtopic(_slug, class_level)
                _day_topic = None
                for _t in topics_full:
                    if _t.get('topic') == _parent or _t.get('topic_key') == _parent:
                        _day_topic = _t
                        break
                if _day_topic is None and topics_full:
                    _day_topic = topics_full[0]
                profile['curator_subtopic'] = {
                    'slug': _slug,
                    'name': subtopic_title(_slug),
                    'day_topic': _day_topic or {},
                    'day_index': _today.toordinal(),
                }
    except Exception as _exc:
        logger.warning('curator_subtopic injection failed: %s', _exc)

    return profile


def _pick_topic_fields(t: Dict[str, Any]) -> Dict[str, Any]:
    """Подготовить запись weak_topics-style из полного topic_data."""
    return {
        'subject': t['subject'],
        'topic': t['topic'],
        'weakness_score': t['weakness_score'],
        'accuracy': t['accuracy'],
        'attempts': t['attempts'],
        'avg_level_solved': t['avg_level_solved'],
        'floor_level': t['floor_level'],
        'subtopic_hints': t['subtopic_hints'],
        # новые поля (PR percent_to_level + calibration + per-topic)
        'measured': t['measured'],
        'calibration': t['calibration'],
        'pct': t['pct'],
        'level_from_pct': t['level_from_pct'],
        'target_level': t['target_level'],
        'stretch_level': t['stretch_level'],
        # PER-TOPIC DIFFICULTY MATCHING
        'level_window': t['level_window'],
        'level_low': t['level_low'],
        'level_high': t['level_high'],
        'test_correct': t.get('test_correct'),
        'test_total': t.get('test_total'),
        'final_level': t.get('final_level'),
        'priority': t['priority'],
    }

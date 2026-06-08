# -*- coding: utf-8 -*-
"""
daily_tasks/profile.py — Step 1: построение профиля пользователя.

Собирает данные из AdaptiveTestResult + TaskSolution + AdaptiveTask,
вычисляет weakness_score по формуле из ТЗ, отбирает 7 слабых и 3 сильных тем.
"""

import logging
from typing import Dict, List, Optional, Tuple

from models import (
    db, User, AdaptiveTestResult, TaskSolution, AdaptiveTask
)
from services.topic_taxonomy import (
    SUBTOPICS, TOPIC_NAMES_RU, SUBTOPIC_NAMES_RU
)
from services.adaptive_topics_registry import (
    ADAPTIVE_TOPICS_BY_GRADE, get_db_topic, is_registered
)

logger = logging.getLogger(__name__)

# Дефолтный class_level для пользователей без preferred_grade в БД.
# Основная аудитория FORMYLA — 8–9 классы (ВсОШ-2027), поэтому
# при отсутствии явного выбора класса считаем юзера 9-классником,
# а не 5-классником (как было раньше).
_DEFAULT_CLASS_LEVEL = 9

# ──────────────────────────────────────────────
# Константы
# ──────────────────────────────────────────────

_SUBJECT_PREFIX_MAP: Dict[str, str] = {
    'Алгебра': 'algebra',
    'Геометрия': 'geometry',
    'Комбинаторика': 'combinatorics',
    'Теория чисел': 'number_theory',
    'Логика': 'logic',
}

_WEAK_THRESHOLD = 35            # минимальный weakness_score для попадания в слабые
_MAX_WEAK_PER_SUBJECT = 2       # макс. слабых тем из одного раздела
_TOP_WEAK_COUNT = 7             # сколько слабых тем отдаём
_TOP_STRONG_COUNT = 3           # сколько сильных тем отдаём
_MIN_STRONG_ATTEMPTS = 5        # мин. попыток для сильной темы


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────

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
    # Grade 7-11: по префиксу db_topic
    if class_level >= 7:
        for prefix, subject in _SUBJECT_PREFIX_MAP.items():
            if db_topic.startswith(prefix):
                return subject
        return 'unknown'
    # Grade 5-6: из SUBTOPICS.
    # NB: фактическая схема SUBTOPICS в текущей таксономии —
    # ``Dict[str, List[str]]`` (значение это список ID подтем, БЕЗ
    # полей `subjects` / `grades` / `topics`). Если когда-нибудь
    # схема расширится до dict с метаданными — этот блок продолжит
    # работать.
    entry = SUBTOPICS.get(db_topic)
    if isinstance(entry, dict) and entry.get('subjects'):
        return entry['subjects'][0]
    # fallback: через TOPIC_NAMES_RU
    short = TOPIC_NAMES_RU.get(db_topic, db_topic)
    for prefix, subject in _SUBJECT_PREFIX_MAP.items():
        if short.startswith(prefix) or db_topic.startswith(prefix):
            return subject
    return 'unknown'


def _get_topic_catalog(class_level: int) -> List[Dict]:
    """Получить каталог тем для класса.

    Grade 5-6 → SUBTOPICS (topic_taxonomy), 10 тем.
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
    # Grade 5-6: из SUBTOPICS.
    # Фактическая схема SUBTOPICS — ``Dict[str, List[str]]`` (нет
    # отдельного поля `grades`). Поэтому для 5-6 классов отдаём
    # весь каталог тем — фильтрация по подклассу будет на стороне
    # LLM-плана. Если запись окажется dict с явным `grades` — он
    # будет соблюдён.
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
    """
    Формула weakness_score (0–100) из ТЗ.

    weakness_score = 100 * (1 - accuracy) * min(1, attempts/5)
                     + max(0, 10 * (class_expected_level - avg_level_solved))
    """
    term1 = 100.0 * (1.0 - accuracy) * min(1.0, attempts / 5.0)
    term2 = max(0.0, 10.0 * (class_expected_level - avg_level_solved))
    return round(term1 + term2, 1)


def _floor_level(class_expected_level: int, avg_level_solved: float) -> int:
    """Минимальный уровень сложности для генерации (ТЗ строка 118)."""
    return max(2, int(avg_level_solved) - 1, class_expected_level - 2)


def _get_subtopic_hints(db_topic: str, class_level: int, topic_key: str = '') -> List[str]:
    """Получить список подтем (hints) для темы — не более 5."""
    hints: List[str] = []
    if class_level <= 6:
        # SUBTOPICS в текущей таксономии: Dict[str, List[str]] — flat
        # список ID подтем. Старый код ожидал dict с полем 'topics'.
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
        # Grade 7+: ADAPTIVE_TOPICS_BY_GRADE[class_level] is a list of dicts
        grade_data = ADAPTIVE_TOPICS_BY_GRADE.get(class_level, [])
        # Find the entry matching topic_key in the list
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


# ──────────────────────────────────────────────
# Основная функция
# ──────────────────────────────────────────────

def build_profile(user_id: int) -> Dict:
    """
    Построить профиль пользователя для генерации «Задач дня».

    Возвращает dict (см. ТЗ раздел 1 Step 1):
    {
        "user_id": int,
        "class_level": int,
        "class_expected_level": int,
        "adaptive_summary": {
            "total_attempts": int,
            "overall_accuracy": float,
            "avg_level_solved": float,
        },
        "weak_topics": [ ... ],   # 7 тем
        "strong_topics": [ ... ],  # 3 темы
    }
    """
    # ── 1. Получаем пользователя ──
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")

    raw_grade = user.preferred_grade
    if not raw_grade:
        logger.warning(
            "build_profile: user_id=%d has empty preferred_grade — "
            "falling back to class_level=%d",
            user_id, _DEFAULT_CLASS_LEVEL,
        )
        class_level = _DEFAULT_CLASS_LEVEL
    else:
        try:
            class_level = int(raw_grade)
        except (TypeError, ValueError):
            logger.warning(
                "build_profile: user_id=%d has non-numeric preferred_grade=%r — "
                "falling back to class_level=%d",
                user_id, raw_grade, _DEFAULT_CLASS_LEVEL,
            )
            class_level = _DEFAULT_CLASS_LEVEL
    expected_level = _class_expected_level(class_level)

    # ── 2. Каталог тем для класса ──
    topic_catalog = _get_topic_catalog(class_level)
    if not topic_catalog:
        raise ValueError(f"No topics found for class level {class_level}")

    # ── 3. Собираем статистику по каждой теме из TaskSolution ──
    # Берём все решения пользователя со связанными задачами
    solutions_query = (
        db.session.query(TaskSolution, AdaptiveTask)
        .join(AdaptiveTask, TaskSolution.task_id == AdaptiveTask.id)
        .filter(TaskSolution.user_id == user_id)
        .all()
    )

    # Агрегируем по topic (db_topic из AdaptiveTask)
    topic_stats: Dict[str, Dict] = {}
    for sol, task in solutions_query:
        topic = task.topic  # db_topic
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

    # ── 4. Достаём final_level из AdaptiveTestResult ──
    test_results = (
        db.session.query(AdaptiveTestResult)
        .filter(
            AdaptiveTestResult.user_id == user_id,
            AdaptiveTestResult.class_level == class_level,
        )
        .all()
    )
    test_level_map: Dict[str, int] = {}
    for tr in test_results:
        test_level_map[tr.topic] = tr.final_level

    # ── 5. Строим per-topic статистику для каталога ──
    all_topics_data: List[Dict] = []
    total_attempts = 0
    total_correct = 0
    total_level_sum = 0

    for topic_entry in topic_catalog:
        db_topic = topic_entry['db_topic']
        stats = topic_stats.get(db_topic, {
            'attempts': 0,
            'correct': 0,
            'level_sum': 0,
            'subject': _extract_subject(db_topic, class_level),
        })

        attempts = stats['attempts']
        correct = stats['correct']
        accuracy = round(correct / attempts, 4) if attempts > 0 else 0.0
        avg_level = round(stats['level_sum'] / attempts, 2) if attempts > 0 else 0.0

        weakness = _calc_weakness_score(accuracy, attempts, expected_level, avg_level)
        final_level = test_level_map.get(db_topic)
        floor = _floor_level(expected_level, avg_level) if attempts > 0 else max(2, expected_level - 2)

        topic_data = {
            'subject': stats['subject'],
            'topic': db_topic,
            'topic_key': topic_entry.get('topic_key', db_topic),
            'weakness_score': weakness,
            'accuracy': accuracy,
            'attempts': attempts,
            'avg_level_solved': avg_level,
            'final_level': final_level,
            'floor_level': floor,
            'subtopic_hints': _get_subtopic_hints(
                db_topic, class_level, topic_entry.get('topic_key', '')
            ),
        }
        all_topics_data.append(topic_data)

        total_attempts += attempts
        total_correct += correct
        total_level_sum += stats['level_sum']

    # ── 6. Глобальный adaptive_summary ──
    overall_accuracy = round(total_correct / total_attempts, 4) if total_attempts > 0 else 0.0
    overall_avg_level = round(total_level_sum / total_attempts, 2) if total_attempts > 0 else 0.0

    adaptive_summary = {
        'total_attempts': total_attempts,
        'overall_accuracy': overall_accuracy,
        'avg_level_solved': overall_avg_level,
    }

    # ── 7. Отбор слабых тем (max 7) ──
    sorted_by_weakness = sorted(
        all_topics_data,
        key=lambda t: t['weakness_score'],
        reverse=True,
    )

    weak_topics: List[Dict] = []
    subject_count: Dict[str, int] = {}

    for t in sorted_by_weakness:
        if len(weak_topics) >= _TOP_WEAK_COUNT:
            break
        # Пропускаем, если weakness_score ниже порога
        if t['weakness_score'] < _WEAK_THRESHOLD and len(weak_topics) >= 3:
            continue
        # Max 2 темы из одного раздела
        subj = t['subject']
        if subject_count.get(subj, 0) >= _MAX_WEAK_PER_SUBJECT:
            continue
        weak_topics.append({
            'subject': t['subject'],
            'topic': t['topic'],
            'weakness_score': t['weakness_score'],
            'accuracy': t['accuracy'],
            'attempts': t['attempts'],
            'avg_level_solved': t['avg_level_solved'],
            'floor_level': t['floor_level'],
            'subtopic_hints': t['subtopic_hints'],
        })
        subject_count[subj] = subject_count.get(subj, 0) + 1

    # Если набрали меньше 7 — добираем из оставшихся без ограничения subject
    if len(weak_topics) < _TOP_WEAK_COUNT:
        used_topics = {wt['topic'] for wt in weak_topics}
        for t in sorted_by_weakness:
            if len(weak_topics) >= _TOP_WEAK_COUNT:
                break
            if t['topic'] in used_topics:
                continue
            weak_topics.append({
                'subject': t['subject'],
                'topic': t['topic'],
                'weakness_score': t['weakness_score'],
                'accuracy': t['accuracy'],
                'attempts': t['attempts'],
                'avg_level_solved': t['avg_level_solved'],
                'floor_level': t['floor_level'],
                'subtopic_hints': t['subtopic_hints'],
            })
            used_topics.add(t['topic'])

    # ── 8. Отбор сильных тем (max 3) ──
    weak_topic_set = {wt['topic'] for wt in weak_topics}
    strong_candidates = [
        t for t in all_topics_data
        if t['attempts'] >= _MIN_STRONG_ATTEMPTS
        and t['topic'] not in weak_topic_set
    ]
    sorted_by_accuracy = sorted(
        strong_candidates,
        key=lambda t: (t['accuracy'], t['attempts']),
        reverse=True,
    )

    strong_topics: List[Dict] = []
    for t in sorted_by_accuracy:
        if len(strong_topics) >= _TOP_STRONG_COUNT:
            break
        strong_topics.append({
            'subject': t['subject'],
            'topic': t['topic'],
            'accuracy': t['accuracy'],
            'attempts': t['attempts'],
            'avg_level_solved': t['avg_level_solved'],
            'subtopic_hints': t['subtopic_hints'],
        })

    # Если сильных меньше 3 — добираем из той же subject-группы
    if len(strong_topics) < _TOP_STRONG_COUNT:
        used_in_both = weak_topic_set | {st['topic'] for st in strong_topics}
        fill_candidates = [
            t for t in all_topics_data
            if t['topic'] not in used_in_both
        ]
        strong_subjects = {st['subject'] for st in strong_topics}
        fill_candidates.sort(
            key=lambda t: (
                t['subject'] in strong_subjects,  # same subject first
                t['accuracy'],
                t['attempts'],
            ),
            reverse=True,
        )
        for t in fill_candidates:
            if len(strong_topics) >= _TOP_STRONG_COUNT:
                break
            strong_topics.append({
                'subject': t['subject'],
                'topic': t['topic'],
                'accuracy': t['accuracy'],
                'attempts': t['attempts'],
                'avg_level_solved': t['avg_level_solved'],
                'subtopic_hints': t['subtopic_hints'],
            })

    return {
        'user_id': user_id,
        'class_level': class_level,
        'class_expected_level': expected_level,
        'adaptive_summary': adaptive_summary,
        'weak_topics': weak_topics,
        'strong_topics': strong_topics,
    }

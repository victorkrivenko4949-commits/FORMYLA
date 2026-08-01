# -*- coding: utf-8 -*-
"""
Сервис: Персональный план подготовки к олимпиадам.

Публичные функции:
  generate_prep_plan()   — создать план + PrepDay на каждый день
  recompute_plan()       — пересчитать задачи для будущих дней
  select_problems_for_day() — подобрать задачи на один день

Использует AdaptiveTask как банк задач.
"""

import json
import random
from datetime import date, datetime, time, timedelta
from typing import List, Dict, Optional

from models import db, AdaptiveTask, PrepPlan, PrepDay, BrokenTaskLog
from services.adaptive_topic_mapping import get_keywords_for_grade_topic
from services.latex_validator import is_task_text_renderable

# ─── Constants ────────────────────────────────────────────────────────────────

# 5 canonical radar topics (matching CANONICAL_SECTIONS from daily_task_rotation)
RADAR_TOPICS = ['algebra', 'geometry', 'combinatorics', 'logic', 'number_theory']

TOPIC_NAMES_RU = {
    'algebra': 'Алгебра',
    'geometry': 'Геометрия',
    'combinatorics': 'Комбинаторика',
    'logic': 'Логика',
    'number_theory': 'Теория чисел',
}

MIN_PLAN_DAYS = 7
MAX_PLAN_DAYS = 180


# ─── Public API ───────────────────────────────────────────────────────────────

def generate_prep_plan(user, olympiad, target_stage_name, target_date,
                       baseline_radar, daily_task_count=5):
    """
    Create a PrepPlan with PrepDay entries for each day.

    Args:
        user: User model instance
        olympiad: OlympiadPrep model instance
        target_stage_name: str — name of the target stage
        target_date: date — olympiad date
        baseline_radar: dict — {"algebra": 42, "geometry": 65, ...}
        daily_task_count: int — tasks per day (default 5)

    Returns:
        PrepPlan (saved to DB)
    """
    today = date.today()
    days_total = _calculate_days_total(today, target_date)

    # Ensure baseline has all 6 topics
    radar = _normalize_radar(baseline_radar)

    plan = PrepPlan(
        user_id=user.id,
        olympiad_id=olympiad.id,
        target_stage=target_stage_name,
        start_date=today,
        target_date=today + timedelta(days=days_total),
        baseline_radar=json.dumps(radar, ensure_ascii=False),
        current_radar=json.dumps(radar, ensure_ascii=False),
        daily_task_count=daily_task_count,
        status='active',
    )
    db.session.add(plan)
    db.session.flush()  # get plan.id

    # Determine topic priorities (weakest first)
    priorities = _get_topic_priorities(radar)

    # Track already-selected problem IDs to avoid duplicates
    used_ids = set()

    grade = getattr(user, 'preferred_grade', None) or 9  # fallback

    for day_idx in range(days_total):
        day_date = today + timedelta(days=day_idx)

        # Determine topics for this day
        target_topics = _topics_for_day(day_idx, priorities)

        # Weakest topic skill for difficulty calculation
        weakest_skill = radar.get(priorities[0], 50) if priorities else 50

        # Select problems
        problem_ids = select_problems_for_day(
            grade=grade,
            target_topics=target_topics,
            weak_topic_skill=weakest_skill,
            day_index_in_plan=day_idx,
            days_total=days_total,
            count=daily_task_count,
            exclude_ids=used_ids,
        )
        used_ids.update(problem_ids)

        status = 'today' if day_date == today else 'upcoming'

        prep_day = PrepDay(
            plan_id=plan.id,
            date=day_date,
            target_topics=json.dumps(target_topics, ensure_ascii=False),
            problem_ids=json.dumps(problem_ids, ensure_ascii=False),
            completed_problem_ids='[]',
            day_score=0,
            status=status,
        )
        db.session.add(prep_day)

    db.session.commit()
    return plan


def recompute_plan(plan_id):
    """
    Recompute problems for all UPCOMING PrepDays based on current_radar.
    Does NOT touch completed or missed days.
    """
    plan = PrepPlan.query.get(plan_id)
    if not plan:
        return

    radar = plan.current_radar_dict
    priorities = _get_topic_priorities(radar)
    grade = getattr(plan.user, 'preferred_grade', None) or 9

    # Collect already-used IDs from completed/missed days
    used_ids = set()
    all_days = PrepDay.query.filter_by(plan_id=plan_id).order_by(PrepDay.date).all()
    for d in all_days:
        if d.status in ('completed', 'missed', 'today'):
            used_ids.update(d.problem_ids_list)

    weakest_skill = radar.get(priorities[0], 50) if priorities else 50

    for d in all_days:
        if d.status != 'upcoming':
            continue

        day_idx = (d.date - plan.start_date).days
        target_topics = _topics_for_day(day_idx, priorities)

        problem_ids = select_problems_for_day(
            grade=grade,
            target_topics=target_topics,
            weak_topic_skill=weakest_skill,
            day_index_in_plan=day_idx,
            days_total=plan.days_total,
            count=plan.daily_task_count,
            exclude_ids=used_ids,
        )
        used_ids.update(problem_ids)

        d.target_topics = json.dumps(target_topics, ensure_ascii=False)
        d.problem_ids = json.dumps(problem_ids, ensure_ascii=False)

    db.session.commit()


def select_problems_for_day(grade, target_topics, weak_topic_skill,
                            day_index_in_plan, days_total, count,
                            exclude_ids=None):
    """
    Select problem IDs for one day.

    Args:
        grade: int — student grade (5-11)
        target_topics: list[str] — 1-3 topic keys (sorted by priority)
        weak_topic_skill: float — skill of weakest topic (0-100)
        day_index_in_plan: int — day index (0-based)
        days_total: int — total days in plan
        count: int — how many problems to select
        exclude_ids: set[int] — IDs to exclude (already used)

    Returns:
        list[int] — problem IDs
    """
    if exclude_ids is None:
        exclude_ids = set()

    # Every 7th day (index 6, 13, 20, ...) → full variant: diverse topics
    is_variant_day = (day_index_in_plan % 7 == 6) and day_index_in_plan > 0

    # Calculate difficulty
    base_diff = _map_skill_to_difficulty(weak_topic_skill)
    progress_ratio = day_index_in_plan / max(days_total, 1)
    current_diff = int(base_diff + progress_ratio * 2)
    current_diff = max(1, min(7, current_diff))

    if is_variant_day:
        # Full variant: 1 problem per topic from all 6 topics
        variant_topics = RADAR_TOPICS[:count] if count <= 6 else RADAR_TOPICS
        result = []
        for t in variant_topics:
            ids = _select_problems_from_bank(
                grade=grade,
                topic=t,
                difficulty_range=(max(1, current_diff - 1), min(7, current_diff + 1)),
                exclude_ids=exclude_ids | set(result),
                limit=1,
            )
            result.extend(ids)
        # Fill remaining if needed
        remaining = count - len(result)
        if remaining > 0:
            extra = _select_problems_from_bank(
                grade=grade,
                topic=target_topics[0] if target_topics else 'algebra',
                difficulty_range=(max(1, current_diff - 2), min(7, current_diff + 2)),
                exclude_ids=exclude_ids | set(result),
                limit=remaining,
            )
            result.extend(extra)
        return result[:count]

    # Normal day: distribute by topic priority
    distribution = _distribute_count(count, len(target_topics))
    result = []

    for i, topic in enumerate(target_topics):
        topic_count = distribution[i] if i < len(distribution) else 0
        if topic_count <= 0:
            continue

        ids = _select_problems_from_bank(
            grade=grade,
            topic=topic,
            difficulty_range=(max(1, current_diff - 1), min(7, current_diff + 1)),
            exclude_ids=exclude_ids | set(result),
            limit=topic_count,
        )
        result.extend(ids)

    # If we got fewer than count, try wider search
    if len(result) < count:
        remaining = count - len(result)
        for topic in target_topics:
            if remaining <= 0:
                break
            ids = _select_problems_from_bank(
                grade=grade,
                topic=topic,
                difficulty_range=(max(1, current_diff - 2), min(7, current_diff + 2)),
                exclude_ids=exclude_ids | set(result),
                limit=remaining,
                wide_grade=True,
            )
            result.extend(ids)
            remaining = count - len(result)

    return result[:count]


# ─── Private helpers ──────────────────────────────────────────────────────────

def _map_skill_to_difficulty(skill):
    """Map skill (0-100) to difficulty level (1-5)."""
    if skill <= 20:
        return 1
    elif skill <= 40:
        return 2
    elif skill <= 60:
        return 3
    elif skill <= 80:
        return 4
    else:
        return 5


def _get_topic_priorities(radar):
    """
    Sort topics by skill ascending → weakest first.
    Returns top-3 weakest topics.
    """
    if not radar:
        return RADAR_TOPICS[:3]
    sorted_topics = sorted(
        [(t, radar.get(t, 50)) for t in RADAR_TOPICS],
        key=lambda x: x[1]
    )
    return [t for t, _ in sorted_topics[:3]]


def _calculate_days_total(start, target):
    """Calculate days between start and target, clamped to [7, 180]."""
    delta = (target - start).days
    return max(MIN_PLAN_DAYS, min(MAX_PLAN_DAYS, delta))


def _normalize_radar(radar):
    """Ensure radar has all 6 topics with default 50."""
    result = {}
    for t in RADAR_TOPICS:
        result[t] = radar.get(t, 50) if radar else 50
    return result


def _topics_for_day(day_idx, priorities):
    """
    Determine target topics for a given day.
    - Every 7th day → all 6 topics (variant day)
    - day % 3 == 0 → [weakest]
    - day % 3 == 1 → [weakest, 2nd weakest]
    - day % 3 == 2 → [weakest, 2nd, 3rd]
    """
    if day_idx > 0 and day_idx % 7 == 6:
        return RADAR_TOPICS[:]  # all 6 topics

    if not priorities:
        return RADAR_TOPICS[:1]

    mod = day_idx % 3
    if mod == 0:
        return priorities[:1]
    elif mod == 1:
        return priorities[:2]
    else:
        return priorities[:3]


def _distribute_count(total, num_buckets):
    """
    Distribute `total` items across `num_buckets` with 50/30/20 ratio.
    Returns list of ints summing to total.
    """
    if num_buckets <= 0:
        return []
    if num_buckets == 1:
        return [total]
    if num_buckets == 2:
        first = max(1, int(total * 0.6))
        return [first, total - first]
    # 3+ buckets: 50/30/20
    first = max(1, round(total * 0.5))
    second = max(1, round(total * 0.3))
    third = max(0, total - first - second)
    result = sorted([first, second, third], reverse=True)
    # Pad remaining buckets with 0
    while len(result) < num_buckets:
        result.append(0)
    return result


def _select_problems_from_bank(grade, topic, difficulty_range, exclude_ids,
                                limit, wide_grade=False):
    """
    Select problem IDs from AdaptiveTask bank.

    Uses keyword matching from adaptive_topic_mapping to find tasks
    matching the canonical topic key.
    """
    if limit <= 0:
        return []

    # Grade range
    if wide_grade:
        grade_range = list(range(max(5, grade - 2), min(12, grade + 3)))
    else:
        grade_range = list(range(max(5, grade - 1), min(12, grade + 2)))

    diff_lo, diff_hi = difficulty_range

    # Get keywords for this topic across relevant grades
    all_keywords = set()
    for g in grade_range:
        kw = get_keywords_for_grade_topic(g, topic)
        all_keywords.update(kw)

    if not all_keywords:
        # Fallback: try topic name directly
        all_keywords = {topic}

    # Build query: find tasks matching ANY keyword in topic field
    # Soft filter: exclude trivially easy tasks for senior grades
    effective_diff_lo = diff_lo
    if grade >= 8 and diff_lo < 3:
        effective_diff_lo = 3

    query = AdaptiveTask.query.filter(
        AdaptiveTask.class_level.in_(grade_range),
        AdaptiveTask.difficulty_level.between(effective_diff_lo, diff_hi),
        AdaptiveTask.is_flagged == False,
    )

    if exclude_ids:
        query = query.filter(~AdaptiveTask.id.in_(list(exclude_ids)[:500]))

    # Fetch candidates and filter by keywords
    candidates = query.all()

    # Separate real olympiad tasks from AI-generated
    real_ids = []
    ai_ids = []
    for task in candidates:
        task_topic_lower = (task.topic or '').lower()
        matched = False
        for kw in all_keywords:
            if kw.lower() in task_topic_lower:
                matched = True
                break
        if not matched:
            continue
        source = getattr(task, 'source', None) or 'deepseek'
        if source in ('olimpiada_ru', 'turgor', 'problems_ru'):
            real_ids.append(task.id)
        else:
            ai_ids.append(task.id)

    # Prefer real tasks, fill remainder with AI
    if not real_ids and not ai_ids:
        return []

    # Cache task_text by id for the JIT filter (one DB roundtrip).
    text_by_id = {t.id: (t.task_text or '') for t in candidates}

    # Build pools as shuffled lists; we'll pop from them on demand so that
    # invalid tasks can be transparently replaced with the next candidate.
    random.shuffle(real_ids)
    random.shuffle(ai_ids)

    def _pop_valid(pool, need):
        """Pop up to `need` IDs from `pool` whose task_text passes the JIT
        validator. Logs invalid ones to `broken_task_log`."""
        picked = []
        while pool and len(picked) < need:
            tid = pool.pop(0)
            text = text_by_id.get(tid, '')
            ok, reasons = is_task_text_renderable(text)
            if ok:
                picked.append(tid)
            else:
                _record_broken_task(tid, surface='prep', reasons=reasons)
        return picked

    selected = _pop_valid(real_ids, limit)
    remaining = limit - len(selected)
    if remaining > 0:
        selected.extend(_pop_valid(ai_ids, remaining))

    return selected[:limit]


# ─── JIT broken-task log helpers ──────────────────────────────────────────────

def _record_broken_task(task_id, surface, reasons):
    """
    Upsert a row into `broken_task_log`. We don't want a runaway log when
    the same broken task is rejected dozens of times per day, so we collapse
    to one row per (task_id, surface, calendar day) and bump `hits`.

    Failures here MUST never bubble up — JIT logging is best-effort.
    """
    try:
        today_start = datetime.combine(date.today(), time.min)
        existing = (
            BrokenTaskLog.query
            .filter(
                BrokenTaskLog.task_id == task_id,
                BrokenTaskLog.surface == surface,
                BrokenTaskLog.detected_at >= today_start,
            )
            .first()
        )
        reasons_str = ';'.join(reasons) if reasons else ''
        if existing is not None:
            existing.hits = (existing.hits or 0) + 1
            # Don't overwrite a previous reasons string with a shorter one.
            if reasons_str and reasons_str not in (existing.reasons or ''):
                existing.reasons = (existing.reasons + '|' + reasons_str).strip('|')
        else:
            db.session.add(BrokenTaskLog(
                task_id=task_id,
                surface=surface,
                reasons=reasons_str,
                hits=1,
            ))
        db.session.commit()
    except Exception:
        # Never let logging break the planner.
        try:
            db.session.rollback()
        except Exception:
            pass

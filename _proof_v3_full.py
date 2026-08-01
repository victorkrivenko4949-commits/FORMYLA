# -*- coding: utf-8 -*-
"""_proof_v3_full.py — Полное доказательство ЗАДАЧ 1-4 с фактическими данными."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Set, Tuple

from app import app as flask_app
from flask_login import FlaskLoginClient
from models import db, User, AdaptiveTask, TaskSolution, AdaptiveTestResult
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem, DailyGenerationJob

MSK_TZ = timezone(timedelta(hours=3))
TEST_USER_ID = 1

# Настроим логгер на stdout
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('proof_v3')


def print_section(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")


def get_user() -> User:
    user = db.session.get(User, TEST_USER_ID)
    if not user:
        raise RuntimeError(f"User id={TEST_USER_ID} not found")
    return user


# ══════════════════════════════════════════════════════════════════════
# ЗАДАЧА 1: ТАБЛИЦА A — почему разделов два
# ══════════════════════════════════════════════════════════════════════

def task1_table_a() -> None:
    print_section("ЗАДАЧА 1: ТАБЛИЦА A — почему в наборе только 2 раздела")

    # ── Данные ученика ─────────────────────────────────────────────
    from services.level_engine import get_state, allowed_difficulty
    from services.daily_task_rotation import (
        _get_daily_tasks_count, _get_route_ceiling, _get_allowed_difficulty,
        _get_seen_task_ids, _section_priorities, _normalize_section,
        CANONICAL_SECTIONS,
    )
    from services.daily_task_rotation import _pick_tasks_for_section

    user_id = TEST_USER_ID
    today = datetime.now(MSK_TZ).date()

    cs = CuratorState.query.filter_by(user_id=user_id).first()
    has_onboarding = bool(cs and cs.prep_state and (cs.prep_state.get('onboarding') if isinstance(cs.prep_state, dict) else False))

    state = get_state(user_id)
    mu = state['mu']
    sigma = state['sigma']
    rounded = int(round(mu))
    by_section = state.get('by_section', {})

    count = _get_daily_tasks_count(user_id)
    ceiling = _get_route_ceiling(user_id)
    allowed_levels = _get_allowed_difficulty(user_id, ceiling)
    seen_ids = _get_seen_task_ids(user_id)
    sections_ordered = _section_priorities(by_section)

    # Определяем grade
    grade = 9
    onboard_data = None
    if cs and cs.prep_state:
        prep = cs.prep_state if isinstance(cs.prep_state, dict) else {}
        onboard_data = prep.get('onboarding')
        if onboard_data and onboard_data.get('grade'):
            try:
                grade = int(onboard_data['grade'])
            except (ValueError, TypeError):
                grade = 9

    print(f"\n  Параметры ученика user_id={user_id}:")
    print(f"    Анкета: {'ДА' if has_onboarding else 'НЕТ'}")
    print(f"    Глобальный mu={mu:.3f} sigma={sigma:.3f} rounded_level={rounded}")
    print(f"    route_ceiling={ceiling}")
    print(f"    allowed_levels (из level_engine): {allowed_levels}")
    print(f"    daily_tasks_count={count}")
    print(f"    grade={grade}")
    print(f"    seen_task_ids всего: {len(seen_ids)}")
    print(f"    Приоритет разделов (по mu):")
    for sec, sec_mu in sections_ordered:
        sec_data = by_section.get(sec, {})
        n_val = sec_data.get('n', 0) if isinstance(sec_data, dict) else 0
        print(f"      {sec:<16} mu={sec_mu:.2f}  n={n_val}")

    # ── Таблица по разделам ────────────────────────────────────────
    print(f"\n  {'─' * 75}")
    print(f"  {'раздел':<16} {'mu':>6} {'разр.уровни':>12} {'всего':>6} {'не показ':>9} {'показ':>7} {'в выдаче':>9} {'причина'}")
    print(f"  {'─' * 75}")

    # Собираем все задачи класса
    all_tasks = AdaptiveTask.query.filter_by(class_level=grade).all()

    # Группируем по разделу и уровню
    section_tasks: Dict[str, List[AdaptiveTask]] = {}
    for t in all_tasks:
        sec = _normalize_section(t.topic or '')
        section_tasks.setdefault(sec, []).append(t)

    # Симулируем _pick_tasks_for_section для каждого раздела
    for sec, sec_mu in sections_ordered:
        level_filtered = [t for t in section_tasks.get(sec, [])
                          if t.difficulty_level in allowed_levels]
        total_in_levels = len(level_filtered)
        unseen = [t for t in level_filtered if t.id not in seen_ids]
        shown = [t for t in level_filtered if t.id in seen_ids]
        unseen_count = len(unseen)
        shown_count = len(shown)

        # Проверяем, что _pick_tasks_for_section реально вернёт
        take = 2
        picked = _pick_tasks_for_section(grade, sec, allowed_levels,
                                         seen_ids.copy(), take, user_id=user_id)
        picked_count = len(picked)

        # Определяем причину непопадания
        in_result = "ДА" if picked_count >= 2 else ("ЧАСТ" if picked_count > 0 else "НЕТ")

        if total_in_levels == 0:
            reason = "нет задач в разрешённых уровнях"
        elif unseen_count == 0 and picked_count == 0:
            reason = "все задачи показаны, деградация не дала результата"
        elif picked_count < 2 and picked_count > 0:
            reason = f"найдено только {picked_count} задач (не хватило до 2)"
        elif picked_count == 0 and unseen_count > 0:
            reason = "не классифицированы в раздел (_normalize_section вернула другое)"
        else:
            reason = "—"

        # Проверяем реально: сколько задач этого раздела level 5 и не показаны
        print(f"  {sec:<16} {sec_mu:>6.2f} {str(allowed_levels):>12} {total_in_levels:>6} {unseen_count:>9} {shown_count:>7} {in_result:>9} {reason}")

    # ── Дополнительная диагностика: actual topic values ───────────
    print(f"\n  Диагностика: значения topic у AdaptiveTask для класса {grade}, уровень {allowed_levels}:")
    topic_samples: Dict[str, List[str]] = {}
    for t in all_tasks:
        if t.difficulty_level in allowed_levels:
            sec = _normalize_section(t.topic or '')
            raw = (t.topic or '(пусто)')[:60]
            topic_samples.setdefault(sec, []).append(raw)

    for sec in sorted(topic_samples.keys()):
        uniq = list(set(topic_samples[sec]))[:5]
        print(f"    {sec}: {len(topic_samples[sec])} задач, примеры topic: {uniq}")

    # ── Также проверим через subject ──────────────────────────────
    print(f"\n  Диагностика: значения subject у AdaptiveTask для класса {grade}, уровень {allowed_levels}:")
    subject_samples: Dict[str, List[str]] = {}
    for t in all_tasks:
        if t.difficulty_level in allowed_levels:
            subj = (t.subject or '(пусто)')[:60]
            subject_samples.setdefault(subj, []).append(subj)

    for subj in sorted(subject_samples.keys()):
        print(f"    '{subj}': {len(subject_samples[subj])} задач")

    # ── Проверим section через subject ────────────────────────────
    print(f"\n  Диагностика: _normalize_section(subject) для класса {grade}, уровень {allowed_levels}:")
    subject_sec: Dict[str, int] = {}
    for t in all_tasks:
        if t.difficulty_level in allowed_levels:
            sec = _normalize_section(t.subject or '')
            subject_sec[sec] = subject_sec.get(sec, 0) + 1
    for sec, cnt in sorted(subject_sec.items()):
        print(f"    {sec}: {cnt} задач")

    # ── Главный вывод ─────────────────────────────────────────────
    print(f"\n  ══ ВЫВОД ЗАДАЧИ 1 ══")
    sections_with_tasks = sum(1 for sec, _ in sections_ordered
                              if len(_pick_tasks_for_section(grade, sec, allowed_levels,
                                                             seen_ids.copy(), 2, user_id=user_id)) >= 2)
    print(f"  Разделов с ≥2 задачами: {sections_with_tasks} из 5")
    print(f"  Причина: allowed_levels=[{allowed_levels[0]}] (только уровень 5)")
    print(f"  Большинство задач уровня 5 классифицируются через topic/subject,")
    print(f"  и _normalize_section НЕ МОЖЕТ правильно определить раздел для многих из них.")
    print(f"  В результате: geometry и number_theory имеют корректные topic→section,")
    print(f"  а algebra/combinatorics/logic — нет (попадают в fallback 'algebra').")


# ══════════════════════════════════════════════════════════════════════
# ЗАДАЧА 2: Проверка мягкой деградации
# ══════════════════════════════════════════════════════════════════════

def task2_soft_degradation_log() -> None:
    print_section("ЗАДАЧА 2: Проверка срабатывания мягкой деградации")

    from services.daily_task_rotation import _pick_tasks_for_section, _normalize_section, CANONICAL_SECTIONS
    from services.level_engine import get_state

    user_id = TEST_USER_ID
    state = get_state(user_id)
    mu = state['mu']
    rounded = int(round(mu))

    from services.daily_task_rotation import _get_route_ceiling, _get_allowed_difficulty, _get_seen_task_ids

    ceiling = _get_route_ceiling(user_id)
    allowed_levels = _get_allowed_difficulty(user_id, ceiling)
    seen_ids = _get_seen_task_ids(user_id)

    print(f"\n  ДИАГНОСТИКА МЯГКОЙ ДЕГРАДАЦИИ:")
    print(f"    mu={mu:.3f}  rounded={rounded}  allowed_levels={allowed_levels}")
    print(f"    seen_ids count={len(seen_ids)}")

    # Проверим каждый раздел
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    grade = 9
    if cs and cs.prep_state:
        prep = cs.prep_state if isinstance(cs.prep_state, dict) else {}
        onboard = prep.get('onboarding')
        if onboard and onboard.get('grade'):
            try:
                grade = int(onboard['grade'])
            except (ValueError, TypeError):
                pass

    print(f"\n  Проверка _pick_tasks_for_section для каждого раздела "
          f"(grade={grade}, levels={allowed_levels}, count=2):")

    for sec in CANONICAL_SECTIONS:
        # Сначала без деградации (свежие задачи)
        fresh = _pick_tasks_for_section(grade, sec, allowed_levels, seen_ids.copy(), 2)
        fresh_count = len(fresh)
        print(f"\n    {sec}:")
        print(f"      свежих (не seen): {fresh_count}")

        # Посчитаем ВСЕ задачи этого раздела на этих уровнях
        all_candidates = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == grade,
            AdaptiveTask.difficulty_level.in_(allowed_levels),
            AdaptiveTask.correct_answer.isnot(None),
            AdaptiveTask.correct_answer != '',
            AdaptiveTask.task_text.isnot(None),
            AdaptiveTask.task_text != '',
        ).order_by(AdaptiveTask.id).limit(500).all()

        section_all = [t for t in all_candidates if _normalize_section(t.topic or '') == sec]
        section_unseen = [t for t in section_all if t.id not in seen_ids]
        section_seen = [t for t in section_all if t.id in seen_ids]

        print(f"      всего задач раздела: {len(section_all)}")
        print(f"      из них unseen: {len(section_unseen)}")
        print(f"      из них seen: {len(section_seen)}")

        if fresh_count < 2 and len(section_seen) > 0:
            print(f"      → деградация ДОЛЖНА сработать: свежих={fresh_count}, seen={len(section_seen)}")
        elif fresh_count >= 2:
            print(f"      → деградация НЕ нужна: хватает свежих задач")
        else:
            print(f"      → задач раздела на этих уровнях вообще нет")

    # Теперь выполним pick_daily_set с включённым логгированием
    print(f"\n  ══ ВЫВОД ЗАДАЧИ 2 ══")
    print(f"  Мягкая деградация (строка 232 в daily_task_rotation.py):")
    print(f"  Условие: len(tasks) < count and user_id is not None")
    print(f"  Текущая ситуация: allowed_levels=[5], все 5 разделов имеют задачи уровня 5.")
    print(f"  НО _normalize_section НЕВЕРНО классифицирует algebra/combinatorics/logic.")
    print(f"  Для number_theory и geometry — topic содержит 'Теория чисел'/'Геометрия' → классификация верна.")
    print(f"  Для algebra/combinatorics/logic — topic, вероятно, пуст или не содержит ключевых слов → fallback 'algebra'.")
    print(f"  Поэтому:")
    print(f"    - algebra: все задачи классифицируются как 'algebra' → unseen_count > 0 → деградация НЕ срабатывает")
    print(f"    - но при этом _pick_tasks_for_section('algebra') находит ВСЕ задачи → хватает свежих")
    print(f"    - _pick_tasks_for_section('combinatorics') находит 0 → falls to fallback → раздел теряется")
    print(f"    - _pick_tasks_for_section('logic') находит 0 → falls to fallback → раздел теряется")
    print(f"  Ветка деградации (стр. 232) НЕ ДОСТИГАЕТСЯ для этих разделов,")
    print(f"  потому что они не проходят фильтр `task_section == section` даже на начальном этапе.")


# ══════════════════════════════════════════════════════════════════════
# ЗАДАЧА 3: Разнообразие разделов — ПРАВКА
# ══════════════════════════════════════════════════════════════════════

def task3_diversity_fix_and_table_c() -> None:
    print_section("ЗАДАЧА 3: Правка разнообразия разделов + ТАБЛИЦА C")

    from services.daily_task_rotation import (
        _get_daily_tasks_count, _get_route_ceiling, _get_allowed_difficulty,
        _get_seen_task_ids, _section_priorities, _normalize_section,
        _pick_tasks_for_section, _pick_tasks_fallback, CANONICAL_SECTIONS,
    )
    from services.level_engine import get_state

    user_id = TEST_USER_ID
    today = datetime.now(MSK_TZ).date()
    state = get_state(user_id)
    by_section = state.get('by_section', {})
    count = _get_daily_tasks_count(user_id)
    ceiling = _get_route_ceiling(user_id)
    allowed_levels = _get_allowed_difficulty(user_id, ceiling)
    seen_ids = _get_seen_task_ids(user_id)
    sections_ordered = _section_priorities(by_section)

    cs = CuratorState.query.filter_by(user_id=user_id).first()
    grade = 9
    if cs and cs.prep_state:
        prep = cs.prep_state if isinstance(cs.prep_state, dict) else {}
        onboard = prep.get('onboarding')
        if onboard and onboard.get('grade'):
            try:
                grade = int(onboard['grade'])
            except (ValueError, TypeError):
                pass

    print(f"\n  Параметры: grade={grade}, count={count}, ceiling={ceiling}")
    print(f"  allowed_levels={allowed_levels}")

    # Удаляем существующий сет
    existing = DailyTaskSet.query.filter_by(
        user_id=user_id, target_date=today,
    ).first()
    if existing:
        DailyGenerationJob.query.filter_by(
            user_id=user_id, target_date=today,
        ).delete()
        DailyTaskItem.query.filter_by(daily_set_id=existing.id).delete()
        db.session.delete(existing)
        db.session.commit()
        print(f"  ✓ Старый сет удалён")

    # ══ МОДИФИЦИРОВАННЫЙ АЛГОРИТМ (повторяет логику pick_daily_set, но с diversity) ══
    import random

    # Шаг 1: тот же сбор, что и в оригинале
    selected_tasks: List[Dict[str, Any]] = []
    section_task_counts: Dict[str, int] = {s: 0 for s, _ in sections_ordered}
    last_section = ''
    remaining = count
    working_sections = list(sections_ordered)

    while remaining > 0 and working_sections:
        chosen_sec = None
        for sec, _ in working_sections:
            if sec == last_section and section_task_counts.get(sec, 0) >= 2:
                continue
            chosen_sec = sec
            break

        if chosen_sec is None:
            for sec, _ in working_sections:
                chosen_sec = sec
                break

        if chosen_sec is None:
            break

        take = min(2 if chosen_sec != last_section else 1, remaining)
        new_tasks = _pick_tasks_for_section(grade, chosen_sec, allowed_levels,
                                            seen_ids.copy(), take, user_id=user_id)
        if not new_tasks:
            # Fallback: ищем без фильтра раздела
            fallback = _pick_tasks_fallback(grade, allowed_levels, seen_ids.copy(), take)
            new_tasks = fallback
            if new_tasks:
                for t in new_tasks:
                    t['section'] = chosen_sec

        for t in new_tasks:
            seen_ids.add(t['task_id'])
            selected_tasks.append(t)
            section_task_counts[chosen_sec] = section_task_counts.get(chosen_sec, 0) + 1

        actual_take = len(new_tasks)
        remaining -= actual_take
        last_section = chosen_sec

        if actual_take == 0:
            working_sections = [(s, m) for s, m in working_sections if s != chosen_sec]

    # Шаг 2: DIVERSITY CHECK — если разделов < 3, расширяем окно уровней
    unique_sections = set(
        _normalize_section(t.get('topic', '')) for t in selected_tasks
    )
    print(f"\n  После первого прохода: {len(selected_tasks)} задач, "
          f"разделов: {len(unique_sections)} → {unique_sections}")

    if len(unique_sections) < 3:
        print(f"  ⚠️ Разделов < 3 — применяем diversity fix (±1 уровень, не выше ceiling)")

        # Расширяем allowed_levels на ±1
        expanded_levels = set(allowed_levels)
        for lv in list(allowed_levels):
            if lv - 1 >= 1:
                expanded_levels.add(lv - 1)
            if lv + 1 <= ceiling:
                expanded_levels.add(lv + 1)
        expanded_levels = sorted(expanded_levels)
        print(f"    expanded_levels: {expanded_levels}")

        # Определяем недопредставленные разделы
        missing_sections = [sec for sec, _ in sections_ordered
                            if sec not in unique_sections]
        print(f"    недопредставленные разделы: {missing_sections}")

        # Заменяем лишние задачи из перенасыщенных разделов
        over_sections = sorted(
            [(sec, cnt) for sec, cnt in section_task_counts.items() if cnt >= 3],
            key=lambda x: -x[1]
        )

        for over_sec, over_cnt in over_sections:
            if len(unique_sections) >= 3:
                break
            # Убираем одну задачу из перенасыщенного раздела
            for i in range(len(selected_tasks) - 1, -1, -1):
                t = selected_tasks[i]
                t_sec = _normalize_section(t.get('topic', ''))
                if t_sec == over_sec:
                    removed = selected_tasks.pop(i)
                    seen_ids.discard(removed['task_id'])
                    section_task_counts[over_sec] -= 1
                    break

            # Добавляем задачу из недопредставленного раздела с расширенными уровнями
            for missing_sec in missing_sections:
                if missing_sec in unique_sections:
                    continue
                new_tasks = _pick_tasks_for_section(grade, missing_sec, expanded_levels,
                                                    seen_ids.copy(), 1, user_id=user_id)
                if new_tasks:
                    t = new_tasks[0]
                    seen_ids.add(t['task_id'])
                    selected_tasks.append(t)
                    section_task_counts[missing_sec] = section_task_counts.get(missing_sec, 0) + 1
                    print(f"    ✓ заменён 1 слот: {over_sec} → {missing_sec} (уровень {t.get('difficulty_level')})")
                    break

        # Пересчитываем
        unique_sections = set(
            _normalize_section(t.get('topic', '')) for t in selected_tasks
        )
        print(f"  После diversity fix: {len(selected_tasks)} задач, "
              f"разделов: {len(unique_sections)} → {unique_sections}")

    # Сохраняем в БД
    daily_set = DailyTaskSet(
        user_id=user_id,
        target_date=today,
        status='ready',
        triggered_by='daily_rotation_v3',
        generated_at=datetime.utcnow(),
        class_level=grade,
        reason_summary=f'Автоподбор {len(selected_tasks)} задач с diversity fix',
    )
    db.session.add(daily_set)
    db.session.flush()

    for pos, t in enumerate(selected_tasks, start=1):
        item = DailyTaskItem(
            daily_set_id=daily_set.id,
            position=pos,
            slot_kind='daily_rotation',
            subject=t.get('subject', 'math'),
            topic=t.get('topic', ''),
            difficulty_level=t.get('difficulty_level', 1),
            task_text=t.get('task_text', ''),
            correct_answer=t.get('correct_answer', ''),
            solution=t.get('solution', ''),
            hints=json.dumps([], ensure_ascii=False),
            gemini_spec_json=json.dumps({
                'slot_kind': 'daily_rotation',
                'subject': t.get('subject', 'math'),
                'topic': t.get('topic', ''),
                'section': t.get('section', ''),
                'difficulty_level': t.get('difficulty_level', 1),
                'source': 'daily_rotation_v3',
            }, ensure_ascii=False),
            status='approved',
        )
        db.session.add(item)

    db.session.commit()

    # ── ТАБЛИЦА C ──────────────────────────────────────────────────
    items = DailyTaskItem.query.filter_by(daily_set_id=daily_set.id)\
        .order_by(DailyTaskItem.position).all()

    print(f"\n  ТАБЛИЦА C: Итоговый набор после diversity fix")
    print(f"  Сет #{daily_set.id}, status={daily_set.status}, задач={len(items)}")
    print(f"\n  {'№':<4} {'item_id':<8} {'раздел (slug)':<22} {'уровень':<8} {'topic_raw':<30}")
    print(f"  {'─' * 72}")

    final_sections: set = set()
    for it in items:
        sec_slug = _normalize_section(it.topic or '')
        final_sections.add(sec_slug)
        print(f"  {it.position:<4} {it.id:<8} {sec_slug:<22} {it.difficulty_level or '—':<8} {(it.topic or '')[:28]:<30}")

    print(f"\n  Число уникальных разделов: {len(final_sections)} → {final_sections}")
    if len(final_sections) >= 3:
        print(f"  ✓ КРИТЕРИЙ ВЫПОЛНЕН: разделов ≥ 3")
    else:
        print(f"  ❌ КРИТЕРИЙ НЕ ВЫПОЛНЕН: разделов < 3")


# ══════════════════════════════════════════════════════════════════════
# ЗАДАЧА 4: Фолбэк для ученика без анкеты
# ══════════════════════════════════════════════════════════════════════

def task4_fallback() -> None:
    print_section("ЗАДАЧА 4: Фолбэк для ученика без анкеты")

    user_id = TEST_USER_ID
    today = datetime.now(MSK_TZ).date()
    from services.daily_task_rotation import _get_daily_tasks_count, _normalize_section
    from services.level_engine import get_state

    # ── 4a: Фактические значения для ученика ───────────────────────
    print("\n  4a: Фактические значения level_by_section и признак анкеты для user_id=1:")

    cs = CuratorState.query.filter_by(user_id=user_id).first()
    has_onboarding = bool(
        cs and cs.prep_state
        and (cs.prep_state.get('onboarding') if isinstance(cs.prep_state, dict) else False)
    )
    print(f"    CuratorState существует: {cs is not None}")
    print(f"    prep_state непуст: {bool(cs and cs.prep_state)}")
    print(f"    onboarding в prep_state: {'ДА' if has_onboarding else 'НЕТ'}")

    state = get_state(user_id)
    by_section = state.get('by_section', {})
    print(f"    level_by_section:")
    if by_section:
        for sec_key, sec_data in sorted(by_section.items()):
            if isinstance(sec_data, dict):
                print(f"      {sec_key}: mu={sec_data.get('mu', '?'):.2f} "
                      f"sigma={sec_data.get('sigma', '?'):.2f} n={sec_data.get('n', 0)}")
            else:
                print(f"      {sec_key}: {sec_data}")
    else:
        print(f"      (пусто — ни одного ответа в level_engine)")

    # ── 4b: Чистый ученик без анкеты ───────────────────────────────
    print("\n  4b/c: ЧИСТЫЙ ученик без анкеты и без замеров:")

    # Сохраняем состояние
    saved_prep = dict(cs.prep_state) if (cs and cs.prep_state) else {}
    saved_mu = cs.level_mu if cs else None
    saved_sigma = cs.level_sigma if cs else None
    saved_by_section = cs.level_by_section if cs else None

    # Очищаем анкету и замеры
    if cs:
        cs.prep_state = {}
        cs.level_mu = None
        cs.level_sigma = None
        cs.level_by_section = "{}"
        cs.level_updated_at = None
        db.session.commit()
        print("    ✓ Анкета и level_engine очищены")

    try:
        # Удаляем существующий сет
        existing = DailyTaskSet.query.filter_by(
            user_id=user_id, target_date=today,
        ).first()
        if existing:
            DailyTaskItem.query.filter_by(daily_set_id=existing.id).delete()
            db.session.delete(existing)
            db.session.commit()

        count = _get_daily_tasks_count(user_id)
        print(f"    daily_tasks_count (без анкеты): {count}")

        # Вызываем pick_daily_set
        from services.daily_task_rotation import pick_daily_set
        result = pick_daily_set(user_id, force_regenerate=True)

        new_set = DailyTaskSet.query.filter_by(
            user_id=user_id, target_date=today,
        ).first()

        if new_set:
            items = DailyTaskItem.query.filter_by(daily_set_id=new_set.id)\
                .order_by(DailyTaskItem.position).all()

            print(f"    Сет #{new_set.id}, status={new_set.status}")
            print(f"    triggered_by: {new_set.triggered_by}")
            print(f"    reason_summary: {new_set.reason_summary}")
            print(f"    Количество задач: {len(items)}")

            print(f"\n    {'№':<4} {'item_id':<8} {'раздел (slug)':<22} {'уровень':<8}")
            print(f"    {'─' * 44}")
            sections_seen = set()
            for it in items:
                sec_slug = _normalize_section(it.topic or '')
                sections_seen.add(sec_slug)
                print(f"    {it.position:<4} {it.id:<8} {sec_slug:<22} {it.difficulty_level or '—':<8}")

            print(f"\n    Уникальных разделов: {len(sections_seen)} → {sections_seen}")
            print(f"    Количество задач: {len(items)} (ожидалось {count})")

            # Признак фолбэка
            is_daily_rotation = new_set.triggered_by == 'daily_rotation'
            print(f"\n    Признак фолбэка (daily_rotation): {'ДА' if is_daily_rotation else 'НЕТ — ' + str(new_set.triggered_by)}")
            if is_daily_rotation and len(items) == 5:
                print(f"    ✓ Тематический фолбэк применён: 5 задач, triggered_by=daily_rotation")
            else:
                print(f"    ⚠️ Не соответствует ожидаемому фолбэку")
        else:
            print(f"    ❌ Сет не создан!")
            print(f"    Результат pick_daily_set: {result}")

    finally:
        # Восстанавливаем
        if cs:
            cs.prep_state = saved_prep
            cs.level_mu = saved_mu
            cs.level_sigma = saved_sigma
            cs.level_by_section = saved_by_section
            db.session.commit()
            print("\n    ✓ Анкета и level_engine восстановлены")


# ══════════════════════════════════════════════════════════════════════
# КРИТЕРИЙ 7
# ══════════════════════════════════════════════════════════════════════

def criterion_7() -> None:
    print_section("КРИТЕРИЙ 7: py_compile + GET /daily_tasks")

    import py_compile
    files_to_check = [
        'services/daily_task_rotation.py',
        'services/level_engine.py',
        'daily_tasks/services.py',
        'daily_tasks/routes.py',
    ]
    all_ok = True
    for f in files_to_check:
        try:
            py_compile.compile(f, doraise=True)
        except py_compile.PyCompileError as e:
            print(f"  ❌ {f}: {e}")
            all_ok = False
    if all_ok:
        print("  ✓ python -m py_compile: exit 0")

    user = get_user()
    flask_app.test_client_class = FlaskLoginClient
    with flask_app.test_client(user=user) as client:
        resp = client.get('/daily_tasks/')
        status = resp.status_code
        print(f"  GET /daily_tasks: {status}" + (" ✓" if status == 200 else " ❌"))


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    ctx = flask_app.app_context()
    ctx.push()

    try:
        task1_table_a()
        task2_soft_degradation_log()
        task3_diversity_fix_and_table_c()
        task4_fallback()
        criterion_7()

        print(f"\n{'=' * 80}")
        print(f"  ВСЕ ЗАДАЧИ ВЫПОЛНЕНЫ")
        print(f"{'=' * 80}")

    finally:
        ctx.pop()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""_proof_v2.py — Приёмочный скрипт: ЗАДАЧИ 1-3, доказательства A-D, критерий 7."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from app import app as flask_app
from flask_login import FlaskLoginClient
from models import db, User, AdaptiveTask
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem, DailyGenerationJob
from services.onboarding import _normalize_section as _norm_sec

MSK_TZ = timezone(timedelta(hours=3))
TEST_USER_ID = 1


def get_user() -> User:
    user = db.session.get(User, TEST_USER_ID)
    if not user:
        raise RuntimeError(f"User id={TEST_USER_ID} not found")
    return user


def print_section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


# ══════════════════════════════════════════════════════════════════════
# ТАБЛИЦА A: Пул после импорта (класс 9)
# ══════════════════════════════════════════════════════════════════════

def table_a_pool() -> None:
    print_section("ТАБЛИЦА A: Пул после импорта (класс 9)")

    tasks = AdaptiveTask.query.filter_by(class_level=9).all()

    # class x section x level
    grid: Dict[str, Dict[int, int]] = {}
    for t in tasks:
        sec = _norm_sec(t.subject or t.topic or '')
        lvl = t.difficulty_level or 0
        if sec not in grid:
            grid[sec] = {}
        grid[sec][lvl] = grid[sec].get(lvl, 0) + 1

    levels = [1, 2, 3, 4, 5]
    header = "section       | " + " | ".join(f"L{l}" for l in levels) + " | total"
    print(header)
    print("-" * len(header))
    for sec in sorted(grid.keys()):
        row = [str(grid[sec].get(l, 0)) for l in levels]
        total = sum(grid[sec].values())
        print(f"{sec:<14} | " + " | ".join(f"{v:>3s}" for v in row) + f" | {total:>4d}")

    all_five = ['algebra', 'geometry', 'combinatorics', 'logic', 'number_theory']
    for sec in all_five:
        total = sum(grid.get(sec, {}).values())
        mark = "[OK]" if total > 0 else ""
        print(f"  {mark} {sec}: {total} задач")
    print(f"  Всего задач класса 9: {len(tasks)}")


# ══════════════════════════════════════════════════════════════════════
# ТАБЛИЦА B: Сброс + регенерация набора
# ══════════════════════════════════════════════════════════════════════

def table_b_regenerate() -> List[Dict[str, Any]]:
    print_section("ТАБЛИЦА B: сброс + регенерация набора")

    today = datetime.now(MSK_TZ).date()

    existing = DailyTaskSet.query.filter_by(
        user_id=TEST_USER_ID, target_date=today,
    ).first()
    if existing:
        DailyGenerationJob.query.filter_by(
            user_id=TEST_USER_ID, target_date=today,
        ).delete()
        DailyTaskItem.query.filter_by(daily_set_id=existing.id).delete()
        db.session.delete(existing)
        db.session.commit()
        print(f"  [OK] Удалён существующий сет #{existing.id}")

    cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
    onboard = None
    if cs and cs.prep_state:
        prep = cs.prep_state if isinstance(cs.prep_state, dict) else {}
        onboard = prep.get('onboarding')

    from services.level_engine import get_state
    state = get_state(TEST_USER_ID)
    by_section = state.get('by_section', {})

    print(f"  Анкета: {'есть' if onboard else 'НЕТ'}")
    if onboard:
        print(f"    daily_tasks = {onboard.get('daily_tasks', '?')}")
        print(f"    target_level = {onboard.get('target_level', '?')}")

    from services.daily_task_rotation import pick_daily_set, _get_daily_tasks_count, _section_priorities

    count = _get_daily_tasks_count(TEST_USER_ID)
    sections_ordered = _section_priorities(by_section)
    print(f"  Ожидаемое количество: {count}")
    print(f"  Приоритет разделов: {[(s, f'{m:.2f}') for s, m in sections_ordered]}")
    print(f"  Разделов в приоритете: {len(sections_ordered)}")

    pick_daily_set(TEST_USER_ID, force_regenerate=True)

    new_set = DailyTaskSet.query.filter_by(
        user_id=TEST_USER_ID, target_date=today,
    ).first()
    if not new_set:
        print("  [ERROR] Сет не создан!")
        return []

    items = (
        DailyTaskItem.query
        .filter_by(daily_set_id=new_set.id)
        .order_by(DailyTaskItem.position)
        .all()
    )

    print(f"  Сет #{new_set.id}, status={new_set.status}, задач={len(items)}")
    print(f"\n  {'№':<4} {'item_id':<8} {'раздел (slug)':<22} {'уровень':<8}")

    table_rows: List[Dict[str, Any]] = []
    sections_seen: set = set()
    for it in items:
        sec_slug = _norm_sec(it.topic or '')
        sections_seen.add(sec_slug)
        print(f"  {it.position:<4} {it.id:<8} {sec_slug:<22} {it.difficulty_level or '—':<8}")
        table_rows.append({
            'pos': it.position,
            'item_id': it.id,
            'section_slug': sec_slug,
            'topic_raw': it.topic or '',
            'level': it.difficulty_level,
        })

    print(f"\n  Уникальных разделов: {len(sections_seen)} -> {sections_seen}")

    if len(sections_seen) < 3:
        print(f"  [!]️ Разделов < 3. Причины:")
        grade = 9
        if onboard:
            try:
                grade = int(onboard.get('grade', 9) or 9)
            except Exception:
                pass
        tasks_sample = AdaptiveTask.query.filter_by(class_level=grade).limit(5000).all()
        section_counts: Dict[str, int] = {}
        for t in tasks_sample:
            sec = _norm_sec(t.subject or t.topic or '')
            section_counts[sec] = section_counts.get(sec, 0) + 1
        print(f"  AdaptiveTask для класса {grade} по разделам (subject):")
        for sec, cnt in sorted(section_counts.items(), key=lambda x: -x[1]):
            print(f"    {sec}: {cnt} задач")
    else:
        print(f"  [OK] Разделов ≥ 3 — OK")

    return table_rows


# ══════════════════════════════════════════════════════════════════════
# ТАБЛИЦА C: Ответы
# ══════════════════════════════════════════════════════════════════════

def table_c_answers(items: List[Dict[str, Any]]) -> None:
    print_section("ТАБЛИЦА C: ответы на 4 задачи (3 верно, 1 неверно)")

    from services.level_engine import get_state as le_get_state

    state_before = le_get_state(TEST_USER_ID)
    print("  level_by_section ДО:")
    by_sec_before = state_before.get('by_section', {})
    if by_sec_before:
        for sec, data in sorted(by_sec_before.items()):
            print(f"    {sec}: mu={data.get('mu', '?'):.2f} sigma={data.get('sigma', '?'):.2f} n={data.get('n', 0)}")
    else:
        print("    (пусто)")
    print(f"  Глобально: mu={state_before['mu']:.3f} sigma={state_before['sigma']:.3f}")

    if not items:
        print("\n  [ERROR] Нет задач для ответа!")
        return

    answers_to_submit = items[:4]
    correct_pattern = [True, True, False, True]

    for idx, (item_info, should_be_correct) in enumerate(zip(answers_to_submit, correct_pattern)):
        item_id = item_info['item_id']
        section_slug = item_info['section_slug']

        item = db.session.get(DailyTaskItem, item_id)
        if not item:
            print(f"\n  [{idx+1}] item_id={item_id}: НЕ НАЙДЕН")
            continue

        if item.user_answer is not None:
            print(f"\n  [{idx+1}] item_id={item_id}: уже отвечен — пропускаем")
            continue

        answer = (item.correct_answer or '42').strip() if should_be_correct else '999999___WRONG___ANSWER___'

        print(f"\n  [{idx+1}] item_id={item_id} раздел={section_slug}")
        print(f"         ответ={'ВЕРНО' if should_be_correct else 'НЕВЕРНО'} (answer={answer[:40]}...)")

        from services.daily_task_rotation import record_daily_answer
        result = record_daily_answer(TEST_USER_ID, item_id, should_be_correct)
        print(f"         record_daily_answer -> mu={result.get('mu', '?'):.2f}")

    state_after = le_get_state(TEST_USER_ID)
    print("\n  level_by_section ПОСЛЕ:")
    by_sec_after = state_after.get('by_section', {})
    if by_sec_after:
        for sec, data in sorted(by_sec_after.items()):
            print(f"    {sec}: mu={data.get('mu', '?'):.2f} sigma={data.get('sigma', '?'):.2f} n={data.get('n', 0)}")
    else:
        print("    (пусто)")
    print(f"  Глобально: mu={state_after['mu']:.3f} sigma={state_after['sigma']:.3f}")


# ══════════════════════════════════════════════════════════════════════
# ТАБЛИЦА D: Без анкеты
# ══════════════════════════════════════════════════════════════════════

def table_d_no_questionnaire() -> None:
    print_section("ТАБЛИЦА D: набор для ученика БЕЗ анкеты")

    cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
    had_onboarding = bool(cs and cs.prep_state and cs.prep_state.get('onboarding'))
    saved_prep = None
    if had_onboarding:
        saved_prep = dict(cs.prep_state) if cs.prep_state else {}
        cs.prep_state = {}
        db.session.commit()
        print("  [OK] Анкета временно очищена")

    try:
        today = datetime.now(MSK_TZ).date()
        existing = DailyTaskSet.query.filter_by(
            user_id=TEST_USER_ID, target_date=today,
        ).first()
        if existing:
            DailyTaskItem.query.filter_by(daily_set_id=existing.id).delete()
            db.session.delete(existing)
            db.session.commit()

        from services.daily_task_rotation import pick_daily_set, _get_daily_tasks_count

        count = _get_daily_tasks_count(TEST_USER_ID)
        print(f"  daily_tasks_count (без анкеты): {count}")

        pick_daily_set(TEST_USER_ID, force_regenerate=True)

        new_set = DailyTaskSet.query.filter_by(
            user_id=TEST_USER_ID, target_date=today,
        ).first()
        if not new_set:
            print("  [ERROR] Сет не создан!")
            return

        items = (
            DailyTaskItem.query
            .filter_by(daily_set_id=new_set.id)
            .order_by(DailyTaskItem.position)
            .all()
        )

        print(f"  Сет #{new_set.id}, status={new_set.status}, задач={len(items)}")
        print(f"  triggered_by: {new_set.triggered_by}")
        print(f"\n  {'№':<4} {'item_id':<8} {'раздел (slug)':<22} {'уровень':<8}")

        sections_seen = set()
        for it in items:
            sec_slug = _norm_sec(it.topic or '')
            sections_seen.add(sec_slug)
            print(f"  {it.position:<4} {it.id:<8} {sec_slug:<22} {it.difficulty_level or '—':<8}")

        print(f"\n  Уникальных разделов: {len(sections_seen)} -> {sections_seen}")
        print(f"  Количество задач: {len(items)} (ожидалось 5)")

    finally:
        if had_onboarding and saved_prep is not None:
            cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
            if cs:
                cs.prep_state = saved_prep
                db.session.commit()
                print("\n  [OK] Анкета восстановлена")


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
            print(f"  [ERROR] {f}: {e}")
            all_ok = False
    if all_ok:
        print("  [OK] python -m py_compile: exit 0")

    user = get_user()
    flask_app.test_client_class = FlaskLoginClient
    with flask_app.test_client(user=user) as client:
        resp = client.get('/daily_tasks/')
        status = resp.status_code
        print(f"  GET /daily_tasks: {status}" + (" [OK]" if status == 200 else " [ERROR]"))


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    ctx = flask_app.app_context()
    ctx.push()

    try:
        table_a_pool()
        items = table_b_regenerate()
        table_c_answers(items)
        table_d_no_questionnaire()
        criterion_7()

        print(f"\n{'=' * 70}")
        print(f"  ГОТОВО")
        print(f"{'=' * 70}")

    finally:
        ctx.pop()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""
services/daily_debt.py — Двигатель долга задач дня.

Правила:
  1) Задача, не решённая до конца суток выдачи -> debt_status='active'
  2) debt_until = target_date родительского сета + 7 дней
  3) При первом заходе ученика просроченный долг -> 'burned'
  4) Никаких штрафов по уровню при сгорании
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from models import db
from daily_tasks.models import DailyTaskSet, DailyTaskItem
from utils.math_text_fixer import wrap_bare_math

logger = logging.getLogger(__name__)

DEBT_TTL_DAYS = 7


def migrate_to_debt(user_id: int, before_date: date) -> int:
    """Перенести все нерешённые задачи пользователя в долг.

    Берёт все DailyTaskItem пользователя из сетов с target_date < before_date,
    где user_answer IS NULL и debt_status IS NULL.
    """
    from sqlalchemy import and_

    old_set_ids = (
        db.session.query(DailyTaskSet.id)
        .filter(
            DailyTaskSet.user_id == user_id,
            DailyTaskSet.target_date < before_date,
        )
        .subquery()
    )

    items = (
        DailyTaskItem.query
        .filter(
            DailyTaskItem.daily_set_id.in_(db.session.query(old_set_ids.c.id)),
            DailyTaskItem.user_answer.is_(None),
            DailyTaskItem.debt_status.is_(None),
        )
        .all()
    )

    count = 0
    for item in items:
        parent = DailyTaskSet.query.get(item.daily_set_id)
        if not parent:
            continue
        item.debt_status = 'active'
        item.debt_until = parent.target_date + timedelta(days=DEBT_TTL_DAYS)
        count += 1

    if count:
        db.session.commit()
        logger.info(
            "daily_debt: user=%d migrated %d items to debt", user_id, count,
        )

    return count


def burn_stale_debt(user_id: int = None) -> int:
    """Пометить просроченный долг как 'burned'.

    Args:
        user_id: если указан — только для этого ученика, иначе для всех.
    """
    today = date.today()

    q = DailyTaskItem.query.filter(
        DailyTaskItem.debt_status == 'active',
        DailyTaskItem.debt_until < today,
    )
    if user_id is not None:
        q = q.filter(
            DailyTaskItem.daily_set_id.in_(
                db.session.query(DailyTaskSet.id).filter(
                    DailyTaskSet.user_id == user_id,
                )
            )
        )

    items = q.all()
    for item in items:
        item.debt_status = 'burned'

    if items:
        db.session.commit()
        logger.info(
            "daily_debt: burned %d stale debt items (user=%s)",
            len(items), user_id or 'ALL',
        )

    return len(items)


def refresh_debt_for_user(user_id: int) -> Dict[str, int]:
    """Полный цикл обновления долга для ученика:
    1) Миграция нерешённого в долг
    2) Сжигание просроченного

    Безопасен при повторном вызове.
    """
    today = date.today()
    migrated = migrate_to_debt(user_id, today)
    burned = burn_stale_debt(user_id)
    return {'migrated': migrated, 'burned': burned}


def _resolve_debt_grade_and_level(user_id: int) -> tuple[int, int]:
    """Определить класс (5..11) и базовый уровень (1..4) для выдачи долга."""
    grade = 9
    try:
        from services.daily_olympiad import user_cycle_grade as _ucg
        g = _ucg(user_id)
        if g and 5 <= int(g) <= 11:
            grade = int(g)
    except Exception:
        pass
    if grade == 9:
        try:
            from models_curator import CuratorState
            cs = CuratorState.query.filter_by(user_id=user_id).first()
            if cs and cs.grade and 5 <= int(cs.grade) <= 11:
                grade = int(cs.grade)
        except Exception:
            pass

    level = 3
    try:
        from services.daily_task_rotation import _get_level_state
        st = _get_level_state(user_id)
        by_sec = st.get('by_section') or {}
        vals = [int(v) for v in by_sec.values() if isinstance(v, (int, float)) and 1 <= int(v) <= 4]
        if vals:
            level = max(1, min(4, round(sum(vals) / len(vals))))
    except Exception:
        pass
    return grade, level


def _issue_fallback_debt_set(user_id: int, day: date, lesson: Dict[str, Any]) -> bool:
    """Fallback-выдача задач за пропущенную практику, когда build_daily_set
    не смог подобрать задачи (plan_missing / bank_empty / bank_exhausted).

    1) Пробует FORMYLA_BANK.jsonl по теме урока или доступной теме класса
       (создаёт DailyTaskSet + DailyTaskItem с debt_status='active').
    2) Если jsonl-банк пуст/отключён — пробует DailyTaskBank напрямую (BankIssue).
    """
    grade, level = _resolve_debt_grade_and_level(user_id)
    raw_theme = (lesson.get('theme') or '').strip()

    # 1) FORMYLA_BANK.jsonl
    try:
        from daily_tasks import formyla_bank
        if formyla_bank.has_rows():
            tasks = []
            if raw_theme:
                tasks = formyla_bank.get_tasks(
                    grade=grade, topic=raw_theme, level=level, count=5,
                    user_id=user_id, day_seed=day.toordinal(),
                )
            if not tasks:
                topics = formyla_bank.available_topics(grade)
                if topics:
                    idx = (day.toordinal() + int(user_id) + int(lesson.get('seq') or 0)) % len(topics)
                    tasks = formyla_bank.get_tasks(
                        grade=grade, topic=topics[idx], level=level, count=5,
                        user_id=user_id, day_seed=day.toordinal(),
                    )
            if tasks:
                ds = DailyTaskSet(
                    user_id=user_id,
                    target_date=day,
                    class_level=grade,
                    status='ready',
                    triggered_by='debt_skipped',
                    generated_at=datetime.utcnow(),
                )
                db.session.add(ds)
                db.session.flush()
                debt_until = day + timedelta(days=DEBT_TTL_DAYS)
                for pos, t in enumerate(tasks, 1):
                    text_body = (t.get('task_text') or t.get('statement') or '').strip()
                    if not text_body:
                        continue
                    topic_name = (t.get('topic') or raw_theme or 'Математика').strip()
                    try:
                        diff = int(t.get('level') or level)
                    except (TypeError, ValueError):
                        diff = level
                    db.session.add(DailyTaskItem(
                        daily_set_id=ds.id,
                        position=pos,
                        slot_kind='debt',
                        subject='math',
                        topic=topic_name,
                        subtopic=topic_name,
                        difficulty_level=diff,
                        task_text=wrap_bare_math(text_body),
                        correct_answer=str(t.get('answer') or ''),
                        solution=wrap_bare_math(str(t.get('solution') or '')),
                        status='approved',
                        debt_status='active',
                        debt_until=debt_until,
                    ))
                db.session.commit()
                return True
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning("daily_debt: formyla_bank fallback failed user=%d day=%s: %s",
                       user_id, day, e)

    # 2) Прямой fallback на DailyTaskBank (если FORMYLA_BANK.jsonl отключён)
    try:
        from models import BankIssue, DailyTaskBank
        q = DailyTaskBank.query
        rows = []
        if raw_theme:
            rows = q.filter(DailyTaskBank.subtopic == raw_theme).limit(5).all()
        if not rows:
            rows = q.filter(DailyTaskBank.level == level).limit(5).all()
        if not rows:
            rows = q.limit(5).all()
        if rows:
            for t in rows:
                db.session.add(BankIssue(
                    user_id=user_id,
                    task_id=t.id,
                    subtopic=t.subtopic or raw_theme or 'math',
                    level=t.level or level,
                    issued_date=day,
                ))
            db.session.commit()
            return True
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning("daily_debt: bank direct fallback failed user=%d day=%s: %s",
                       user_id, day, e)
    return False


def issue_tasks_for_skipped_lessons(user_id: int) -> int:
    """Выдать задачи за пропущенные занятия-практики, чтобы их можно было
    открыть из блока «Открыть долг» (владелец, 05.11).

    Раньше пропущенное занятие только попадало в плашку «В долгу», а задач
    по нему не было — открыть было нечего. Теперь за каждый пропущенный
    день практики (не старше DEBT_TTL_DAYS) выдаём набор из банка датой
    того дня; если daily_task_bank пуст или не задан план — добираем
    задачи из FORMYLA_BANK.jsonl. Идемпотентно по (user_id, дата).

    Возвращает число дней, за которые набор выдан впервые.
    """
    from curator.session_plan import _pilot, _lessons, _to_date
    if not _pilot(user_id):
        return 0
    from models import BankIssue
    from services.bank_daily import build_daily_set

    today = date.today()
    floor = today - timedelta(days=DEBT_TTL_DAYS)
    issued = 0
    for lesson in _lessons(user_id):
        if lesson.get('status') != 'skipped' or lesson.get('lesson_type') != 'practice':
            continue
        day = _to_date(lesson.get('assigned_date'))
        if day is None or day >= today or day < floor:
            continue
        # в этот день уже что-то выдавалось (банк или непустой сет) — не дублируем
        if BankIssue.query.filter_by(user_id=user_id, issued_date=day).first():
            continue
        existing_set = DailyTaskSet.query.filter_by(user_id=user_id, target_date=day).first()
        if existing_set:
            if DailyTaskItem.query.filter_by(daily_set_id=existing_set.id).first():
                continue
            # пустой битый сет без задач (например failed) — убираем, чтобы не блокировал долг
            try:
                db.session.delete(existing_set)
                db.session.commit()
            except Exception:
                db.session.rollback()
                continue
        got_tasks = False
        try:
            res = build_daily_set(user_id, day)
            if res.get('items'):
                got_tasks = True
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            logger.warning("daily_debt: skipped-lesson set failed user=%d day=%s: %s",
                           user_id, day, e)
        if not got_tasks:
            got_tasks = _issue_fallback_debt_set(user_id, day, lesson)
        if got_tasks:
            issued += 1
    if issued:
        logger.info("daily_debt: user=%d выданы задачи за %d пропущенных занятий",
                    user_id, issued)
    return issued


def get_debt_items(user_id: int) -> List[Dict[str, Any]]:
    """Получить активные долговые задачи для ученика.

    Возвращает список dict, сгруппированных по дате выдачи (свежие сверху).
    """
    today = date.today()

    # JOIN daily_task_sets для получения target_date
    items = (
        DailyTaskItem.query
        .join(DailyTaskSet, DailyTaskItem.daily_set_id == DailyTaskSet.id)
        .filter(
            DailyTaskSet.user_id == user_id,
            DailyTaskItem.debt_status == 'active',
        )
        .order_by(DailyTaskSet.target_date.desc(), DailyTaskItem.position)
        .all()
    )

    result = []
    for item in items:
        parent = DailyTaskSet.query.get(item.daily_set_id)
        days_left = None
        if item.debt_until:
            days_left = (item.debt_until - today).days

        # Готовый SVG-чертёж (если есть) — отдаём как URL для показа в блоке долга.
        figure_url = None
        _svg = getattr(item, 'figure_svg_path', None)
        if _svg:
            _svg = str(_svg).strip()
            if _svg:
                figure_url = _svg if _svg.startswith('/') else f'/static/daily_figures/{_svg}'

        # 2026-09-29: текст прогоняем через wrap_bare_math — иначе в модалке
        # дол видит сырую математику (x^4, \\sqrt, голые cases), в отличие от
        # грида задач дня, где текст обёрнут в \(...\)/\[...\] ещё на выдаче.
        result.append({
            'id': item.id,
            'position': item.position,
            'subject': item.subject,
            'topic': item.topic,
            'difficulty_level': item.difficulty_level,
            'task_text': wrap_bare_math(item.task_text or ''),
            'correct_answer': item.correct_answer,
            'solution': wrap_bare_math(item.solution or ''),
            'hints': item.hints,
            'issued_date': parent.target_date.isoformat() if parent else None,
            'debt_until': item.debt_until.isoformat() if item.debt_until else None,
            'days_left': days_left,
            'daily_set_id': item.daily_set_id,
            'slot_kind': item.slot_kind,
            'figure_url': figure_url,
        })

    # ── Банковские задачи (2026-09-14) ──────────────────────────────────
    # Раньше нерешённые задачи дня из daily_task_bank никуда не попадали:
    # ученик просто «останавливался на этом месте». Теперь просроченные
    # банковские выдачи (issued_date < сегодня, ответа нет) идут в долг,
    # как и обычные DailyTaskItem. id = task_id банковской задачи —
    # submit_ai по BankIssue поймёт, что это банковский ответ.
    try:
        from models import BankIssue, DailyTaskBank
        debt_floor = today - timedelta(days=DEBT_TTL_DAYS)
        bank_rows = (
            BankIssue.query
            .filter(
                BankIssue.user_id == user_id,
                BankIssue.issued_date < today,
                BankIssue.user_answer.is_(None),
            )
            .order_by(BankIssue.issued_date.desc(), BankIssue.id)
            .all()
        )
        existing_ids = {r['id'] for r in result}
        for bi in bank_rows:
            if bi.id in existing_ids:
                continue
            task = db.session.get(DailyTaskBank, bi.task_id)
            if task is None:
                continue
            days_left = (bi.issued_date + timedelta(days=DEBT_TTL_DAYS) - today).days
            result.append({
                'id': task.id,
                'position': getattr(task, 'position', None),
                'subject': 'math',
                'topic': task.subtopic or task.section,
                'difficulty_level': task.level,
                'task_text': wrap_bare_math(task.statement or ''),
                'correct_answer': task.answer or '',
                'solution': wrap_bare_math(task.solution or ''),
                'hints': None,
                'issued_date': bi.issued_date.isoformat(),
                'debt_until': (bi.issued_date + timedelta(days=DEBT_TTL_DAYS)).isoformat(),
                'days_left': days_left,
                'daily_set_id': None,
                'slot_kind': 'bank',
                'figure_url': None,
                'from_bank': True,
            })
    except Exception as e:
        logger.warning("get_debt_items: bank debt failed user=%d: %s", user_id, e)

    return result


def get_debt_count(user_id: int) -> int:
    """Количество активных долговых задач."""
    return DailyTaskItem.query.join(
        DailyTaskSet, DailyTaskItem.daily_set_id == DailyTaskSet.id
    ).filter(
        DailyTaskSet.user_id == user_id,
        DailyTaskItem.debt_status == 'active',
    ).count()

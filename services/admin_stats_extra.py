# -*- coding: utf-8 -*-
"""
services/admin_stats_extra.py — дополнительные блоки админ-статистики /admin/users.

ADMIN_STATS_EXTRA_V1 (25.09.2026), по запросу владельца («всё сразу»):
  1. Воронка: регистрация → анкета → первая задача → задачи дня → активность.
  2. Удержание D1/D7/D30 (доля пользователей, активных спустя N дней после
     регистрации; когорта — зарегистрированные не раньше N дней назад).
  3. Слабые темы: худший процент верных ответов (задачи дня + банк).
  4. Проблемные задачи: чаще всего решаемые неверно.
  5. По типам задач: где решают и с каким успехом (+ среднее время).
  6. Серии (стрики) по длине.
  7. AI-тьютор: сообщения, пользователи, топ агентов + стоимость генерации
     задач дня.
  8. Роли: сколько учителей/родителей, привязки, активность по ролям.

Каждый блок независим и падает тихо (пустой результат), чтобы страница
открывалась даже при отсутствии части таблиц.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _parse_dt(v):
    """SQLite возвращает даты строкой из raw-SQL — парсим defensively."""
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                return datetime.strptime(v, fmt)
            except ValueError:
                continue
    return None


def _pct(part, whole):
    return round(part * 100.0 / whole, 1) if whole else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 1-2. Воронка и удержание
# ──────────────────────────────────────────────────────────────────────────────

def funnel_stats() -> dict:
    """Воронка регистрации + удержание D1/D7/D30."""
    out = {'steps': [], 'retention': {}}
    try:
        from models import db, User
        from models_curator import CuratorState
        from sqlalchemy import text

        users = User.query.filter(User.is_guest.is_(False)).all()
        total = len(users)

        # анкета пройдена: onboarded_at или CuratorState.intake.completed
        intake_ids = {u.id for u in users if getattr(u, 'onboarded_at', None)}
        try:
            for cs in CuratorState.query.all():
                raw = getattr(cs, 'prep_state', None)
                if isinstance(raw, str):
                    try:
                        import json as _json
                        raw = _json.loads(raw)
                    except Exception:
                        raw = {}
                ps = raw if isinstance(raw, dict) else {}
                intake = ps.get('intake') if isinstance(ps.get('intake'), dict) else {}
                if intake.get('completed') and not intake.get('skipped'):
                    intake_ids.add(cs.user_id)
        except Exception as e:
            logger.warning('funnel_stats: curator_state skipped: %r', e)

        # решили хоть одну задачу (факты из solved_stats)
        try:
            from services.solved_stats import solved_counts_by_user
            solved_ids = set(solved_counts_by_user().keys())
        except Exception as e:
            logger.warning('funnel_stats: solved_counts skipped: %r', e)
            solved_ids = set()

        # пользовались задачами дня
        try:
            from daily_tasks.models import DailyTaskSet
            daily_ids = {r[0] for r in db.session.query(DailyTaskSet.user_id).distinct().all()}
        except Exception as e:
            logger.warning('funnel_stats: daily_task_sets skipped: %r', e)
            daily_ids = set()

        # активны за 7 дней (site_events)
        week_ago = datetime.utcnow() - timedelta(days=7)
        try:
            rows = db.session.execute(text(
                'SELECT DISTINCT user_id FROM site_events WHERE ts >= :since'
            ), {'since': week_ago}).fetchall()
            active7_ids = {r[0] for r in rows}
        except Exception as e:
            logger.warning('funnel_stats: site_events skipped: %r', e)
            active7_ids = set()

        steps = [
            ('Зарегистрировано', total),
            ('Прошли анкету', len(intake_ids)),
            ('Решили хоть одну задачу', len(solved_ids & {u.id for u in users})),
            ('Пользовались задачами дня', len(daily_ids & {u.id for u in users})),
            ('Активны за последние 7 дней', len(active7_ids & {u.id for u in users})),
        ]
        out['steps'] = [
            {'name': name, 'count': cnt, 'pct': _pct(cnt, total)}
            for name, cnt in steps
        ]

        # ── удержание D1/D7/D30 ──
        try:
            rows = db.session.execute(text(
                'SELECT user_id, MAX(ts) FROM site_events GROUP BY user_id'
            )).fetchall()
            last_seen = {r[0]: _parse_dt(r[1]) for r in rows if r[0] is not None}
        except Exception as e:
            logger.warning('funnel_stats: retention skipped: %r', e)
            last_seen = {}

        now = datetime.utcnow()
        for days, key in ((1, 'd1'), (7, 'd7'), (30, 'd30')):
            cohort = 0
            retained = 0
            for u in users:
                created = getattr(u, 'created_at', None)
                if created is None or (now - created) < timedelta(days=days):
                    continue
                cohort += 1
                seen = last_seen.get(u.id)
                if seen is not None and seen >= created + timedelta(days=days):
                    retained += 1
            out['retention'][key] = {
                'cohort': cohort, 'retained': retained,
                'pct': _pct(retained, cohort),
            }
    except Exception as e:
        logger.warning('funnel_stats failed: %r', e)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 3. Слабые темы
# ──────────────────────────────────────────────────────────────────────────────

def weak_themes_stats(min_answers: int = 5, limit: int = 12) -> list:
    """Топ тем с худшим % верных (задачи дня + банк)."""
    agg = {}  # (источник, тема) -> {answered, correct}

    def _add(source, theme, answered, correct):
        key = (source, theme or '—')
        e = agg.setdefault(key, {'answered': 0, 'correct': 0})
        e['answered'] += int(answered or 0)
        e['correct'] += int(correct or 0)

    try:
        from models import db
        from daily_tasks.models import DailyTaskItem
        from sqlalchemy import func
        rows = (db.session.query(
                    DailyTaskItem.topic, DailyTaskItem.subject,
                    func.count(DailyTaskItem.id),
                    func.sum(db.case((DailyTaskItem.is_correct == True, 1), else_=0)),
                )
                .filter(DailyTaskItem.user_answer.isnot(None))
                .group_by(DailyTaskItem.subject, DailyTaskItem.topic)
                .all())
        for topic, subject, answered, correct in rows:
            _add('Задачи дня', topic or subject, answered, correct)
    except Exception as e:
        logger.warning('weak_themes_stats: daily skipped: %r', e)

    try:
        from models import db, BankIssue
        from sqlalchemy import func
        rows = (db.session.query(
                    BankIssue.subtopic,
                    func.count(BankIssue.id),
                    func.sum(db.case((BankIssue.is_correct == True, 1), else_=0)),
                )
                .filter(BankIssue.user_answer.isnot(None))
                .group_by(BankIssue.subtopic)
                .all())
        for subtopic, answered, correct in rows:
            _add('Банк', subtopic, answered, correct)
    except Exception as e:
        logger.warning('weak_themes_stats: bank skipped: %r', e)

    out = []
    for (source, theme), e in agg.items():
        if e['answered'] < min_answers:
            continue
        out.append({
            'source': source,
            'theme': (theme[:70] + '…') if len(theme) > 70 else theme,
            'answered': e['answered'],
            'correct': e['correct'],
            'pct': _pct(e['correct'], e['answered']),
        })
    out.sort(key=lambda x: x['pct'])
    return out[:limit]


# ──────────────────────────────────────────────────────────────────────────────
# 4. Проблемные задачи
# ──────────────────────────────────────────────────────────────────────────────

def problem_tasks_stats(min_wrong: int = 3, limit: int = 10) -> list:
    """Задачи, которые чаще всего решают неверно (по тексту условия)."""
    out = []
    try:
        from models import db
        from daily_tasks.models import DailyTaskItem
        from sqlalchemy import func

        prefix = func.substr(DailyTaskItem.task_text, 1, 90)
        rows = (db.session.query(
                    prefix,
                    func.count(DailyTaskItem.id),
                    func.sum(db.case((DailyTaskItem.is_correct == True, 1), else_=0)),
                )
                .filter(DailyTaskItem.user_answer.isnot(None))
                .group_by(prefix)
                .having(func.sum(db.case((DailyTaskItem.is_correct == False, 1), else_=0)) >= min_wrong)
                .all())
        for text, answered, correct in rows:
            answered = int(answered or 0)
            correct = int(correct or 0)
            out.append({
                'text': (text[:90] + '…') if len(text or '') > 90 else (text or '—'),
                'answered': answered,
                'wrong': answered - correct,
                'pct': _pct(correct, answered),
            })
        out.sort(key=lambda x: x['wrong'], reverse=True)
    except Exception as e:
        logger.warning('problem_tasks_stats failed: %r', e)
    return out[:limit]


# ──────────────────────────────────────────────────────────────────────────────
# 5. По типам задач
# ──────────────────────────────────────────────────────────────────────────────

def task_types_stats() -> list:
    """Где решают и с каким успехом: отвечено / верно / % / среднее время."""

    def _src(name):
        return {'name': name, 'answered': 0, 'correct': 0, 'avg_sec': None}

    daily = _src('Задачи дня')
    try:
        from models import db
        from daily_tasks.models import DailyTaskItem
        from sqlalchemy import func
        r = (db.session.query(func.count(DailyTaskItem.id),
                              func.sum(db.case((DailyTaskItem.is_correct == True, 1), else_=0)),
                              func.avg(DailyTaskItem.time_spent_seconds))
             .filter(DailyTaskItem.user_answer.isnot(None)).one())
        daily['answered'], daily['correct'] = int(r[0] or 0), int(r[1] or 0)
        daily['avg_sec'] = round(float(r[2]), 1) if r[2] is not None else None
    except Exception as e:
        logger.warning('task_types_stats: daily skipped: %r', e)

    bank = _src('Банк задач')
    try:
        from models import db, BankIssue
        from sqlalchemy import func
        r = (db.session.query(func.count(BankIssue.id),
                              func.sum(db.case((BankIssue.is_correct == True, 1), else_=0)),
                              func.avg(BankIssue.time_spent_seconds))
             .filter(BankIssue.user_answer.isnot(None)).one())
        bank['answered'], bank['correct'] = int(r[0] or 0), int(r[1] or 0)
        bank['avg_sec'] = round(float(r[2]), 1) if r[2] is not None else None
    except Exception as e:
        logger.warning('task_types_stats: bank skipped: %r', e)

    olymp = _src('Олимпиады')
    try:
        from models_olympiad import TaskAttempt
        total = TaskAttempt.query.count()
        solved = TaskAttempt.query.filter(TaskAttempt.status == 'solved').count()
        olymp['answered'], olymp['correct'] = total, solved
    except Exception as e:
        logger.warning('task_types_stats: olympiad skipped: %r', e)

    insights = _src('Отработка неточностей')
    try:
        from models_insights import InsightPracticeTask
        total = InsightPracticeTask.query.filter(
            InsightPracticeTask.user_answer.isnot(None)).count()
        correct = InsightPracticeTask.query.filter(
            InsightPracticeTask.user_answer.isnot(None),
            InsightPracticeTask.is_correct.is_(True)).count()
        insights['answered'], insights['correct'] = total, correct
    except Exception as e:
        logger.warning('task_types_stats: insights skipped: %r', e)

    practice = _src('Тренажёры (/section)')
    try:
        from models import TestResult
        total = TestResult.query.filter(TestResult.test_type == 'practice').count()
        correct = TestResult.query.filter(TestResult.test_type == 'practice',
                                          TestResult.is_correct.is_(True)).count()
        practice['answered'], practice['correct'] = total, correct
    except Exception as e:
        logger.warning('task_types_stats: practice skipped: %r', e)

    rows = [daily, bank, olymp, insights, practice]
    for r in rows:
        r['pct'] = _pct(r['correct'], r['answered'])
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# 6. Серии (стрики)
# ──────────────────────────────────────────────────────────────────────────────

def streak_stats() -> dict:
    """Распределение пользователей по длине текущей серии дней."""
    buckets = {'0': 0, '1–2': 0, '3–6': 0, '7–13': 0, '14–29': 0, '30+': 0}
    out = {'buckets': buckets, 'records': 0, 'avg': 0, 'max_ever': 0}
    try:
        from models import StreakRecord
        recs = StreakRecord.query.all()
        out['records'] = len(recs)
        if recs:
            cur = [r.current_streak or 0 for r in recs]
            out['avg'] = round(sum(cur) / len(cur), 1)
            out['max_ever'] = max((r.max_streak or 0 for r in recs), default=0)
            for v in cur:
                if v <= 0:
                    buckets['0'] += 1
                elif v <= 2:
                    buckets['1–2'] += 1
                elif v <= 6:
                    buckets['3–6'] += 1
                elif v <= 13:
                    buckets['7–13'] += 1
                elif v <= 29:
                    buckets['14–29'] += 1
                else:
                    buckets['30+'] += 1
    except Exception as e:
        logger.warning('streak_stats failed: %r', e)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 7. AI-тьютор и генерация
# ──────────────────────────────────────────────────────────────────────────────

AGENT_NAMES = {
    'general': 'Общий',
    'algebra': 'Алгебра',
    'geometry': 'Геометрия',
    'number_theory': 'Теория чисел',
    'combinatorics': 'Комбинаторика',
    'movement': 'Движение',
    'logic': 'Логика',
    'mentor': 'Наставник',
}


def ai_tutor_stats() -> dict:
    out = {
        'assistant_total': 0,
        'assistant_week': 0,
        'users_week': 0,
        'top_agents': [],
    }
    try:
        from models import db, ChatMessage
        from sqlalchemy import func
        week_ago = datetime.utcnow() - timedelta(days=7)
        month_ago = datetime.utcnow() - timedelta(days=30)

        out['assistant_total'] = ChatMessage.query.filter(
            ChatMessage.role == 'assistant').count()
        out['assistant_week'] = ChatMessage.query.filter(
            ChatMessage.role == 'assistant',
            ChatMessage.timestamp >= week_ago).count()
        out['users_week'] = db.session.query(func.count(func.distinct(ChatMessage.user_id))).filter(
            ChatMessage.timestamp >= week_ago).scalar() or 0

        rows = (db.session.query(ChatMessage.agent_type, func.count(ChatMessage.id))
                .filter(ChatMessage.timestamp >= month_ago)
                .group_by(ChatMessage.agent_type)
                .order_by(func.count(ChatMessage.id).desc())
                .limit(5).all())
        out['top_agents'] = [
            {'name': AGENT_NAMES.get(a or 'general', a or '—'), 'count': int(c or 0)}
            for a, c in rows
        ]
    except Exception as e:
        logger.warning('ai_tutor_stats: chat skipped: %r', e)

    return out


# ──────────────────────────────────────────────────────────────────────────────
# 8. Роли: учителя и родители
# ──────────────────────────────────────────────────────────────────────────────

def roles_stats() -> dict:
    out = {
        'students': 0, 'teachers': 0, 'parents': 0,
        'parents_bound': 0,
        'groups': 0, 'groups_with_members': 0, 'group_members': 0,
        'active_by_role': {},
    }
    try:
        from models import db, User
        from sqlalchemy import text

        users = User.query.filter(User.is_guest.is_(False)).all()
        out['students'] = sum(1 for u in users if (u.role or 'student') == 'student')
        out['teachers'] = sum(1 for u in users if u.role == 'teacher')
        out['parents'] = sum(1 for u in users if u.role == 'parent')
        out['parents_bound'] = sum(1 for u in users
                                   if u.role == 'parent' and getattr(u, 'child_email', None))

        try:
            from models import T10Group, T10GroupMember
            out['groups'] = T10Group.query.count()
            out['group_members'] = T10GroupMember.query.count()
            from sqlalchemy import func
            out['groups_with_members'] = (db.session.query(
                func.count(func.distinct(T10GroupMember.group_id))).scalar() or 0)
        except Exception as e:
            logger.warning('roles_stats: groups skipped: %r', e)

        # активность за 7 дней по ролям
        week_ago = datetime.utcnow() - timedelta(days=7)
        try:
            rows = db.session.execute(text(
                'SELECT DISTINCT user_id FROM site_events WHERE ts >= :since'
            ), {'since': week_ago}).fetchall()
            active_ids = {r[0] for r in rows}
            role_of = {u.id: (u.role or 'student') for u in users}
            counts = {}
            for uid in active_ids:
                r = role_of.get(uid)
                if r:
                    counts[r] = counts.get(r, 0) + 1
            out['active_by_role'] = counts
        except Exception as e:
            logger.warning('roles_stats: activity skipped: %r', e)
    except Exception as e:
        logger.warning('roles_stats failed: %r', e)
    return out

# -*- coding: utf-8 -*-
"""
curator/session_plan.py — SESSION_PLAN_V1 (26.10.2026): план занятий 1-из-6.

Ротация занятий в блоке из шести (регламент тарифов Premium):
  занятие 1 — ИЗУЧЕНИЕ МЕТОДА (70% разбор метода + 3 задачи по методу)
  занятия 2-5 — ПРАКТИКА (задачи дня по теме, которую назначил куратор)
  занятие 6 — РЕАЛЬНЫЙ ПРОБНИК (полный вариант прошлых лет выбранной
              олимпиады, длительность по регламенту)

Для «Работяги» (6 занятий/нед) блок = 1 неделя: метод + 4 практики +
пробник каждую неделю. Для «Спокойного» (3 занятия/нед) блок = 2 недели.

Правила (см. ревью 26.10.2026):
  * прогресс считается только по ЗАВЕРШЁННЫМ занятиям — открытие страницы,
    сообщения в чате и пропущенные дни ничего не двигают;
  * завершение занятия — серверная транзиция: практика — отвечены все
    задачи сета дня; метод — отвечены все задачи метод-сета; пробник —
    сдан пробник (stage_submit). Повторный вызов не двигает прогресс;
  * расписание доступно только пилотным аккаунтам (victor, lavrik);
    остальным всё остаётся как было (функции возвращают inactive);
  * тема практики — та, что назначает куратор (ротация цикла
    monthly_cycle), привязанная к выбранной олимпиаде пользователя.
"""
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

BLOCK_SIZE = 6
TABLE_NAME = 'curator_lessons'

LESSON_LABELS = {
    'method': 'изучение метода',
    'practice': 'практика',
    'probnik': 'пробник',
}


def ensure_tables() -> None:
    db.session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            lesson_type VARCHAR(16) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'assigned',
            theme VARCHAR(128),
            method_code VARCHAR(64),
            method_name VARCHAR(256),
            probnik_code VARCHAR(64),
            probnik_title VARCHAR(256),
            olympiad_slug VARCHAR(64),
            assigned_date DATE,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """))
    db.session.commit()


def _pilot(user_id: int) -> bool:
    try:
        from services.pilot import is_pilot_user
        return bool(is_pilot_user(int(user_id)))
    except Exception:
        return False


# ── Выбор олимпиады и класса пользователя ────────────────────────────────

def _user_olympiad(user_id: int) -> Optional[str]:
    """Slug олимпиады из активного prep-плана (каноническое хранилище выбора)."""
    try:
        row = db.session.execute(text(
            "SELECT op.slug FROM prep_plans pp "
            "JOIN olympiad_prep op ON op.id = pp.olympiad_id "
            "WHERE pp.user_id = :uid AND pp.status = 'active' "
            "ORDER BY pp.id DESC LIMIT 1"
        ), {'uid': user_id}).fetchone()
        return row[0] if row else None
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] olympiad lookup failed: %r', e)
        return None


def _user_grade(user_id: int) -> Optional[int]:
    try:
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs and cs.grade:
            return int(cs.grade)
    except Exception:
        pass
    try:
        from models import User
        u = User.query.get(user_id)
        if u:
            g = getattr(u, 'preferred_grade', None) or getattr(u, 'class_level', None)
            if g:
                return int(g)
    except Exception:
        pass
    return None


def _theme_for_user(user_id: int) -> Optional[str]:
    """Тема, назначенная куратором (ротация monthly_cycle)."""
    try:
        from curator.monthly_cycle import get_today_info
        return get_today_info(user_id).get('subtopic') or None
    except Exception:
        return None


# ── Подбор метода и пробника ─────────────────────────────────────────────

def _pick_method(user_id: int) -> Dict[str, str]:
    """Метод недели из method_week.catalog (тот же, что в плане куратора)."""
    try:
        from method_week.catalog import method_for_week
        m = method_for_week(user_id)
        if m:
            return {
                'code': m.get('method_code') or '',
                'name': m.get('method_name') or m.get('name_ru') or '',
            }
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] method pick failed: %r', e)
    return {'code': '', 'name': ''}


_OLYMP_COMPETITION = {
    'vsosh': 'ВсОШ',
    'euler': 'Европейская олимпиада «Эйлер»',
    'lomonosov': 'Ломоносов',
}


def _pick_probnik(user_id: int, olympiad_slug: Optional[str],
                  used_codes: set) -> Optional[Dict[str, str]]:
    """Реальный пробник: опубликованный, под олимпиаду и класс, не пройденный.

    Ищет точное совпадение по олимпиаде и классу; если нет — пробник
    подходящего класса; если и их нет — любой опубликованный (с пометкой).
    """
    grade = _user_grade(user_id)
    competition = _OLYMP_COMPETITION.get(olympiad_slug or '', '') if olympiad_slug else ''
    try:
        rows = db.session.execute(text(
            "SELECT code, title, competition, grade FROM olympiad_probniks "
            "WHERE is_published = TRUE ORDER BY sort_order NULLS LAST, id"
        )).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] probnik query failed: %r', e)
        return None

    def match(r) -> int:
        score = 0
        if competition and (competition.lower() in str(r[2] or '').lower()):
            score += 4
        if grade and str(r[3]) == str(grade):
            score += 2
        return score

    candidates = [r for r in rows if r[0] not in used_codes]
    if not candidates:
        candidates = list(rows)  # все пройдены — разрешаем повторный прогон
    if not candidates:
        return None
    best = sorted(candidates, key=match, reverse=True)[0]
    return {'code': best[0], 'title': best[1] or best[0]}


# ── Ротация и запись занятий ──────────────────────────────────────────────

def _lessons(user_id: int) -> List[Dict[str, Any]]:
    ensure_tables()
    rows = db.session.execute(text(
        f"SELECT id, seq, lesson_type, status, theme, method_code, method_name, "
        f"probnik_code, probnik_title, olympiad_slug, assigned_date, completed_at "
        f"FROM {TABLE_NAME} WHERE user_id = :uid ORDER BY seq"
    ), {'uid': user_id}).fetchall()
    return [dict(zip(
        ('id', 'seq', 'lesson_type', 'status', 'theme', 'method_code',
         'method_name', 'probnik_code', 'probnik_title', 'olympiad_slug',
         'assigned_date', 'completed_at'), r)) for r in rows]


def _completed_count(user_id: int) -> int:
    ensure_tables()
    row = db.session.execute(text(
        f"SELECT count(*) FROM {TABLE_NAME} "
        f"WHERE user_id = :uid AND status = 'completed'"
    ), {'uid': user_id}).fetchone()
    return int(row[0]) if row else 0


def _lesson_type_for_position(completed: int) -> str:
    """Занятие 1 блока — метод, занятие 6 — пробник, остальные — практика."""
    pos = (completed % BLOCK_SIZE) + 1
    if pos == 1:
        return 'method'
    if pos == BLOCK_SIZE:
        return 'probnik'
    return 'practice'


def _insert_lesson(user_id: int, seq: int, lesson_type: str) -> None:
    theme = method_code = method_name = probnik_code = probnik_title = None
    olympiad_slug = _user_olympiad(user_id)
    if lesson_type == 'practice':
        theme = _theme_for_user(user_id)
    elif lesson_type == 'method':
        m = _pick_method(user_id)
        method_code, method_name = m['code'], m['name']
    elif lesson_type == 'probnik':
        used = {l['probnik_code'] for l in _lessons(user_id) if l['probnik_code']}
        p = _pick_probnik(user_id, olympiad_slug, used)
        if p:
            probnik_code, probnik_title = p['code'], p['title']
    db.session.execute(text(
        f"INSERT INTO {TABLE_NAME} "
        f"(user_id, seq, lesson_type, status, theme, method_code, method_name, "
        f"probnik_code, probnik_title, olympiad_slug, assigned_date) "
        f"VALUES (:uid, :seq, :lt, 'assigned', :theme, :mc, :mn, :pc, :pt, :os, :ad)"
    ), {
        'uid': user_id, 'seq': seq, 'lt': lesson_type, 'theme': theme,
        'mc': method_code, 'mn': method_name, 'pc': probnik_code,
        'pt': probnik_title, 'os': olympiad_slug, 'ad': date.today(),
    })
    db.session.commit()
    logger.info('[session_plan] assigned lesson #%s type=%s user=%s',
                seq, lesson_type, user_id)


def current_lesson(user_id: int) -> Optional[Dict[str, Any]]:
    """Текущее (незавершённое) занятие. Создаёт следующее, если все готовы."""
    if not _pilot(user_id):
        return None
    ensure_tables()
    lessons = _lessons(user_id)
    assigned = [l for l in lessons if l['status'] == 'assigned']
    if assigned:
        return assigned[0]
    # все завершены — создаём следующее по ротации
    seq = (lessons[-1]['seq'] if lessons else 0) + 1
    lesson_type = _lesson_type_for_position(_completed_count(user_id))
    _insert_lesson(user_id, seq, lesson_type)
    lessons = _lessons(user_id)
    assigned = [l for l in lessons if l['status'] == 'assigned']
    return assigned[0] if assigned else None


def complete_current_lesson(user_id: int, lesson_type: Optional[str] = None) -> bool:
    """Отметить текущее занятие завершённым (идемпотентно).

    lesson_type — опциональная проверка типа (например, 'probnik' при
    сдаче пробника): если тип не совпадает с текущим, ничего не делаем.
    Возвращает True, если занятие было отмечено сейчас.
    """
    if not _pilot(user_id):
        return False
    ensure_tables()
    lesson = current_lesson(user_id)
    if not lesson:
        return False
    if lesson_type and lesson['lesson_type'] != lesson_type:
        return False
    if lesson['status'] != 'assigned':
        return False
    db.session.execute(text(
        f"UPDATE {TABLE_NAME} SET status = 'completed', "
        f"completed_at = :now WHERE id = :lid AND status = 'assigned'"
    ), {'now': datetime.utcnow(), 'lid': lesson['id']})
    db.session.commit()
    logger.info('[session_plan] completed lesson #%s (%s) user=%s',
                lesson['seq'], lesson['lesson_type'], user_id)
    return True


# ── Хуки завершения (вызываются из мест сдачи) ───────────────────────────

def maybe_complete_practice(user_id: int, daily_set_id: int) -> bool:
    """Практика завершена, если все задачи сегодняшнего сета отвечены."""
    try:
        from daily_tasks.models import DailyTaskItem
        items = DailyTaskItem.query.filter_by(daily_set_id=daily_set_id).all()
        if not items:
            return False
        if all(it.user_answer is not None for it in items):
            return complete_current_lesson(user_id, lesson_type='practice')
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] practice hook failed: %r', e)
    return False


def maybe_complete_method(user_id: int) -> bool:
    """Метод завершён, если все задачи метод-сета отвечены."""
    try:
        from method_week.models import MethodWeekSet, MethodWeekAnswer
        s = MethodWeekSet.query.filter_by(user_id=user_id).order_by(
            MethodWeekSet.id.desc()).first()
        if not s or not s.tasks_json:
            return False
        import json as _json
        tasks = _json.loads(s.tasks_json) if isinstance(s.tasks_json, str) else (s.tasks_json or [])
        if not tasks:
            return False
        answered = {a.position for a in MethodWeekAnswer.query.filter_by(
            set_id=s.id).all() if a.user_answer}
        if all(int(t.get('position') or 0) in answered for t in tasks):
            return complete_current_lesson(user_id, lesson_type='method')
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] method hook failed: %r', e)
    return False


def maybe_complete_probnik(user_id: int, probnik_code: str) -> bool:
    """Пробник сдан — завершаем занятие-пробник."""
    try:
        lesson = current_lesson(user_id)
        if not lesson or lesson['lesson_type'] != 'probnik':
            return False
        if lesson['probnik_code'] and lesson['probnik_code'] != probnik_code:
            return False
        return complete_current_lesson(user_id, lesson_type='probnik')
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] probnik hook failed: %r', e)
    return False


# ── Публичная сводка (дашборд задач дня + план куратора) ─────────────────

CTA_FOR_TYPE = {
    # Страница «Метод недели» на /daily_tasks отключена по просьбе владельца
    # (2026-10-22, METHOD_WEEK_UI_ENABLED=0), поэтому метод ведёт на страницу
    # метода в атласе 102 методов (/olympiad/methods/<код> — если код известен).
    'method': '/olympiad/methods',
    'practice': '/daily_tasks',
    'probnik': '/olympiad/probnik/',
}


def session_info(user_id: int) -> Dict[str, Any]:
    """Сводка текущего занятия для интерфейса. Никогда не бросает."""
    if not _pilot(user_id):
        return {'active': False}
    try:
        lesson = current_lesson(user_id)
        if not lesson:
            return {'active': False}
        completed = _completed_count(user_id)
        pos_in_block = (completed % BLOCK_SIZE) + 1
        t = lesson['lesson_type']
        cta = CTA_FOR_TYPE.get(t, '/daily_tasks')
        if t == 'method' and lesson['method_code']:
            cta = f"/olympiad/methods/{lesson['method_code']}"
        if t == 'probnik' and lesson['probnik_code']:
            cta = f"/olympiad/probnik/{lesson['probnik_code']}"
        return {
            'active': True,
            'seq': lesson['seq'],
            'lesson_type': t,
            'lesson_label': LESSON_LABELS.get(t, t),
            'position_in_block': pos_in_block,
            'block_size': BLOCK_SIZE,
            'completed_lessons': completed,
            'theme': lesson['theme'],
            'method_name': lesson['method_name'],
            'probnik_code': lesson['probnik_code'],
            'probnik_title': lesson['probnik_title'],
            'olympiad_slug': lesson['olympiad_slug'],
            'cta_url': cta,
            'status': lesson['status'],
        }
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] session_info failed: %r', e)
        return {'active': False}

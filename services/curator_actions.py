# -*- coding: utf-8 -*-
"""services/curator_actions.py — действия, которые ИИ-куратор делает сам.

Владелец (06.11.2026): куратор не только отвечает, но и может по
просьбе ученика:
  * поднять (или снизить) уровень сложности задач дня;
  * поменять дни занятий (столько же дней, сколько даёт тариф);
  * перестроить задачи дня под другую олимпиаду — темы идут в порядке
    популярности на этой олимпиаде в классе ученика.

Как это работает: модель в конце ответа пишет служебную строку
    [[ACTION {"type": "set_days", "days": [0, 2, 4]}]]
сервер её вырезает, проверяет и выполняет. Ученик видит обычный ответ
и строку с итогом («✅ Готово: …» или «⚠️ Не получилось…» с подсказкой
написать в поддержку). Никогда не бросает.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger('formyla.curator_actions')

SUPPORT_HINT = ('Нажми справа от меня на иконку поддержки 💬 и напиши '
                'свою просьбу или проблему — команда ответит.')

_ACTION_RE = re.compile(r'\[\[\s*ACTION\s*(\{.*?\})\s*\]\]', re.S)

WEEKDAYS_RU = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница',
               'суббота', 'воскресенье']
WEEKDAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

MAX_ACTIONS_PER_REPLY = 3


def is_admin_id(user_id: Optional[int]) -> bool:
    """CURATOR_ADMIN_V1: новые функции куратора пока только для админов."""
    if not user_id:
        return False
    try:
        from models import User
        u = User.query.get(int(user_id))
        return bool(u is not None and u.is_admin)
    except Exception:  # noqa: BLE001
        return False


# ── Разбор ответа модели ────────────────────────────────────────────────

def extract_actions(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Вырезать служебные строки действий. → (чистый текст, действия)."""
    actions: List[Dict[str, Any]] = []
    for m in _ACTION_RE.finditer(text or ''):
        try:
            a = json.loads(m.group(1))
            if isinstance(a, dict) and a.get('type'):
                actions.append(a)
        except (ValueError, TypeError):
            logger.warning('[curator_actions] bad action json: %r', m.group(1)[:200])
    clean = _ACTION_RE.sub('', text or '').strip()
    return clean, actions[:MAX_ACTIONS_PER_REPLY]


# ── Отдельные действия ──────────────────────────────────────────────────

def _fail(msg: str) -> Dict[str, Any]:
    return {'ok': False, 'message': f'⚠️ {msg} {SUPPORT_HINT}'}


def change_level(user_id: int, delta: int) -> Dict[str, Any]:
    """Уровень задач дня ±1 (шкала 1–4). Действует со следующей выдачи."""
    try:
        from datetime import datetime
        from models import db
        from models_curator import CuratorState
        from services.level_engine import get_state, MIN_SIGMA
        delta = 1 if int(delta) > 0 else -1
        old = get_state(user_id)['level']
        new = max(1, min(4, old + delta))
        if new == old:
            edge = 'максимальный (4)' if delta > 0 else 'минимальный (1)'
            return {'ok': False,
                    'message': f'ℹ️ Уровень уже {edge} — менять некуда.'}
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs is None:
            cs = CuratorState(user_id=user_id)
            db.session.add(cs)
        cs.level_mu = float(new)
        cs.level_sigma = max(MIN_SIGMA, float(cs.level_sigma or MIN_SIGMA))
        cs.level_updated_at = datetime.utcnow().isoformat()
        db.session.commit()
        logger.info('[curator_actions] level user=%s %s -> %s', user_id, old, new)
        word = 'поднял' if delta > 0 else 'снизил'
        return {'ok': True,
                'message': f'✅ Готово: {word} уровень задач дня с {old} до {new}. '
                           f'Новые задачи будут уже такого уровня со следующей выдачи.'}
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_actions] level failed: %r', e)
        _rollback()
        return _fail('Не получилось поменять уровень.')


def set_days(user_id: int, days: Any) -> Dict[str, Any]:
    """Новые дни занятий: ровно столько, сколько даёт тариф."""
    try:
        from curator.session_plan import _pilot_variant
        from services.schedule_days import required_days_count, save_user_days
        plan = _pilot_variant(user_id)
        need = required_days_count(plan) if plan else None
        if need is None:
            return _fail('Дни занятий выбираются только на тарифах «Работяга» и «Спокойный».')
        try:
            vals = sorted({int(d) for d in (days or [])})
        except (TypeError, ValueError):
            vals = []
        if len(vals) != need or any(d < 0 or d > 6 for d in vals):
            return {'ok': False,
                    'message': f'ℹ️ На твоём тарифе нужно выбрать ровно {need} '
                               f'дн. занятий — назови их, и я поменяю.'}
        if not save_user_days(user_id, vals, plan):
            return _fail('Не получилось сохранить новые дни.')
        label = ', '.join(WEEKDAYS_SHORT[d] for d in vals)
        return {'ok': True,
                'message': f'✅ Готово: теперь занятия по дням {label}. '
                           f'Остальные дни — выходные.'}
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_actions] days failed: %r', e)
        _rollback()
        return _fail('Не получилось поменять дни занятий.')


def _find_olympiad(slug: str):
    from models import OlympiadPrep
    from services.daily_olympiad import _PREP_TO_CATALOG
    candidates = [slug] + [k for k, v in _PREP_TO_CATALOG.items() if v == slug]
    for s in candidates:
        row = OlympiadPrep.query.filter_by(slug=s).first()
        if row is not None:
            return row
    return None


def set_olympiad(user_id: int, slug: str) -> Dict[str, Any]:
    """Перестроить задачи дня под олимпиаду (через план подготовки)."""
    try:
        from datetime import date, timedelta
        from models import db, PrepPlan, User
        from services.daily_olympiad import profile_for, user_cycle_grade, catalog_slug
        slug = (slug or '').strip().lower()
        grade = user_cycle_grade(user_id)
        if not slug:
            return _fail('Не понял, какую олимпиаду выбрать.')
        olymp = _find_olympiad(slug)
        if olymp is None:
            return _fail('Такой олимпиады нет в нашем списке.')
        prof = profile_for(olymp.slug, grade, freq=True)
        if not prof:
            return {'ok': False,
                    'message': f'ℹ️ Олимпиады «{olymp.name}» нет для {grade} класса '
                               f'(или по ней пока нет задач) — выбери другую.'}
        plan = (PrepPlan.query.filter_by(user_id=user_id, status='active')
                .order_by(PrepPlan.id.desc()).first())
        if plan is not None:
            plan.olympiad_id = olymp.id
            db.session.commit()
        else:
            from services.prep_planner import generate_prep_plan
            user = User.query.get(user_id)
            generate_prep_plan(user, olymp, None, date.today() + timedelta(days=60), {})
        try:
            from curator.monthly_cycle import apply_olympiad_cycle
            apply_olympiad_cycle(user_id)
        except Exception as e:  # noqa: BLE001
            logger.warning('[curator_actions] apply cycle failed: %r', e)
        top = top_themes_line(olymp.slug, grade, k=3)
        tail = f' Первыми пойдут самые частые там темы: {top}.' if top else ''
        return {'ok': True,
                'message': f'✅ Готово: задачи дня теперь под «{prof["name"]}», '
                           f'{grade} класс.{tail} Новый порядок — со следующей выдачи.'}
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_actions] olympiad failed: %r', e)
        _rollback()
        return _fail('Не получилось перестроить задачи под олимпиаду.')


def _rollback() -> None:
    try:
        from models import db
        db.session.rollback()
    except Exception:
        pass


# ── Справка для промпта ─────────────────────────────────────────────────

def top_themes_line(slug: str, grade: Optional[int], k: int = 5) -> str:
    try:
        from services.daily_olympiad import topic_stats
        st = topic_stats(slug, int(grade)) if grade else None
        if not st:
            return ''
        total = int(st.get('n_classified') or 0) or 1
        return '; '.join(f"{t['title']} ({round(100 * t['count'] / total)}%)"
                         for t in (st.get('themes') or [])[:k])
    except Exception:
        return ''


def olympiads_for_grade(grade: Optional[int]) -> List[Tuple[str, str]]:
    """[(slug, название)] олимпиад, под которые можно перестроить задачи."""
    out: List[Tuple[str, str]] = []
    if not grade:
        return out
    try:
        from services.daily_olympiad import (OLYMPIAD_PROFILES, _FREQ_NAMES,
                                             _freq_data, profile_for)
        slugs = list((_freq_data().get('olympiads') or {}).keys())
        slugs += [s for s in OLYMPIAD_PROFILES if s not in slugs]
        for s in slugs:
            prof = profile_for(s, grade, freq=True)
            if prof:
                out.append((s, prof['name']))
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_actions] olympiads list failed: %r', e)
    return out


def state_lines(user_id: int, grade: Optional[int]) -> List[str]:
    """Строки «Данных ученика» про уровень, дни и олимпиаду."""
    lines: List[str] = []
    try:
        from services.level_engine import get_state
        lines.append(f"- уровень задач дня: {get_state(user_id)['level']} из 4")
    except Exception:
        pass
    try:
        from curator.session_plan import _pilot_variant, _chosen_days
        from services.schedule_days import required_days_count
        plan = _pilot_variant(user_id)
        days = _chosen_days(user_id, plan) if plan else None
        if days:
            lines.append('- дни занятий: ' + ', '.join(WEEKDAYS_SHORT[d] for d in days)
                         + f' (на тарифе нужно ровно {required_days_count(plan)})')
    except Exception:
        pass
    try:
        from services.daily_olympiad import user_olympiad
        uo = user_olympiad(user_id)
        if uo:
            lines.append(f"- задачи дня сейчас под олимпиаду: {uo['name']} (slug {uo['slug']})")
            top = top_themes_line(uo['slug'], grade)
            if top:
                lines.append(f'- самые частые темы этой олимпиады в {grade} классе '
                             f'(по реальным вариантам): {top}')
        else:
            lines.append('- олимпиада для задач дня не выбрана')
    except Exception:
        pass
    avail = olympiads_for_grade(grade)
    if avail:
        lines.append('- олимпиады, под которые можно перестроить задачи дня (slug — название): '
                     + '; '.join(f'{s} — {n}' for s, n in avail))
    return lines


# ── Выполнение ──────────────────────────────────────────────────────────

def run_actions(user_id: int, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for a in actions:
        t = str(a.get('type') or '')
        if t == 'raise_level':
            results.append(change_level(user_id, +1))
        elif t == 'lower_level':
            results.append(change_level(user_id, -1))
        elif t == 'set_days':
            results.append(set_days(user_id, a.get('days')))
        elif t == 'set_olympiad':
            results.append(set_olympiad(user_id, a.get('slug') or ''))
        else:
            results.append(_fail('Это я пока сделать не могу.'))
        results[-1]['type'] = t
    return results


def apply_reply(user_id: int, text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Ответ модели → (текст для ученика с итогами действий, результаты)."""
    clean, actions = extract_actions(text)
    if not actions or not is_admin_id(user_id):
        return clean, []
    results = run_actions(user_id, actions)
    notes = '\n'.join(r['message'] for r in results)
    return (clean + '\n\n' + notes).strip(), results

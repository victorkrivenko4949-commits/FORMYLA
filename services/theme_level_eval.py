# -*- coding: utf-8 -*-
"""
services/theme_level_eval.py — THEME_EVAL_V1 (18.10.2026).

Итог по теме после каждых 10 решённых задач дня из банка (BankIssue).

Правило (L — уровень задач в последней десятке, round(mean), 1..4;
C — сколько из этих 10 решено верно):
    C >= 8  -> L + 1  (не выше 4)
    C 6..7  -> L
    C 4..5  -> L - 1  (не ниже 1)
    C 2..3  -> L - 2  (не ниже 1)
    C 0..1  -> 1
Пример: задачи уровня 3, верно 0 -> итог 1.

Итог пишется в CuratorState.level_by_theme[theme_id] = {mu, n, sigma, ...}
(это и есть данные радаров по разделам), а по разделу — среднее итогов его
тем -> CuratorState.level_by_section[section] (общий радар). Другие ключи в
этих JSON не трогаем. Пересчёт только когда число отвеченных задач изменилось
(кэш в prep_state['theme_eval']['answered_total']).

Сопоставление темы банка (BankIssue.subtopic — человеческое название) с
theme_id (G9_T05) — через data/theme_titles.json с учётом класса ученика.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from models import db

logger = logging.getLogger(__name__)

BLOCK = 10
EVAL_SIGMA = 0.35


def verdict(level: int, correct: int) -> int:
    """Итоговый уровень темы по десятке: уровень задач + сколько верно."""
    L = max(1, min(4, int(level)))
    c = max(0, min(BLOCK, int(correct)))
    if c >= 8:
        v = L + 1
    elif c >= 6:
        v = L
    elif c >= 4:
        v = L - 1
    elif c >= 2:
        v = L - 2
    else:
        v = 1
    return max(1, min(4, v))


def _norm(s: str) -> str:
    return ' '.join((s or '').replace('ё', 'е').lower().split())


_TITLE_INDEX: Optional[Dict[str, List[str]]] = None


def _title_index() -> Dict[str, List[str]]:
    """normalized title -> [theme_id, ...] (одно название бывает у нескольких классов)."""
    global _TITLE_INDEX
    if _TITLE_INDEX is not None:
        return _TITLE_INDEX
    idx: Dict[str, List[str]] = defaultdict(list)
    try:
        from services.theme_registry import all_themes, theme_title
        for tid, _sec in all_themes():
            idx[_norm(theme_title(tid))].append(tid)
    except Exception as e:  # noqa: BLE001
        logger.warning('[theme_eval] title index failed: %r', e)
    _TITLE_INDEX = dict(idx)
    return _TITLE_INDEX


def theme_id_for(subtopic: str, grade: Optional[int]) -> Optional[str]:
    cands = _title_index().get(_norm(subtopic)) or []
    if not cands:
        # вдруг в subtopic уже лежит theme_id
        s = (subtopic or '').strip()
        return s if s and s[0] == 'G' and '_T' in s else None
    if grade:
        pref = f'G{int(grade)}_'
        for tid in cands:
            if tid.startswith(pref):
                return tid
    return cands[0]


def _user_grade(user_id: int) -> Optional[int]:
    try:
        from models import User
        u = db.session.get(User, user_id)
        g = getattr(u, 'preferred_grade', None) or getattr(u, 'class_level', None)
        return int(g) if g else None
    except Exception:  # noqa: BLE001
        return None


def _load_json(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def collect(user_id: int) -> Dict[str, Any]:
    """Сырые данные по темам (без записи): {theme_key: {...}}."""
    from models import BankIssue, DailyTaskBank
    rows = (
        db.session.query(BankIssue, DailyTaskBank.section)
        .outerjoin(DailyTaskBank, DailyTaskBank.id == BankIssue.task_id)
        .filter(BankIssue.user_id == user_id, BankIssue.user_answer.isnot(None))
        .order_by(BankIssue.answered_at.asc(), BankIssue.id.asc())
        .all()
    )
    grade = _user_grade(user_id)
    groups: Dict[str, Dict[str, Any]] = {}
    for issue, section in rows:
        key = _norm(issue.subtopic)
        if not key:
            continue
        g = groups.setdefault(key, {
            'title': (issue.subtopic or '').strip(),
            'theme_id': theme_id_for(issue.subtopic, grade),
            'section': None,
            'items': [],
        })
        if section and not g['section']:
            g['section'] = section
        g['items'].append((int(issue.level or 1), bool(issue.is_correct)))

    out: Dict[str, Any] = {}
    for key, g in groups.items():
        items = g['items']
        n = len(items)
        blocks = n // BLOCK
        res = {
            'title': g['title'],
            'theme_id': g['theme_id'],
            'section': g['section'],
            'answered': n,
            'correct_total': sum(1 for _, c in items if c),
            'blocks': blocks,
            'to_next': (BLOCK - n % BLOCK) % BLOCK if blocks else BLOCK - n,
            'level': None,
            'last10_level': None,
            'last10_correct': None,
        }
        if blocks:
            last = items[blocks * BLOCK - BLOCK: blocks * BLOCK]
            lvl = round(sum(l for l, _ in last) / len(last))
            cor = sum(1 for _, c in last if c)
            res['last10_level'] = lvl
            res['last10_correct'] = cor
            res['level'] = verdict(lvl, cor)
        out[key] = res
    return {'answered_total': len(rows), 'themes': out}


def evaluate_user(user_id: int, force: bool = False) -> Dict[str, Any]:
    """Пересчитать итоги и записать в CuratorState. Возвращает collect()."""
    from models_curator import CuratorState
    from sqlalchemy.orm.attributes import flag_modified

    data = collect(user_id)
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None:
        return data
    prep = _load_json(cs.prep_state)
    cache = prep.get('theme_eval') or {}
    if not force and cache.get('answered_total') == data['answered_total'] and cache.get('v') == 1:
        return data

    lbt = _load_json(cs.level_by_theme)
    lbs = _load_json(cs.level_by_section)
    now = datetime.utcnow().isoformat(timespec='seconds')
    per_section: Dict[str, List[int]] = defaultdict(list)

    for key, t in data['themes'].items():
        if t['level'] is None:
            continue
        tid = t['theme_id'] or t['title']
        prev = lbt.get(tid) if isinstance(lbt.get(tid), dict) else {}
        lbt[tid] = {
            **prev,
            'mu': float(t['level']),
            'sigma': EVAL_SIGMA,
            'n': int(t['answered']),
            'source': 'bank10',
            'last10_level': t['last10_level'],
            'last10_correct': t['last10_correct'],
            'updated_at': now,
        }
        sec = t['section']
        if not sec and t['theme_id']:
            try:
                from services.theme_registry import section_of_theme
                sec = section_of_theme(t['theme_id'])
            except Exception:  # noqa: BLE001
                sec = None
        if sec:
            per_section[sec].append(int(t['level']))

    for sec, levels in per_section.items():
        prev = lbs.get(sec) if isinstance(lbs.get(sec), dict) else {}
        lbs[sec] = {
            **prev,
            'mu': round(sum(levels) / len(levels), 2),
            'sigma': EVAL_SIGMA,
            'n': int(prev.get('n', 0)) if prev else 0,
            'themes_evaluated': len(levels),
            'source': 'bank10',
            'updated_at': now,
        }

    try:
        cs.level_by_theme = json.dumps(lbt, ensure_ascii=False)
        cs.level_by_section = json.dumps(lbs, ensure_ascii=False)
        cs.level_updated_at = now
        prep['theme_eval'] = {'v': 1, 'answered_total': data['answered_total'], 'updated_at': now}
        cs.prep_state = prep
        flag_modified(cs, 'prep_state')
        db.session.commit()
        logger.info('[theme_eval] user=%s themes=%d sections=%d', user_id,
                    sum(1 for t in data['themes'].values() if t['level'] is not None), len(per_section))
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[theme_eval] save failed: %r', e)
    return data

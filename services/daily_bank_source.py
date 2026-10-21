# -*- coding: utf-8 -*-
"""services/daily_bank_source.py — основной банк как источник внутри единой выдачи (шаг 8.2).

Вызывается из daily_tasks.formyla_bank.get_tasks() ПЕРЕД выборкой из JSONL:
если в daily_task_bank есть задачи по ключу (класс, тема, уровень) — берутся они,
недостающее добирает JSONL. Так основной банк становится приоритетным хранилищем
позади уже работающего алгоритма (тема дня по циклу, уровень ученика, норма из анкеты),
а не второй системой со своим планом и расписанием.

Правила:
  * тема передаётся русским названием (как в JSONL) — здесь переводится в theme_id
    через data/theme_titles.json с учётом класса; класс из ключа обязан совпасть;
  * берётся только ТОЧНЫЙ уровень (соседние уровни добирает JSONL по своим правилам);
  * уже выданные этому ученику задачи (bank_issues) исключаются;
  * выданное помечается строкой в bank_issues (flush без commit — коммитит вызывающий
    код вместе с созданием DailyTaskSet); по этим строкам бейдж админа (#128) видит источник;
  * любая ошибка (нет app context, нет таблицы) -> пустой список, выдача идёт из JSONL.

Отключение без деплоя: DAILY_BANK_PRIORITY=0.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return (os.environ.get("DAILY_BANK_PRIORITY") or "1").strip() != "0"


@lru_cache(maxsize=1)
def _title_index() -> Dict[tuple, str]:
    """(grade, title) -> theme_id по data/theme_titles.json."""
    try:
        from services.daily_bank_keys import _theme_titles, parse_theme_id
    except Exception:
        return {}
    out: Dict[tuple, str] = {}
    for tid, title in _theme_titles().items():
        parsed = parse_theme_id(tid)
        if parsed and title:
            out[(parsed[0], title.strip())] = tid
    return out


def theme_id_for(grade: int, topic: str) -> Optional[str]:
    """Принимает theme_id или русское название; возвращает theme_id нужного класса или None."""
    from services.daily_bank_keys import parse_theme_id
    t = (topic or "").strip()
    if not t:
        return None
    parsed = parse_theme_id(t)
    if parsed:
        return t if parsed[0] == int(grade) else None
    return _title_index().get((int(grade), t))


def _msk_today():
    return (datetime.utcnow() + timedelta(hours=3)).date()


def _norm(s: str) -> str:
    return " ".join((s or "").split()).strip()


def pick_from_table(grade: int, topic: str, level: int, count: int, user_id: int,
                    exclude_texts: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Задачи точного уровня из daily_task_bank в формате formyla_bank (list[dict]).

    Пустой список — если выключено, тема не распознана, таблица пуста или произошла ошибка.
    """
    if not enabled() or user_id is None or count <= 0:
        return []
    theme_id = theme_id_for(grade, topic)
    if not theme_id:
        return []

    from models import db, DailyTaskBank, BankIssue

    issued = {
        int(r[0]) for r in db.session.query(BankIssue.task_id)
        .filter(BankIssue.user_id == user_id).all() if r[0] is not None
    }
    rows = (DailyTaskBank.query
            .filter_by(subtopic=theme_id, level=int(level))
            .all())
    excluded = {_norm(t) for t in (exclude_texts or set())}
    fresh = [t for t in rows
             if t.id not in issued and _norm(t.statement) and _norm(t.statement) not in excluded
             and (t.answer or "").strip()]
    if not fresh:
        return []

    fresh.sort(key=lambda t: hashlib.md5(f"{user_id}:{t.id}".encode("utf-8")).hexdigest())
    chosen = fresh[:count]

    today = _msk_today()
    for t in chosen:
        db.session.add(BankIssue(user_id=user_id, task_id=t.id, subtopic=t.subtopic,
                                 level=t.level, issued_date=today))
    db.session.flush()

    out: List[Dict[str, Any]] = []
    for t in chosen:
        out.append({
            "task_text": t.statement,
            "correct_answer": t.answer or "",
            "solution": t.solution or "",
            "level": int(t.level),
            "position": t.position,
            "topic": (topic or "").strip(),
            "figure_svg_path": t.svg_path or "",
            "source": "daily_task_bank",
            "bank_task_id": t.id,
        })
    logger.info("daily_bank_source: user=%s %s L%s -> %d из таблицы (нужно %d)",
                user_id, theme_id, level, len(out), count)
    return out

# -*- coding: utf-8 -*-
"""curator/daily_plan.py — ежедневное письмо куратора: «что у тебя и что делать».

Куратор НЕ выдаёт задачи. Он каждый день пишет короткий план строго из фактов
(curator.messenger.get_student_facts) + метода недели и плана методов на месяц
(method_week.catalog). Текст всегда есть — даже если поводов для тревоги нет.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SECTION_NAMES = {
    'algebra': 'алгебра', 'geometry': 'геометрия', 'combinatorics': 'комбинаторика',
    'logic': 'логика', 'number_theory': 'теория чисел',
}

_HOWTO = {
    'algebra': 'в алгебре сначала выписывай, что дано и что найти, и ищи замену переменной или разложение на множители',
    'geometry': 'в геометрии всегда делай крупный чертёж и отмечай равные углы и отрезки — половина решения в этом',
    'combinatorics': 'в комбинаторике начинай с маленьких случаев (n = 1, 2, 3) и ищи закономерность',
    'logic': 'в логике перебирай варианты по порядку и записывай, что уже исключено',
    'number_theory': 'в теории чисел смотри на остатки от деления и на последнюю цифру',
}


def _status_block(f: Dict[str, Any]) -> List[str]:
    out = []
    total = f.get('today_total', 0) or 0
    solved = f.get('today_solved', 0) or 0
    correct = f.get('today_correct', 0) or 0
    if total and solved == 0:
        out.append("Сегодня у тебя %d задач дня, пока ни одна не решена." % total)
    elif total:
        out.append("Сегодня решено %d из %d, верно — %d." % (solved, total, correct))
    else:
        out.append("Задачи дня на сегодня ещё не выданы — открой их первыми.")
    streak = f.get('streak_days') or 0
    if streak >= 3:
        out.append("Серия %d дней подряд — держи темп." % streak)
    missed = f.get('missed_days_last_week') or 0
    if missed >= 3:
        out.append("За неделю пропущено %d дней: лучше 3 задачи каждый день, чем 10 раз в неделю." % missed)
    if f.get('debt_size'):
        burn = f.get('debt_burns_tomorrow') or 0
        tail = ", %d из них сгорят завтра" % burn if burn else ''
        out.append("В долге %d задач%s." % (f['debt_size'], tail))
    if f.get('level_delta'):
        d = f['level_delta']
        out.append("Уровень за неделю %s на %d (сейчас %s)." % ('вырос' if d > 0 else 'снизился', abs(d), f.get('level_now')))
    return out


def _plan_block(f: Dict[str, Any], method: Optional[Dict[str, Any]],
                mw_progress: Optional[Dict[str, int]]) -> List[str]:
    out = []
    steps = []
    if f.get('debt_size'):
        steps.append("закрой хотя бы одну задачу из долга")
    if f.get('today_total', 0) and f.get('today_pending', 0):
        steps.append("реши %d задачи дня" % min(3, f['today_pending']))
    if method:
        name = method.get('method_name', '')
        code = method.get('method_code', '')
        if mw_progress and mw_progress.get('total'):
            done, total = mw_progress['completed'], mw_progress['total']
            if done < total:
                steps.append("по методу недели %s «%s» осталось %d из %d задач" % (code, name, total - done, total))
            else:
                steps.append("метод недели %s «%s» закрыт — молодец" % (code, name))
        else:
            steps.append("прочитай разбор метода недели %s «%s» и реши 3 задачи на него" % (code, name))
    if steps:
        out.append("План на сегодня: " + "; ".join(steps) + ".")
    weak = f.get('weakest_sections') or []
    if weak:
        sec = weak[0].get('section', '')
        pct = weak[0].get('accuracy_pct', 0) or 0
        pct_s = str(int(pct)) if pct == int(pct) else str(pct)
        name = SECTION_NAMES.get(sec, sec)
        out.append("Самое слабое место — %s (%s%% верных). Как решать: %s." % (
            name, pct_s, _HOWTO.get(sec, 'разбирай решение после каждой ошибки')))
    if method and method.get('reason'):
        out.append("Метод недели выбран не случайно: %s." % method['reason'])
    return out


def get_daily_plan(user_id: int, today: Optional[date] = None) -> Dict[str, Any]:
    from curator.messenger import get_student_facts
    today = today or date.today()
    facts: Dict[str, Any] = {}
    try:
        facts = get_student_facts(user_id)
    except Exception as exc:
        logger.warning("daily_plan: facts failed user=%s: %s", user_id, exc)

    method = None
    mw_progress = None
    try:
        from method_week.catalog import method_for_week, week_start
        method = method_for_week(user_id, today)
        from method_week.models import MethodWeekSet, MethodWeekAnswer, ensure_tables
        ensure_tables()
        s = MethodWeekSet.query.filter_by(user_id=user_id, week_start=week_start(today)).first()
        if s and s.status == 'ready':
            done = MethodWeekAnswer.query.filter_by(set_id=s.id) \
                .filter(MethodWeekAnswer.user_answer.isnot(None)).count()
            mw_progress = {'completed': done, 'total': len(s.tasks)}
    except Exception as exc:
        logger.warning("daily_plan: method week lookup failed: %s", exc)

    status = _status_block(facts)
    plan = _plan_block(facts, method, mw_progress)
    return {
        'date': today.isoformat(),
        'status_lines': status,
        'plan_lines': plan,
        'text': ' '.join(status + plan),
        'method': ({'code': method.get('method_code'), 'name': method.get('method_name'),
                    'section': method.get('section_ru')} if method else None),
    }

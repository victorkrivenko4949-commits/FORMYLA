# -*- coding: utf-8 -*-
"""Генерация «Метода недели» через deepseek-v4-pro (режим thinking).

Пайплайн (все вызовы — thinking):
  1. lesson    — разбор метода под уровень ученика (Markdown + LaTeX)
  2. tasks     — 4 кандидата задач на метод (нужно 3), JSON
  3. verify    — независимое решение каждой задачи; ответ сверяется с
                 эталоном (compare_math_answers). Расхождение -> задача
                 отбрасывается; если верных < 3 — догенерация (1 раунд)
  4. latex     — нормализация формул (method_week/latex.py)
  5. persist   — запись в MethodWeekSet
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MODEL = os.environ.get('METHOD_WEEK_MODEL', 'deepseek-v4-pro').strip()
MAX_TOKENS = int(os.environ.get('METHOD_WEEK_MAX_TOKENS', '16000'))
NEED_TASKS = 3
CANDIDATES = 4

_LEVEL_HINT = {
    1: 'ученик только начинает, формулировки простые, числа маленькие',
    2: 'базовый уровень школьной олимпиады (школьный этап)',
    3: 'уверенный школьный этап, лёгкий муниципальный',
    4: 'муниципальный этап ВсОШ',
    5: 'сильный муниципальный / слабый региональный',
    6: 'региональный этап ВсОШ',
    7: 'сильный региональный / заключительный этап',
}


def _extract_json(text: str) -> Any:
    """Достаём JSON из ответа модели (возможны ```json ... ``` и рассуждения)."""
    if not text:
        raise ValueError('empty model output')
    t = text.strip()
    m = re.search(r'```(?:json)?\s*(.*?)```', t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    starts = [i for i in (t.find('{'), t.find('[')) if i >= 0]
    if not starts:
        raise ValueError('no JSON in output')
    start = min(starts)
    for end in range(len(t), start, -1):
        try:
            return json.loads(t[start:end])
        except Exception:
            continue
    raise ValueError('cannot parse JSON')


def _method_context(method: Dict[str, Any]) -> str:
    parts = ["Код метода: %s" % method.get('method_code'), "Название: %s" % method.get('method_name')]
    for key, title in (('definition_md', 'Определение'), ('main_theorems_md', 'Основные факты'),
                       ('typical_techniques_md', 'Типичные приёмы'), ('triggers_md', 'Когда применять'),
                       ('pitfalls_md', 'Типичные ошибки')):
        v = method.get(key)
        if isinstance(v, str) and v.strip():
            parts.append("%s: %s" % (title, v.strip()[:1500]))
    return '\n'.join(parts)


def lesson_prompt(method: Dict[str, Any], grade: int, level: int) -> List[Dict[str, str]]:
    sys = ("Ты — опытный преподаватель олимпиадной математики. Пишешь по-русски, "
           "кратко и по делу, формулы — только в LaTeX внутри $...$ (строчные) или $$...$$ (выключные). "
           "Никаких \\( \\) и \\[ \\].")
    user = (
        "Напиши разбор метода для ученика %d класса, уровень %d/7 (%s).\n\n%s\n\n"
        "Структура (Markdown, заголовки ###):\n"
        "### Идея метода — 3–5 предложений простыми словами\n"
        "### Когда применять — 3–4 признака в условии задачи\n"
        "### Алгоритм — нумерованные шаги\n"
        "### Разобранный пример — одна задача с полным решением именно этим методом\n"
        "### Типичные ошибки — 2–3 пункта\n"
        "Объём 250–450 слов. Выведи только Markdown без вступлений."
    ) % (grade, level, _LEVEL_HINT.get(level, ''), _method_context(method))
    return [{'role': 'system', 'content': sys}, {'role': 'user', 'content': user}]


def tasks_prompt(method: Dict[str, Any], grade: int, level: int, count: int,
                 avoid: Optional[List[str]] = None) -> List[Dict[str, str]]:
    sys = ("Ты — составитель олимпиадных задач. Отвечаешь СТРОГО одним JSON-массивом без пояснений. "
           "Формулы — только LaTeX в $...$. Никаких \\( \\).")
    avoid_txt = ''
    if avoid:
        avoid_txt = "\nНе повторяй сюжеты этих задач:\n- " + "\n- ".join(a[:200] for a in avoid)
    user = (
        "Составь %d разных задач, которые решаются методом «%s» (%s), для ученика %d класса, "
        "уровень %d/7 (%s). Сложность по возрастанию: 1-я — тренировочная, "
        "2-я — стандартная олимпиадная, %d-я — с изюминкой.\n"
        "Требования: у каждой задачи ОДИН однозначный краткий ответ (число, выражение, «да/нет», "
        "конечный список), который можно проверить автоматически; решение — полное и обязательно "
        "использует данный метод; задачи не должны быть известными дословно.\n%s\n"
        "Формат каждого элемента массива: "
        '{"statement": "...", "answer": "...", "solution": "...", '
        '"hints": ["подсказка 1", "подсказка 2"], "difficulty": 1-5, "method_step": "какой шаг метода ключевой"}'
    ) % (count, method.get('method_name'), method.get('method_code'), grade, level,
         _LEVEL_HINT.get(level, ''), count, avoid_txt)
    return [{'role': 'system', 'content': sys}, {'role': 'user', 'content': user}]


def solve_prompt(statement: str) -> List[Dict[str, str]]:
    sys = ("Ты — сильный решатель олимпиадных задач. Реши задачу самостоятельно и выведи СТРОГО JSON: "
           '{"answer": "краткий итоговый ответ", "confident": true/false, '
           '"issue": "если условие некорректно/неоднозначно — опиши, иначе пустая строка"}')
    return [{'role': 'system', 'content': sys}, {'role': 'user', 'content': statement}]


def _norm(s: Any) -> str:
    t = re.sub(r'[\s$\\{}]+', '', str(s)).lower()
    t = re.sub(r'^[a-zа-я]\w*=', '', t)          # x=5 -> 5
    t = t.replace(',', '.').rstrip('.;')          # 0,5 -> 0.5 ; «5.» -> 5
    return t


def _answers_match(a: str, b: str) -> bool:
    try:
        from utils.math_answer_utils import compare_math_answers
        if compare_math_answers(str(a), str(b)):
            return True
    except Exception:
        pass
    return _norm(a) != '' and _norm(a) == _norm(b)


def _update(set_id: int, step: str, pct: int) -> None:
    try:
        from models import db
        from .models import MethodWeekSet
        s = db.session.get(MethodWeekSet, set_id)
        if s:
            s.current_step = step
            s.progress_pct = pct
            db.session.commit()
    except Exception:
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


def _as_list(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get('tasks') or raw.get('items') or []
    else:
        items = []
    return [t for t in items if isinstance(t, dict)]


async def _run_pipeline(set_id: int, method: Dict[str, Any], grade: int, level: int,
                        log: List[str]) -> Tuple[str, List[Dict[str, Any]], float]:
    from daily_tasks.pipeline.deepseek_client import DeepSeekClient
    from .latex import normalize_latex, process_task

    cost = 0.0
    verified: List[Dict[str, Any]] = []

    async with DeepSeekClient() as client:
        client._model = MODEL  # принудительно v4-pro независимо от DEEPSEEK_MODEL

        # 1. lesson
        _update(set_id, 'lesson', 10)
        text, usage = await client.async_chat(MODEL, lesson_prompt(method, grade, level),
                                              temperature=0.4, max_tokens=MAX_TOKENS, thinking=True)
        cost += usage.cost_usd
        lesson = normalize_latex(text)
        log.append("lesson ok (%d tok)" % usage.output_tokens)

        # 2. tasks
        _update(set_id, 'tasks', 35)
        text, usage = await client.async_chat(MODEL, tasks_prompt(method, grade, level, CANDIDATES),
                                              temperature=0.7, max_tokens=MAX_TOKENS, thinking=True)
        cost += usage.cost_usd
        cands = _as_list(_extract_json(text))
        log.append("tasks: %d candidates" % len(cands))

        # 3. verify
        async def verify_batch(batch: List[Dict[str, Any]]) -> None:
            nonlocal cost
            for t in batch:
                if len(verified) >= NEED_TASKS:
                    return
                _update(set_id, 'verify_%d' % (len(verified) + 1), 50 + 10 * len(verified))
                stmt = (t.get('statement') or '').strip()
                ans = str(t.get('answer') or '').strip()
                if not stmt or not ans:
                    log.append("skip: empty statement/answer")
                    continue
                try:
                    vt, vu = await client.async_chat(MODEL, solve_prompt(stmt), temperature=0.1,
                                                     max_tokens=MAX_TOKENS, thinking=True)
                    cost += vu.cost_usd
                    v = _extract_json(vt)
                except Exception as exc:
                    log.append("verify error: %s" % exc)
                    continue
                if not isinstance(v, dict):
                    log.append("reject (solver output not dict)")
                    continue
                issue = (v.get('issue') or '').strip()
                v_ans = str(v.get('answer', ''))
                if issue:
                    log.append("reject (issue): %s" % issue[:120])
                    continue
                if not _answers_match(ans, v_ans):
                    log.append("reject (answer mismatch): gen=%r solver=%r" % (ans, v_ans))
                    continue
                pt = process_task(t)
                if not pt.get('latex_ok'):
                    log.append("reject (latex)")
                    continue
                pt['verified_answer'] = v_ans
                verified.append(pt)
                log.append("accept: %s" % stmt[:60])

        await verify_batch(cands)
        if len(verified) < NEED_TASKS:
            _update(set_id, 'regen', 80)
            text, usage = await client.async_chat(
                MODEL, tasks_prompt(method, grade, level, NEED_TASKS - len(verified) + 1,
                                    avoid=[c.get('statement', '') for c in cands]),
                temperature=0.8, max_tokens=MAX_TOKENS, thinking=True)
            cost += usage.cost_usd
            try:
                more = _as_list(_extract_json(text))
            except Exception as exc:
                more = []
                log.append("regen parse error: %s" % exc)
            await verify_batch(more)

    verified.sort(key=lambda t: int(t.get('difficulty') or 3))
    final = verified[:NEED_TASKS]
    for i, t in enumerate(final, start=1):
        t['position'] = i
    return lesson, final, cost


def _worker(app, set_id: int, method: Dict[str, Any], grade: int, level: int) -> None:
    with app.app_context():
        from models import db
        from .models import MethodWeekSet
        log: List[str] = []
        try:
            lesson, tasks, cost = asyncio.run(_run_pipeline(set_id, method, grade, level, log))
            s = db.session.get(MethodWeekSet, set_id)
            if not s:
                return
            if len(tasks) < NEED_TASKS:
                s.status = 'failed'
                s.error_message = 'Проверку прошли только %d задач из %d' % (len(tasks), NEED_TASKS)
            else:
                s.status = 'ready'
            s.lesson_md = lesson
            s.tasks_json = json.dumps(tasks, ensure_ascii=False)
            s.total_cost_usd = float(cost)
            s.model_name = MODEL + ' (thinking)'
            s.progress_pct = 100
            s.current_step = 'done'
            s.finished_at = datetime.utcnow()
            s.pipeline_log = '\n'.join(log)[:20000]
            db.session.commit()
            logger.info("method_week: set #%s %s cost=$%.4f", set_id, s.status, cost)
        except Exception as exc:
            logger.exception("method_week: pipeline failed set=%s: %s", set_id, exc)
            try:
                db.session.rollback()
                s = db.session.get(MethodWeekSet, set_id)
                if s:
                    s.status = 'failed'
                    s.error_message = str(exc)[:2000]
                    s.pipeline_log = '\n'.join(log)[:20000]
                    s.finished_at = datetime.utcnow()
                    db.session.commit()
            except Exception:
                db.session.rollback()


def start_generation(app, set_id: int, method: Dict[str, Any], grade: int, level: int) -> None:
    th = threading.Thread(target=_worker, args=(app, set_id, method, grade, level),
                          name='method_week-%d' % set_id, daemon=True)
    th.start()

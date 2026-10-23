# -*- coding: utf-8 -*-
"""Обработка LaTeX в текстах метода недели (как в задачах дня)."""
from __future__ import annotations

import re
from typing import Any, Dict, List

try:
    from utils.math_text_fixer import wrap_bare_math  # тот же фиксер, что в задачах дня
except Exception:  # pragma: no cover
    def wrap_bare_math(text: str) -> str:  # type: ignore
        return text


def normalize_latex(text: str) -> str:
    """Приводим формулы к виду, который рендерит KaTeX на странице задач дня:
    \\( \\) -> $ $, \\[ \\] -> $$ $$, чиним непарные $, затем wrap_bare_math."""
    if not text:
        return ''
    t = str(text)
    t = t.replace('\\(', '$').replace('\\)', '$')
    t = t.replace('\\[', '$$').replace('\\]', '$$')
    t = re.sub(r'\$\$\s*\$\$', '', t)
    # непарный одиночный $ — убираем последний
    singles = len(re.findall(r'(?<!\$)\$(?!\$)', t))
    if singles % 2 == 1:
        idx = t.rfind('$')
        if idx >= 0:
            t = t[:idx] + t[idx + 1:]
    # \frac12 -> \frac{1}{2}
    t = re.sub(r'\\frac(\d)(\d)', r'\\frac{\1}{\2}', t)
    try:
        t = wrap_bare_math(t)
    except Exception:
        pass
    return t.strip()


def latex_ok(text: str) -> bool:
    """Грубая проверка: парность $ и фигурных скобок."""
    if text is None:
        return True
    t = str(text)
    if len(re.findall(r'(?<!\$)\$(?!\$)', t)) % 2 != 0:
        return False
    return t.count('{') == t.count('}')


def process_task(task: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(task)
    out['statement'] = normalize_latex(task.get('statement') or task.get('task_text') or '')
    out['answer'] = (str(task.get('answer') or '')).strip()
    out['solution'] = normalize_latex(task.get('solution') or '')
    hints: List[str] = []
    for h in (task.get('hints') or [])[:3]:
        if isinstance(h, str) and h.strip():
            hints.append(normalize_latex(h))
    out['hints'] = hints
    out['latex_ok'] = latex_ok(out['statement']) and latex_ok(out['solution'])
    return out

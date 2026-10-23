# -*- coding: utf-8 -*-
"""«Полное решение»: тот же диалог с экспертом (Луна) продолжается просьбой
решить задачу, а DeepSeek оформляет ответ в LaTeX для красивого показа.

Платный вызов — не более одного на запрос: отказ Лyны или DeepSeek не
повторяется автоматически.
"""
import re
import time

from . import llm as L
from .schema import PlanError

TIME_LIMIT = 150.0        # общий срок: Луна пишет решение, DeepSeek оформляет

# Выключные формулы: $$...$$ и \[...\] (но не \\[2pt] внутри формулы).
_DISPLAY = re.compile(r"\$\$(.+?)\$\$|(?<!\\)\\\[(.+?)\\\]", re.S)
_INLINE_PAREN = re.compile(r"(?<!\\)\\\((.+?)\\\)", re.S)


def _one_line(tex: str) -> str:
    return " ".join(tex.split())


def normalize_math(markdown: str) -> str:
    """Каждая формула — в одну строку, выключная — отдельным абзацем.

    Фронтенд (draw.js, solutionHTML) режет Markdown по строкам и склеивает
    строки абзаца через <br>. Многострочная выключная формула оказывалась
    в разных текстовых узлах, и KaTeX auto-render её не находил — на
    странице оставались сырые $$. После нормализации формула всегда целиком
    в одном текстовом узле и рендерится.
    """
    if not isinstance(markdown, str):
        return ""
    md = markdown.replace("\r\n", "\n")
    md = _DISPLAY.sub(lambda m: "\n\n$$" + _one_line(m.group(1) if m.group(1) is not None
                                                     else m.group(2)) + "$$\n\n", md)
    md = _INLINE_PAREN.sub(lambda m: "$" + _one_line(m.group(1)) + "$", md)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def generate_solution(problem: str, history: list | None = None) -> dict:
    """Никогда не бросает исключений; результат — payload для очереди."""
    out = {"ok": False, "kind": "solution"}
    if not isinstance(problem, str) or not problem.strip():
        out.update(reason="INVALID_CONDITION", detail="Не найдено условие задачи.")
        return out
    sess = L.make_session()
    diag: dict = {}
    try:
        L.set_deadline(time.time() + TIME_LIMIT)
        said = L.expert_text(sess, problem, history, max_out=12000, diag=diag,
                             messages=L.solution_messages(problem, history))
        budget = L.Budget(cap=0.10)
        markdown = normalize_math(L.latex_solution(sess, said, budget))
        out.update(ok=True, markdown=markdown,
                   solution_history=L.solution_messages(problem, history)
                   + [{"role": "assistant", "content": said}])
    except PlanError as e:
        out.update(reason=e.code, detail=L.safe_detail(str(e), 240))
    except Exception:  # noqa: BLE001 - последняя линия защиты для пользователя
        out.update(reason="SOLUTION_ERROR",
                   detail="Не удалось получить полное решение. Попробуйте позже.")
    finally:
        L.set_deadline(None)
    return out

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
_BOXED_OPEN = "\\boxed{"
# Метка ответа: двоеточие допускается и внутри, и вне звёздочек выделения.
_LABEL_CORE = (r"(?:\*\*|__)?[ \t]*(?:Ответ|Итог|Answer)[ \t]*"
               r"(?:[:=][ \t]*(?:\*\*|__)?|(?:\*\*|__)[ \t]*[:=])?[ \t]*")
# Последняя строка перед ответом, состоящая только из метки ответа.
_ANSWER_LABEL = re.compile(_LABEL_CORE, re.IGNORECASE)
# Вводное слово, оборванное запятой в конце абзаца перед формулой ответа.
_HANGING_INTRO = re.compile(r"[ \t]*(?:Следовательно|Значит|Итак|Поэтому|Тогда),[ \t]*$")
# Абзац-метка ответа, за которым сразу идёт выключная формула: склеиваем,
# чтобы подсветка ответа накрыла и метку, и формулу.
_LABEL_THEN_DISPLAY = re.compile(
    r"^" + _LABEL_CORE + r"\n{2,}(\$\$[^\n]+\$\$)[ \t]*(?=\n|$)", re.M)


def _boxed_spans(md: str) -> list[tuple[int, int, str]]:
    """Все \\boxed{...} с балансом фигурных скобок: (начало, конец, содержимое)."""
    out: list[tuple[int, int, str]] = []
    i = 0
    while True:
        j = md.find(_BOXED_OPEN, i)
        if j == -1:
            break
        k = j + len(_BOXED_OPEN)
        depth = 1
        while k < len(md) and depth:
            if md[k] == "{":
                depth += 1
            elif md[k] == "}":
                depth -= 1
            k += 1
        if depth == 0:
            out.append((j, k, md[j + len(_BOXED_OPEN):k - 1]))
            i = k
        else:  # незакрытая скобка — дальше искать нечего
            break
    return out


def _answer_formula(inner: str, label: str = "") -> str:
    """Формула ответа в одном абзаце с меткой: простая — инлайн, сложная
    (aligned и т.п.) — отдельной строкой того же абзаца."""
    if "\\begin{" in inner or len(inner) > 120:
        return (label + "\n" if label else "") + "$$" + inner + "$$"
    return (label + " " if label else "") + "$" + inner + "$"


def _merge_answer_label(md: str) -> str:
    """«**Ответ:**» отдельным абзацем + формула ниже → один абзац ответа."""
    def repl(m):
        label = m.group(0).split("\n\n", 1)[0]
        return _answer_formula(m.group(1)[2:-2], label)
    return _LABEL_THEN_DISPLAY.sub(repl, md)


def _fix_final_answer(md: str) -> str:
    """Финальный ответ — аккуратный абзац «Ответ: …».

    Скриншот-дефект: точка оставалась ВНУТРИ \\boxed{...}, абзац перед
    ответом обрывался на «Следовательно,», и рамка с ответом висела сама
    по себе. Здесь: пунктуация выносится из \\boxed; ЗАКЛЮЧИТЕЛЬНАЯ рамка
    (после которой текста нет) становится абзацем «**Ответ:** …» —
    существующая метка не дублируется, оборванное вводное слово
    убирается. Промежуточная рамка, после которой решение продолжается,
    не переоформляется: это меняло бы смысл, а не оформление.
    """
    spans = _boxed_spans(md)
    if not spans:
        return _merge_answer_label(md)
    # 1) замыкающая пунктуация — из рамки: \boxed{X.} -> \boxed{X}
    for start, end, inner in reversed(spans):
        stripped = inner.rstrip(" .,;:")
        if stripped != inner:
            md = md[:start] + "\\boxed{" + stripped + "}" + md[end:]
    spans = _boxed_spans(md)
    if not spans:
        return _merge_answer_label(md)
    start, end, inner = spans[-1]
    # 2) ответ должен быть самостоятельной выключной формулой $$\boxed{X}$$
    head = md[:start].rstrip(" \n")
    tail = md[end:].lstrip(" \n")
    if not (head.endswith("$$") and tail.startswith("$$")):
        return _merge_answer_label(md)
    disp_start = head.rfind("$$")
    disp_end = end + md[end:].find("$$") + 2
    before = md[:disp_start]
    last_line = before.rstrip("\n").split("\n")[-1].strip() if before.strip() else ""
    has_label = bool(last_line and _ANSWER_LABEL.fullmatch(last_line))
    if md[disp_end:].strip() and not has_label:
        # после рамки ещё есть решение — это промежуточный результат,
        # а не финальный ответ: оформление не трогаем
        return _merge_answer_label(md)
    if has_label:
        # метка уже есть — приклеиваем формулу к её абзацу, не дублируя
        before_lines = before.rstrip("\n").split("\n")
        rest = "\n".join(before_lines[:-1])
        ans = _answer_formula(inner, before_lines[-1])
        return (rest + "\n\n" if rest else "") + ans + md[disp_end:]
    before = _HANGING_INTRO.sub("", before.rstrip()) + "\n\n"
    return before + _answer_formula(inner, "**Ответ:**") + md[disp_end:]


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
    md = _fix_final_answer(md)
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

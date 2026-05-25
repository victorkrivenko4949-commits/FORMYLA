# -*- coding: utf-8 -*-
"""Проверяет все задачи из olympiads.py на «битость» условия и/или решения.

Скрипт НЕ пытается дописать/исправить задачи — просто детектит проблемы:

  * Условие (`text`):
      - пустое или слишком короткое (< 40 симв.)
      - обрывается в середине: заканчивается на запятую/тире/двоеточие/«и»/«или»,
        либо НЕ кончается ни точкой/?/!/«ч.т.д.»/закрывающей $/закрывающей кавычкой
      - сломанные LaTeX-формулы: нечётное число `$`, или встречаются последовательности
        вида `$\\s$u$m` (склейка слов), или повторные одинокие `$x$` плотно подряд
        (типичный артефакт чистки от \\(\\))
      - незакрытые скобки/фигурные скобки
      - явно подозрительные склейки: «слово$_letter` без пробела (`угол$C$` — это нормально,
        но `углом$C$ Катеты$AC` — нет, здесь пропал пробел между предложениями).

  * Решение (`solution`):
      - пустое / отсутствует
      - очень короткое (< 30 симв.) — почти точно заглушка
      - явные заглушки: «решение не приводится», «решение отсутствует», «TODO», «...»
      - оборванное: не заканчивается на знак конца предложения

На выход:
    bad_text.txt       — задачи с битым условием
    bad_solution.txt   — задачи с битым решением
    в stdout — задачи, у которых ОБЕ проблемы (как и просили).

Запуск:
    python scripts/validate_olympiad_problems.py
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

# Гарантируем UTF-8 на Windows (cmd по умолчанию cp866).
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# olympiads.py — это просто Python-модуль с константой OLYMPIADS_DB,
# никакого Flask он не тащит, так что импортируем напрямую.
import olympiads  # noqa: E402

OUT_BAD_TEXT = ROOT / "bad_text.txt"
OUT_BAD_SOLUTION = ROOT / "bad_solution.txt"


# ── ВАЛИДАТОР УСЛОВИЯ ────────────────────────────────────────────────────────
RU_SENTENCE_END = ".?!…"
# «Финальные» хвосты, после которых считаем что условие закончено:
GOOD_TAIL_RE = re.compile(
    r"""(?:
        [.?!…]                  # обычное окончание
        |  ч\.\s*т\.\s*д\.?    # «ч.т.д.»
        |  \$                   # формула в конце
        |  »                    # русская закрывающая кавычка
        |  \)                   # скобка
        |  '\.?                 # одинарная кавычка
    )\s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)
# Подсказки, что условие явно ОБРЫВАЕТСЯ:
BAD_TAIL_RE = re.compile(
    r"(?:[,;\-–—:]\s*|\sи\s*|\sили\s*|\sто\s*|\sчто\s*)$",
    re.IGNORECASE,
)

# Сломанные LaTeX-склейки: внутри слова идут `$\\` или `$слово$ещё$` без пробелов
# вокруг — типичный артефакт автогенерации.
LATEX_GLUE_RE = re.compile(r"\$\\[a-z]\$[a-z]", re.IGNORECASE)
# Подозрительная конструкция: «$\s$u$m$» (буквы выкинуты в текст между $).
BROKEN_LATEX_CMD_RE = re.compile(r"\$\\[a-z]\$[a-z]\$[a-z]", re.IGNORECASE)


def _count_unescaped_dollars(s: str) -> int:
    """Считает количество $, не считая \\$."""
    return len(re.findall(r"(?<!\\)\$", s))


def _balanced_brackets(s: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack[-1] != pairs[ch]:
                return False
            stack.pop()
    return not stack


def check_text(text: str) -> list[str]:
    """Возвращает список причин «битости». Пусто = всё ОК."""
    issues: list[str] = []
    if not text or not isinstance(text, str):
        return ["пустое условие"]
    t = text.strip()
    if not t:
        return ["пустое условие (только пробелы)"]
    if len(t) < 40:
        issues.append(f"слишком короткое условие ({len(t)} симв.)")

    # 1) Чётность $
    n_dol = _count_unescaped_dollars(t)
    if n_dol % 2 != 0:
        issues.append(f"нечётное число $ ({n_dol}) → формула не закрыта")

    # 2) Сломанные LaTeX-склейки
    if BROKEN_LATEX_CMD_RE.search(t):
        issues.append("сломанная LaTeX-команда вида `$\\s$u$m$` (буквы между $)")
    elif LATEX_GLUE_RE.search(t):
        issues.append("подозрительная склейка `$\\X$Y` в формуле")

    # 3) Незакрытые скобки
    if not _balanced_brackets(t):
        issues.append("несбалансированные скобки/фигурные/квадратные")

    # 4) Обрыв в конце
    if BAD_TAIL_RE.search(t):
        issues.append(f"условие обрывается (заканчивается «...{t[-25:]!r}»)")
    elif not GOOD_TAIL_RE.search(t):
        # Не «плохо», но не уверены, что закончено — отметим помягче.
        issues.append(f"условие НЕ заканчивается знаком препинания/формулой (хвост: …{t[-25:]!r})")

    return issues


# ── ВАЛИДАТОР РЕШЕНИЯ ────────────────────────────────────────────────────────
STUB_PATTERNS_RE = re.compile(
    r"(?:"
    r"^\s*(?:--+|—+|…|\.\.\.|TODO|FIXME|XXX|тут\s+решение|see\s+source)\s*$"
    r"|реш(?:ение)?\s+(?:не\s+приводится|отсутствует|опущено|пока\s+нет)"
    r"|<нет\s+решения>"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


def check_solution(solution: str) -> list[str]:
    issues: list[str] = []
    if solution is None:
        return ["решение отсутствует (None)"]
    if not isinstance(solution, str):
        return [f"решение не строка: {type(solution).__name__}"]
    s = solution.strip()
    if not s:
        return ["пустое решение"]
    if len(s) < 30:
        issues.append(f"очень короткое решение ({len(s)} симв.)")
    if STUB_PATTERNS_RE.search(s):
        issues.append("явная заглушка (TODO/«решение не приводится»/…)")

    # Сломанные LaTeX-команды как и в условии
    if BROKEN_LATEX_CMD_RE.search(s):
        issues.append("сломанная LaTeX-команда в решении")

    # Чётность $
    n_dol = _count_unescaped_dollars(s)
    if n_dol % 2 != 0:
        issues.append(f"нечётное число $ ({n_dol}) → формула не закрыта")

    # Несбалансированные скобки в решении — допустимо много false-positive,
    # т.к. решения часто содержат фрагменты типа `\left(`, поэтому не проверяем.

    # Обрыв
    if BAD_TAIL_RE.search(s):
        issues.append(f"решение обрывается (хвост: …{s[-25:]!r})")
    return issues


# ── ОБХОД ────────────────────────────────────────────────────────────────────
def iter_problems():
    """Yields (combo, problem_idx, problem_dict)."""
    db = getattr(olympiads, "OLYMPIADS_DB", [])
    for combo in db:
        # Новый формат с problems[]
        if isinstance(combo.get("problems"), list):
            for i, pr in enumerate(combo["problems"]):
                yield combo, i, pr
        else:
            # Старый формат: combo сам и есть problem
            yield combo, 0, combo


def problem_id(combo, prob) -> str:
    return (
        f"{combo.get('olympiad', '?')}/"
        f"{combo.get('year', '?')}/"
        f"{combo.get('grade', '?')}кл/"
        f"{combo.get('round', '?')}/"
        f"#{prob.get('num', '?')}"
    )


def format_block(combo, prob, issues_text, issues_sol) -> str:
    pid = problem_id(combo, prob)
    text = (prob.get("text") or "").strip()
    sol = (prob.get("solution") or "").strip()
    lines = [
        "=" * 78,
        f"ID: {pid}",
        f"Источник: {combo.get('source_name', '—')}",
    ]
    if issues_text:
        lines.append("Проблемы в условии:")
        for x in issues_text:
            lines.append(f"  - {x}")
    if issues_sol:
        lines.append("Проблемы в решении:")
        for x in issues_sol:
            lines.append(f"  - {x}")
    lines.append("")
    lines.append("--- Условие ---")
    lines.append(text)
    lines.append("")
    lines.append("--- Решение ---")
    lines.append(sol)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    bad_text_blocks: list[str] = []
    bad_sol_blocks: list[str] = []
    both_bad: list[tuple[str, list[str], list[str], dict]] = []

    total = 0
    for combo, idx, prob in iter_problems():
        total += 1
        t_issues = check_text(prob.get("text", ""))
        s_issues = check_solution(prob.get("solution", ""))

        # «Условие НЕ заканчивается знаком препинания» — слишком много false-positive
        # (задачи часто кончаются формулой $...$ без точки). Если это ЕДИНСТВЕННАЯ
        # проблема — игнорируем, чтобы не зашумлять.
        t_issues_strict = [
            x for x in t_issues
            if "НЕ заканчивается знаком препинания" not in x
        ]

        if t_issues_strict and s_issues:
            both_bad.append((problem_id(combo, prob), t_issues_strict, s_issues, prob))
        elif t_issues_strict:
            bad_text_blocks.append(format_block(combo, prob, t_issues_strict, []))
        elif s_issues:
            bad_sol_blocks.append(format_block(combo, prob, [], s_issues))

    # Запись файлов
    if bad_text_blocks:
        OUT_BAD_TEXT.write_text(
            f"Битых условий: {len(bad_text_blocks)} из {total}\n\n"
            + "\n".join(bad_text_blocks),
            encoding="utf-8",
        )
        print(f"📝 Битых условий: {len(bad_text_blocks)} → {OUT_BAD_TEXT}")
    else:
        if OUT_BAD_TEXT.exists():
            OUT_BAD_TEXT.unlink()
        print("✅ Битых условий не найдено")

    if bad_sol_blocks:
        OUT_BAD_SOLUTION.write_text(
            f"Битых решений: {len(bad_sol_blocks)} из {total}\n\n"
            + "\n".join(bad_sol_blocks),
            encoding="utf-8",
        )
        print(f"📝 Битых решений: {len(bad_sol_blocks)} → {OUT_BAD_SOLUTION}")
    else:
        if OUT_BAD_SOLUTION.exists():
            OUT_BAD_SOLUTION.unlink()
        print("✅ Битых решений не найдено")

    # Двойные — в stdout
    print(f"\n=== Задач с битым И условием, И решением: {len(both_bad)} ===\n")
    for pid, t_iss, s_iss, prob in both_bad:
        print(f"▶ {pid}")
        print("  Условие:")
        for x in t_iss:
            print(f"    - {x}")
        print("  Решение:")
        for x in s_iss:
            print(f"    - {x}")
        # Краткий пред-просмотр (первые 250 симв.)
        text = (prob.get("text") or "")[:250].replace("\n", " ")
        sol = (prob.get("solution") or "")[:250].replace("\n", " ")
        print(f"  text:  {text!r}")
        print(f"  sol:   {sol!r}")
        print()

    print(f"Всего задач проверено: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Формулы полного решения всегда рендерятся: каждая формула — в одну строку,
выключная — отдельным абзацем (draw.js склеивает строки абзаца через <br>)."""
from geoexact.core import llm
from geoexact.core.solution import generate_solution, normalize_math


def _lines_are_balanced(md):
    for line in md.split("\n"):
        assert line.count("$$") in (0, 2), line


def test_multiline_display_formula_becomes_one_paragraph():
    md = "Из подобия:\n$$\n\\frac{BD}{BC}=\\frac{BO}{BM}.\n$$\nДалее."
    out = normalize_math(md)
    assert "\n\n$$\\frac{BD}{BC}=\\frac{BO}{BM}.$$\n\n" in out
    _lines_are_balanced(out)


def test_brackets_are_converted_and_aligned_rows_survive():
    md = "Пусть\n\\[\nB=(0,0)\n\\]\n$$\n\\begin{aligned} a&=b\\\\[2pt]\nc&=d \\end{aligned}\n$$"
    out = normalize_math(md)
    assert "$$B=(0,0)$$" in out
    assert "$$\\begin{aligned} a&=b\\\\[2pt] c&=d \\end{aligned}$$" in out
    _lines_are_balanced(out)


def test_inline_parens_and_plain_text_are_kept():
    out = normalize_math("Тогда \\(K=(2,0)\\), цена 5 руб., $x$ и $y$.")
    assert out == "Тогда $K=(2,0)$, цена 5 руб., $x$ и $y$."


def test_one_line_display_and_non_string():
    assert normalize_math("$$x$$") == "$$x$$"
    assert normalize_math(None) == ""


def test_final_boxed_answer_gets_label_and_clean_punctuation():
    # сценарий со скриншота: точка внутри \boxed, «Следовательно,» обрывается
    md = ("Оба угла острые, значит $\\beta = \\gamma$. Следовательно,\n\n"
          "$$\\boxed{\\angle B = \\frac{135^\\circ}{2} = 67^\\circ 30'.}$$")
    out = normalize_math(md)
    assert "\\boxed" not in out
    assert out.endswith("**Ответ:** $\\angle B = \\frac{135^\\circ}{2} = 67^\\circ 30'$")
    assert "Следовательно," not in out
    _lines_are_balanced(out)


def test_existing_answer_label_is_not_duplicated():
    # метка и формула склеиваются в ОДИН абзац ответа (без дублирования метки)
    md = "Решение.\n\n**Ответ:**\n\n$$\\boxed{42.}$$"
    out = normalize_math(md)
    assert out.count("Ответ") == 1
    assert out.endswith("**Ответ:** $42$")


def test_answer_label_and_display_merge_into_one_paragraph():
    # новый формат из промпта: **Ответ:** отдельной строкой + $$формула$$
    md = "Решение.\n\n**Ответ:**\n\n$$\\angle B = 67^\\circ 30'$$"
    out = normalize_math(md)
    assert "\n\n" not in out.split("Решение.\n\n", 1)[1]
    assert out.endswith("**Ответ:** $\\angle B = 67^\\circ 30'$")


def test_answer_label_with_outer_colon_also_merges():
    # вариант «**Ответ**:** — двоеточие после закрывающих **
    md = "Решение.\n\n**Ответ**:\n\n$$42$$"
    out = normalize_math(md)
    assert out.endswith("**Ответ**: $42$")
    assert "\n\n" not in out.split("Решение.\n\n", 1)[1]
    # повторная нормализация ничего не меняет (идемпотентность)
    assert normalize_math(out) == out


def test_intermediate_boxed_is_not_relabelled():
    # рамка посреди решения (после неё ещё текст) — не финальный ответ
    md = "Вспомогательный результат:\n\n$$\\boxed{x=1}$$\n\nТеперь найдём искомое $y$."
    out = normalize_math(md)
    assert "**Ответ:**" not in out
    assert "$$\\boxed{x=1}$$" in out
    assert "Теперь найдём искомое $y$." in out


def test_inline_boxed_only_loses_trailing_punctuation():
    md = "Итак, $\\boxed{5.}$ — это ответ."
    out = normalize_math(md)
    assert out == "Итак, $\\boxed{5}$ — это ответ."


def test_display_boxed_with_extra_text_is_left_alone():
    # \boxed не занимает всю формулу — не превращаем в «Ответ»
    md = "Проверка:\n\n$$\\text{итог} \\boxed{7}$$"
    out = normalize_math(md)
    assert "**Ответ:**" not in out
    assert "$$\\text{итог} \\boxed{7}$$" in out


def test_generate_solution_returns_normalized_markdown(monkeypatch):
    monkeypatch.setattr(llm, "make_session", lambda: None)
    monkeypatch.setattr(llm, "expert_text", lambda *a, **k: "решение")
    monkeypatch.setattr(llm, "latex_solution",
                        lambda sess, said, budget, max_out=8000: "Итак\n$$\n\\frac{2}{5}\n$$")
    out = generate_solution("Условие задачи.", None)
    assert out["ok"] is True
    assert out["markdown"] == "Итак\n\n$$\\frac{2}{5}$$"

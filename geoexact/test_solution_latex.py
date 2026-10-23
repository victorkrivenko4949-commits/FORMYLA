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


def test_generate_solution_returns_normalized_markdown(monkeypatch):
    monkeypatch.setattr(llm, "make_session", lambda: None)
    monkeypatch.setattr(llm, "expert_text", lambda *a, **k: "решение")
    monkeypatch.setattr(llm, "latex_solution",
                        lambda sess, said, budget, max_out=8000: "Итак\n$$\n\\frac{2}{5}\n$$")
    out = generate_solution("Условие задачи.", None)
    assert out["ok"] is True
    assert out["markdown"] == "Итак\n\n$$\\frac{2}{5}$$"

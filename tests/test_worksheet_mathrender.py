# -*- coding: utf-8 -*-
"""Этап 5: рендер формул для PDF через matplotlib.mathtext (настоящие дроби/корни/индексы)."""
import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("PIL")

from teacher.worksheets import mathrender  # noqa: E402


@pytest.mark.parametrize("latex", [
    r"\frac{n^2+1}{2} \cdot x^{10} \le \sqrt{a_1}",
    r"\dfrac{a}{b}", r"\angle ABC = 90^\circ", r"\text{см}^2", r"\mathrm{НОД}(a,b)",
    r"x_{1,2} = \frac{-b \pm \sqrt{b^2-4ac}}{2a}", r"a \equiv b \pmod{7}", r"\sqrt[3]{27}",
    r"\sum_{k=1}^{n} k^2", r"\left(\frac{1}{2}\right)^n",
])
def test_render_png(latex):
    png, w, h, d = mathrender.render_png(latex, fontsize=11)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert w > 0 and h > 0 and d >= 0


def test_paragraph_html_inline_and_display(tmp_path):
    html, had, warns = mathrender.paragraph_html(
        r"Пусть $\frac{a}{b}$ и $$x = \frac{1}{2}$$ тогда <ok> & $\foo{bad}$.", str(tmp_path), fontsize=11)
    assert had
    assert html.count("<img ") == 2 and 'valign="-' in html
    assert "<br/>" in html                     # display-формула на отдельной строке
    assert "&lt;ok&gt; &amp;" in html          # текст экранирован
    assert len(warns) == 1 and "foo" in warns[0]  # битая формула -> fallback + warning
    assert len(list(tmp_path.iterdir())) == 2

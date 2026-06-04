# -*- coding: utf-8 -*-
"""
Утилита для безопасного рендеринга Markdown-полей раздела «Олимпиады».

Особенности:
  * Сохраняет LaTeX-формулы ($...$, $$...$$, \\(...\\), \\[...\\]) — MathJax
    отрендерит их на клиенте (CDN подключается в `base.html`).
  * Поддерживает базовые расширения Markdown: списки, заголовки, код-блоки,
    таблицы, переносы строк.
  * Возвращает `markupsafe.Markup`, чтобы Jinja не экранировала результат.

Использование:
    from services.md_render import md_render
    app.jinja_env.filters['md_render'] = md_render

В шаблоне:
    {{ task.condition_md | md_render }}
"""

from __future__ import annotations

import re

import markdown as _markdown
from markupsafe import Markup


# Регексы для защиты LaTeX-блоков от markdown-парсера.
# Порядок важен: $$ ... $$, \[ ... \], \( ... \), $ ... $ (последний — самый жадный).
_LATEX_PATTERNS = [
    re.compile(r'\$\$(.+?)\$\$', re.DOTALL),    # $$...$$
    re.compile(r'\\\[(.+?)\\\]', re.DOTALL),    # \[...\]
    re.compile(r'\\\((.+?)\\\)', re.DOTALL),    # \(...\)
    re.compile(r'\$([^\$\n]+?)\$'),             # $...$
]

_MD_EXTENSIONS = [
    'extra',          # tables, fenced_code, footnotes, ...
    'sane_lists',
    'nl2br',
]

# Дополнительные параметры для рендеринга Markdown.
# unsafe_allow_raw_html=True — необходим для inline-SVG в worked_example_md.
_MD_EXTENSION_CONFIGS = {
    'extra': {
        'markdown.extensions.extra': {
            'unsafe_allow_raw_html': True,
        },
    },
}


def _protect_latex(text: str) -> tuple[str, list[str]]:
    """Заменить LaTeX-фрагменты на плейсхолдеры, вернуть (текст, список фрагментов)."""
    placeholders: list[str] = []

    def _make_repl(pattern_idx: int):
        def _repl(m: re.Match) -> str:
            idx = len(placeholders)
            # Восстановим исходный синтаксис, чтобы MathJax увидел его в HTML.
            full = m.group(0)
            placeholders.append(full)
            # Уникальный плейсхолдер без markdown-спецсимволов.
            return f'@@LATEXBLOCK_{pattern_idx}_{idx}@@'
        return _repl

    for i, pat in enumerate(_LATEX_PATTERNS):
        text = pat.sub(_make_repl(i), text)
    return text, placeholders


def _restore_latex(html: str, placeholders: list[str]) -> str:
    """Подставить LaTeX-фрагменты обратно в готовый HTML."""
    for i, pat in enumerate(_LATEX_PATTERNS):
        # У нас есть плейсхолдеры вида @@LATEXBLOCK_<i>_<idx>@@.
        # Идём по индексам этого паттерна.
        pass
    # Простой обратный обход: ищем по индексу глобального списка.
    for idx, original in enumerate(placeholders):
        for i in range(len(_LATEX_PATTERNS)):
            ph = f'@@LATEXBLOCK_{i}_{idx}@@'
            if ph in html:
                html = html.replace(ph, original)
                break
    return html


def md_render(text: str | None) -> Markup:
    """Отрендерить Markdown в безопасный HTML, сохраняя LaTeX-формулы.

    На вход принимает строку (или None — вернёт пустую Markup).  На выходе —
    `markupsafe.Markup`, который Jinja не экранирует.

    Поддерживает inline-SVG и другой raw HTML за счёт
    `unsafe_allow_raw_html=True` в конфиге расширения `extra`.
    """
    if not text:
        return Markup('')

    protected, placeholders = _protect_latex(text)
    html = _markdown.markdown(
        protected,
        extensions=_MD_EXTENSIONS,
        extension_configs=_MD_EXTENSION_CONFIGS,
        output_format='html5',
    )
    html = _restore_latex(html, placeholders)
    return Markup(html)

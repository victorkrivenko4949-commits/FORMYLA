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
      # nl2br убран: одиночные переносы строк делали текст и формулы "расплывчатыми"
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


# Регексы для зачистки <br> рядом с display-math плейсхолдером.
# Расширение nl2br Markdown превращает все \n в <br>, в том числе внутри
# $$...$$ блоков — что ломает KaTeX (он видит обрыв формулы по <br>).
# Мы убираем <br>\n до и после плейсхолдера ПЕРЕД восстановлением LaTeX.
_RE_BR_AROUND_PH = re.compile(r'(?:<br\s*/?>\s*)*(@@LATEXBLOCK_\d+_\d+@@)(?:\s*<br\s*/?>)*')


def _restore_latex(html: str, placeholders: list[str]) -> str:
    """Подставить LaTeX-фрагменты обратно в готовый HTML.

    Дополнительно вычищает <br> теги, которые nl2br расширение втыкает
    вокруг плейсхолдеров — иначе они попадают внутрь $$...$$ блока
    и KaTeX обрывает рендеринг формулы.
    """
    # 1) Убрать <br> до/после плейсхолдеров (особенно критично для $$...$$).
    html = _RE_BR_AROUND_PH.sub(r'\1', html)

    # 2) Подставить LaTeX обратно.
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

    PR math_normalize (инцидент 2026-06-10):
    Прогоняем текст через :func:`services.math_text_normalizer.normalize_math_text`
    ПЕРЕД защитой LaTeX. Это автоматически оборачивает «голые» математические
    выражения (`x^2`, `sqrt(x)`, `{x+y=1; x*y=2}`) в `$...$`, чтобы KaTeX/MathJax
    отрендерил их как формулы, а не сырой ASCII.
    """
    if not text:
        return Markup('')

    # ── Math auto-normalize ──
    try:
        from services.math_text_normalizer import normalize_math_text
        text = normalize_math_text(text)
    except Exception:
        # Любая ошибка нормализатора — не валим страницу, рендерим как есть.
        pass

    protected, placeholders = _protect_latex(text)
    html = _markdown.markdown(
        protected,
        extensions=_MD_EXTENSIONS,
        extension_configs=_MD_EXTENSION_CONFIGS,
        output_format='html5',
    )
    html = _restore_latex(html, placeholders)
    return Markup(html)

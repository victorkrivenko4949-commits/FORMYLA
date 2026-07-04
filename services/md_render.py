# -*- coding: utf-8 -*-
"""
РЈС‚РёР»РёС‚Р° РґР»СЏ Р±РµР·РѕРїР°СЃРЅРѕРіРѕ СЂРµРЅРґРµСЂРёРЅРіР° Markdown-РїРѕР»РµР№ СЂР°Р·РґРµР»Р° В«РћР»РёРјРїРёР°РґС‹В».

РћСЃРѕР±РµРЅРЅРѕСЃС‚Рё:
  * РЎРѕС…СЂР°РЅСЏРµС‚ LaTeX-С„РѕСЂРјСѓР»С‹ ($...$, $$...$$, \\(...\\), \\[...\\]) вЂ” MathJax
    РѕС‚СЂРµРЅРґРµСЂРёС‚ РёС… РЅР° РєР»РёРµРЅС‚Рµ (CDN РїРѕРґРєР»СЋС‡Р°РµС‚СЃСЏ РІ `base.html`).
  * РџРѕРґРґРµСЂР¶РёРІР°РµС‚ Р±Р°Р·РѕРІС‹Рµ СЂР°СЃС€РёСЂРµРЅРёСЏ Markdown: СЃРїРёСЃРєРё, Р·Р°РіРѕР»РѕРІРєРё, РєРѕРґ-Р±Р»РѕРєРё,
    С‚Р°Р±Р»РёС†С‹, РїРµСЂРµРЅРѕСЃС‹ СЃС‚СЂРѕРє.
  * Р’РѕР·РІСЂР°С‰Р°РµС‚ `markupsafe.Markup`, С‡С‚РѕР±С‹ Jinja РЅРµ СЌРєСЂР°РЅРёСЂРѕРІР°Р»Р° СЂРµР·СѓР»СЊС‚Р°С‚.

РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ:
    from services.md_render import md_render
    app.jinja_env.filters['md_render'] = md_render

Р’ С€Р°Р±Р»РѕРЅРµ:
    {{ task.condition_md | md_render }}
"""

from __future__ import annotations

import re

import markdown as _markdown
from markupsafe import Markup


# Р РµРіРµРєСЃС‹ РґР»СЏ Р·Р°С‰РёС‚С‹ LaTeX-Р±Р»РѕРєРѕРІ РѕС‚ markdown-РїР°СЂСЃРµСЂР°.
# РџРѕСЂСЏРґРѕРє РІР°Р¶РµРЅ: $$ ... $$, \[ ... \], \( ... \), $ ... $ (РїРѕСЃР»РµРґРЅРёР№ вЂ” СЃР°РјС‹Р№ Р¶Р°РґРЅС‹Р№).
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

# Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹Рµ РїР°СЂР°РјРµС‚СЂС‹ РґР»СЏ СЂРµРЅРґРµСЂРёРЅРіР° Markdown.
# unsafe_allow_raw_html=True вЂ” РЅРµРѕР±С…РѕРґРёРј РґР»СЏ inline-SVG РІ worked_example_md.
_MD_EXTENSION_CONFIGS = {
    'extra': {
        'markdown.extensions.extra': {
            'unsafe_allow_raw_html': True,
        },
    },
}


def _protect_latex(text: str) -> tuple[str, list[str]]:
    """Р—Р°РјРµРЅРёС‚СЊ LaTeX-С„СЂР°РіРјРµРЅС‚С‹ РЅР° РїР»РµР№СЃС…РѕР»РґРµСЂС‹, РІРµСЂРЅСѓС‚СЊ (С‚РµРєСЃС‚, СЃРїРёСЃРѕРє С„СЂР°РіРјРµРЅС‚РѕРІ)."""
    placeholders: list[str] = []

    def _make_repl(pattern_idx: int):
        def _repl(m: re.Match) -> str:
            idx = len(placeholders)
            # Р’РѕСЃСЃС‚Р°РЅРѕРІРёРј РёСЃС…РѕРґРЅС‹Р№ СЃРёРЅС‚Р°РєСЃРёСЃ, С‡С‚РѕР±С‹ MathJax СѓРІРёРґРµР» РµРіРѕ РІ HTML.
            full = m.group(0)
            placeholders.append(full)
            # РЈРЅРёРєР°Р»СЊРЅС‹Р№ РїР»РµР№СЃС…РѕР»РґРµСЂ Р±РµР· markdown-СЃРїРµС†СЃРёРјРІРѕР»РѕРІ.
            return f'@@LATEXBLOCK_{pattern_idx}_{idx}@@'
        return _repl

    for i, pat in enumerate(_LATEX_PATTERNS):
        text = pat.sub(_make_repl(i), text)
    return text, placeholders


# Р РµРіРµРєСЃС‹ РґР»СЏ Р·Р°С‡РёСЃС‚РєРё <br> СЂСЏРґРѕРј СЃ display-math РїР»РµР№СЃС…РѕР»РґРµСЂРѕРј.
# Р Р°СЃС€РёСЂРµРЅРёРµ nl2br Markdown РїСЂРµРІСЂР°С‰Р°РµС‚ РІСЃРµ \n РІ <br>, РІ С‚РѕРј С‡РёСЃР»Рµ РІРЅСѓС‚СЂРё
# $$...$$ Р±Р»РѕРєРѕРІ вЂ” С‡С‚Рѕ Р»РѕРјР°РµС‚ KaTeX (РѕРЅ РІРёРґРёС‚ РѕР±СЂС‹РІ С„РѕСЂРјСѓР»С‹ РїРѕ <br>).
# РњС‹ СѓР±РёСЂР°РµРј <br>\n РґРѕ Рё РїРѕСЃР»Рµ РїР»РµР№СЃС…РѕР»РґРµСЂР° РџР•Р Р•Р” РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёРµРј LaTeX.
_RE_BR_AROUND_PH = re.compile(r'(?:<br\s*/?>\s*)*(@@LATEXBLOCK_\d+_\d+@@)(?:\s*<br\s*/?>)*')


def _restore_latex(html: str, placeholders: list[str]) -> str:
    """РџРѕРґСЃС‚Р°РІРёС‚СЊ LaTeX-С„СЂР°РіРјРµРЅС‚С‹ РѕР±СЂР°С‚РЅРѕ РІ РіРѕС‚РѕРІС‹Р№ HTML.

    Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ РІС‹С‡РёС‰Р°РµС‚ <br> С‚РµРіРё, РєРѕС‚РѕСЂС‹Рµ nl2br СЂР°СЃС€РёСЂРµРЅРёРµ РІС‚С‹РєР°РµС‚
    РІРѕРєСЂСѓРі РїР»РµР№СЃС…РѕР»РґРµСЂРѕРІ вЂ” РёРЅР°С‡Рµ РѕРЅРё РїРѕРїР°РґР°СЋС‚ РІРЅСѓС‚СЂСЊ $$...$$ Р±Р»РѕРєР°
    Рё KaTeX РѕР±СЂС‹РІР°РµС‚ СЂРµРЅРґРµСЂРёРЅРі С„РѕСЂРјСѓР»С‹.
    """
    # 1) РЈР±СЂР°С‚СЊ <br> РґРѕ/РїРѕСЃР»Рµ РїР»РµР№СЃС…РѕР»РґРµСЂРѕРІ (РѕСЃРѕР±РµРЅРЅРѕ РєСЂРёС‚РёС‡РЅРѕ РґР»СЏ $$...$$).
    html = _RE_BR_AROUND_PH.sub(r'\1', html)

    # 2) РџРѕРґСЃС‚Р°РІРёС‚СЊ LaTeX РѕР±СЂР°С‚РЅРѕ.
    for idx, original in enumerate(placeholders):
        for i in range(len(_LATEX_PATTERNS)):
            ph = f'@@LATEXBLOCK_{i}_{idx}@@'
            if ph in html:
                html = html.replace(ph, original)
                break
    return html


def md_render(text: str | None) -> Markup:
    """РћС‚СЂРµРЅРґРµСЂРёС‚СЊ Markdown РІ Р±РµР·РѕРїР°СЃРЅС‹Р№ HTML, СЃРѕС…СЂР°РЅСЏСЏ LaTeX-С„РѕСЂРјСѓР»С‹.

    РќР° РІС…РѕРґ РїСЂРёРЅРёРјР°РµС‚ СЃС‚СЂРѕРєСѓ (РёР»Рё None вЂ” РІРµСЂРЅС‘С‚ РїСѓСЃС‚СѓСЋ Markup).  РќР° РІС‹С…РѕРґРµ вЂ”
    `markupsafe.Markup`, РєРѕС‚РѕСЂС‹Р№ Jinja РЅРµ СЌРєСЂР°РЅРёСЂСѓРµС‚.

    РџРѕРґРґРµСЂР¶РёРІР°РµС‚ inline-SVG Рё РґСЂСѓРіРѕР№ raw HTML Р·Р° СЃС‡С‘С‚
    `unsafe_allow_raw_html=True` РІ РєРѕРЅС„РёРіРµ СЂР°СЃС€РёСЂРµРЅРёСЏ `extra`.

    PR math_normalize (РёРЅС†РёРґРµРЅС‚ 2026-06-10):
    РџСЂРѕРіРѕРЅСЏРµРј С‚РµРєСЃС‚ С‡РµСЂРµР· :func:`services.math_text_normalizer.normalize_math_text`
    РџР•Р Р•Р” Р·Р°С‰РёС‚РѕР№ LaTeX. Р­С‚Рѕ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё РѕР±РѕСЂР°С‡РёРІР°РµС‚ В«РіРѕР»С‹РµВ» РјР°С‚РµРјР°С‚РёС‡РµСЃРєРёРµ
    РІС‹СЂР°Р¶РµРЅРёСЏ (`x^2`, `sqrt(x)`, `{x+y=1; x*y=2}`) РІ `$...$`, С‡С‚РѕР±С‹ KaTeX/MathJax
    РѕС‚СЂРµРЅРґРµСЂРёР» РёС… РєР°Рє С„РѕСЂРјСѓР»С‹, Р° РЅРµ СЃС‹СЂРѕР№ ASCII.
    """
    if not text:
        return Markup('')

    # в”Ђв”Ђ Math auto-normalize в”Ђв”Ђ
    try:
        from services.math_text_normalizer import normalize_math_text
        text = normalize_math_text(text)
    except Exception:
        # Р›СЋР±Р°СЏ РѕС€РёР±РєР° РЅРѕСЂРјР°Р»РёР·Р°С‚РѕСЂР° вЂ” РЅРµ РІР°Р»РёРј СЃС‚СЂР°РЅРёС†Сѓ, СЂРµРЅРґРµСЂРёРј РєР°Рє РµСЃС‚СЊ.
        pass
    # Downgrade trivial single-line $$..$$ -> inline $..$ (fixes centered/scattered symbols)     
    text = re.sub(r'\$\$([^\n]{1,40}?)\$\$', r'$\1$', text)
    protected, placeholders = _protect_latex(text)
    html = _markdown.markdown(
        protected,
        extensions=_MD_EXTENSIONS,
        extension_configs=_MD_EXTENSION_CONFIGS,
        output_format='html5',
    )
    html = _restore_latex(html, placeholders)
    return Markup(html)


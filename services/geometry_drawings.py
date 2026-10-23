# -*- coding: utf-8 -*-
"""Jinja-фильтр для вставки чертежей геометрии в HTML, отрендеренный из
``worked_example_md`` методов раздела F (ВсОШ-9).

Идея: метод F содержит подзаголовки вида
``#### Задача 1.1`` / ``#### Задача 1.2`` и т.п., которые после
рендера Markdown превращаются в ``<h4>Задача 1.1</h4>``.  Этот фильтр
после каждого такого заголовка вставляет блок ``<figure>`` с одним или
двумя SVG-чертежами (в зависимости от того, что лежит в
``static/img/vsosh9_geometry/F{code}_{n}.{m}_{k}.svg``).

Поведение:
    • Принимает (html, method_code).  Если method_code не входит в
      набор F-методов — возвращает html как есть.
    • Сканирует ``static/img/vsosh9_geometry/`` один раз (lru_cache) и
      строит карту ``{code: {(family, idx): [rel_url, ...]}}``.
    • Для каждого найденного заголовка «Задача N.M» в HTML вставляет
      контейнер с найденными SVG-картинками; если для задачи нет ни
      одного SVG — ничего не делает (карточка задачи остаётся как
      раньше, на странице coming-soon).
    • Маркап картинок: ``<figure class="oly-geo-fig">`` с одной или двумя
      ``<img>``, чтобы CSS базовой темы мог расставить их в строку
      (grid: 1fr 1fr) на десктопе и стопкой на мобиле.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Dict, List, Tuple

from flask import url_for
from markupsafe import Markup

# Корень репозитория — на два уровня выше services/.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SVG_DIR = os.path.join(_ROOT, "static", "img", "vsosh9_geometry")

# Карта (method_code, family, task_idx) -> [filename, filename, ...]
# Имена файлов: F{code}_{family}.{task}_{nr}.svg, где nr in 1..2.
_FN_RE = re.compile(
    r"^F(?P<code>\w+)_(?P<family>\d+)\.(?P<task>\d+)_(?P<nr>[12])\.svg$"
)


@lru_cache(maxsize=1)
def _scan_drawings() -> Dict[Tuple[str, int, int], List[str]]:
    out: Dict[Tuple[str, int, int], List[str]] = {}
    if not os.path.isdir(_SVG_DIR):
        return out
    for name in sorted(os.listdir(_SVG_DIR)):
        m = _FN_RE.match(name)
        if not m:
            continue
        code = "F" + m.group("code")
        fam = int(m.group("family"))
        task = int(m.group("task"))
        nr = int(m.group("nr"))
        key = (code, fam, task)
        out.setdefault(key, []).append((nr, name))
    # Sort each list by nr.
    sorted_out: Dict[Tuple[str, int, int], List[str]] = {}
    for k, v in out.items():
        sorted_out[k] = [name for _, name in sorted(v)]
    return sorted_out


# Заголовок «Задача N.M» как <h4>.  Допускаем класс / id у h4 и
# произвольный whitespace перед закрывающим >.
_TASK_HEAD_RE = re.compile(
    r"(<h4\b[^>]*>\s*Задача\s+(?P<family>\d+)\.(?P<task>\d+)[^<]*</h4>)",
    re.IGNORECASE,
)


def inject_geometry_drawings(html, method_code: str | None):
    """Inject <figure> blocks with SVG drawings after each
    ``<h4>Задача N.M</h4>`` heading."""
    if html is None or method_code is None:
        return html
    code = method_code.strip()
    if not code.startswith("F"):
        return html

    drawings = _scan_drawings()
    raw = str(html)

    def _replace(match: re.Match) -> str:
        heading = match.group(1)
        try:
            fam = int(match.group("family"))
            task = int(match.group("task"))
        except (TypeError, ValueError):
            return heading
        files = drawings.get((code, fam, task))
        if not files:
            return heading
        try:
            imgs = []
            for fname in files:
                src = url_for("static", filename="img/vsosh9_geometry/" + fname)
                imgs.append(
                    '<img class="oly-geo-img" src="%s" alt="%s, задача %d.%d, рисунок %s" loading="lazy"/>'
                    % (src, code, fam, task, fname.rsplit("_", 1)[-1].rsplit(".", 1)[0])
                )
            grid_cls = "oly-geo-fig oly-geo-fig--two" if len(files) > 1 else "oly-geo-fig"
            figure = (
                '<figure class="%s">' % grid_cls
                + "".join(imgs)
                + "</figure>"
            )
            return heading + figure
        except Exception:
            return heading

    new_html = _TASK_HEAD_RE.sub(_replace, raw)
    if isinstance(html, Markup):
        return Markup(new_html)
    return new_html

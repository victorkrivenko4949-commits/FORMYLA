"""Индексы в подписях точек: B_1, K_2, I_A, A1 -> буква с нижним индексом.

Рендер подписывает точку её именем из плана буквально: «B_1». В условиях
олимпиад индекс пишется снизу, и подпись «B_1» на чертеже выглядит как
опечатка. Модуль оборачивает render.render_svg (самым внешним слоем, после
bisector_marks + finish_svg) и переписывает ТОЛЬКО содержимое текстовых
элементов подписей точек (class="lab"): «B_1» -> «B» + <tspan> «1» со
смещением вниз и уменьшенным кеглем. Атрибут data-point, геометрия, раскладка
и все прочие элементы не меняются; имена точек в плане остаются прежними.

Распознаются: X_1, X_12, X1, X12 (цифровой индекс, прямой шрифт),
X_A, X_ab (буквенный индекс, курсив как у подписи). Остальное — без изменений.
GEOEXACT_LABEL_SUBSCRIPTS=0 выключает.
"""
from __future__ import annotations

import functools
import os
import re
import xml.etree.ElementTree as ET

ENABLED = (os.environ.get("GEOEXACT_LABEL_SUBSCRIPTS") or "1").strip().lower() not in ("0", "no", "off")
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)

_DIGITS = re.compile(r"^([A-Za-z])_?(\d{1,2})$")
_LETTERS = re.compile(r"^([A-Za-z])_([A-Za-z]{1,2})$")
SUB_DY = "0.33em"
SUB_SIZE = "68%"


def split_label(name: str) -> tuple[str, str, bool] | None:
    """(база, индекс, индекс_цифровой) или None, если индекса нет."""
    if not isinstance(name, str):
        return None
    m = _DIGITS.match(name)
    if m:
        return m[1], m[2], True
    m = _LETTERS.match(name)
    if m:
        return m[1], m[2], False
    return None


def subscript_labels(svg: str) -> str:
    """Переписать подписи точек с индексами; при любой проблеме вернуть SVG как есть."""
    if not isinstance(svg, str) or "_" not in svg and not re.search(r'class="lab"[^>]*>[A-Za-z]\d', svg):
        return svg
    try:
        root = ET.fromstring(svg, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    except ET.ParseError:
        return svg
    changed = False
    for text in root.iter("{" + NS + "}text"):
        if "lab" not in (text.get("class") or "").split():
            continue
        if len(text) or not text.text:
            continue                              # уже размечено или пусто
        parts = split_label(text.text.strip())
        if parts is None or parts[0] + ("_" if "_" in text.text else "") + parts[1] != text.text.strip():
            continue
        base, index, digits = parts
        text.text = base
        sub = ET.SubElement(text, "{" + NS + "}tspan",
                            {"class": "sub", "dy": SUB_DY, "font-size": SUB_SIZE})
        if digits:
            sub.set("font-style", "normal")
        sub.text = index
        changed = True
    if not changed:
        return svg
    return ET.tostring(root, encoding="unicode")


def install(renderer) -> bool:
    """Обернуть render.render_svg самым внешним слоем. Повторный вызов — no-op."""
    if not ENABLED:
        return False
    original = getattr(renderer, "render_svg", None)
    if original is None or getattr(original, "_label_subscripts", False):
        return False

    @functools.wraps(original)
    def render_svg(plan, sol, *args, **kwargs):
        svg = original(plan, sol, *args, **kwargs)
        try:
            return subscript_labels(svg)
        except Exception:  # noqa: BLE001 — косметика не должна ломать чертёж
            return svg
    render_svg._label_subscripts = True
    render_svg._original = original
    renderer.render_svg = render_svg
    return True

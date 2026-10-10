# -*- coding: utf-8 -*-
"""Рендер формул для PDF: LaTeX -> PNG через matplotlib.mathtext (без TeX, шрифт Computer Modern —
«как в учебнике»: настоящие дроби, корни, индексы). Используется в teacher/worksheets/pdf.py.

Это не «свой рендер»: парсинг и вёрстка формул — целиком matplotlib. При недоступности matplotlib
или ошибке разбора конкретной формулы — fallback на latex_to_text() с warning.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

DELIMS = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|\$(.+?)\$", re.S)
_DISPLAY_GROUPS = (0, 1)  # индексы групп $$...$$ и \[...\]

_available: Optional[bool] = None


def available() -> bool:
    global _available
    if _available is None:
        try:
            import matplotlib  # noqa: F401
            import numpy  # noqa: F401
            from PIL import Image  # noqa: F401
            _available = True
        except Exception:  # noqa: BLE001
            _available = False
    return _available


def _prep(latex: str) -> str:
    s = latex.strip()
    s = re.sub(r"\\[dt]frac", r"\\frac", s)
    s = re.sub(r"\\text(?:bf|it|rm)?\s*\{", r"\\mathrm{", s)
    s = re.sub(r"\\(le|ge)(?![a-zA-Z])", lambda m: "\\" + m.group(1) + "q", s)
    s = s.replace(r"\degree", r"^\circ").replace(r"\displaystyle", "").replace(r"\,", r"\ ")
    s = re.sub(r"\\pmod\s*\{([^{}]*)\}", r"\\ (\\mathrm{mod}\\ \1)", s)
    s = re.sub(r"\\mod\s*\{([^{}]*)\}", r"\\ \\mathrm{mod}\\ \1", s)
    s = s.replace(r"\ne ", r"\neq ").replace(r"\not=", r"\neq")
    return s


def render_png(latex: str, fontsize: float = 11, dpi: int = 300,
               fontset: Optional[str] = None) -> Tuple[bytes, float, float, float]:
    """-> (png_bytes, width_pt, height_pt, depth_pt). Бросает исключение при ошибке разбора."""
    import io
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from matplotlib.font_manager import FontProperties
    from matplotlib.mathtext import MathTextParser
    from PIL import Image

    matplotlib.rcParams["mathtext.fontset"] = fontset or os.environ.get("WORKSHEETS_MATH_FONTSET", "cm")
    rp = MathTextParser("agg").parse("$" + _prep(latex) + "$", dpi=dpi, prop=FontProperties(size=fontsize))
    _ox, _oy, w, h, d, img = rp
    alpha = np.asarray(img)
    rgba = np.zeros(alpha.shape + (4,), dtype=np.uint8)
    rgba[..., 3] = alpha
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    k = 72.0 / dpi
    return buf.getvalue(), w * k, h * k, d * k


def paragraph_html(text: str, tmpdir: str, fontsize: float = 11, max_width_pt: float = 170 * 72 / 25.4,
                   fallback: Optional[Callable[[str], Tuple[str, bool]]] = None,
                   escape: Optional[Callable[[str], str]] = None) -> Tuple[str, bool, List[str]]:
    """Текст с $...$ -> разметка reportlab Paragraph с inline <img> формул (выравнивание по базовой
    линии через valign). Возвращает (html, had_math, warnings)."""
    esc = escape or (lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    warnings: List[str] = []
    had = False
    out: List[str] = []
    pos = 0
    for m in DELIMS.finditer(text or ""):
        out.append(esc(text[pos:m.start()]))
        pos = m.end()
        had = True
        gi = next(i for i, g in enumerate(m.groups()) if g is not None)
        latex = m.group(gi + 1)
        display = gi in _DISPLAY_GROUPS
        try:
            if not available():
                raise ImportError("matplotlib недоступен")
            png, w, h, d = render_png(latex, fontsize=fontsize * (1.15 if display else 1.0))
            if w > max_width_pt:
                scale = max_width_pt / w
                w, h, d = w * scale, h * scale, d * scale
            name = hashlib.sha1((latex + str(display)).encode("utf-8")).hexdigest()[:16] + ".png"
            path = os.path.join(tmpdir, name)
            if not os.path.exists(path):
                with open(path, "wb") as fh:
                    fh.write(png)
            img = f'<img src="{path}" width="{w:.2f}" height="{h:.2f}" valign="{-d:.2f}"/>'
            out.append(f"<br/>{img}<br/>" if display else img)
        except Exception as e:  # noqa: BLE001
            fb = fallback(m.group(0))[0] if fallback else latex
            out.append(esc(fb))
            warnings.append(f"формула не отрендерена ({type(e).__name__}): {latex[:40]}")
    out.append(esc(text[pos:] if text else ""))
    return "".join(out), had, warnings

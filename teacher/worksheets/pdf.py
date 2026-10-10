# -*- coding: utf-8 -*-
"""PDF листка (этап 5): GET /teacher/worksheet/<id>.pdf?with_solutions=0|1&space=<мм>

reportlab + DejaVuSans, A4. Шапка (название, класс, дата, учитель), задачи с номерами,
место под решение. Формулы: серверного рендера KaTeX в проекте нет (только клиентский
KaTeX в base.html) -> fallback: LaTeX приводится к читаемому тексту (\\frac -> a/b,
\\cdot -> ·, ^{2} -> ², ...), в подвале warning. with_solutions=1 -> только владелец:
раздел «Решения» + диагональный водяной знак «для учителя»; ученику -> 403.
Доступ к with_solutions=0: владелец или ученик с назначением на этот листок.
"""
from __future__ import annotations

import io
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from flask import abort, request, send_file
from flask_login import current_user, login_required

from models import db
from teacher import teacher_bp
from teacher.worksheets import bank_index, selector
from teacher.worksheets.models import Worksheet, WorksheetAssignment

logger = logging.getLogger(__name__)

FONT_NAME = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"
_FONT_CANDIDATES = [
    os.environ.get("WORKSHEETS_PDF_FONT", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
]


# ───────────────────────── зависимости и шрифт ──────────────────────────────

def _ensure_reportlab():
    """reportlab импортируется лениво. Если его нет и мы на Render (env RENDER)
    или WORKSHEETS_PIP_AUTOINSTALL=1 — один раз ставим pip'ом (как AUTO-MIGRATION:
    без ручных шагов). Иначе — ImportError наверх (-> 503)."""
    try:
        import reportlab  # noqa: F401
        return
    except ImportError:
        pass
    allow = os.environ.get("WORKSHEETS_PIP_AUTOINSTALL") or ("1" if os.environ.get("RENDER") else "0")
    if allow != "1":
        raise ImportError("reportlab не установлен: добавьте reportlab>=4.0 в requirements.txt")
    logger.warning("worksheets.pdf: reportlab отсутствует — устанавливаю (pip install reportlab)")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "reportlab>=4.0"], check=True, timeout=180)
    import importlib
    importlib.invalidate_caches()
    import reportlab  # noqa: F401


def _font_path() -> Optional[str]:
    for p in _FONT_CANDIDATES:
        if p and os.path.exists(p):
            return p
    try:
        import matplotlib
        p = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf", "DejaVuSans.ttf")
        if os.path.exists(p):
            return p
    except Exception:  # noqa: BLE001
        pass
    return None


def _register_fonts() -> Tuple[str, str, List[str]]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    warnings: List[str] = []
    path = _font_path()
    if not path:
        warnings.append("DejaVuSans не найден — использован Helvetica (кириллица может не отображаться)")
        return "Helvetica", "Helvetica-Bold", warnings
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, path))
        bold = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
        pdfmetrics.registerFont(TTFont(FONT_BOLD, bold if os.path.exists(bold) else path))
    return FONT_NAME, FONT_BOLD, warnings


# ───────────────────────── формулы: LaTeX -> текст ──────────────────────────────

_SUP = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_SYMBOLS = {
    r"\cdot": "·", r"\times": "×", r"\le": "≤", r"\leq": "≤", r"\ge": "≥", r"\geq": "≥", r"\ne": "≠", r"\neq": "≠",
    r"\pm": "±", r"\infty": "∞", r"\ldots": "…", r"\dots": "…", r"\cdots": "⋯", r"\angle": "∠", r"\degree": "°",
    r"\circ": "°", r"\triangle": "△", r"\parallel": "∥", r"\perp": "⊥", r"\in": "∈", r"\notin": "∉",
    r"\subset": "⊂", r"\cup": "∪", r"\cap": "∩", r"\to": "→", r"\rightarrow": "→", r"\Rightarrow": "⇒",
    r"\Leftrightarrow": "⇔", r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\pi": "π",
    r"\varphi": "φ", r"\phi": "φ", r"\lambda": "λ", r"\mu": "μ", r"\sigma": "σ", r"\omega": "ω", r"\theta": "θ",
    r"\sqrt": "√", r"\%": "%", r"\,": " ", r"\;": " ", r"\!": "", r"\quad": "  ", r"\qquad": "    ",
    r"\left": "", r"\right": "", r"\big": "", r"\Big": "", r"\displaystyle": "", r"\mid": "|", r"\div": "÷",
    r"\equiv": "≡", r"\approx": "≈", r"\sum": "Σ", r"\prod": "Π", r"\frac": "", r"\dfrac": "", r"\tfrac": "",
}
_DELIMS = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|\$(.+?)\$", re.S)
_FRAC = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_TEXT = re.compile(r"\\(?:text|mathrm|mathbf|mathbb|mathcal|operatorname|textbf|textit)\s*\{([^{}]*)\}")
_SUPB = re.compile(r"\^\{([^{}]*)\}")
_SUBB = re.compile(r"_\{([^{}]*)\}")
_OVERLINE = re.compile(r"\\overline\s*\{([^{}]*)\}")


def latex_to_text(s: str) -> Tuple[str, bool]:
    """Грубое, но читаемое приведение формул к Unicode-тексту. Возвращает (text, had_math)."""
    had = False

    def conv(m):
        nonlocal had
        had = True
        f = next(g for g in m.groups() if g is not None)
        for _ in range(3):
            f = _FRAC.sub(lambda mm: f"({mm.group(1)})/({mm.group(2)})" if (len(mm.group(1)) > 1 or len(mm.group(2)) > 1) else f"{mm.group(1)}/{mm.group(2)}", f)
        f = f.replace(r"^{\circ}", "°").replace(r"^\circ", "°")
        f = _TEXT.sub(r"\1", f)
        f = _OVERLINE.sub(r"\1", f)
        f = _SUPB.sub(lambda mm: mm.group(1).translate(_SUP) if all(c in "0123456789+-=()n" for c in mm.group(1)) else "^(" + mm.group(1) + ")", f)
        f = _SUBB.sub(lambda mm: mm.group(1).translate(_SUB) if all(c in "0123456789+-=()" for c in mm.group(1)) else "_(" + mm.group(1) + ")", f)
        f = re.sub(r"\^(\w)", lambda mm: mm.group(1).translate(_SUP), f)
        f = re.sub(r"_(\w)", lambda mm: mm.group(1).translate(_SUB), f)
        for k in sorted(_SYMBOLS, key=len, reverse=True):
            f = f.replace(k, _SYMBOLS[k])
        f = f.replace("{", "").replace("}", "")
        return " ".join(f.split())

    out = _DELIMS.sub(conv, s or "")
    return out, had


# ───────────────────────────── сборка PDF ───────────────────────────────────

def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _source_line(src: Optional[Dict[str, Any]]) -> str:
    if not src:
        return ""
    parts = [str(src[k]) for k in ("olympiad", "stage", "year") if src.get(k)]
    if src.get("grade"):
        parts.append(f"{src['grade']} класс")
    if src.get("number"):
        parts.append(f"№{src['number']}")
    return ", ".join(parts)


def _teacher_name(ws: Worksheet) -> str:
    u = ws.teacher
    for attr in ("display_name", "nickname", "name", "username"):
        v = getattr(u, attr, None)
        if v:
            return str(v)
    try:
        from services.user_helpers import display_name_from_email
        return display_name_from_email(getattr(u, "email", "") or "")
    except Exception:  # noqa: BLE001
        return getattr(u, "email", "") or f"id {ws.teacher_id}"


def build_pdf(ws: Worksheet, with_solutions: bool = False, space_mm: int = 60) -> Tuple[bytes, List[str]]:
    _ensure_reportlab()
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    font, bold, warnings = _register_fonts()
    had_math_any = False

    st_title = ParagraphStyle("t", fontName=bold, fontSize=16, leading=20, spaceAfter=2)
    st_meta = ParagraphStyle("m", fontName=font, fontSize=9.5, leading=12, textColor=colors.HexColor("#444444"))
    st_num = ParagraphStyle("n", fontName=bold, fontSize=11, leading=14)
    st_body = ParagraphStyle("b", fontName=font, fontSize=11, leading=15)
    st_src = ParagraphStyle("s", fontName=font, fontSize=8.5, leading=11, textColor=colors.HexColor("#666666"))
    st_h2 = ParagraphStyle("h", fontName=bold, fontSize=14, leading=18, spaceBefore=6, spaceAfter=6)
    st_center = ParagraphStyle("c", fontName=font, fontSize=8, leading=10, alignment=TA_CENTER,
                               textColor=colors.HexColor("#888888"))

    rows = sorted(ws.tasks, key=lambda r: r.position)
    recs = [(r, bank_index.get(r.task_id)) for r in rows]
    story: List[Any] = []

    story.append(Paragraph(_esc(ws.title), st_title))
    meta = f"{ws.grade} класс · {datetime.utcnow().strftime('%d.%m.%Y')} · Учитель: {_esc(_teacher_name(ws))}"
    if ws.group is not None:
        meta += f" · Группа: {_esc(ws.group.name)}"
    story.append(Paragraph(meta, st_meta))
    story.append(Table([[""]], colWidths=[170 * mm], rowHeights=[2],
                       style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, colors.HexColor("#f4a259"))])))
    story.append(Spacer(1, 6 * mm))

    for row, rec in recs:
        if rec is None:
            block = [Paragraph(f"Задача {row.position}", st_num),
                     Paragraph("<i>задача не найдена в банке</i>", st_body)]
        else:
            text, had = latex_to_text(rec.get("task_text") or "")
            had_math_any |= had
            t = selector.to_task(rec, row.target_level)
            head = f"Задача {row.position}"
            src = _source_line(t["source"])
            block = [Paragraph(head + f"  <font size=8 color='#888888'>уровень {t['level']}</font>", st_num),
                     Paragraph(_esc(text), st_body)]
            if src:
                block.append(Paragraph(_esc(src), st_src))
            if t["has_figure"]:
                block.append(Paragraph("<i>к задаче есть чертёж — см. на сайте</i>", st_src))
        if not with_solutions and space_mm > 0:
            block.append(Spacer(1, space_mm * mm))
        else:
            block.append(Spacer(1, 4 * mm))
        story.append(KeepTogether(block))

    if with_solutions:
        story.append(PageBreak())
        story.append(Paragraph("Решения (для учителя)", st_h2))
        for row, rec in recs:
            if rec is None:
                continue
            ans, h1 = latex_to_text(str(rec.get("correct_answer") or ""))
            sol, h2 = latex_to_text(str(rec.get("solution") or ""))
            had_math_any |= (h1 or h2)
            block = [Paragraph(f"Задача {row.position}", st_num)]
            if ans:
                block.append(Paragraph("<b>Ответ:</b> " + _esc(ans), st_body))
            if sol:
                for para in [p for p in sol.split("\n") if p.strip()]:
                    block.append(Paragraph(_esc(para), st_body))
            block.append(Spacer(1, 4 * mm))
            story.append(KeepTogether(block))

    if had_math_any:
        warnings.append("Формулы выведены текстом (серверного рендера KaTeX в проекте нет)")

    footer_note = " · ".join(warnings) if warnings else ""

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"стр. {doc.page}")
        canvas.drawString(15 * mm, 10 * mm, "FORMYLA.net")
        if footer_note:
            canvas.setFont(font, 7)
            canvas.drawCentredString(A4[0] / 2, 6 * mm, footer_note[:160])
        if with_solutions:
            canvas.setFont(bold, 54)
            canvas.setFillColor(colors.Color(0.85, 0.3, 0.1, alpha=0.13))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "ДЛЯ УЧИТЕЛЯ")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=ws.title, author="FORMYLA.net")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue(), warnings


# ───────────────────────────────── роут ─────────────────────────────────────

def _can_view(ws: Worksheet, with_solutions: bool) -> bool:
    role = getattr(current_user, "role", "student") or "student"
    if role == "teacher" and ws.teacher_id == current_user.id:
        return True
    if with_solutions:
        return False
    return WorksheetAssignment.query.filter_by(worksheet_id=ws.id, student_id=current_user.id).first() is not None


@teacher_bp.route("/teacher/worksheet/<int:ws_id>.pdf", methods=["GET"])
@login_required
def worksheet_pdf(ws_id: int):
    ws = db.session.get(Worksheet, ws_id)
    if ws is None:
        abort(404)
    with_solutions = request.args.get("with_solutions", "0") in ("1", "true", "yes")
    if not _can_view(ws, with_solutions):
        abort(403)
    try:
        space = max(0, min(150, int(request.args.get("space", 60))))
    except ValueError:
        space = 60
    try:
        data, warnings = build_pdf(ws, with_solutions=with_solutions, space_mm=space)
    except ImportError as e:
        return {"error": str(e)}, 503
    for w in warnings:
        logger.info("worksheets.pdf ws=%s: %s", ws.id, w)
    safe = re.sub(r"[^\w\-]+", "_", ws.title, flags=re.U).strip("_") or f"worksheet_{ws.id}"
    name = f"{safe}{'_solutions' if with_solutions else ''}.pdf"
    resp = send_file(io.BytesIO(data), mimetype="application/pdf", as_attachment=False, download_name=name)
    resp.headers["X-Worksheet-Warnings"] = str(len(warnings))
    return resp

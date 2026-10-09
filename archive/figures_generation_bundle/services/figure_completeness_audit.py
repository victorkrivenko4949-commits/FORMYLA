# -*- coding: utf-8 -*-
"""services/figure_completeness_audit.py — визуальная проверка полноты чертежа.

После построения чертёж рендерится в PNG и отправляется в Gemini (vision,
через OdiRouter) вместе с условием задачи.  Модель проверяет, всё ли из
условия отражено на чертеже:

  * все равные углы отмечены дугами;
  * все равные отрезки отмечены засечками;
  * все отрезки/стороны с известной длиной подписаны числом;
  * все заданные углы подписаны числом;
  * искомый объект помечен «?».

Если что-то пропущено — модель возвращает JSON с `complete: false` и
`repair_plan` (список объектов, которые нужно добавить), чтобы в тот же чат
дозаполнить план.  Пунктирные (вспомогательные) линии считаются обычными.

Без внешних зависимостей кроме PIL (рендер) и requests (вызов).
"""

from __future__ import annotations

import base64
import io
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def svg_to_png_bytes(svg: str, scale: int = 2) -> Optional[bytes]:
    """Рендер SVG → PNG (байты).  None при сбое рендера."""
    try:
        import tempfile

        # Импортируем локальный рендер (лежит в корне проекта).
        import sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)

        import _svg_to_png as renderer

        svg_path = tempfile.mktemp(suffix=".svg")
        png_path = tempfile.mktemp(suffix=".png")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
        renderer.render(svg_path, png_path, scale=scale)
        with open(png_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.warning("[figure_audit] svg_to_png failed: %s", e)
        return None


def _gemini_vision(json_payload: dict, timeout=(15, 60)) -> Optional[str]:
    """Вызвать Gemini (vision) через OdiRouter OpenAI-compatible endpoint."""
    try:
        import requests as _requests
        key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not key:
            return None
        base = (os.environ.get("GEMINI_API_BASE") or "https://api.odirouter.ai/v1").strip().rstrip("/")
        model = (os.environ.get("GEMINI_VISION_MODEL") or "gemini-3.7-flash").strip()
        resp = _requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, **json_payload},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning("[figure_audit] gemini vision HTTP %s: %s", resp.status_code, resp.text[:200])
            return None
        body = resp.json()
        if not body.get("choices"):
            return None
        return (body["choices"][0].get("message", {}) or {}).get("content") or None
    except Exception as e:
        logger.warning("[figure_audit] gemini vision failed: %s", e)
        return None


_AUDIT_SYSTEM = (
    "Ты — строгий проверяющий геометрических чертежей для школьных задач. "
    "Тебе дают РИСУНОК чертежа и текст условия. Проверь, ВСЁ ли из условия "
    "отражено на чертеже.\n"
    "Проверяй:\n"
    "1) все равные углы отмечены одинаковыми дугами;\n"
    "2) все равные отрезки отмечены одинаковыми засечками;\n"
    "3) каждый отрезок/сторона с известной длиной подписан числом;\n"
    "4) каждый заданный угол подписан числом;\n"
    "5) искомый объект (что просят «найти») помечен знаком «?».\n"
    "Пунктирные линии считай обычными линиями.\n\n"
    "Верни СТРОГО один JSON-объект, без markdown и пояснений:\n"
    '{"complete": true/false, '
    '"missing": ["краткое описание пропущенного", ...], '
    '"repair_plan": [{"type": "...", "...": "..."}]}\n'
    "Если всё отражено — complete=true, missing=[], repair_plan=[].\n"
    "Если есть пропуски — complete=false и в repair_plan перечисли объекты "
    "(используй типы из geometric_engine: free_point, segment, midpoint, "
    "angle_label, length_label, equal_segments_mark, equal_angles_mark, "
    "right_angle_mark, midpoint_mark)."
)


def audit_figure_completeness(
    svg: str,
    condition_text: str,
    timeout=(15, 60),
) -> Dict[str, Any]:
    """Проверить полноту чертежа через Gemini vision.

    Returns:
      {"complete": bool, "missing": [str], "repair_plan": [dict], "raw": str}
      При недоступности vision или ошибке — {"complete": True, "skipped": True}.
    """
    import json

    png = svg_to_png_bytes(svg)
    if png is None:
        logger.warning("[figure_audit] no png — skip completeness audit")
        return {"complete": True, "skipped": True, "missing": [], "repair_plan": []}

    b64 = base64.b64encode(png).decode()
    prompt = f"Условие задачи:\n{condition_text}\n\nПроверь полноту чертежа и верни JSON."
    payload = {
        "messages": [
            {"role": "system", "content": _AUDIT_SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }
    content = _gemini_vision(payload, timeout=timeout)
    if content is None:
        logger.warning("[figure_audit] gemini empty — skip completeness audit")
        return {"complete": True, "skipped": True, "missing": [], "repair_plan": []}

    data = None
    try:
        data = json.loads(content)
    except Exception:
        # Возможно модель обернула в markdown или добавила текст.
        import re
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None

    if not isinstance(data, dict):
        logger.warning("[figure_audit] bad json from gemini: %s", content[:200])
        return {"complete": True, "skipped": True, "missing": [], "repair_plan": []}

    return {
        "complete": bool(data.get("complete", True)),
        "missing": list(data.get("missing") or []),
        "repair_plan": list(data.get("repair_plan") or []),
        "raw": content,
    }

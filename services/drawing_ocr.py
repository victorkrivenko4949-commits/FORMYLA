# -*- coding: utf-8 -*-
# OCR helper: extract problem text from a student-uploaded image.
# Uses the same OpenRouter Gemini vision model we already pay for.
import base64
import logging
from typing import Optional, Tuple

from services.openrouter_client import OpenRouterClient, OpenRouterError

logger = logging.getLogger(__name__)
_openrouter = OpenRouterClient()

MODEL_OCR = "google/gemini-3.1-pro-preview"

# Prompt is built from unicode escapes to keep this source file
# pure ASCII (the tool that wrote this file has trouble streaming
# long Cyrillic content reliably).
_SP = (
    "\u0422\u044b \u2014 \u043f\u043e\u043c\u043e\u0449\u043d\u0438\u043a "
    "OCR \u0434\u043b\u044f \u0433\u0435\u043e\u043c\u0435\u0442\u0440\u0438"
    "\u0447\u0435\u0441\u043a\u0438\u0445 \u0437\u0430\u0434\u0430\u0447. "
    "\u041d\u0430 \u0432\u0445\u043e\u0434 \u0442\u044b \u043f\u043e\u043b"
    "\u0443\u0447\u0430\u0435\u0448\u044c \u0444\u043e\u0442\u043e \u0438"
    "\u043b\u0438 \u0441\u043a\u0440\u0438\u043d\u0448\u043e\u0442 \u0441 "
    "\u0443\u0441\u043b\u043e\u0432\u0438\u0435\u043c \u0437\u0430\u0434"
    "\u0430\u0447\u0438 (\u0443\u0447\u0435\u0431\u043d\u0438\u043a, \u0442"
    "\u0435\u0442\u0440\u0430\u0434\u044c, \u0441\u043b\u0430\u0439\u0434, "
    "\u0434\u043e\u0441\u043a\u0430). \u0422\u0432\u043e\u044f \u0437\u0430"
    "\u0434\u0430\u0447\u0430 \u2014 \u0438\u0437\u0432\u043b\u0435\u0447"
    "\u044c \u0442\u0435\u043a\u0441\u0442 \u0443\u0441\u043b\u043e\u0432"
    "\u0438\u044f \u041d\u0410 \u0420\u0423\u0421\u0421\u041a\u041e\u041c "
    "\u044f\u0437\u044b\u043a\u0435.\n\n"
    "\u041f\u0420\u0410\u0412\u0418\u041b\u0410:\n"
    "1) \u0412\u0435\u0440\u043d\u0438 \u0422\u041e\u041b\u042c\u041a\u041e "
    "\u0442\u0435\u043a\u0441\u0442 \u0437\u0430\u0434\u0430\u0447\u0438 \u2014"
    " \u0431\u0435\u0437 markdown, \u0431\u0435\u0437 \u043a\u0430\u0432\u044b"
    "\u0447\u0435\u043a, \u0431\u0435\u0437 \u043a\u043e\u043c\u043c\u0435\u043d"
    "\u0442\u0430\u0440\u0438\u0435\u0432.\n"
    "2) \u0421\u043e\u0445\u0440\u0430\u043d\u044f\u0439 \u043c\u0430\u0442"
    "\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u043e"
    "\u0431\u043e\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f (ABC, \u03c9, "
    "\u2220, \u2225, \u22a5, \u00b0, \u221a) \u043a\u0430\u043a \u0435\u0441"
    "\u0442\u044c.\n"
    "3) \u0415\u0441\u043b\u0438 \u043d\u0430 \u0444\u043e\u0442\u043e \u041d"
    "\u0415\u0422 \u0432\u043d\u044f\u0442\u043d\u043e\u0433\u043e \u0443\u0441"
    "\u043b\u043e\u0432\u0438\u044f (\u043f\u0443\u0441\u0442\u0430\u044f \u043a"
    "\u0430\u0440\u0442\u0438\u043d\u043a\u0430, \u0442\u043e\u043b\u044c\u043a"
    "\u043e \u0447\u0435\u0440\u0442\u0451\u0436 \u0431\u0435\u0437 \u0442\u0435"
    "\u043a\u0441\u0442\u0430, \u0444\u043e\u0442\u043e \u043a\u043e\u0442\u0430,"
    " \u0438 \u0442.\u043f.) \u2014 \u0432\u0435\u0440\u043d\u0438 \u0440\u043e"
    "\u0432\u043d\u043e \u0441\u0442\u0440\u043e\u043a\u0443: __NO_PROBLEM__\n"
    "4) \u0415\u0441\u043b\u0438 \u043d\u0430 \u0444\u043e\u0442\u043e \u043d"
    "\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0437\u0430\u0434\u0430"
    "\u0447 \u2014 \u0432\u044b\u0431\u0435\u0440\u0438 \u0422\u041e\u041b\u042c"
    "\u041a\u041e \u041e\u0414\u041d\u0423 (\u0441\u0430\u043c\u0443\u044e \u043f"
    "\u043e\u043b\u043d\u0443\u044e \u0438\u043b\u0438 \u043e\u0431\u0432\u0435"
    "\u0434\u0451\u043d\u043d\u0443\u044e \u043a\u0440\u0430\u0441\u043d\u044b"
    "\u043c).\n"
    "5) \u041d\u0415 \u043f\u0440\u0438\u0434\u0443\u043c\u044b\u0432\u0430\u0439"
    " \u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u0439 \u0432\u0440"
    "\u043e\u0434\u0435 \xab\u043f\u043e\u0441\u0442\u0440\u043e\u0439\u0442"
    "\u0435 \u0447\u0435\u0440\u0442\u0451\u0436\xbb \u2014 \u044d\u0442\u043e"
    " \u0440\u0430\u0431\u043e\u0442\u0430 \u0434\u0440\u0443\u0433\u043e\u0439"
    " \u0441\u0442\u0430\u0434\u0438\u0438."
)


def ocr_problem_image(
    image_bytes: bytes,
    mime: str = "image/png",
) -> Tuple[Optional[str], float]:
    """Run vision-OCR on a problem photo. Returns (text or None, cost_usd).

    All transport failures are swallowed and surface as (None, 0.0) so the
    /drawing route can decide how to respond to the user.
    """
    if not image_bytes:
        return None, 0.0
    try:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = "data:" + mime + ";base64," + b64
        resp = _openrouter.chat(
            model=MODEL_OCR,
            messages=[
                {"role": "system", "content": _SP},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "\u0418\u0437\u0432\u043b\u0435\u043a\u0438 "
                                "\u0443\u0441\u043b\u043e\u0432\u0438\u0435 "
                                "\u0437\u0430\u0434\u0430\u0447\u0438 \u0441 "
                                "\u044d\u0442\u043e\u0433\u043e \u0438\u0437"
                                "\u043e\u0431\u0440\u0430\u0436\u0435\u043d"
                                "\u0438\u044f."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            temperature=0.0,
            max_tokens=2500,
        )
        text = (resp.get("content") or "").strip()
        cost = float(resp.get("cost_usd") or 0.0)
        if not text or text == "__NO_PROBLEM__":
            return None, cost
        # strip surrounding quotes / markdown fences if model added them
        if text.startswith("```"):
            text = text.strip("`").lstrip("\n").rstrip("\n")
        text = text.strip('"').strip("'").strip()
        if not text or len(text) < 4:
            return None, cost
        return text, cost
    except OpenRouterError as e:
        logger.warning("[drawing-ocr] transport failure: %s", e)
        return None, 0.0
    except Exception as e:  # pragma: no cover
        logger.warning("[drawing-ocr] unexpected error: %s", e)
        return None, 0.0
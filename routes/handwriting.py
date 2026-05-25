# -*- coding: utf-8 -*-
"""
Handwriting helper endpoint.

POST /api/handwriting/prepare
    body:  { "text": str, "mode": "raw"|"ai_format", "max_line": int? }
    reply: { "ok": True,
             "processed_text": str,
             "lines": [str, ...],
             "latex_segments": [str, ...],
             "ai_used": bool }

Behaviour:
    mode = "raw"        — backend just splits the text into lines no longer
                          than `max_line` characters (default 40) using a
                          space-aware greedy algorithm; LaTeX segments
                          (anything between $…$) are extracted into
                          `latex_segments` and kept inline as <m>i</m>
                          placeholders so the frontend can rerender them
                          via KaTeX.
    mode = "ai_format"  — additionally asks an LLM (OpenRouter /
                          anthropic claude-3.5-haiku) to lightly proofread
                          and re-shape the text for a handwritten note,
                          keeping math intact. Falls back to "raw"
                          silently if OPENROUTER_API_KEY is missing or
                          the call fails — the endpoint never 5xx's on
                          AI failure.

The endpoint is intentionally light-weight: it does *not* render
anything to canvas — drawing happens entirely in the browser via
static/js/board/handwriting.js. The server's only job is to give the
client a clean, line-broken text and a list of LaTeX fragments.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Tuple

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

handwriting_bp = Blueprint("handwriting_bp", __name__, url_prefix="/api/handwriting")

# ─── Configuration ──────────────────────────────────────────────────────────
DEFAULT_MAX_LINE = 40          # characters per line in raw mode
HARD_TEXT_LIMIT = 4000         # protect from accidental megabytes
AI_MODEL = os.environ.get("HANDWRITING_AI_MODEL", "anthropic/claude-3.5-haiku")

# Vision OCR for the "распознать рукопись с доски" feature.
# Primary: Claude Opus 4.7 — very strong on cyrillic handwriting and
# multi-line math. The fast variant is tried as backup, then a cheap
# fallback chain for the rare case Anthropic models are unavailable.
OCR_VISION_MODEL = os.environ.get(
    "HANDWRITING_OCR_MODEL", "anthropic/claude-opus-4.7"
)
OCR_FALLBACK_MODELS = [
    "anthropic/claude-opus-4.7",
    "anthropic/claude-opus-4.7-fast",
    "anthropic/claude-opus-4.6",
    "anthropic/claude-sonnet-4.6",
    "openai/gpt-4o-mini",
    "google/gemini-2.0-flash-001",
]
# Hard cap on incoming image payload (base64 PNG dataURL). 1.5 MB ≈
# ~2 MB of PNG, which is way more than a single «burst» of strokes
# needs (a few words at most).
OCR_IMAGE_MAX_BYTES = 1_500_000

# ─── Helpers ────────────────────────────────────────────────────────────────


_MATH_RE = re.compile(r"\$([^$\n]+?)\$")


def _extract_latex(text: str) -> Tuple[str, List[str]]:
    """Replace each $…$ math span with a <m{i}/> placeholder.

    Returns (text_with_placeholders, list_of_latex_fragments). Order is
    preserved so the client can re-insert them in the same positions.
    """
    fragments: List[str] = []

    def _store(m: re.Match) -> str:
        fragments.append(m.group(1).strip())
        return f"<m{len(fragments) - 1}/>"

    return _MATH_RE.sub(_store, text), fragments


def _wrap_lines(text: str, max_line: int) -> List[str]:
    """Word-aware greedy wrap. Preserves explicit \\n line breaks."""
    max_line = max(8, min(int(max_line or DEFAULT_MAX_LINE), 200))
    out: List[str] = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            out.append("")
            continue
        # tokenise keeping <m{i}/> placeholders as single units so we don't
        # accidentally split inside them.
        tokens = re.findall(r"<m\d+/>|\S+|\s+", paragraph)
        cur = ""
        for tok in tokens:
            candidate = cur + tok
            if len(candidate) <= max_line or not cur.strip():
                cur = candidate
            else:
                out.append(cur.rstrip())
                cur = tok.lstrip()
        if cur:
            out.append(cur.rstrip())
    return out


# ─── AI re-formatting (optional, graceful fallback) ─────────────────────────


# NB: the JSON example inside the prompt contains literal `{` and `}` —
# we cannot use str.format() here because it would try to interpret them
# as fields. Instead we splice the line-width with a plain string-replace
# token (`__MAX_LINE__`) which never collides with real prompt content.
_SYSTEM_PROMPT = (
    "Ты помощник для рукописного конспекта по математике. "
    "Тебе дан фрагмент текста (русский, возможны формулы LaTeX в виде "
    "$…$ — НЕ ТРОГАЙ их и НЕ удаляй). Задачи:\n"
    "1. Исправь явные опечатки и пунктуацию.\n"
    "2. Разбей текст на короткие строки не длиннее __MAX_LINE__ символов.\n"
    "3. Сохрани каждую формулу $…$ как есть, не переводи в слова.\n"
    "4. Не выдумывай новый текст — только лёгкая редактура.\n"
    "Верни СТРОГО JSON: {\"lines\": [\"...\", \"...\"]}. "
    "Никаких пояснений, никакой обёртки в код-блоки."
)


def _build_system_prompt(max_line: int) -> str:
    return _SYSTEM_PROMPT.replace("__MAX_LINE__", str(int(max_line)))


def _ai_reformat(text: str, max_line: int) -> List[str] | None:
    """Try to re-wrap the text via OpenRouter. Returns None on any failure.

    Uses the shared services.openrouter_client singleton so we automatically
    benefit from rate-limiting, retry, and the circuit breaker.
    """
    if not os.environ.get("OPENROUTER_API_KEY"):
        return None
    try:
        # Lazy import — avoids loading httpx/openrouter at module import time
        # when the endpoint is not used.
        from services.openrouter_client import openrouter, OpenRouterError
    except Exception as e:           # pragma: no cover — defensive
        logger.warning("[handwriting] openrouter import failed: %s", e)
        return None
    try:
        resp = openrouter.chat(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": _build_system_prompt(max_line)},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        content = (resp.get("content") or "").strip()
        # The model occasionally wraps the answer in ```json … ``` despite
        # the instruction — strip that defensively.
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I).strip()
        data = json.loads(content)
        lines = data.get("lines")
        if isinstance(lines, list) and all(isinstance(x, str) for x in lines):
            # never trust the model for max_line — re-wrap any over-long output
            wrapped: List[str] = []
            for ln in lines:
                if len(ln) <= max_line:
                    wrapped.append(ln)
                else:
                    wrapped.extend(_wrap_lines(ln, max_line))
            return wrapped
    except OpenRouterError as e:
        logger.warning("[handwriting] OpenRouter error → fallback to raw: %s", e)
    except Exception as e:           # pragma: no cover — log & fallback
        logger.warning("[handwriting] AI reformat failed: %s", e)
    return None


# ─── Endpoint ───────────────────────────────────────────────────────────────


@handwriting_bp.post("/prepare")
def prepare() -> Any:
    """Return cleaned, line-broken text + extracted LaTeX fragments."""
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    text = str(payload.get("text", "") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": "empty text"}), 400
    if len(text) > HARD_TEXT_LIMIT:
        text = text[:HARD_TEXT_LIMIT]
    mode = str(payload.get("mode", "raw"))
    max_line = int(payload.get("max_line") or DEFAULT_MAX_LINE)
    max_line = max(8, min(max_line, 200))

    # 1) Pull out LaTeX into placeholders.
    placeholder_text, latex_segments = _extract_latex(text)

    ai_used = False
    lines: List[str] | None = None
    if mode == "ai_format":
        ai_lines = _ai_reformat(placeholder_text, max_line)
        if ai_lines is not None:
            lines = ai_lines
            ai_used = True
    if lines is None:
        lines = _wrap_lines(placeholder_text, max_line)

    # 2) Re-assemble the “processed_text” for the client UI preview —
    #    placeholders are kept; the client renders them through KaTeX.
    processed_text = "\n".join(lines)

    return jsonify({
        "ok": True,
        "processed_text": processed_text,
        "lines": lines,
        "latex_segments": latex_segments,
        "ai_used": ai_used,
        "mode": "ai_format" if ai_used else "raw",
        "max_line": max_line,
    })


# ─── Vision OCR endpoint (handwriting → beautiful Caveat) ──────────────────


# Small map of common LaTeX commands → unicode equivalents. Used to
# scrub model output if the model slips and emits LaTeX despite the
# instruction. We deliberately keep this list short — the goal is just
# to make the result *readable*, not a perfect math typesetter.
_LATEX_TO_UNICODE = {
    r"\sqrt": "√",
    r"\cdot": "·",
    r"\times": "×",
    r"\div": "÷",
    r"\pm": "±",
    r"\mp": "∓",
    r"\le": "≤",
    r"\leq": "≤",
    r"\ge": "≥",
    r"\geq": "≥",
    r"\ne": "≠",
    r"\neq": "≠",
    r"\approx": "≈",
    r"\infty": "∞",
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\theta": "θ",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\pi": "π",
    r"\sigma": "σ",
    r"\phi": "φ",
    r"\omega": "ω",
    r"\sum": "∑",
    r"\int": "∫",
    r"\Delta": "Δ",
}

_SUPERSCRIPTS = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUBSCRIPTS   = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")


def _delatex(s: str) -> str:
    """Convert leftover LaTeX-ish bits to plain unicode.

    Handles: $…$, $$…$$, common \\commands, ^{…} / _{…}, \\frac{a}{b},
    and lonely braces/backslashes. Idempotent: calling it twice yields
    the same result.
    """
    if not s:
        return s
    # Strip inline / display math delimiters.
    s = re.sub(r"\${1,2}", "", s)
    # \frac{a}{b}  →  (a)/(b)
    s = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", s)
    # Replace known commands.
    for cmd, repl in _LATEX_TO_UNICODE.items():
        s = s.replace(cmd, repl)
    # x^{…}  →  superscript unicode (only digits/operators).
    def _sup(m):
        inner = m.group(1)
        if re.fullmatch(r"[0-9+\-=()n]+", inner):
            return inner.translate(_SUPERSCRIPTS)
        return "^(" + inner + ")"
    s = re.sub(r"\^\s*\{([^{}]*)\}", _sup, s)
    # x_{…} → subscript unicode.
    def _sub(m):
        inner = m.group(1)
        if re.fullmatch(r"[0-9+\-=()]+", inner):
            return inner.translate(_SUBSCRIPTS)
        return "_(" + inner + ")"
    s = re.sub(r"_\s*\{([^{}]*)\}", _sub, s)
    # x^2 (no braces) → x²
    s = re.sub(r"\^([0-9])", lambda m: m.group(1).translate(_SUPERSCRIPTS), s)
    s = re.sub(r"_([0-9])", lambda m: m.group(1).translate(_SUBSCRIPTS), s)
    # Strip any leftover lonely braces and backslashes.
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    # Collapse whitespace.
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


_OCR_SYSTEM_PROMPT = (
    "Ты — система распознавания рукописного текста на интерактивной доске.\n"
    "На картинке — короткий фрагмент рукописи (русский язык, иногда цифры "
    "и простые формулы), который только что нарисовал пользователь мышкой "
    "или пальцем. Картинка одноцветная (одна тёмная линия на белом "
    "фоне).\n\n"
    "Твоя ЕДИНСТВЕННАЯ задача — выдать тот текст, который написан, и "
    "ничего более.\n\n"
    "Правила:\n"
    "1. Верни СТРОГО JSON в формате: {\"text\": \"...\"}.\n"
    "2. Никакого пояснения, никаких ```json … ``` обёрток.\n"
    "3. Если на картинке непонятная закорючка — верни \"text\": \"\".\n"
    "4. Сохраняй регистр букв как у автора (заглавные/строчные).\n"
    "5. ЗАПРЕЩЕНО использовать LaTeX, доллары $...$, обратные слэши \\, фигурные скобки {} для формул. "
    "Если нарисовано «корень из 2x» — пиши обычными символами: «√(2x)», «√2x», "
    "степени — Unicode-символами: x² x³ x⁻¹, дроби — наклонная черта «(a+b)/c», "
    "греческие буквы как есть «α β π». Текст должен выглядеть так же, как "
    "написал ученик, без программной разметки.\n"
    "6. НЕ исправляй орфографию ученика — копируй то, что видишь."
)


def _ocr_image(image_b64: str) -> Dict[str, Any]:
    """Send a PNG dataURL fragment to OpenRouter vision and parse the JSON.

    Returns:
        {"ok": True, "text": str, "model": str}  on success
        {"ok": False, "error": str}              on every failure path
    The caller is expected to map ok=False onto an HTTP 200 with a
    silent fallback (so the UI never blocks the user).
    """
    if not image_b64:
        return {"ok": False, "error": "empty image"}
    if not os.environ.get("OPENROUTER_API_KEY"):
        return {"ok": False, "error": "OPENROUTER_API_KEY not set"}

    # Detect mime quickly so we feed OpenRouter a valid data URL.
    mime = "image/png"
    head_raw = image_b64
    if head_raw.startswith("data:"):
        # already a data URL — extract the mime and the base64 payload
        try:
            comma = head_raw.index(",")
            header = head_raw[5:comma]
            mime = header.split(";", 1)[0] or "image/png"
            image_b64 = head_raw[comma + 1:]
        except Exception:
            return {"ok": False, "error": "malformed data URL"}

    try:
        from services.openrouter_client import openrouter, OpenRouterError
    except Exception as e:           # pragma: no cover — defensive
        return {"ok": False, "error": f"openrouter import failed: {e}"}

    data_url = f"data:{mime};base64,{image_b64}"
    # Try the configured model first; if OpenRouter responds with «model
    # not found / no endpoints» we transparently fall back to the next
    # candidate. This makes the feature resilient when OpenRouter
    # renames or deprecates model slugs.
    candidates = [OCR_VISION_MODEL] + [m for m in OCR_FALLBACK_MODELS if m != OCR_VISION_MODEL]
    last_err: str = ""
    resp = None
    used_model = None
    for model in candidates:
        try:
            resp = openrouter.chat(
                model=model,
                messages=[
                    {"role": "system", "content": _OCR_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Распознай рукопись на картинке и верни JSON."},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                temperature=0.0,
                max_tokens=300,
            )
            used_model = model
            break
        except OpenRouterError as e:
            msg = str(e)
            last_err = f"{model}: {msg}"
            # "No endpoints found" / "404" → try next; other errors → stop.
            if "404" in msg or "No endpoints" in msg or "model" in msg.lower():
                logger.warning("[handwriting/recognize] %s — trying next", last_err)
                continue
            return {"ok": False, "error": f"openrouter: {last_err}"}
        except Exception as e:       # pragma: no cover
            last_err = f"{model}: {e}"
            logger.warning("[handwriting/recognize] vision call failed: %s", last_err)
            continue
    if resp is None:
        return {"ok": False, "error": f"all vision models failed; last: {last_err}"}

    content = (resp.get("content") or "").strip()
    # Some models still wrap in ```json fences — strip defensively.
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I).strip()
    text = ""
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            text = str(data.get("text") or "").strip()
    except Exception:
        # Plain-text fallback: if the model ignored the JSON instruction
        # and just answered with the recognised text, accept it anyway.
        if 0 < len(content) < 500 and "\n" not in content[:2]:
            text = content.strip().strip('"')

    # Server-side LaTeX safety net. The prompt forbids $…$ but we still
    # convert any leftover LaTeX to plain unicode so the handwriting
    # renderer never displays raw markup like `$\sqrt{2x}$`.
    text = _delatex(text)

    return {"ok": True, "text": text, "model": used_model or OCR_VISION_MODEL}


@handwriting_bp.post("/recognize")
def recognize() -> Any:
    """OCR a small PNG fragment of recent pen strokes.

    Body: { "image": <data URL or raw base64>, "hint": <optional str> }
    Reply: { "ok": True, "text": str, "font": "Caveat", "model": str }
           { "ok": True, "text": "", ...} when the model saw nothing.
           { "ok": False, "error": str }  on hard server errors.
    """
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    image_b64 = str(payload.get("image", "") or "")
    if not image_b64:
        return jsonify({"ok": False, "error": "missing image"}), 400
    # Reject obvious oversized payloads early (cheaper than going to OpenRouter).
    if len(image_b64) > OCR_IMAGE_MAX_BYTES:
        return jsonify({"ok": False, "error": "image too large"}), 413

    result = _ocr_image(image_b64)
    if not result.get("ok"):
        # Soft failure — the UI will leave the original strokes intact.
        logger.info("[handwriting/recognize] soft-fail: %s", result.get("error"))
        return jsonify({
            "ok": False,
            "text": "",
            "error": result.get("error") or "unknown",
        }), 200

    return jsonify({
        "ok": True,
        "text": result.get("text") or "",
        "font": "Caveat",
        "model": result.get("model") or OCR_VISION_MODEL,
    })


# Exported for tests:
__all__ = [
    "handwriting_bp",
    "_extract_latex",
    "_wrap_lines",
    "_ocr_image",
    "OCR_VISION_MODEL",
]

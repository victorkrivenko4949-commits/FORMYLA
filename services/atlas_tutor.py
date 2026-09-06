# -*- coding: utf-8 -*-
"""AI-наставник визуального атласа методов (backend).

Thin, provider-isolated backend for the atlas tutor. Responsibilities:

  * build a compact, bounded TutorContext from the *server-side* atlas data
    (never trusts client-supplied method content);
  * enforce the hint ladder (levels 0–4, spoiler gate at level 4);
  * call an OpenAI-compatible chat API (multimodal when images are attached);
  * apply a per-user in-memory rate limit;
  * return a validated JSON payload (never raw model JSON to the client).

Provider selection is via environment variables so the layer can be swapped
without touching the HTML:

  ATLAS_TUTOR_API_BASE   (default: https://api.deepseek.com/v1)
  ATLAS_TUTOR_API_KEY    (default: DEEPSEEK_API_KEY)
  ATLAS_TUTOR_MODEL      (default: deepseek-v4-flash)
  ATLAS_TUTOR_VISION_MODEL (default: deepseek-v4-flash-vision-exp)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time

import requests

from services import atlas_methods

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

API_BASE = os.environ.get("ATLAS_TUTOR_API_BASE", "https://api.deepseek.com/v1").rstrip("/")
API_KEY = os.environ.get("ATLAS_TUTOR_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("ATLAS_TUTOR_MODEL", "deepseek-v4-flash").strip()
VISION_MODEL = os.environ.get("ATLAS_TUTOR_VISION_MODEL", "deepseek-v4-flash-vision-exp").strip()

REQUEST_TIMEOUT = int(os.environ.get("ATLAS_TUTOR_TIMEOUT", "60"))
MAX_IMAGES = int(os.environ.get("ATLAS_TUTOR_MAX_IMAGES", "4"))
MAX_IMAGE_BYTES = int(os.environ.get("ATLAS_TUTOR_MAX_IMAGE_BYTES", str(6 * 1024 * 1024)))
MAX_MESSAGE = 4000
MAX_HISTORY = 12
MAX_INPUT_JSON_BYTES = 8 * 1024 * 1024

ALLOWED_MODES = {"free", "hint", "explain", "check", "trigger", "visual", "compare"}
ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp"}

_SYSTEM_PROMPT_PATH = os.path.join("data", "tutor", "atlas_tutor_system.txt")


def load_system_prompt() -> str:
    try:
        with open(_SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        logger.warning("[atlas_tutor] system prompt not found (%s); using inline fallback", e)
        return (
            "Ты — строгий, доброжелательный наставник по олимпиадной математике. "
            "Работай только с переданным контекстом метода и задачи. Не выдавай "
            "полное решение без spoilerAllowed=true. Отвечай по-русски, формулы в LaTeX."
        )


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class TutorError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


# --------------------------------------------------------------------------
# Rate limiting (in-memory, per user_id / ip)
# --------------------------------------------------------------------------

_rate_lock = threading.Lock()
_rate_buckets: dict = {}


def _rate_limited(key: str, limit: int = 20, window: float = 60.0) -> bool:
    now = time.time()
    with _rate_lock:
        hits = _rate_buckets.get(key, [])
        hits = [t for t in hits if now - t < window]
        if len(hits) >= limit:
            _rate_buckets[key] = hits
            return True
        hits.append(now)
        _rate_buckets[key] = hits
        return False


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------

def _safe_int(value, default: int, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _validate_images(images) -> list[dict]:
    """Return a validated list of {mime, data_b64} (data WITHOUT prefix)."""
    if not images:
        return []
    if not isinstance(images, list):
        raise TutorError("images должен быть списком", 400, "bad_images")
    if len(images) > MAX_IMAGES:
        raise TutorError(f"Можно прикрепить не более {MAX_IMAGES} изображений", 400, "too_many_images")

    out = []
    for img in images:
        if not isinstance(img, dict):
            raise TutorError("Некорректный формат изображения", 400, "bad_image")
        mime = (img.get("mimeType") or img.get("mime") or "image/jpeg").lower()
        # normalize common aliases
        if mime == "image/jpg":
            mime = "image/jpeg"
        if mime not in ALLOWED_IMAGE_MIME:
            raise TutorError(f"Неподдерживаемый формат изображения: {mime}", 400, "bad_image_mime")
        b64 = (img.get("data") or "").strip()
        if not b64:
            raise TutorError("Пустое изображение", 400, "empty_image")
        # strip data URL prefix if present
        b64 = re.sub(r"^data:image/[a-z+.-]+;base64,", "", b64, flags=re.I)
        try:
            raw = base64.b64decode(b64, validate=False)
        except Exception:
            raise TutorError("Изображение повреждено (некорректный base64)", 400, "bad_image")
        if len(raw) > MAX_IMAGE_BYTES:
            raise TutorError("Изображение слишком большое", 400, "image_too_large")
        out.append({"mime": mime, "data_b64": b64})
    return out


# --------------------------------------------------------------------------
# LLM call (OpenAI-compatible, isolated provider layer)
# --------------------------------------------------------------------------

def _chat_payload(messages: list[dict], model: str | None = None, temperature: float = 0.3) -> dict:
    return {
        "model": model or MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1600,
    }


def _chat_headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def _require_key():
    if not API_KEY:
        raise TutorError("AI-ключ не настроен на сервере", 503, "no_key")


def _raise_for_status(status_code: int, body: str) -> None:
    if status_code in (401, 403):
        raise TutorError("Ошибка авторизации AI-провайдера", 502, "auth_error")
    if status_code == 429:
        raise TutorError("Слишком много запросов, попробуйте позже", 429, "rate_limited")
    if status_code >= 500:
        raise TutorError("Провайдер ИИ временно недоступен", 502, "provider_error")
    raise TutorError(f"Ошибка провайдера ИИ ({status_code})", 502, "provider_error")


def _call_chat(messages: list[dict], model: str | None = None, temperature: float = 0.3) -> str:
    _require_key()
    url = f"{API_BASE}/chat/completions"
    payload = _chat_payload(messages, model, temperature)
    headers = _chat_headers()

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise TutorError("Модель вернула пустой ответ", 502, "empty_content")
                content = choices[0].get("message", {}).get("content")
                if content:
                    return _clean_model_output(content)
                reasoning = choices[0].get("message", {}).get("reasoning_content")
                if reasoning:
                    return _clean_model_output(str(reasoning))
                raise TutorError("Модель вернула пустой ответ", 502, "empty_content")
            if resp.status_code in (401, 403, 429) or resp.status_code >= 500:
                _raise_for_status(resp.status_code, resp.text[:300])
            last_err = TutorError(f"Ошибка провайдера ИИ ({resp.status_code})", 502, "provider_error")
            time.sleep(0.5 * (attempt + 1))
        except requests.exceptions.Timeout:
            last_err = TutorError("Превышено время ожидания ответа ИИ", 504, "timeout")
        except requests.exceptions.ConnectionError:
            last_err = TutorError("Нет связи с провайдером ИИ", 502, "network_error")
        except TutorError:
            raise
        except Exception as e:  # pragma: no cover - defensive
            last_err = TutorError(f"Ошибка обращения к ИИ: {e}", 502, "provider_error")

    if isinstance(last_err, TutorError):
        raise last_err
    raise TutorError("Не удалось получить ответ ИИ", 502, "provider_error")


def stream_chat(messages: list[dict], model: str | None = None, temperature: float = 0.3):
    """Yield text deltas from an OpenAI-compatible streaming response.

    Yields str chunks. Raises TutorError on any provider error (after the
    connection is established, a mid-stream error yields a final sentinel).
    """
    _require_key()
    url = f"{API_BASE}/chat/completions"
    payload = _chat_payload(messages, model, temperature)
    payload["stream"] = True
    headers = _chat_headers()

    resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT, stream=True)
    if resp.status_code != 200:
        _raise_for_status(resp.status_code, resp.text[:300])

    first_chunk_seen = False
    try:
        for raw_line in resp.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            choices = data.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if piece:
                first_chunk_seen = True
                yield piece
        if not first_chunk_seen:
            # Provider returned no streamed content — fall back to error.
            raise TutorError("Модель вернула пустой ответ", 502, "empty_content")
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        raise TutorError("Соединение с ИИ прервано", 502, "stream_interrupted") from e
    finally:
        resp.close()


def _clean_model_output(content) -> str:
    """If the model returned a JSON blob, extract its message; strip fences."""
    text = str(content).strip()
    text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```\s*$", "", text)
    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
            for key in ("message", "reply", "answer", "text", "content"):
                if isinstance(data, dict) and data.get(key):
                    return str(data[key]).strip()
        except Exception:
            pass
    return text


# --------------------------------------------------------------------------
# Context / prompt assembly
# --------------------------------------------------------------------------

def _selection_context(selection: dict | None) -> str | None:
    if not selection or not isinstance(selection, dict):
        return None
    text = (selection.get("selectedText") or "").strip()
    if not text:
        return None
    lines = ["Выделенный фрагмент:", f"<<< {text[:2000]} >>>"]
    if selection.get("sectionTitle"):
        lines.append(f"Заголовок блока: {selection.get('sectionTitle')[:200]}")
    if selection.get("sectionId"):
        lines.append(f"Идентификатор блока: {selection.get('sectionId')[:120]}")
    if selection.get("exampleIndex") is not None:
        lines.append(f"Номер примера: {selection.get('exampleIndex')}")
    if selection.get("stage"):
        lines.append(f"Стадия чертежа: {selection.get('stage')}")
    if selection.get("beforeText"):
        lines.append(f"Текст до выделения: {selection.get('beforeText')[:400]}")
    if selection.get("afterText"):
        lines.append(f"Текст после выделения: {selection.get('afterText')[:400]}")
    return "\n".join(lines)


def _build_user_prompt(payload: dict) -> str:
    method_code = (payload.get("methodCode") or "").strip()
    mode = payload.get("mode") or "free"
    if mode not in ALLOWED_MODES:
        mode = "free"
    hint_level = _safe_int(payload.get("hintLevel"), 0, 0, 4)
    spoiler_allowed = bool(payload.get("spoilerAllowed"))
    student_grade = payload.get("studentGrade")
    message = (payload.get("message") or "").strip()

    sections = ["[КОНТЕКСТ УЧЕБНОГО МАТЕРИАЛА]"]

    method_ctx = atlas_methods.build_method_context(method_code)
    if method_ctx:
        sections.append(
            "Метод: {code} · {name} (раздел {section}, классы {grades}, сложность {difficulty}/4)".format(
                code=method_ctx["code"],
                name=method_ctx["name"],
                section=method_ctx["section"],
                grades=", ".join(str(g) for g in method_ctx["grades"]) or "—",
                difficulty=method_ctx["difficulty"] if method_ctx["difficulty"] is not None else "—",
            )
        )
        sections.append(f"Определение: {method_ctx['definition']}")
        sections.append(f"Теоремы и факты: {method_ctx['theorems']}")
        sections.append(f"Типичные приёмы: {method_ctx['techniques']}")
        sections.append(f"Триггеры: {method_ctx['triggers']}")
        sections.append(f"Почему работает: {method_ctx['whyItWorks']}")
        sections.append(f"Типичные ошибки: {method_ctx['pitfalls']}")
        if method_ctx["signalPhrases"]:
            sections.append("Сигнальные формулировки: " + "; ".join(method_ctx["signalPhrases"]))
        if method_ctx["firstMoves"]:
            sections.append("Первые ходы: " + "; ".join(method_ctx["firstMoves"]))
        if method_ctx["relatedMethods"]:
            sections.append("Связанные методы: " + ", ".join(method_ctx["relatedMethods"]))
        if method_ctx["prerequisites"]:
            sections.append("Предварительные знания: " + ", ".join(method_ctx["prerequisites"]))
    else:
        sections.append("Метод не найден — попроси ученика открыть конкретный метод.")

    # Example context.
    example_index = payload.get("exampleIndex")
    if example_index is not None:
        ex_ctx = atlas_methods.build_example_context(method_code, example_index)
        if ex_ctx:
            sections.append(
                "[ВЫБРАННАЯ ЗАДАЧА] №{index}: {title}\n{body}".format(**ex_ctx)
            )
            if ex_ctx.get("visualSpec"):
                sections.append(f"Описание чертежа (visual_spec): {ex_ctx['visualSpec']}")
            if ex_ctx.get("stageNotes"):
                notes = "; ".join(f"{k}: {v}" for k, v in ex_ctx["stageNotes"].items())
                sections.append(f"Пояснения к стадиям: {notes}")
        else:
            sections.append("[ВЫБРАННАЯ ЗАДАЧА] Задача не найдена.")

    # Visual stage context (for visual mode).
    if mode == "visual" and example_index is not None:
        stage = payload.get("stage") or "condition"
        vis_ctx = atlas_methods.build_visual_context(method_code, example_index, stage)
        if vis_ctx:
            if vis_ctx.get("available"):
                sections.append(
                    "[ЧЕРТЁЖ] {visualId}, стадия {stageName} ({stage}), тип {visualType}".format(
                        visualId=vis_ctx["visualId"],
                        stageName=vis_ctx["stageName"],
                        stage=vis_ctx["stage"],
                        visualType=vis_ctx["visualType"],
                    )
                )
                sections.append(f"Пояснение стадии: {vis_ctx['stageNote']}")
                if vis_ctx.get("svgLabels"):
                    sections.append("Подписи на чертеже: " + ", ".join(vis_ctx["svgLabels"]))
            else:
                sections.append("[ЧЕРТЁЖ] " + vis_ctx.get("note", "Чертежа нет."))

    # Selection context.
    sel = _selection_context(payload.get("selection"))
    if sel:
        sections.append("[ВЫДЕЛЕННЫЙ ФРАГМЕНТ]\n" + sel)

    # UI state.
    sections.append(
        "[СОСТОЯНИЕ] режим={mode}, уровень_подсказки={hint}, спойлер_разрешён={spoiler}, класс={grade}".format(
            mode=mode,
            hint=hint_level,
            spoiler="да" if spoiler_allowed else "нет",
            grade=student_grade if student_grade else "не указан",
        )
    )

    sections.append("[ЗАПРОС УЧЕНИКА]")
    sections.append(message or "(без текста — выполни выбранное действие)")

    return "\n\n".join(sections)


def _hint_ladder_instruction(hint_level: int, spoiler_allowed: bool) -> str:
    ladder = {
        0: "УРОВЕНЬ 0 (диагностика): выясни, что дано, что требуется и что ученик уже заметил. Не давай ходов.",
        1: "УРОВЕНЬ 1 (направление): укажи объект или признак, на который нужно посмотреть. Без конкретных вычислений.",
        2: "УРОВЕНЬ 2 (методический ход): предложи конкретное преобразование, построение, инвариант или разбиение, но без вычислений до ответа.",
        3: "УРОВЕНЬ 3 (каркас решения): перечисли 2–4 шага с пропусками, которые ученик должен заполнить сам.",
        4: "УРОВЕНЬ 4 (полное решение): разрешено ТОЛЬКО если spoiler_allowed=true.",
    }
    if hint_level == 4 and not spoiler_allowed:
        return (
            "Ученик запросил полное решение (уровень 4), но спойлер НЕ разрешён. "
            "Откажи мягко и предложи уровень 3 либо явное подтверждение «показать решение»."
        )
    return ladder[hint_level]


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def prepare_chat(payload: dict, user_id=None, client_ip=None) -> dict:
    """Validate + build context + assemble model messages.

    Returns a dict with keys: messages, model, mode, hint_level,
    spoiler_allowed, suggested_actions, method_links, images.

    Raises TutorError for any user-facing failure (before any network call).
    """
    if not isinstance(payload, dict):
        raise TutorError("Некорректный запрос", 400, "bad_request")

    # Basic rate limit keyed by user or IP.
    rl_key = f"u:{user_id}" if user_id else f"ip:{client_ip or 'anon'}"
    if _rate_limited(rl_key):
        raise TutorError("Слишком много запросов. Подождите немного.", 429, "rate_limited")

    message = (payload.get("message") or "").strip()
    mode = payload.get("mode") or "free"
    if mode not in ALLOWED_MODES:
        mode = "free"

    # Selection-only questions (e.g. "Это непонятно") may have no message.
    if not message and not (payload.get("selection") or {}).get("selectedText"):
        raise TutorError("Введите сообщение", 400, "empty_message")
    if len(message) > MAX_MESSAGE:
        raise TutorError(f"Сообщение слишком длинное (максимум {MAX_MESSAGE} символов)", 400, "too_long")

    images = _validate_images(payload.get("images"))
    history = _validate_history(payload.get("history"))

    system_prompt = load_system_prompt()
    hint_level = _safe_int(payload.get("hintLevel"), 0, 0, 4)
    spoiler_allowed = bool(payload.get("spoilerAllowed"))

    # Hint ladder + spoiler gate.
    if mode == "hint":
        system_prompt += "\n\n" + _hint_ladder_instruction(hint_level, spoiler_allowed)
    elif mode == "check":
        system_prompt += (
            "\n\nРЕЖИМ check: разбери решение по шагам, отметь корректные шаги, "
            "найди ПЕРВЫЙ проблемный шаг, укажи тип проблемы (ошибка/не обосновано/стиль) "
            "и минимальную правку. Не переписывай всё решение."
        )
    elif mode == "visual":
        system_prompt += (
            "\n\nРЕЖИМ visual: объясни чертёж по stage_notes/visual_spec/подписям. "
            "Не выдумывай элементы, которых нет в переданных данных."
        )
    elif mode == "trigger":
        system_prompt += (
            "\n\nРЕЖИМ trigger: используй триггеры, сигнальные фразы, первые ходы и ловушки. "
            "Дай 3–5 надёжных признаков, 1–2 ложных сигнала и отличие от похожих методов."
        )

    user_prompt = _build_user_prompt(payload)

    # Assemble messages with explicit boundaries. User text is untrusted and
    # placed in a clearly delimited section; the system prompt cannot be
    # overridden because it is a separate message role.
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})

    if images:
        # Multimodal: the last user message carries text + images.
        content_parts = [{"type": "text", "text": user_prompt}]
        for img in images:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['mime']};base64,{img['data_b64']}"},
            })
        messages.append({"role": "user", "content": content_parts})
        model = VISION_MODEL
    else:
        messages.append({"role": "user", "content": user_prompt})
        model = MODEL

    return {
        "messages": messages,
        "model": model,
        "mode": mode,
        "hint_level": hint_level,
        "spoiler_allowed": spoiler_allowed,
        "suggested_actions": _suggested_actions(mode, hint_level, spoiler_allowed),
        "method_links": _method_links(payload),
    }


def handle_chat(payload: dict, user_id=None, client_ip=None) -> dict:
    """Validate, build context, call the model, return a client-safe dict.

    Raises TutorError for any user-facing or provider failure.
    """
    prepared = prepare_chat(payload, user_id=user_id, client_ip=client_ip)

    reply = _call_chat(prepared["messages"], model=prepared["model"])

    return {
        "message": reply,
        "status": "ok",
        "hintLevel": prepared["hint_level"],
        "spoilerAllowed": prepared["spoiler_allowed"],
        "mode": prepared["mode"],
        "suggestedActions": prepared["suggested_actions"],
        "methodLinks": prepared["method_links"],
    }


def _validate_history(history) -> list[dict]:
    if not history:
        return []
    if not isinstance(history, list):
        return []
    out = []
    for h in history:
        if not isinstance(h, dict):
            continue
        role = h.get("role")
        if role not in ("user", "assistant"):
            continue
        content = h.get("content")
        if not isinstance(content, str):
            continue
        out.append({"role": role, "content": content[:2000]})
    return out[-MAX_HISTORY:]


def _suggested_actions(mode: str, hint_level: int, spoiler_allowed: bool) -> list[dict]:
    actions = []
    if mode in ("hint", "free"):
        if hint_level < 3:
            actions.append({"type": "next_hint", "label": "Ещё маленький намёк"})
        actions.append({"type": "check_step", "label": "Проверить мой следующий шаг"})
        if hint_level >= 3 and not spoiler_allowed:
            actions.append({"type": "reveal", "label": "Я сдаюсь — показать решение"})
    elif mode == "check":
        actions.append({"type": "check_step", "label": "Проверить исправленное решение"})
    elif mode == "trigger":
        actions.append({"type": "open_method", "label": "Открыть похожий метод"})
    return actions


def _method_links(payload: dict) -> list[dict]:
    method_code = (payload.get("methodCode") or "").strip()
    method = atlas_methods.get_method(method_code)
    if not method:
        return []
    codes = (method.get("related_methods") or [])[:5]
    links = []
    for c in codes:
        m2 = atlas_methods.get_method(c)
        if m2:
            links.append({"code": c, "name": m2.get("method_name", c)})
    return links


def health() -> dict:
    return {
        "available": bool(API_KEY),
        "model": MODEL,
        "visionModel": VISION_MODEL,
        "methodsLoaded": len(atlas_methods._load_atlas()["methods"]),
    }

# -*- coding: utf-8 -*-
"""
Kimi client for solution review (vision + text) via api.moonshot.ai.
For users from Russia: uses .ai domain (not .cn which is geo-blocked).

Usage:
    from services.kimi_review import review_solution
    result = review_solution(attempt_id=42)
    # result: {'raw_response': str, 'label': str, 'error': Optional[str]}

Requirements:
    - KIMI_API_KEY env var (api key for Kimi Platform)
    - KIMI_MODEL env var (model name, e.g. 'kimi-k3')
    - Images: base64 only (no URL) -- Kimi API constraint
"""

import base64
import logging
import os
import time
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)

# ── Kimi API endpoint (use .ai domain — .cn is geo-blocked in Russia) ─
KIMI_API_URL = "https://api.moonshot.ai/v1/chat/completions"

# ── Valid labels (strict set of 3) ──────────────────────────────────
VALID_LABELS = {
    "\u0445\u043e\u0434 \u0432\u0435\u0440\u043d\u044b\u0439",                         # "ход верный"
    "\u0432\u0435\u0440\u043d\u044b\u0439 \u043e\u0442\u0432\u0435\u0442, \u0434\u044b\u0440\u0430 \u0432 \u0440\u0430\u0441\u0441\u0443\u0436\u0434\u0435\u043d\u0438\u0438",  # "верный ответ, дыра в рассуждении"
    "\u0443\u0433\u0430\u0434\u0430\u043b",                                           # "угадал"
}


def _get_kimi_key() -> str:
    """Read KIMI_API_KEY from environment; raise if missing."""
    key = os.environ.get("KIMI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("KIMI_API_KEY not set in environment")
    return key


def _get_kimi_model() -> str:
    """Read KIMI_MODEL from environment; auto-upgrade slow models."""
    model = os.environ.get("KIMI_MODEL", "").strip()
    if not model:
        # kimi-k2.6: fast (3s), returns content directly. kimi-k3 is slow (56s).
        model = "kimi-k2.6"
    # auto-upgrade old/slow models to kimi-k2.6
    if "k2-0905" in model or "kimi-k3" in model:
        logger.info("[Kimi] model %s → upgrading to kimi-k2.6 (faster)", model)
        model = "kimi-k2.6"
    return model


def _extract_label(raw_response: str) -> Optional[str]:
    """Extract a valid label from Kimi raw response.

    The model is prompted to return its label on the LAST line as one of
    three exact strings.  If the last non-empty line matches exactly,
    we return it; otherwise None (the whole response stays as raw_response).
    """
    lines = [ln.strip() for ln in raw_response.strip().split("\n") if ln.strip()]
    if not lines:
        return None
    last_line = lines[-1]
    # Allow the model to wrap in quotes or brackets; try exact match first
    candidate = last_line.strip('"\'\u201c\u201d\u2018\u2019[]')
    if candidate in VALID_LABELS:
        return candidate
    # Also try the original last line exactly
    if last_line in VALID_LABELS:
        return last_line
    return None


def call_kimi_api(
    text: str = "",
    image_base64: Optional[str] = None,
    image_mime: str = "image/jpeg",
) -> str:
    """Call Kimi API (api.moonshot.ai) with text and/or image, return raw response.

    Args:
        text: Text prompt (solution text or task description).
        image_base64: Base64-encoded image (no data URI prefix).
        image_mime: MIME type of the image (default image/jpeg).

    Returns:
        Raw response text from the model.

    Raises:
        RuntimeError on API failure after retries.
    """
    api_key = _get_kimi_key()
    model = _get_kimi_model()

    # ── Build messages ───────────────────────────────────────────────
    system_prompt = (
        "Ты — ассистент-математик, проверяющий решения олимпиадных задач. "
        "Ты получаешь условие задачи, верный ответ и решение ученика (текст или фото). "
        "Твоя задача — разобрать ход решения и поставить ОДНУ из трёх меток "
        "СТРОГО на последней строке ответа без кавычек и знаков препинания:\n"
        "ход верный\n"
        "верный ответ, дыра в рассуждении\n"
        "угадал\n"
        "Перед меткой дай краткий комментарий (1-3 предложения) о ходе решения. "
        "Метка должна быть на отдельной последней строке."
    )

    user_content = []
    if text:
        user_content.append({"type": "text", "text": text})
    if image_base64:
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{image_mime};base64,{image_base64}",
                "detail": "high",
            },
        })

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content if len(user_content) > 1 else (user_content[0]["text"] if user_content else "")},
    ]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 1.0,
        "max_tokens": 1024,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    max_retries = 3
    base_delay = 2.0

    for attempt in range(max_retries):
        try:
            logger.info(f"[Kimi] api.moonshot.ai attempt {attempt + 1}/{max_retries} model={model}")
            resp = requests.post(
                KIMI_API_URL,
                headers=headers,
                json=payload,
                timeout=120,
            )

            if resp.status_code == 200:
                data = resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    msg = data["choices"][0].get("message", {}) or {}
                    content = msg.get("content") or ""
                    # All moonshot.ai models are reasoning models:
                    # content is often empty, real answer in reasoning_content.
                    if not content:
                        content = msg.get("reasoning_content") or ""
                        if content:
                            logger.info(f"[Kimi] using reasoning_content ({len(content)} chars)")
                    if content:
                        logger.info(f"[Kimi] ok ({len(content)} chars)")
                        return content
                    raise RuntimeError("Kimi: empty content in response (both content and reasoning_content empty)")
                raise RuntimeError("Kimi: no choices in response")

            if resp.status_code in (401, 403):
                raise RuntimeError(
                    f"Kimi auth/access denied ({resp.status_code}): {resp.text[:200]}"
                )

            if resp.status_code == 429:
                wait = 30
                logger.warning(f"[Kimi] 429, waiting {wait}s")
                time.sleep(wait)
                continue

            if resp.status_code in (500, 502, 503, 504):
                wait = base_delay * (2 ** attempt)
                logger.warning(f"[Kimi] {resp.status_code}, waiting {wait}s")
                time.sleep(wait)
                continue

            raise RuntimeError(f"Kimi HTTP {resp.status_code}: {resp.text[:300]}")

        except requests.exceptions.Timeout:
            wait = base_delay * (2 ** attempt)
            logger.warning(f"[Kimi] timeout, waiting {wait}s")
            time.sleep(wait)
        except requests.exceptions.ConnectionError as e:
            wait = base_delay * (2 ** attempt)
            logger.warning(f"[Kimi] connection error: {e}, waiting {wait}s")
            time.sleep(wait)
        except RuntimeError:
            raise  # non-retryable

    raise RuntimeError(f"Kimi: failed after {max_retries} attempts")


def review_solution(
    attempt_id: int,
    surface: str = "probe",
) -> Dict[str, Any]:
    """Review a solution attempt via Kimi and return label + raw response.

    Args:
        attempt_id: ID of the SolutionAttempt row.
        surface: One of 'probe', 'daily_task', 'method' — checked against toggles.

    Returns:
        {'raw_response': str, 'label': Optional[str], 'error': Optional[str]}

    Does NOT modify mu, sigma, is_correct, or any scoring column.
    Saves result to kimi_reviews table.
    """
    from models import db, SolutionAttempt, AdaptiveTask
    from models import KimiReview  # type: ignore[attr-defined]

    # ── Toggle check ─────────────────────────────────────────────────
    if not _kimi_enabled_for(surface):
        return {
            "raw_response": "",
            "label": None,
            "error": f"Kimi review disabled for surface '{surface}'",
        }

    attempt = db.session.get(SolutionAttempt, attempt_id)
    if not attempt:
        return {"raw_response": "", "label": None, "error": f"SolutionAttempt {attempt_id} not found"}

    # ── Build prompt with task context ───────────────────────────────
    task = db.session.get(AdaptiveTask, attempt.task_id)
    task_text = task.task_text if task else "(task not found)"
    correct_answer = task.correct_answer if task and task.correct_answer else "(not available)"

    prompt_text = (
        f"Задача:\n{task_text}\n\n"
        f"Верный ответ: {correct_answer}\n\n"
    )

    image_base64 = None
    if attempt.attempt_type == "text":
        prompt_text += f"Решение ученика (текст):\n{attempt.solution_text or '(пусто)'}"
    elif attempt.attempt_type == "photo":
        prompt_text += "Решение ученика на фото ниже."
        if attempt.file_path:
            # Build absolute path from static folder
            from flask import current_app
            abs_path = os.path.join(current_app.static_folder, attempt.file_path)
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, "rb") as f:
                        image_bytes = f.read()
                    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                except Exception as e:
                    logger.warning(f"[Kimi] failed to read photo {abs_path}: {e}")
            else:
                logger.warning(f"[Kimi] photo file not found: {abs_path}")

    # ── Call API ─────────────────────────────────────────────────────
    try:
        raw_response = call_kimi_api(
            text=prompt_text,
            image_base64=image_base64,
        )
    except Exception as e:
        logger.error(f"[Kimi] API call failed: {e}")
        # Save failed review too (for debugging)
        review = KimiReview(
            solution_attempt_id=attempt_id,
            raw_response=str(e)[:2000],
            label=None,
        )
        db.session.add(review)
        db.session.commit()
        return {"raw_response": "", "label": None, "error": str(e)}

    label = _extract_label(raw_response)

    # ── Persist ──────────────────────────────────────────────────────
    review = KimiReview(
        solution_attempt_id=attempt_id,
        raw_response=raw_response,
        label=label,
    )
    db.session.add(review)
    db.session.commit()

    return {
        "raw_response": raw_response,
        "label": label,
        "error": None,
    }


def review_text(
    task_text: str,
    correct_answer: str,
    solution_text: str,
    surface: str = "probe",
    image_base64: Optional[str] = None,
) -> Dict[str, Any]:
    """Review a solution via Kimi without a SolutionAttempt record.

    For surfaces that don't create SolutionAttempt (daily_tasks, olympiad methods).

    Returns:
        {'raw_response': str, 'label': Optional[str], 'error': Optional[str]}
    """
    from models import db, KimiReview

    if not _kimi_enabled_for(surface):
        return {
            "raw_response": "",
            "label": None,
            "error": f"Kimi review disabled for surface '{surface}'",
        }

    prompt_text = (
        f"Задача:\n{task_text}\n\n"
        f"Верный ответ: {correct_answer}\n\n"
        f"Решение ученика:\n{solution_text}"
    )

    try:
        raw_response = call_kimi_api(
            text=prompt_text,
            image_base64=image_base64,
        )
    except Exception as e:
        logger.error(f"[Kimi] review_text API call failed: {e}")
        return {"raw_response": "", "label": None, "error": str(e)}

    label = _extract_label(raw_response)

    review = KimiReview(
        solution_attempt_id=None,
        raw_response=raw_response,
        label=label,
    )
    db.session.add(review)
    db.session.commit()

    return {
        "raw_response": raw_response,
        "label": label,
        "error": None,
    }


def _kimi_enabled_for(surface: str) -> bool:
    """Check if Kimi review is enabled for the given surface.

    Looks at fields on the current user:
      - kimi_review_probe (bool)   for 'probe'
      - kimi_review_daily (bool)   for 'daily_task'
      - kimi_review_method (bool)  for 'method'

    If user is not logged in or fields are missing, returns False.
    """
    try:
        from flask_login import current_user
        if not current_user or not current_user.is_authenticated:
            return False
        if surface == "probe":
            return bool(getattr(current_user, "kimi_review_probe", False))
        elif surface == "daily_task":
            return bool(getattr(current_user, "kimi_review_daily", False))
        elif surface == "method":
            return bool(getattr(current_user, "kimi_review_method", False))
        return False
    except Exception:
        return False

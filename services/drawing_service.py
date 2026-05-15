# -*- coding: utf-8 -*-
# Drawing service: code-generation pipeline for geometry diagrams.
# Pipeline overview (see routes/drawing.py for the HTTP surface):
#   1. Hash the problem text and look it up in an on-disk cache.
#   2. Ask Claude Sonnet to author matplotlib code (text-only LLM call).
#   3. Run that code inside services.sandbox (AST whitelist + subprocess).
#   4. If the sandbox raises, feed the traceback back to the LLM for repair
#      (max 2 iterations).
#   5. Persist PNG to cache and to DrawingGeneration log; return bytes + meta.

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

from services.openrouter_client import openrouter, OpenRouterError
from services.sandbox import (
    run_drawing_code,
    SandboxError,
    SandboxRejected,
    SandboxTimeout,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------- config

# Hard-coded per product decision: drawing pipeline runs on the newest Sonnet
# slug; do NOT make this env-configurable.  Fallback is DeepSeek (cheap) for
# the rare case the primary slug is unavailable on OpenRouter.
MODEL_PRIMARY = "anthropic/claude-sonnet-4.7"
MODEL_FALLBACK = "deepseek/deepseek-chat"

MAX_REPAIR_ITERS = 2
CACHE_TTL_SEC = 30 * 24 * 3600     # 30 days
CACHE_DIR_NAME = os.path.join("static", "generated", "cache")

SYSTEM_PROMPT = (
    "Ты пишешь Python-код на matplotlib для построения геометрических\n"
    "чертежей по русскоязычному условию задачи. Возвращай ТОЛЬКО код в\n"
    "блоке ```python, без пояснений до или после.\n\n"
    "Жёсткие требования к коду:\n"
    "- Разрешены только импорты: matplotlib, numpy, math.\n"
    "- Никаких import os/sys/subprocess/socket/requests, никаких open/exec/\n"
    "  eval, никаких сетевых вызовов или файловых операций.\n"
    "- Создавай ровно одну фигуру через plt.subplots(), без plt.show().\n"
    "- НЕ вызывай plt.savefig: обёртка сама сохранит plt.gcf() в PNG.\n\n"
    "Стиль чертежа:\n"
    "- Чёрные линии 2 px на чисто белом фоне (#FFFFFF).\n"
    "- Шрифт подписей: sans-serif, 18-22 px, цвет чёрный.\n"
    "- Имена вершин — одиночные заглавные латинские буквы (A, B, C, …).\n"
    "- Двухбуквенные сочетания (AB, BC) — это отрезки, не вершины.\n"
    "- Длины подписывай числом без префикса (5, 7, …) рядом с серединой\n"
    "  соответствующего отрезка.\n"
    "- Углы рисуй дугами; подпись «N°» внутри угла.\n"
    "- Прямые углы — квадратиком, равные отрезки — короткими штрихами,\n"
    "  равные углы — двойными дугами.\n"
    "- Никаких теней, градиентов, цветных элементов кроме чёрного.\n\n"
    "Геометрическая корректность:\n"
    "- Координаты вычисляй математически точно (теоремы синусов/косинусов,\n"
    "  свойства окружностей и т.д.).\n"
    "- Соблюдай пропорции: фигура должна выглядеть так, как описано в\n"
    "  условии, без визуальных искажений.\n"
    "- Не добавляй построений, которых нет в условии (высоты, биссектрисы\n"
    "  и т.п.).\n\n"
    "Канва: plt.subplots(figsize=(8, 8), dpi=128), ax.set_aspect('equal'),\n"
    "ax.axis('off'). Подгоняй xlim/ylim вручную с запасом 10 процентов от\n"
    "максимального габарита фигуры."
)


# ------------------------------------------------------------------ result

@dataclass
class DrawingResult:
    image_bytes: bytes
    code: str
    model: Optional[str]
    cost_usd: float
    render_ms: int
    cache_hit: bool
    repair_iters: int
    attempts: List[dict] = field(default_factory=list)


# ------------------------------------------------------------------ helpers

_CODE_FENCE_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE
)


def _extract_code(text: str) -> Optional[str]:
    if not text:
        return None
    m = _CODE_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    s = text.strip()
    if s.startswith("import ") or s.startswith("from "):
        return s
    return None


def _problem_hash(problem: str) -> str:
    payload = (MODEL_PRIMARY + "::" + problem.strip()).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _cache_paths(app_root: str, sha: str):
    base = os.path.join(app_root, CACHE_DIR_NAME)
    os.makedirs(base, exist_ok=True)
    png = os.path.join(base, sha + ".png")
    meta = os.path.join(base, sha + ".meta.txt")
    return png, meta


def _read_cache(png_path: str, meta_path: str) -> Optional[tuple]:
    if not os.path.exists(png_path):
        return None
    if time.time() - os.path.getmtime(png_path) > CACHE_TTL_SEC:
        return None
    try:
        with open(png_path, "rb") as f:
            data = f.read()
        if not data or data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        code = ""
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                code = f.read()
        return data, code
    except OSError:
        return None


def _write_cache(png_path: str, meta_path: str, image_bytes: bytes, code: str):
    try:
        with open(png_path, "wb") as f:
            f.write(image_bytes)
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(code)
    except OSError as e:
        logger.warning("[drawing] failed to write cache: %s", e)


# ------------------------------------------------------------------ LLM


def _call_llm(messages: list, model: str) -> dict:
    """Return openrouter.chat() result with low temperature, JSON ignored."""
    return openrouter.chat(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=2048,
    )


def _build_initial_messages(problem: str) -> list:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": problem.strip()},
    ]


def _build_repair_messages(
    problem: str, prev_code: str, error_text: str
) -> list:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": problem.strip()},
        {"role": "assistant", "content": "```python\n" + prev_code + "\n```"},
        {
            "role": "user",
            "content": (
                "Код упал при выполнении. Вот traceback:\n"
                "```\n" + error_text.strip() + "\n```\n"
                "Исправь ошибку и верни ПОЛНЫЙ обновлённый код в одном\n"
                "блоке ```python```. Никаких пояснений."
            ),
        },
    ]


# ------------------------------------------------------------------ public


def generate_drawing(
    problem: str,
    *,
    app_root: Optional[str] = None,
    use_cache: bool = True,
) -> DrawingResult:
    """Run the full pipeline. Raises OpenRouterError or SandboxError."""
    started = time.time()
    problem = (problem or "").strip()
    if not problem:
        raise ValueError("empty problem")

    app_root = app_root or os.getcwd()
    sha = _problem_hash(problem)
    png_path, meta_path = _cache_paths(app_root, sha)

    # 1) Cache
    if use_cache:
        cached = _read_cache(png_path, meta_path)
        if cached is not None:
            data, code = cached
            return DrawingResult(
                image_bytes=data,
                code=code,
                model=None,
                cost_usd=0.0,
                render_ms=int((time.time() - started) * 1000),
                cache_hit=True,
                repair_iters=0,
                attempts=[{"stage": "cache", "ok": True}],
            )

    attempts: List[dict] = []
    total_cost = 0.0
    chosen_model = MODEL_PRIMARY
    messages = _build_initial_messages(problem)
    last_code = ""
    last_error = "unknown"

    for iteration in range(MAX_REPAIR_ITERS + 1):
        # --- LLM call (primary, then fallback once) ---
        llm_resp = None
        for candidate in (chosen_model, MODEL_FALLBACK):
            try:
                llm_resp = _call_llm(messages, candidate)
                chosen_model = candidate
                break
            except OpenRouterError as e:
                attempts.append({
                    "stage": "llm",
                    "iter": iteration,
                    "model": candidate,
                    "ok": False,
                    "error": str(e)[:300],
                })
                continue

        if llm_resp is None:
            raise OpenRouterError("all LLMs failed for drawing code generation")

        total_cost += float(llm_resp.get("cost_usd") or 0.0)
        content = (llm_resp.get("content") or "").strip()
        code = _extract_code(content)
        if not code:
            last_error = "no python code block in LLM response"
            attempts.append({
                "stage": "extract",
                "iter": iteration,
                "model": chosen_model,
                "ok": False,
                "error": last_error,
            })
            # Ask again, treating as repair
            messages = _build_repair_messages(problem, last_code or "", last_error)
            continue

        last_code = code

        # --- Sandbox execution ---
        try:
            image_bytes = run_drawing_code(code, timeout=12.0)
            attempts.append({
                "stage": "sandbox",
                "iter": iteration,
                "model": chosen_model,
                "ok": True,
            })
            if use_cache:
                _write_cache(png_path, meta_path, image_bytes, code)
            return DrawingResult(
                image_bytes=image_bytes,
                code=code,
                model=chosen_model,
                cost_usd=round(total_cost, 6),
                render_ms=int((time.time() - started) * 1000),
                cache_hit=False,
                repair_iters=iteration,
                attempts=attempts,
            )
        except (SandboxRejected, SandboxTimeout, SandboxError) as e:
            last_error = type(e).__name__ + ": " + str(e)
            attempts.append({
                "stage": "sandbox",
                "iter": iteration,
                "model": chosen_model,
                "ok": False,
                "error": last_error[:2000],
            })
            messages = _build_repair_messages(problem, code, last_error)
            continue

    # Out of iterations
    raise SandboxError(
        "drawing generation failed after %d repair iterations; last error: %s"
        % (MAX_REPAIR_ITERS, last_error[:500])
    )
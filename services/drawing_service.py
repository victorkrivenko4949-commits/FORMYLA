# -*- coding: utf-8 -*-
# Drawing service: code-generation pipeline for geometry diagrams.
#
# Pipeline overview (HTTP surface lives in routes/drawing.py):
#
#   1. Hash the problem text and look it up in an on-disk PNG cache.
#   2. Ask Claude Sonnet to author matplotlib code (text-only LLM call,
#      conversation kept in `messages` so future critiques continue the same
#      dialog).
#   3. Run that code inside services.sandbox (AST whitelist + subprocess).
#      If the sandbox raises, feed the traceback back to Claude (self-repair
#      loop, MAX_REPAIR_ITERS = 2 iterations).
#   4. NEW: critique stage.  Send (problem, code, PNG) to Gemini 2.5 Pro
#      (vision-capable) and ask for a structured list of geometric errors.
#      Gemini answers with JSON of findings.
#      For each round (MAX_CRITIQUE_ROUNDS = 2):
#         - If findings == []  -> stop, the drawing is good.
#         - Else send the findings back into the SAME Claude dialog with the
#           instruction "по каждой ошибке: согласись и исправь или
#           мотивированно отклони".  Claude returns updated code.
#           We re-run the sandbox (self-repair allowed inside this round).
#   5. Persist PNG to cache and log the run to DrawingGeneration.

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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
MODEL_PRIMARY = "anthropic/claude-opus-4.7"
MODEL_FALLBACK = None

# Critic model — vision-capable, geometry-aware.
MODEL_CRITIC = "google/gemini-3.1-pro"

# Critic stage is OFF by default (slow on Render Free Tier where the
# request timeout is ~100s).  Flip the env var to "1" / "true" to enable.
CRITIC_ENABLED = (os.environ.get("DRAWING_CRITIC_ENABLED", "0")
                  .strip().lower() in ("1", "true", "yes", "on"))

MAX_REPAIR_ITERS = 2          # for syntax/runtime errors inside one round
MAX_CRITIQUE_ROUNDS = 2       # how many times the critic is consulted
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


CRITIC_SYSTEM_PROMPT = (
    "Ты — строгий ревьюер геометрических чертежей. Тебе дают:\n"
    "  (1) текст условия задачи на русском,\n"
    "  (2) исходный Python-код на matplotlib,\n"
    "  (3) PNG этого чертежа.\n"
    "\n"
    "Твоя задача — НАЙТИ ОШИБКИ ГЕОМЕТРИИ И ЧИТАЕМОСТИ. Тебя НЕ интересует\n"
    "стиль кода, его длина или эффективность. Не придирайся к незначительным\n"
    "косметическим мелочам.\n"
    "\n"
    "Ищи (в порядке важности):\n"
    "  * нарушения условия задачи (неверные длины, неверные углы, отсутствие\n"
    "    указанных в условии объектов, лишние построения, не упомянутые в\n"
    "    условии);\n"
    "  * математически неверное расположение точек (например, точка должна\n"
    "    лежать на окружности, но реально лежит вне её);\n"
    "  * несоответствие пропорций (фигура выглядит как другая фигура);\n"
    "  * перекрывающиеся подписи, нечитаемые названия вершин, отрезанные\n"
    "    краями полотна объекты.\n"
    "\n"
    "Не ищи микро-косметику (наклон шрифта, толщина линии в пикселе и т.п.).\n"
    "\n"
    "Верни ОТВЕТ СТРОГО В ВИДЕ ОДНОГО JSON-объекта без дополнительного текста\n"
    "и без markdown-fences, по схеме:\n"
    "\n"
    "  __OPEN_BRACE__\n"
    '    "findings": [ ... ]\n'
    "  __CLOSE_BRACE__\n"
    "\n"
    "где каждый элемент массива — объект:\n"
    "\n"
    "  __OPEN_BRACE__\n"
    '    "id": "f1",\n'
    '    "severity": "blocker" | "major" | "minor",\n'
    '    "title": "краткое название ошибки",\n'
    '    "detail": "конкретное описание: что в коде/чертеже неверно",\n'
    '    "fix_hint": "как именно нужно исправить"\n'
    "  __CLOSE_BRACE__\n"
    "\n"
    "ID должны быть уникальны (f1, f2, ...). Если ошибок не нашёл, верни\n"
    '__OPEN_BRACE__"findings": []__CLOSE_BRACE__.'
)
# `{` and `}` are kept as placeholders to avoid streaming-tool issues; they
# are substituted into real braces right after definition.
CRITIC_SYSTEM_PROMPT = (
    CRITIC_SYSTEM_PROMPT
    .replace("__OPEN_BRACE__", "{")
    .replace("__CLOSE_BRACE__", "}")
)


# ------------------------------------------------------------------ result

@dataclass
class CritiqueFinding:
    id: str
    severity: str
    title: str
    detail: str
    fix_hint: str
    # filled after Claude responds
    claude_decision: Optional[str] = None      # "accepted" | "rejected"
    claude_reasoning: Optional[str] = None


@dataclass
class DrawingResult:
    image_bytes: bytes
    code: str
    model: Optional[str]
    cost_usd: float
    render_ms: int
    cache_hit: bool
    repair_iters: int
    critique_rounds: int = 0
    critique_findings: List[CritiqueFinding] = field(default_factory=list)
    critique_accepted: int = 0
    critique_rejected: int = 0
    attempts: List[dict] = field(default_factory=list)


# ------------------------------------------------------------------ helpers

_CODE_FENCE_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE
)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


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


def _build_repair_user_msg(error_text: str) -> dict:
    return {
        "role": "user",
        "content": (
            "Код упал при выполнении. Вот traceback:\n"
            "```\n" + error_text.strip() + "\n```\n"
            "Исправь ошибку и верни ПОЛНЫЙ обновлённый код в одном\n"
            "блоке ```python```. Никаких пояснений."
        ),
    }


def _build_critique_user_msg(findings: List[CritiqueFinding]) -> dict:
    # Forward the structured critique back to Claude in the same dialog.
    lines = [
        "Внешний ревьюер (Gemini) посмотрел условие задачи, твой код и",
        "сгенерированный PNG. Он нашёл следующие замечания:",
        "",
    ]
    for f in findings:
        lines.append("[" + f.id + " | " + f.severity + "] " + f.title)
        lines.append("  Описание: " + f.detail)
        lines.append("  Подсказка по исправлению: " + f.fix_hint)
        lines.append("")
    lines.extend([
        "По каждой ошибке прими решение:",
        '  - если согласен — исправь её в коде;',
        '  - если НЕ согласен (ревьюер не прав) — оставь как было',
        "    и кратко объясни, почему отклонил.",
        "",
        "Верни ОТВЕТ В ДВУХ ЧАСТЯХ И ИМЕННО В ЭТОМ ПОРЯДКЕ:",
        "",
        "(1) Сводка решений в JSON-объекте без дополнительного текста:",
        '    {"decisions": [{"id": "f1", "decision": "accepted" | "rejected",',
        '                    "reason": "коротко"}]}',
        "",
        "(2) ПОЛНЫЙ обновлённый Python-код в блоке ```python```.",
        "    Если ты со всеми замечаниями не согласен — всё равно",
        "    выложи ТЕКУЩИЙ полный код (без изменений), не пропуская блок.",
    ])
    return {"role": "user", "content": "\n".join(lines)}


def _parse_decisions(text: str, findings: List[CritiqueFinding]) -> None:
    # Mutates `findings` in-place: sets claude_decision and claude_reasoning.
    if not text:
        return
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return
    by_id = {f.id: f for f in findings}
    for d in obj.get("decisions") or []:
        fid = d.get("id")
        if fid in by_id:
            decision = d.get("decision")
            if decision in ("accepted", "rejected"):
                by_id[fid].claude_decision = decision
            by_id[fid].claude_reasoning = (d.get("reason") or "")[:300]


# ------------------------------------------------------------------ critic


def _build_critic_messages(problem: str, code: str, png_bytes: bytes) -> list:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    data_url = "data:image/png;base64," + b64
    user_blocks = [
        {
            "type": "text",
            "text": (
                "Условие задачи:\n"
                "\"\"\"\n" + problem.strip() + "\n\"\"\"\n\n"
                "Исходный код, который нарисовал чертёж:\n"
                "```python\n" + code + "\n```\n\n"
                "Сам PNG прикреплён ниже. Проанализируй чертёж и верни\n"
                "findings строго в требуемом JSON-формате."
            ),
        },
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    return [
        {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
        {"role": "user", "content": user_blocks},
    ]


def _parse_critique_response(text: str) -> List[CritiqueFinding]:
    if not text:
        return []
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return []
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return []
    out: List[CritiqueFinding] = []
    for i, f in enumerate(obj.get("findings") or []):
        out.append(CritiqueFinding(
            id=str(f.get("id") or ("f" + str(i + 1))),
            severity=str(f.get("severity") or "minor"),
            title=str(f.get("title") or "")[:200],
            detail=str(f.get("detail") or "")[:1000],
            fix_hint=str(f.get("fix_hint") or "")[:500],
        ))
    return out


def _critique_with_gemini(
    problem: str, code: str, png_bytes: bytes
) -> Tuple[List[CritiqueFinding], float]:
    """Returns (findings, cost_usd).  Raises OpenRouterError on transport
    failure — caller decides whether to swallow."""
    messages = _build_critic_messages(problem, code, png_bytes)
    resp = openrouter.chat(
        model=MODEL_CRITIC,
        messages=messages,
        temperature=0.0,
        max_tokens=1500,
    )
    content = (resp.get("content") or "").strip()
    findings = _parse_critique_response(content)
    return findings, float(resp.get("cost_usd") or 0.0)


# ------------------------------------------------------------------ main flow


def _generate_code_until_renders(
    problem: str,
    messages: list,
    attempts: list,
    chosen_model: str,
) -> Tuple[bytes, str, str, list, float, int]:
    """
    Runs the LLM + sandbox + self-repair sub-loop.

    Returns: (png, code, used_model, messages_history, cost_usd_added, repair_iters_used)
    Raises:  SandboxError if the loop exhausts MAX_REPAIR_ITERS.
             OpenRouterError if every model candidate fails to respond at all.
    """
    total_cost = 0.0
    last_error = "unknown"
    last_code = ""

    for iteration in range(MAX_REPAIR_ITERS + 1):
        # --- LLM call (primary, then fallback) ---
        llm_resp = None
        for candidate in [c for c in (chosen_model, MODEL_FALLBACK) if c]:
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
            raise OpenRouterError(
                "all LLMs failed for drawing code generation"
            )

        total_cost += float(llm_resp.get("cost_usd") or 0.0)
        content = (llm_resp.get("content") or "").strip()
        # keep dialog history honest
        messages = messages + [{"role": "assistant", "content": content}]

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
            messages = messages + [_build_repair_user_msg(last_error)]
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
            return image_bytes, code, chosen_model, messages, total_cost, iteration
        except (SandboxRejected, SandboxTimeout, SandboxError) as e:
            last_error = type(e).__name__ + ": " + str(e)
            attempts.append({
                "stage": "sandbox",
                "iter": iteration,
                "model": chosen_model,
                "ok": False,
                "error": last_error[:2000],
            })
            messages = messages + [_build_repair_user_msg(last_error)]
            continue

    raise SandboxError(
        "drawing code-generation failed after "
        + str(MAX_REPAIR_ITERS)
        + " repair iterations; last error: "
        + last_error[:500]
    )


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
    messages = _build_initial_messages(problem)

    # 2) First successful render
    image_bytes, code, used_model, messages, cost_added, repair_used = (
        _generate_code_until_renders(
            problem, messages, attempts, MODEL_PRIMARY,
        )
    )
    total_cost += cost_added
    total_repair_iters = repair_used

    # 3) Critique loop (Gemini Vision)
    all_findings: List[CritiqueFinding] = []
    rounds_done = 0
    accepted_total = 0
    rejected_total = 0

    _eff_rounds = MAX_CRITIQUE_ROUNDS if CRITIC_ENABLED else 0
    for round_idx in range(_eff_rounds):
        try:
            findings, critic_cost = _critique_with_gemini(
                problem, code, image_bytes
            )
            total_cost += critic_cost
            attempts.append({
                "stage": "critic",
                "round": round_idx,
                "model": MODEL_CRITIC,
                "ok": True,
                "findings_count": len(findings),
            })
        except OpenRouterError as e:
            # Critic failed — degrade gracefully, keep the current PNG.
            attempts.append({
                "stage": "critic",
                "round": round_idx,
                "model": MODEL_CRITIC,
                "ok": False,
                "error": str(e)[:300],
            })
            break

        if not findings:
            break  # drawing is clean
        rounds_done += 1

        # Ask Claude to revise (same dialog).
        messages = messages + [_build_critique_user_msg(findings)]
        try:
            new_png, new_code, used_model, messages, cost2, repair2 = (
                _generate_code_until_renders(
                    problem, messages, attempts, used_model,
                )
            )
        except (SandboxError, OpenRouterError) as e:
            # Revision failed.  Keep last good PNG.
            attempts.append({
                "stage": "critique-revise",
                "round": round_idx,
                "ok": False,
                "error": str(e)[:300],
            })
            all_findings.extend(findings)
            break

        total_cost += cost2
        total_repair_iters += repair2

        # Parse Claude's decision summary (the JSON before the code block).
        last_assistant_msg = next(
            (m for m in reversed(messages) if m.get("role") == "assistant"),
            None,
        )
        if last_assistant_msg:
            _parse_decisions(last_assistant_msg.get("content", ""), findings)

        # Tally decisions
        for f in findings:
            if f.claude_decision == "accepted":
                accepted_total += 1
            elif f.claude_decision == "rejected":
                rejected_total += 1
        all_findings.extend(findings)

        code = new_code
        image_bytes = new_png

    # 4) Cache + return
    if use_cache:
        _write_cache(png_path, meta_path, image_bytes, code)

    return DrawingResult(
        image_bytes=image_bytes,
        code=code,
        model=used_model,
        cost_usd=round(total_cost, 6),
        render_ms=int((time.time() - started) * 1000),
        cache_hit=False,
        repair_iters=total_repair_iters,
        critique_rounds=rounds_done,
        critique_findings=all_findings,
        critique_accepted=accepted_total,
        critique_rejected=rejected_total,
        attempts=attempts,
    )

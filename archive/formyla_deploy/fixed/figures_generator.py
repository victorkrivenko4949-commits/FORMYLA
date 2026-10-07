# -*- coding: utf-8 -*-
# Blueprint "/figures/generate" — new figure generation pipeline (CH5).
#
# Uses: DeepSeek API directly (not OpenRouter), GeometricEngine for SVG.
# Queue is stored in figure_build_jobs table (DB, not in-process memory).
# Credits are charged only on status=done, refunded on status=failed.
#
# Routes:
#   GET  /figures/generate          — render the generator page
#   POST /figures/generate/start    — create a build job (returns job_id)
#   GET  /figures/generate/status/<int:job_id> — poll job status

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from threading import Lock

import requests
from typing import Any
from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
)

try:
    from flask_login import current_user, login_required
except Exception:
    current_user = None

    def login_required(f):
        return f


from services.figure_validator import validate_figure_json
from services.llm_router import (
    LLMError,
    call_llm,
    logical_model_for_role,
    max_tokens_for_role,
    resolve_provider_model,
    build_provider_chain,
    describe_roles,
    thinking_mode_for_role,
)

logger = logging.getLogger(__name__)

figures_gen_bp = Blueprint("figures_generator", __name__, url_prefix="/figures/generate")

# ── Config ──────────────────────────────────────────────────────────────
# Анализ условия задачи (текст -> JSON чертежа) идёт через Novita AI,
# как и всё остальное распознавание/генерация в проекте.
NOVITA_API_KEY = os.environ.get("NOVITA_API_KEY", "")
if NOVITA_API_KEY:
    NOVITA_API_KEY = NOVITA_API_KEY.strip()
NOVITA_BASE_URL = "https://api.novita.ai/v3/openai/chat/completions"
# Текстовая модель Novita для ризонера (проверено: отвечает 200 OK).
NOVITA_REASONER_MODEL = os.environ.get(
    "NOVITA_REASONER_MODEL", "deepseek/deepseek-v3-0324"
).strip()

# Резерв: прямой DeepSeek API, если ключ Novita не задан.
_REASONER_FALLBACK = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
REASONER_MODEL = os.environ.get("FIGURE_MODEL", _REASONER_FALLBACK).strip()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
if DEEPSEEK_API_KEY:
    DEEPSEEK_API_KEY = DEEPSEEK_API_KEY.strip()
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1/chat/completions"
# deepseek-v4-pro is a reasoning model: a single CoT pass can exceed 90s.
# Use a generous per-request timeout so the job isn't killed mid-reasoning.
DEEPSEEK_TIMEOUT = 300  # seconds
MAX_RETRIES = 2
MAX_PROBLEM_LENGTH = 4000
# Лимит генераций в час на пользователя (настраивается env для тестов).
RATE_LIMIT_MAX = int(os.environ.get("FIGURE_RATE_LIMIT_MAX", "10") or "10")
RATE_LIMIT_WINDOW = int(os.environ.get("FIGURE_RATE_LIMIT_WINDOW", "3600") or "3600")

# Служебный batch-аккаунт (scripts/batch/run_batch.py, _autopilot.py) не должен
# обгонять живых пользователей в очереди чертежей.  Его задачи получают
# приоритет ниже, чем у бесплатных пользователей (0) и подписчиков (1).
BATCH_SERVICE_EMAIL = "batch@formyla.local"
BATCH_PRIORITY = -1

# ── CH15: condition → solution two-layer pipeline ────────────────────────
# Feature flag: пока включён по умолчанию, но legacy-режим остаётся доступен
# через generation_mode='legacy'.  Отключение флага возвращает всё поведение
# к однопроходному «условие -> один JSON».
CONDITION_SOLUTION_ENABLED = (
    os.environ.get(
        "FIGURE_CONDITION_SOLUTION_PIPELINE_ENABLED", "1"
    ).strip().lower()
    in ("1", "true", "yes", "on")
)

# CH16: семантические цвета по visual_role (dark_geometry тема).
# CH30 ЭТАП 1: включено по умолчанию (true) — рендер-слой был живой, но
# выключен.  Можно отключить явным флагом FIGURE_SEMANTIC_COLORS_ENABLED=false.
FIGURE_SEMANTIC_COLORS_ENABLED = (
    os.environ.get(
        "FIGURE_SEMANTIC_COLORS_ENABLED", "1"
    ).strip().lower()
    in ("1", "true", "yes", "on")
)

# CH19: auto-fit презентации по умолчанию для generation_mode="condition_solution".
# Не меняет относительную геометрию — только масштаб и сдвиг сцены.
FIGURE_AUTO_FIT_ENABLED = (
    os.environ.get(
        "FIGURE_AUTO_FIT_ENABLED", "true"
    ).strip().lower()
    in ("1", "true", "yes", "on")
)

# CH21 PART 2: максимум base-repair попыток (env override).
MAX_BASE_REPAIRS = int(os.environ.get("FIGURE_MAX_BASE_REPAIRS", "2") or "2")

# CH19.1: восстановленное списание figure_credits.
# При true — атомарный CAS-декремент на done + refund ровно один раз при failed.
# При false — списание пропускается (для служебных/тестовых прогонов),
# credit_charged остаётся False, логируется FIGURE_CREDITS_BYPASSED.
FIGURE_CREDITS_ENFORCED = (
    os.environ.get(
        "FIGURE_CREDITS_ENFORCED", "true"
    ).strip().lower()
    in ("1", "true", "yes", "on")
)

# Каскад моделей: логическая роль -> логическая модель (env имеет приоритет,
# дефолты — через services.llm_router: base/aux/audit -> v4-flash,
# repair/legacy -> v4-pro).  Провайдер-специфичный маппинг делает роутер.
FIGURE_BASE_MODEL = logical_model_for_role("base")
FIGURE_AUX_MODEL = logical_model_for_role("aux")
FIGURE_REPAIR_MODEL = logical_model_for_role("repair")
FIGURE_AUDIT_MODEL = logical_model_for_role("audit")

# Максимум повторов aux-планировщика при замечаниях аудитора.
MAX_AUX_RETRIES = 2

# ── CH22/base_only: пороги условного аудита и targeted repair ─────────────
# Все пороги — env с префиксом FIGURE_ (см. roo_prompt_base_generation_v2).
AUDIT_SCORE_THRESHOLD = float(os.environ.get("FIGURE_AUDIT_SCORE_THRESHOLD", "0.90"))
SOFT_PENALTY_MAX = int(os.environ.get("FIGURE_SOFT_PENALTY_MAX", "0") or "0")
LONG_CONDITION_CHARS = int(os.environ.get("FIGURE_LONG_CONDITION_CHARS", "400") or "400")
MAX_REPAIR_ATTEMPTS_BASE_ONLY = 1
MAX_REPAIR_ATTEMPTS_DEFAULT = 2
FIGURE_JOB_DEADLINE_SEC = float(os.environ.get("FIGURE_JOB_DEADLINE_SEC", "45"))
# Кэш «нормализованное условие + версия промпта + версия движка + модель» -> план.
FIGURE_PLAN_CACHE: dict = {}
FIGURE_PLAN_CACHE_ENABLED = (
    os.environ.get("FIGURE_PLAN_CACHE_ENABLED", "true").strip().lower()
    in ("1", "true", "yes", "on")
)

# ── visual_check (пост-рендер аудит) ──────────────────────────────────────
FIGURE_VISUAL_CHECK_ENABLED = (
    os.environ.get("FIGURE_VISUAL_CHECK_ENABLED", "true").strip().lower()
    in ("1", "true", "yes", "on")
)
FIGURE_VISUAL_SCORE_THRESHOLD = float(
    os.environ.get("FIGURE_VISUAL_SCORE_THRESHOLD", "0.90")
)
FIGURE_VISUAL_RESEED_ATTEMPTS = int(
    os.environ.get("FIGURE_VISUAL_RESEED_ATTEMPTS", "2") or "2"
)

# CH23 PART B3: двухэтапный aux по умолчанию (LLM-экстрактор шагов +
# детерминированный компилятор services/aux_compiler.py).  При true —
# старый однопроходный aux_planner.
FIGURE_AUX_LEGACY_PLANNER = (
    os.environ.get(
        "FIGURE_AUX_LEGACY_PLANNER", "false"
    ).strip().lower()
    in ("1", "true", "yes", "on")
)

# ── Queue processing config ─────────────────────────────────────────────
QUEUE_POLL_INTERVAL = float(os.environ.get("FIGURE_QUEUE_POLL_INTERVAL", "1"))
QUEUE_WORKER_STARTED = False
_queue_worker_lock = Lock()
# Задания строятся в отдельных потоках, чтобы одно «медленное» задание
# (например, долгий CoT у reasoning-модели) не блокировало всю очередь.
MAX_CONCURRENT_JOBS = int(os.environ.get("FIGURE_MAX_CONCURRENT_JOBS", "2"))
_active_jobs: set = set()
_active_jobs_lock = Lock()

# ── Rate limit (DB-based, not in-memory) ────────────────────────────────


def _rate_check() -> tuple[bool, int]:
    """Check rate limit based on figure_build_jobs created in the last hour.

    Uses DB query (not in-memory defaultdict) so that the limit survives
    process restart, works across multiple workers and is not lost when
    the process recycles.
    """
    try:
        from models import db, FigureBuildJob
        from datetime import datetime, timedelta
        uid = None
        try:
            if current_user is not None and getattr(current_user, "is_authenticated", False):
                uid = getattr(current_user, "id", None)
        except Exception:
            pass
        if uid is None:
            return True, 0
        cutoff = datetime.utcnow() - timedelta(seconds=RATE_LIMIT_WINDOW)
        count = FigureBuildJob.query.filter(
            FigureBuildJob.user_id == uid,
            FigureBuildJob.created_at >= cutoff,
        ).count()
        if count >= RATE_LIMIT_MAX:
            earliest = FigureBuildJob.query.filter(
                FigureBuildJob.user_id == uid,
                FigureBuildJob.created_at >= cutoff,
            ).order_by(FigureBuildJob.created_at).first()
            if earliest and earliest.created_at:
                retry_after = int(RATE_LIMIT_WINDOW - (
                    datetime.utcnow() - earliest.created_at
                ).total_seconds()) + 1
                return False, max(retry_after, 1)
            return False, int(RATE_LIMIT_WINDOW)
        return True, 0
    except Exception as e:
        logger.error("[figures_gen] rate check DB error: %s", e)
        return True, 0  # fail open — allow build, don't block on DB error


# ── Reasoner prompt ─────────────────────────────────────────────────────
_REASONER_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "figures", "reasoner_task.txt"
)

_REASONER_SYSTEM_PROMPT: str = ""
try:
    with open(_REASONER_PROMPT_PATH, "r", encoding="utf-8") as _f:
        _REASONER_SYSTEM_PROMPT = _f.read()
    logger.info("[figures_gen] reasoner prompt loaded (%d chars)",
                len(_REASONER_SYSTEM_PROMPT))
except Exception as _e:
    logger.error("[figures_gen] failed to load reasoner prompt: %s", _e)
    _REASONER_SYSTEM_PROMPT = ""


# ── CH15 prompts (condition → solution two-layer pipeline) ──────────────
def _load_prompt(filename: str) -> str:
    """Загрузить текст промпта из data/figures/, вернуть '' при ошибке."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "data", "figures", filename
    )
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error("[figures_gen] failed to load prompt %s: %s", filename, e)
        return ""


_BASE_PLANNER_PROMPT = _load_prompt("base_planner_task.txt")
_AUX_PLANNER_PROMPT = _load_prompt("aux_planner_task.txt")
_AUDITOR_PROMPT = _load_prompt("figure_auditor_task.txt")
_AUX_EXTRACTOR_PROMPT = _load_prompt("aux_extractor_task.txt")

# Версия промпта base-планировщика (входит в ключ кэша плана).  Обновлять
# при каждой правке data/figures/base_planner_task.txt.
_BASE_PLANNER_PROMPT_VERSION = "base-planner-v5"


# ── CH17: startup self-check (лог, без реальных LLM-запросов) ────────────
def _log_router_self_check() -> None:
    """Ненавязчиво вывести в лог резолв ролей и предупредить об отсутствии
    маппинга.  Не делает реальных запросов."""
    try:
        for row in describe_roles():
            role = row["role"]
            logical = row["logical_model"]
            mapped = row["mapped"]
            missing = [p for p, mid in mapped.items() if mid is None]
            logger.info(
                "[llm_router] role=%s logical=%s providers=%s",
                role, logical,
                [(c["provider"], c["model_id"]) for c in row["providers"]],
            )
            if missing:
                logger.warning(
                    "[llm_router] role=%s logical=%s has no mapping for providers=%s",
                    role, logical, missing,
                )
    except Exception as e:  # pragma: no cover - никогда не должен ронять старт
        logger.warning("[llm_router] self-check failed: %s", e)


_log_router_self_check()


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _repair_figure_json(figure_data) -> dict:
    """Починить типичные ошибки модели перед валидацией.

    Модели Novita (deepseek-v3/r1) часто:
      - не проставляют "id" у пометок (equal_segments_mark и т.п.);
      - используют синоним "angle_mark" / "segment_mark".
    Здесь мы авто-заполняем пропущенный id и нормализуем синонимы типов,
    чтобы валидатор и движок не отклоняли корректный по смыслу чертёж.
    """
    if isinstance(figure_data, str):
        try:
            figure_data = json.loads(figure_data)
        except Exception:
            return {}

    if not isinstance(figure_data, dict):
        return {}

    constructions = figure_data.get("constructions")
    if not isinstance(constructions, list):
        return figure_data

    used_ids = set()
    for c in constructions:
        if isinstance(c, dict) and c.get("id"):
            used_ids.add(str(c["id"]))

    # ── BATCH FIX: авто-починка «отрезок назван точкой» ──
    # Gemini регулярно пишет segment {id:"CD", p1:"CD", p2:"D"} или
    # {id:"EF", p1:"EF"} (без p2).  Это dangling-ссылка: точки "CD"/"EF" нет,
    # есть только точки-буквы.  Если id сегмента — строка из двух букв X,Y
    # и p1/p2 ссылается на сам id, раскрываем id в две буквы.
    point_ids = {str(c["id"]) for c in constructions
                 if isinstance(c, dict) and c.get("id")}
    for c in constructions:
        if not isinstance(c, dict):
            continue
        ctype = c.get("type")
        if ctype not in ("segment", "line", "ray"):
            continue
        cid = str(c.get("id") or "")
        # id вида "AB" (две прописные буквы) — потенциально имя отрезка.
        if not (len(cid) == 2 and cid.isalpha() and cid.isupper()):
            continue
        a, b = cid[0], cid[1]
        p1 = c.get("p1")
        p2 = c.get("p2")
        # Случай 1: p1 == id (модель приняла имя отрезка за точку).
        if p1 == cid:
            if p2 == cid:
                c["p1"], c["p2"] = a, b
            elif p2 in (None, ""):
                if a in point_ids and b in point_ids:
                    c["p1"], c["p2"] = a, b
                elif a in point_ids:
                    c["p1"], c["p2"] = a, b
                else:
                    c["p1"] = a
            elif b in point_ids and (a in point_ids or p2 != b):
                # p2 — корректная точка (напр. p2="D"), p1=id="CD" → p1="C".
                if a in point_ids:
                    c["p1"] = a
            continue
        # Случай 2: p2 == id.
        if p2 == cid:
            if p1 == cid:
                c["p1"], c["p2"] = a, b
            elif p1 in point_ids and b in point_ids:
                c["p2"] = b
            continue

    def _gen_id(i: int, ctype: str) -> str:
        base = f"{ctype}_{i}"
        if base not in used_ids:
            return base
        j = 2
        while f"{base}_{j}" in used_ids:
            j += 1
        return f"{base}_{j}"

    for i, c in enumerate(constructions):
        if not isinstance(c, dict):
            continue
        ctype = str(c.get("type") or "")

        # Нормализуем синонимы типов.
        if ctype == "angle_mark":
            c["type"] = "angle_label"
        elif ctype == "segment_mark":
            c["type"] = "equal_segments_mark"

        # Авто-id для объектов без id.
        if not c.get("id"):
            c["id"] = _gen_id(i, str(c.get("type") or "obj"))
            used_ids.add(c["id"])

    return figure_data


def _extract_json(text: str) -> str | None:
    """Extract a JSON object from a model response.

    The response may contain markdown fences and/or leading reasoning prose.
    We first strip fences, then try the greedy ``{...}`` match (clean output),
    and finally fall back to scanning for the first *balanced* ``{...}`` block
    — this is robust when the model emits reasoning text that itself contains
    braces before the real JSON payload.
    """
    if not text:
        return None

    # 1) Strip markdown code fences.
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    # 2) Greedy {.*} — fast path for clean single-object output.
    m = _JSON_OBJECT_RE.search(text)
    if m:
        candidate = m.group(0).strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass

    # 3) Balanced-brace scan: walk string-aware from each '{' until depth 0.
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end != -1:
            candidate = text[start:end + 1]
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass
        start = text.find("{", start + 1)

    return None


# ── Credit helpers ──────────────────────────────────────────────────────

def _get_figure_credits(user) -> int:
    if user is None:
        return 0
    val = getattr(user, "figure_credits", None)
    if val is None:
        try:
            from models import db
            user.figure_credits = 3
            db.session.commit()
            return 3
        except Exception:
            return 3
    return int(val)


def _charge_credit(job_id: int) -> tuple[bool, str]:
    """Списать 1 кредит при переходе в done.

    FIGURE_CREDITS_ENFORCED:
      * true  — атомарный CAS-декремент (UPDATE ... WHERE credit_charged=0),
                credit_charged=True, journal spend_ch5.
      * false — списание пропускается (служебный/тестовый прогон),
                credit_charged=False, логируется FIGURE_CREDITS_BYPASSED.

    Двойной вызов не списывает дважды: CAS видит credit_charged уже = 1.
    """
    if not FIGURE_CREDITS_ENFORCED:
        logger.info(
            "[figures_gen] FIGURE_CREDITS_BYPASSED: job %d — списание отключено",
            job_id,
        )
        return True, "credits not enforced (bypass)"

    try:
        from models import db, FigureBuildJob, FigureCreditTransaction, User
        from sqlalchemy import update as _sa_update

        # Атомарный CAS: выставить credit_charged=True только если сейчас False.
        result = db.session.execute(
            _sa_update(FigureBuildJob)
            .where(
                FigureBuildJob.id == job_id,
                FigureBuildJob.credit_charged == False,  # noqa: E712
            )
            .values(credit_charged=True)
        )
        if result.rowcount == 0:
            job = FigureBuildJob.query.get(job_id)
            if job is not None and job.credit_charged:
                return True, "already charged"
            return False, "job not found"

        job = FigureBuildJob.query.get(job_id)
        if job is None:
            return False, "job not found"
        user = User.query.get(job.user_id)
        if user is None:
            return False, "user not found"

        credits = _get_figure_credits(user)
        if credits <= 0:
            job.credit_charged = False
            db.session.commit()
            return False, "no credits"

        user.figure_credits = credits - 1
        user.figures_built = (getattr(user, "figures_built", 0) or 0) + 1
        txn = FigureCreditTransaction(
            user_id=user.id,
            amount=-1,
            reason="spend_ch5",
            reference=f"build_job:{job_id}",
        )
        db.session.add(txn)
        db.session.commit()
        logger.info("[figures_gen] credit charged for job %d", job_id)
        return True, ""
    except Exception as e:
        logger.error("[figures_gen] charge_credit failed for %d: %s", job_id, e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return False, str(e)


def _refund_credit(job_id: int) -> None:
    """Refund 1 credit при failed, ровно один раз.

    Возврат выполняется только если credit_charged был выставлен (т.е.
    списание реально произошло).  При FIGURE_CREDITS_ENFORCED=false списания
    не было — возвращать нечего.
    """
    if not FIGURE_CREDITS_ENFORCED:
        logger.info(
            "[figures_gen] FIGURE_CREDITS_BYPASSED: job %d — возврат не требуется",
            job_id,
        )
        return
    try:
        from models import db, FigureBuildJob, FigureCreditTransaction, User
        job = FigureBuildJob.query.get(job_id)
        if not job:
            return
        if not job.credit_charged:
            return
        user = User.query.get(job.user_id)
        if not user:
            return
        current_credits = getattr(user, "figure_credits", 0) or 0
        user.figure_credits = current_credits + 1
        txn = FigureCreditTransaction(
            user_id=user.id,
            amount=1,
            reason="refund_ch5",
            reference=f"build_job:{job_id}",
        )
        db.session.add(txn)
        job.credit_charged = False
        db.session.commit()
        logger.info("[figures_gen] credit refunded for job %d", job_id)
    except Exception as e:
        logger.error("[figures_gen] refund_credit failed for %d: %s", job_id, e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


# ── Reasoner API call (Novita -> DeepSeek fallback) ─────────────────────

def _call_deepseek(messages: list[dict], model_name: str | None = None,
                   role: str = "legacy_reasoner") -> dict:
    """Вызвать LLM.

    Для legacy-ветки (model_name is None) — ПРЯМОЙ DeepSeek API, как было
    изначально (без Novita, без роутера, без reasoning_content).  Для
    condition_solution (model_name задан) — провайдер-специфичный роутер.

    CH20: max_tokens и thinking-политика берутся по роли.
    """
    if model_name is None:
        # ── Legacy: прямой DeepSeek (ровно как в git HEAD) ──
        model = REASONER_MODEL
        api_key = DEEPSEEK_API_KEY
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        resp = requests.post(
            DEEPSEEK_BASE_URL,
            headers=headers,
            json=payload,
            timeout=DEEPSEEK_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()

        content = ""
        if "choices" in body and len(body["choices"]) > 0:
            content = body["choices"][0].get("message", {}).get("content", "")

        usage = body.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost_usd = (prompt_tokens * 0.27 + completion_tokens * 1.10) / 1_000_000

        return {
            "content": content,
            "cost_usd": cost_usd,
            "model": model,
            "usage": usage,
        }

    # ── condition_solution: роутер провайдеров ──
    # CH20: max_tokens и thinking-политика берутся по роли.
    return call_llm(
        (model_name or "").strip(),
        messages,
        max_tokens=max_tokens_for_role(role),
        timeout=(15, DEEPSEEK_TIMEOUT),
        logger=logger,
        role=role,
        thinking_mode=thinking_mode_for_role(role),
    )


# ── Background worker ───────────────────────────────────────────────────

def _run_build_job_thread(app, job_id: int):
    """Run a build job inside its own thread and app context.

    On completion the job id is released from the active set so the
    queue worker can admit the next job.
    """
    try:
        with app.app_context():
            _run_build_job(job_id)
    finally:
        with _active_jobs_lock:
            _active_jobs.discard(job_id)


def _run_build_job(job_id: int):
    """Run the full reasoner + engine pipeline for a build job.

    Updates FigureBuildJob: queued -> thinking -> drawing -> done | failed.
    Credit is charged only on transition to done.
    Must be called inside an app context.
    """
    from models import db, FigureBuildJob

    job = FigureBuildJob.query.get(job_id)
    if not job or job.status != "queued":
        return

    # ── CH22: base_only — чертёж только по условию (fast path) ──
    if getattr(job, "generation_mode", "legacy") == "base_only":
        _run_base_only_job(job_id, job)
        return

    # ── CH-aux: solver_aux — решения нет, генерируем сами + aux ──
    if getattr(job, "generation_mode", "legacy") == "solver_aux":
        _run_solver_aux_job(job_id, job)
        return

    # ── CH15 branch: condition → solution two-layer pipeline ──
    if (
        CONDITION_SOLUTION_ENABLED
        and getattr(job, "generation_mode", "legacy") == "condition_solution"
    ):
        _run_condition_solution_job(job_id, job)
        return

    # ── Step 1: Thinking ──
    job.status = "thinking"
    job.current_stage = "thinking"
    job.updated_at = datetime.utcnow()
    db.session.commit()

    if not _REASONER_SYSTEM_PROMPT:
        job.status = "failed"
        job.error = "Системный промпт ризонера не загружен."
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _refund_credit(job_id)
        return

    user_message = f"Условие задачи:\n{job.problem_text}"

    # Extract build_type marker from problem_text
    system_prompt = _REASONER_SYSTEM_PROMPT
    build_type = "plain"
    text_for_prompt = job.problem_text
    if text_for_prompt.startswith("##BT:"):
        newline_idx = text_for_prompt.index("\n")
        build_type = text_for_prompt[5:newline_idx]
        text_for_prompt = text_for_prompt[newline_idx + 1:]
        user_message = f"Условие задачи:\n{text_for_prompt}"
        if build_type == "aux":
            system_prompt = system_prompt + (
                "\n\nПри построении чертежа добавь вспомогательные элементы: "
                "линии, точки, окружности, которые помогают увидеть идею решения. "
                "Вспомогательные элементы рисуй пунктиром, цветом отличным от основного."
            )
        else:
            system_prompt = system_prompt + (
                "\n\nСтрой только объекты, прямо описанные в условии. "
                "Не добавляй вспомогательных элементов."
            )

    final_json = None
    last_errors = []
    last_resp = None

    for attempt in range(1 + MAX_RETRIES):
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        if attempt == 0:
            messages.append({"role": "user", "content": user_message})
        else:
            error_feedback = (
                "Твой предыдущий JSON-ответ не прошёл проверку.\n"
                "Замечания:\n" + "\n".join(f"- {e}" for e in last_errors) + "\n\n"
                "Исправь ошибки и верни КОРРЕКТНЫЙ JSON без пояснений.\n"
                "Исходное задание:\n" + user_message
            )
            messages.append({"role": "user", "content": error_feedback})

        try:
            last_resp = _call_deepseek(messages)
        except LLMError as e:
            logger.error("[figures_gen] LLM error (attempt %d): %s", attempt, e)
            if e.retryable and attempt < MAX_RETRIES:
                continue
            job.status = "failed"
            job.error = str(e)
            job.updated_at = datetime.utcnow()
            db.session.commit()
            _refund_credit(job_id)
            return
        except Exception as e:
            logger.error("[figures_gen] LLM API error (attempt %d): %s",
                         attempt, e)
            if attempt < MAX_RETRIES:
                continue
            job.status = "failed"
            job.error = f"LLM_UNKNOWN: {type(e).__name__}"
            job.updated_at = datetime.utcnow()
            db.session.commit()
            _refund_credit(job_id)
            return

        content = (last_resp.get("content") or "").strip()
        json_str = _extract_json(content)

        if not json_str:
            last_errors = ["Ответ модели не содержит JSON-объекта."]
            if attempt < MAX_RETRIES:
                continue
            job.status = "failed"
            job.error = (
                f"LLM_NO_JSON: провайдер {last_resp.get('provider')}, "
                f"модель {last_resp.get('model_id')}, попытки {MAX_RETRIES + 1}"
            )
            job.updated_at = datetime.utcnow()
            db.session.commit()
            _refund_credit(job_id)
            return

        # ── Починка типичных ошибок модели (id, синонимы типов) ──
        try:
            repaired = _repair_figure_json(json_str)
            if repaired and isinstance(repaired, dict):
                json_str = json.dumps(repaired, ensure_ascii=False)
        except Exception as _repair_err:
            logger.warning("[figures_gen] repair failed: %s", _repair_err)

        validation = validate_figure_json(json_str)
        if validation.get("valid"):
            final_json = json_str
            _record_stage(
                job_id, "thinking", role="legacy_reasoner",
                provider=last_resp.get("provider"),
                model=last_resp.get("model_id") or REASONER_MODEL,
                attempt=attempt + 1,
                input_tokens=(last_resp.get("usage") or {}).get("prompt_tokens"),
                output_tokens=(last_resp.get("usage") or {}).get("completion_tokens"),
                validation_passed=True,
                estimated_cost_usd=last_resp.get("cost_usd"),
            )
            break
        else:
            last_errors = validation.get("errors", ["Неизвестная ошибка валидации"])
            if attempt < MAX_RETRIES:
                continue
            job.status = "failed"
            job.error = "Модель не смогла создать корректное описание."
            job.updated_at = datetime.utcnow()
            db.session.commit()
            _refund_credit(job_id)
            return

    if final_json is None:
        job.status = "failed"
        job.error = "Не удалось построить описание чертежа."
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _refund_credit(job_id)
        return

    # ── Step 2: Drawing ──
    job.status = "drawing"
    job.current_stage = "drawing"
    job.updated_at = datetime.utcnow()
    db.session.commit()

    try:
        from geometric_engine.engine import GeometricEngine
        figure_data = json.loads(final_json)
        engine = GeometricEngine()
        svg, ctx, attempts_used, violations = engine.build_with_retry(figure_data)

        if not svg and violations:
            job.status = "failed"
            job.error = "Геометрические ограничения не выполнены."
            job.updated_at = datetime.utcnow()
            db.session.commit()
            _refund_credit(job_id)
            return

        if not svg:
            job.status = "failed"
            job.error = "Не удалось построить SVG."
            job.updated_at = datetime.utcnow()
            db.session.commit()
            _refund_credit(job_id)
            return

        # ── Step 2b: Aux figure (CH8) ──
        aux_svg = None
        has_aux = False
        aux_reason = None
        aux_data = figure_data.get("aux") if isinstance(figure_data, dict) else None
        if isinstance(aux_data, dict) and aux_data.get("has_aux") and isinstance(aux_data.get("constructions"), list) and aux_data["constructions"]:
            has_aux = True
            aux_reason = str(aux_data.get("reason", ""))[:500] if aux_data.get("reason") else ""
            try:
                # Build merged spec: base constructions + aux constructions
                merged = dict(figure_data)
                merged["constructions"] = list(figure_data.get("constructions", [])) + aux_data["constructions"]
                aux_svg, _, _, _ = engine.build_with_retry(merged)
            except Exception as e:
                logger.warning("[figures_gen] aux build failed for job %d: %s", job_id, e)
                aux_svg = None

        # ── Step 3: Done ──
        cost = float(last_resp.get("cost_usd", 0.0)) if last_resp else 0.0

        job.status = "done"
        job.svg_path = svg
        job.aux_svg_path = aux_svg
        job.has_aux = has_aux
        job.aux_reason = aux_reason
        job.model_name = REASONER_MODEL
        job.error = None
        job.updated_at = datetime.utcnow()
        db.session.commit()

        # Charge credit only now
        _charge_credit(job_id)

    except json.JSONDecodeError as e:
        job.status = "failed"
        job.error = f"Ошибка разбора JSON: {e}"
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _refund_credit(job_id)
    except ImportError:
        job.status = "failed"
        job.error = "Движок построения недоступен."
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _refund_credit(job_id)
    except Exception as e:
        logger.error("[figures_gen] build error in job %d: %s", job_id, e)
        job.status = "failed"
        job.error = "Ошибка при построении чертежа."
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _refund_credit(job_id)


# ── CH15: condition → solution two-layer pipeline ───────────────────────

def _number_solution_steps(solution_text: str) -> str:
    """Пронумеровать шаги решения (S1, S2, ...) для привязки aux-объектов.

    Разбивает по абзацам/переносам строк.  Если решение уже пронумеровано,
    возвращает его как есть (без повторной нумерации).
    """
    if not solution_text:
        return ""
    text = solution_text.strip()
    if not text:
        return ""

    import re as _re
    # Уже пронумеровано вида "1." / "S1." — не трогаем.
    if _re.search(r"(?m)^\s*(S?\d+)[\.\)]", text):
        return text

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return text
    return "\n".join(f"S{i + 1}. {p}" for i, p in enumerate(paragraphs))


def _fmt_plan_json(plan: Any) -> str:
    """Сериализовать план в компактный JSON для хранения и промптов."""
    if isinstance(plan, str):
        return plan
    try:
        return json.dumps(plan, ensure_ascii=False)
    except Exception:
        return ""


def _set_stage(job, stage: str) -> None:
    """Обновить status + current_stage и закоммитить."""
    from models import db
    job.status = stage
    job.current_stage = stage
    job.updated_at = datetime.utcnow()
    db.session.commit()


def _fail_job(job, message: str) -> None:
    """Пометить job failed, вернуть кредит ровно один раз."""
    from models import db
    job.status = "failed"
    job.error = message
    job.updated_at = datetime.utcnow()
    db.session.commit()
    _refund_credit(job.id)


def _concrete_base_feedback(errors: list) -> str:
    """CH21 PART 2: предметный feedback для base-планировщика."""
    lines = []
    for e in errors:
        if "DEGENERATE_SEGMENT" in e:
            m = re.search(r"объект '([^']+)'", e)
            lines.append(
                f"Объект {m.group(1) if m else '?'} соединяет точку саму с собой. "
                f"Основание высоты нельзя задавать вручную парой точек: используй "
                f"операцию altitude с полями vertex, side_a, side_b и foot_id."
            )
        elif "MISSING_CONDITION_POINT" in e:
            m = re.search(r"точка '([^']+)'", e)
            lines.append(
                f"В условии объявлена точка {m.group(1) if m else '?'}, но она не "
                f"создана. Добавь соответствующую операцию (midpoint / altitude с "
                f"foot_id / free_point)."
            )
        elif "INVALID_LABEL_TEXT" in e:
            lines.append("Убери служебное имя из подписи — пиши реальную величину.")
        else:
            lines.append(e)
    return "\n".join(lines)


def _concrete_engine_feedback(violations: list) -> str:
    """CH21 PART 2: предметный feedback при HARD-отказе движка."""
    lines = []
    for v in (violations or [])[:5]:
        if "угол" in v:
            m = re.search(r"([\d.]+)°", v)
            lines.append(
                f"Движок не смог построить фигуру: угол {m.group(1) if m else '?'}° "
                f"меньше порога. Проверь числовые данные условия, не задавай почти "
                f"совпадающие точки."
            )
        elif "совпадают" in v:
            lines.append(v)
        else:
            lines.append(v)
    return "\n".join(lines)


def _concrete_repair_feedback(hard_errors, repair_warnings, base_plan, aux_plan) -> list:
    """CH21 FIX 3: конкретные сообщения по кодам ошибок с id и контекстом."""
    from services.figure_plan_validator import _declared_ids, _aux_plan

    base_ids = sorted(_declared_ids(_base_constructions_of(base_plan)))
    aux_obj = _aux_plan(aux_plan)
    aux_cs = aux_obj.get("constructions", []) if isinstance(aux_obj, dict) else []

    lines = []
    for e in hard_errors + repair_warnings:
        if "AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION" in e:
            # Достаём id объекта из текста.
            m = re.search(r"'([^']+)'\s*\(([a-z_]+)\)", e)
            oid = m.group(1) if m else "?"
            lines.append(
                f"Объект {oid} (тип {m.group(2) if m else '?'}) не разрешён: цитата "
                f"из решения не содержит действия построения. Либо удали этот объект, "
                f"либо приведи цитату с 'проведём', 'соединим', 'продлим', 'построим' "
                f"или 'опустим'. Если решение не строит его — удали объект."
            )
        elif "INVALID_REFERENCE" in e:
            m = re.search(r"references unknown id '([^']+)'", e)
            oid = m.group(1) if m else "?"
            lines.append(
                f"Объект ссылается на точку '{oid}', которой нет в base_scene. "
                f"Доступные точки base: {', '.join(base_ids) or '(нет)'}. "
                f"Либо используй существующие точки, либо создай '{oid}' отдельной "
                f"операцией (midpoint / altitude с foot_id) внутри aux с evidence."
            )
        elif "MISSING_FOOT_ID" in e:
            lines.append(
                "Операция altitude/median/angle_bisector создаёт точку основания, "
                "но не задан foot_id. Добавь foot_id, например 'H'."
            )
        else:
            lines.append(e)
    return lines


def _plan_hash(plan) -> str:
    """Короткий хеш плана для сравнения попыток."""
    import hashlib
    try:
        s = json.dumps(plan, ensure_ascii=False, sort_keys=True)
    except Exception:
        s = str(plan)
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:10]


def _base_constructions_of(plan):
    from services.figure_plan_validator import _base_constructions
    return _base_constructions(plan)


def _plan_call(prompt_template: str, model_name: str, role: str = "base", **kwargs) -> dict:
    """Один вызов LLM с подстановкой {placeholders} в промпт.

    Промпты содержат JSON-примеры с фигурными скобками, поэтому вместо
    str.format() используется точечная замена только известных плейсхолдеров.

    role задаёт max_tokens и thinking-политику (CH20).  Возвращает
    (resp_dict, json_str).  json_str — None если не удалось извлечь JSON.
    """
    system_prompt = prompt_template
    for key, value in kwargs.items():
        system_prompt = system_prompt.replace("{" + key + "}", str(value))

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Верни строго JSON."},
    ]
    resp = _call_deepseek(messages, model_name=model_name, role=role)
    content = (resp.get("content") or "").strip()
    json_str = _extract_json(content)
    # BATCH FIX: единая починка «отрезок назван точкой» / синонимов типов
    # для ВСЕХ планов (base/aux/audit), не только legacy.
    if json_str:
        try:
            repaired = _repair_figure_json(json_str)
            if isinstance(repaired, dict):
                json_str = json.dumps(repaired, ensure_ascii=False)
        except Exception:
            pass
    return resp, json_str


def _two_stage_aux_plan(job, job_id, condition_text, numbered_solution, base_plan):
    """CH23 PART B3: двухэтапный aux — LLM-экстрактор шагов + компилятор.

    Возвращает (aux_plan, aux_reason, aux_has).  При неустранимой ошибке
    помечает job как failed (AUX_EXTRACT_FAILED / AUX_PLAN_REJECTED) и
    возвращает (None, None, False).
    """
    from models import db
    from services.aux_compiler import compile_steps_to_aux
    from services.figure_plan_validator import validate_condition_solution

    base_ids_list = [
        c.get("id") for c in base_plan.get("constructions", [])
        if isinstance(c, dict) and c.get("id")
    ]
    base_ids_str = ", ".join(str(i) for i in base_ids_list) or "(пусто)"

    repair_feedback = ""
    aux_history = []
    prev_sig = None
    loop_detected = False

    for attempt in range(1 + MAX_AUX_RETRIES):
        model = FIGURE_REPAIR_MODEL if attempt > 0 else FIGURE_AUX_MODEL
        role = "repair" if attempt > 0 else "aux"
        if loop_detected:
            repair_feedback += (
                "\n\nВАЖНО: набор ошибок не изменился после предыдущих попыток. "
                "Убери проблемные шаги. Если решение чисто вычислительное — "
                "верни steps: []."
            )
        try:
            resp, json_str = _plan_call(
                _AUX_EXTRACTOR_PROMPT,
                model,
                role=role,
                condition_text=condition_text,
                numbered_solution_text=numbered_solution,
                base_ids=base_ids_str,
                repair_feedback=repair_feedback,
            )
        except LLMError as e:
            logger.error("[figures_gen] aux extractor LLM error (attempt %d): %s",
                         attempt, e)
            if e.retryable and attempt < MAX_AUX_RETRIES:
                continue
            job.aux_status = "AUX_EXTRACT_FAILED"
            job.aux_fail_reason = _fmt_plan_json({"provider_error": str(e)})
            db.session.commit()
            _fail_job(job, str(e))
            return None, None, False
        except Exception as e:
            logger.error("[figures_gen] aux extractor API error (attempt %d): %s",
                         attempt, e)
            if attempt < MAX_AUX_RETRIES:
                continue
            job.aux_status = "AUX_EXTRACT_FAILED"
            job.aux_fail_reason = _fmt_plan_json({"api_error": str(e)})
            db.session.commit()
            _fail_job(job, "Сервис генерации временно недоступен.")
            return None, None, False

        if not json_str:
            if attempt < MAX_AUX_RETRIES:
                continue
            job.aux_status = "AUX_EXTRACT_FAILED"
            job.aux_fail_reason = _fmt_plan_json({
                "reason": "LLM_NO_JSON",
                "provider": resp.get("provider"),
                "model": resp.get("model_id"),
            })
            db.session.commit()
            _fail_job(job, "Не удалось извлечь шаги построений из решения.")
            return None, None, False

        try:
            steps_data = json.loads(json_str)
        except Exception:
            steps_data = None
        steps = steps_data.get("steps", []) if isinstance(steps_data, dict) else None
        unsupported = steps_data.get("unsupported", []) if isinstance(steps_data, dict) else []
        if not isinstance(steps, list):
            if attempt < MAX_AUX_RETRIES:
                repair_feedback = (
                    "Ответ не содержит поле steps (список). "
                    'Верни строго JSON вида {"steps": [...]}.'
                )
                continue
            job.aux_status = "AUX_EXTRACT_FAILED"
            job.aux_fail_reason = _fmt_plan_json({"reason": "NO_STEPS_FIELD"})
            db.session.commit()
            _fail_job(job, "Не удалось разобрать шаги построений.")
            return None, None, False

        aux_plan, issues = compile_steps_to_aux(steps, base_plan)
        aux_has = bool(aux_plan.get("has_aux"))
        aux_reason = (aux_plan.get("reason") or "")[:500]

        # ── Детерминированная проверка base ↔ aux ──
        inv = validate_condition_solution(
            base_plan, aux_plan, condition_text=condition_text
        )
        repair_warnings = [
            w for w in inv.get("warnings", [])
            if w.startswith("AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION")
            or w.startswith("MISSING_FOOT_ID")
        ]
        hard_errors = inv.get("errors", []) if not inv.get("valid") else []

        if not aux_has:
            # CH27 FIX4: есть unsupported-построения, но нет steps →
            # это AUX_UNSUPPORTED, а не AUX_NOT_NEEDED.
            if unsupported:
                job.aux_status = "AUX_UNSUPPORTED"
                job.aux_fail_reason = _fmt_plan_json({"unsupported": unsupported})
            else:
                job.aux_status = "AUX_NOT_NEEDED"
                job.aux_fail_reason = None
            db.session.commit()
            return aux_plan, aux_reason, False

        if hard_errors or repair_warnings:
            feedback_lines = _concrete_repair_feedback(
                hard_errors, repair_warnings, base_plan, aux_plan
            )
            repair_feedback = (
                "Твои шаги построений НЕ приняты. Замечания:\n"
                + "\n".join(feedback_lines) + "\n\n"
                "Перечитай решение и верни исправленные шаги строго JSON."
            )
            sig = tuple(sorted({e.split(":")[0] for e in hard_errors + repair_warnings}))
            aux_history.append({"attempt": attempt, "error_codes": list(sig), "issues": issues})
            if sig == prev_sig:
                loop_detected = True
            prev_sig = sig
            if attempt < MAX_AUX_RETRIES:
                logger.warning(
                    "[figures_gen] aux extractor retry job %d (attempt %d): %s",
                    job_id, attempt, feedback_lines,
                )
                continue
            job.audit_json = _fmt_plan_json({
                "invariant_errors": hard_errors,
                "repair_warnings": repair_warnings,
                "aux_history": aux_history,
                "issues": issues,
            })
            job.aux_status = "AUX_PLAN_REJECTED"
            job.aux_fail_reason = _fmt_plan_json({
                "codes": list(sig),
                "last_errors": hard_errors + repair_warnings,
            })
            db.session.commit()
            _fail_job(job, "Модель не смогла извлечь корректные построения.")
            return None, None, False

        return aux_plan, aux_reason, aux_has

    # Недостижимо (цикл всегда выходит через return/continue до этой точки).
    job.aux_status = "AUX_EXTRACT_FAILED"
    job.aux_fail_reason = _fmt_plan_json({"reason": "retries_exhausted"})
    db.session.commit()
    _fail_job(job, "Не удалось извлечь построения из решения.")
    return None, None, False


# ── CH22: base_only — чертёж только по условию ───────────────────────────

def _plan_cache_key(condition_text: str, model_name: str) -> str:
    """Ключ кэша: sha256(норм. условие + версия промпта + версия движка + модель)."""
    import hashlib
    try:
        from geometric_engine.engine import GeometricEngine
        engine_ver = getattr(GeometricEngine, "VERSION", "v1")
    except Exception:
        engine_ver = "v1"
    norm = " ".join((condition_text or "").split()).lower()
    raw = f"{norm}|{_BASE_PLANNER_PROMPT_VERSION}|{engine_ver}|{model_name}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _needs_llm_audit(coverage: dict, plan: dict, engine_result: dict,
                     repair_used: bool, condition_text: str,
                     visual: dict = None) -> bool:
    """Условный LLM-аудит: вызывать только при реальной необходимости.

    CH22: на чистом base-задании аудит пропускается, что снимает лишний
    LLM-вызов (5–15 с) с критического пути.
    """
    if visual and visual.get("errors"):
        return True
    if visual and visual.get("visual_score", 1.0) < FIGURE_VISUAL_SCORE_THRESHOLD:
        return True
    if coverage.get("errors"):
        return True
    if coverage.get("score", 1.0) < AUDIT_SCORE_THRESHOLD:
        return True
    if repair_used:
        return True
    if engine_result.get("json_autorepaired"):
        return True
    if engine_result.get("soft_penalty", 0) > SOFT_PENALTY_MAX:
        return True
    # Планы с окружностями/касательными/вписанными фигурами — всегда аудит.
    for c in (plan or {}).get("constructions", []) or []:
        if c.get("type") in (
            "circle_center_radius", "circumcircle", "incircle",
            "circle_three_points", "inscribed_polygon", "point_on_circle",
            "tangent_from_point", "tangent_at_point",
        ):
            return True
    if (plan or {}).get("assumptions"):
        return True
    if len(condition_text or "") > LONG_CONDITION_CHARS:
        return True
    return False


def plan_uses_constraints(plan: Any) -> bool:
    """REC-4: True, если план содержит ограничивающую операцию.

    Ограничивающие операции: angle_at_vertex, segment_length, equal_segments,
    triangle_by_two_angles.  Они фиксируют геометрию точно, а не подбором
    координат.
    """
    from services.figure_plan_validator import _base_constructions, _loads
    for c in _base_constructions(_loads(plan)):
        if c.get("type") in ("angle_at_vertex", "segment_length",
                             "equal_segments", "triangle_by_two_angles"):
            return True
    return False


def _run_base_only_job(job_id: int, job) -> None:
    """CH22: чертёж только по условию (fast path).

    Стадии: base_thinking → base_drawing → coverage_check → done.
    Никакого aux и LLM-аудита в благополучном случае (один LLM-вызов).
    """
    from models import db
    from services.figure_plan_validator import validate_condition_solution
    from services.figure_plan_schemas import parse_base_plan, parse_audit_result
    from services.condition_coverage import check_condition_coverage

    condition_text = (job.problem_text or "").strip()
    # Убрать legacy-маркер ##BT:, если он есть.
    if condition_text.startswith("##BT:"):
        nl = condition_text.find("\n")
        condition_text = condition_text[nl + 1:].strip() if nl != -1 else condition_text

    if not _BASE_PLANNER_PROMPT:
        _fail_job(job, "Системный промпт base_planner не загружен.")
        return

    # ── Stage: base_thinking ──
    _set_stage(job, "base_thinking")

    base_plan = None
    repair_used = False
    repair_feedback = ""
    max_attempts = 1 + MAX_REPAIR_ATTEMPTS_BASE_ONLY
    _t0 = time.perf_counter()

    # Кэш плана (только на чистом пути без repair).
    cache_key = _plan_cache_key(condition_text, FIGURE_BASE_MODEL) \
        if FIGURE_PLAN_CACHE_ENABLED else None
    if cache_key and cache_key in FIGURE_PLAN_CACHE:
        base_plan = FIGURE_PLAN_CACHE[cache_key]
        job.base_model = FIGURE_BASE_MODEL
        job.base_plan_json = _fmt_plan_json(base_plan)
        db.session.commit()
    else:
        for attempt in range(max_attempts):
            model = FIGURE_REPAIR_MODEL if attempt > 0 else FIGURE_BASE_MODEL
            role = "repair" if attempt > 0 else "base"
            try:
                resp, json_str = _plan_call(
                    _BASE_PLANNER_PROMPT,
                    model,
                    role=role,
                    condition_text=condition_text,
                    repair_feedback=repair_feedback,
                )
            except LLMError as e:
                if e.retryable and attempt < max_attempts - 1:
                    continue
                _fail_job(job, str(e))
                return
            except Exception:
                if attempt < max_attempts - 1:
                    continue
                _fail_job(job, "Сервис генерации временно недоступен.")
                return

            if not json_str:
                if attempt < max_attempts - 1:
                    continue
                _fail_job(job, "Модель не вернула JSON base-плана.")
                return

            plan = parse_base_plan(json_str)
            if plan is None:
                if attempt < max_attempts - 1:
                    continue
                _fail_job(job, "Не удалось разобрать base-план.")
                return

            # Форсируем отсутствие aux в base-only.
            plan.pop("aux", None)
            plan["aux"] = {"has_aux": False, "reason": "", "constructions": []}

            base_validation = validate_figure_json(plan)
            if not base_validation.get("valid"):
                repair_feedback = _concrete_base_feedback(
                    base_validation.get("errors", [])
                )
                if attempt < max_attempts - 1:
                    continue
                _fail_job(job, "Модель не смогла создать корректный base-план.")
                return

            # Детерминированная проверка (без aux-части).
            inv = validate_condition_solution(plan, {"has_aux": False},
                                              condition_text=condition_text)
            hard = inv.get("errors", []) if not inv.get("valid") else []
            if hard:
                repair_feedback = _concrete_base_feedback(hard)
                if attempt < max_attempts - 1:
                    continue
                _fail_job(job, "Модель не смогла исправить base-план.")
                return

            base_plan = plan
            repair_used = attempt > 0
            job.base_model = model
            job.base_plan_json = _fmt_plan_json(plan)
            db.session.commit()
            _record_stage(
                job_id, "base_thinking", role=role,
                provider=resp.get("provider"), model=model,
                attempt=attempt + 1,
                input_tokens=(resp.get("usage") or {}).get("prompt_tokens"),
                output_tokens=(resp.get("usage") or {}).get("completion_tokens"),
                latency_ms=int((time.perf_counter() - _t0) * 1000),
                validation_passed=True,
                estimated_cost_usd=resp.get("cost_usd"),
            )
            break

    if base_plan is None:
        _fail_job(job, "Не удалось построить base-план.")
        return

    if cache_key:
        FIGURE_PLAN_CACHE[cache_key] = base_plan

    # ── Stage: base_drawing ──
    _set_stage(job, "base_drawing")
    try:
        from geometric_engine.engine import GeometricEngine
        engine = GeometricEngine()
        engine.settings.semantic_colors = FIGURE_SEMANTIC_COLORS_ENABLED
        engine.settings.auto_fit = FIGURE_AUTO_FIT_ENABLED
        base_svg, ctx, _, base_violations = engine.build_with_retry(base_plan)
        if not base_svg:
            job.audit_json = _fmt_plan_json({"engine_violations": base_violations})
            db.session.commit()
            _fail_job(
                job,
                f"Геометрические ограничения не выполнены: {base_violations[:3]}",
            )
            return
    except Exception as e:
        logger.error("[figures_gen] base_only build error job %d: %s", job_id, e)
        _fail_job(job, "Ошибка при построении base-чертежа.")
        return

    job.svg_path = base_svg
    db.session.commit()

    # ── Stage: coverage_check ──
    _set_stage(job, "coverage_check")
    coverage = check_condition_coverage(condition_text, base_plan,
                                        build_context=ctx, settings=engine.settings)
    coverage_codes = [e.split(":")[0] for e in coverage.get("errors", [])]
    _record_stage(
        job_id, "coverage_check",
        coverage_score=coverage.get("score"),
        validation_passed=coverage.get("complete"),
        error_codes=coverage_codes,
    )

    # ── REC-4: реакция на CONDITION_NOT_REALIZED ──
    # Если данные условия не реализованы численно:
    #   • план без ограничений → targeted repair (указать операцию);
    #   • план с ограничениями → reseed (решатель не сошёлся), без LLM.
    if "CONDITION_NOT_REALIZED" in coverage_codes:
        if not plan_uses_constraints(base_plan):
            feedback = coverage.get("repair_feedback", "") or (
                "CONDITION_NOT_REALIZED: данные условия не реализованы на чертеже. "
                "Задай угол операцией triangle_by_two_angles или angle_at_vertex, "
                "длину — segment_length, равенство — equal_segments. "
                "Не подбирай свободные координаты."
            )
            _fail_job(job, feedback)
            return
        # Ограничения есть, но решатель не сошёлся — reseed до 3 раз без LLM.
        reseed_svg = None
        for seed in (1, 2, 3):
            try:
                from geometric_engine.engine import GeometricEngine
                _eng = GeometricEngine()
                _eng.settings.semantic_colors = FIGURE_SEMANTIC_COLORS_ENABLED
                _eng.settings.auto_fit = FIGURE_AUTO_FIT_ENABLED
                _sv, _cx, _, _v = _eng.build_with_retry(base_plan, seed=seed)
                _cov = check_condition_coverage(
                    condition_text, base_plan, build_context=_cx,
                    settings=_eng.settings,
                )
                if "CONDITION_NOT_REALIZED" not in [
                    e.split(":")[0] for e in _cov.get("errors", [])
                ]:
                    reseed_svg = _sv
                    ctx = _cx
                    base_svg = _sv
                    break
            except Exception as e:
                logger.warning("[figures_gen] reseed %d failed job %d: %s",
                               seed, job_id, e)
        if reseed_svg is None:
            _fail_job(job, coverage.get("repair_feedback", "")
                      or "CONDITION_NOT_REALIZED: геометрия не реализована.")
            return
        job.svg_path = base_svg
        db.session.commit()

    # ── Stage: visual_check (пост-рендер аудит, детерминированный) ──
    visual = None
    if FIGURE_VISUAL_CHECK_ENABLED:
        _set_stage(job, "visual_check")
        _t_visual = time.perf_counter()
        try:
            from services.visual_audit import audit_rendered_figure
            visual = audit_rendered_figure(
                svg=base_svg,
                build_context=ctx,
                base_plan=base_plan,
                condition_text=condition_text,
                settings=engine.settings,
            )
        except Exception as e:
            logger.warning("[figures_gen] visual_check failed job %d: %s",
                           job_id, e)
            visual = None
        if visual is not None:
            _record_stage(
                job_id, "visual_check",
                coverage_score=visual.get("visual_score"),
                validation_passed=visual.get("clean"),
                error_codes=[e.split(":")[0] for e in visual.get("errors", [])],
                latency_ms=int((time.perf_counter() - _t_visual) * 1000),
                visual_score=visual.get("visual_score"),
                label_collisions=len([
                    e for e in visual.get("errors", [])
                    if "LABEL_COLLISION" in e
                ]),
            )

    engine_result = {
        "json_autorepaired": False,
        "soft_penalty": len(base_violations),
    }

    # ── Условный LLM-аудит ──
    approved = True
    audit_json = job.audit_json
    if _AUDITOR_PROMPT and _needs_llm_audit(
        coverage, base_plan, engine_result, repair_used, condition_text, visual
    ):
        try:
            resp, audit_str = _plan_call(
                _AUDITOR_PROMPT,
                FIGURE_AUDIT_MODEL,
                role="audit",
                condition_text=condition_text,
                numbered_solution_text="",
                base_plan_json=_fmt_plan_json(base_plan),
                aux_plan_json='{"has_aux": false, "constructions": []}',
            )
            if audit_str:
                result = parse_audit_result(audit_str)
                if result is not None:
                    audit_json = _fmt_plan_json(result)
                    approved = bool(result.get("approved", True))
        except Exception as e:
            logger.warning("[figures_gen] base_only auditor failed job %d: %s",
                           job_id, e)

    job.audit_json = audit_json
    if not approved and coverage.get("errors"):
        # Аудит + детерминированный чекер сошлись на проблемах → failed.
        _fail_job(job, coverage["repair_feedback"] or "Чертёж не прошёл аудит.")
        return

    # ── Done ──
    job.status = "done"
    job.current_stage = "done"
    job.svg_path = base_svg
    job.aux_svg_path = None
    job.has_aux = False
    job.aux_reason = None
    job.aux_status = "AUX_NOT_NEEDED"
    job.aux_fail_reason = None
    job.model_name = FIGURE_BASE_MODEL
    job.error = None
    job.updated_at = datetime.utcnow()
    db.session.commit()

    _charge_credit(job_id)


# ── CH-aux: solver_aux — решения нет, генерируем сами + доп. построения ────

SOLVER_CACHE: dict = {}
SOLVER_CACHE_ENABLED = (
    os.environ.get("FIGURE_SOLVER_CACHE_ENABLED", "true").strip().lower()
    in ("1", "true", "yes", "on")
)


def _solver_cache_key(condition_text: str) -> str:
    import hashlib
    from services.solution_generator import SOLVER_PROMPT_VERSION
    from services.llm_router import logical_model_for_role
    norm = " ".join((condition_text or "").split()).lower()
    raw = f"{norm}|{SOLVER_PROMPT_VERSION}|{logical_model_for_role('solver')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _drop_aux(job, base_svg, reason: str) -> None:
    """Откат к base-чертежу без доп. построений."""
    from models import db
    job.status = "done"
    job.current_stage = "done"
    job.svg_path = base_svg
    job.aux_svg_path = None
    job.has_aux = False
    job.aux_status = "AUX_DROPPED"
    job.aux_dropped_reason = reason
    job.trust_level = "unverified"
    job.updated_at = datetime.utcnow()
    db.session.commit()


def _run_solver_aux_job(job_id: int, job) -> None:
    """CH-aux: solver-driven aux конвейер.

    Стадии: base_thinking → base_drawing → coverage_check → visual_check →
    aux_template_match → [solving → answer_verify → aux_compile] →
    aux_usefulness → aux_drawing → visual_check → done.

    Правило отката: при ЛЮБОМ сомнении отдаём base-чертёж без aux.
    """
    from models import db
    from services.figure_plan_validator import merge_base_aux
    from services.figure_plan_schemas import parse_base_plan, parse_audit_result
    from services.condition_coverage import check_condition_coverage
    from services.solution_generator import solve_problem, SolverError
    from services.answer_verifier import verify_answer
    from services.aux_compiler import compile_solver_aux
    from services.aux_usefulness import evaluate_usefulness
    from services.visual_audit import audit_rendered_figure

    condition_text = (job.problem_text or "").strip()
    if condition_text.startswith("##BT:"):
        nl = condition_text.find("\n")
        condition_text = condition_text[nl + 1:].strip() if nl != -1 else condition_text

    if not _BASE_PLANNER_PROMPT:
        _fail_job(job, "Системный промпт base_planner не загружен.")
        return

    # ── base_thinking ──
    _set_stage(job, "base_thinking")
    base_plan = None
    for attempt in range(1 + MAX_REPAIR_ATTEMPTS_BASE_ONLY):
        model = FIGURE_REPAIR_MODEL if attempt > 0 else FIGURE_BASE_MODEL
        role = "repair" if attempt > 0 else "base"
        try:
            resp, json_str = _plan_call(
                _BASE_PLANNER_PROMPT, model, role=role,
                condition_text=condition_text, repair_feedback="",
            )
        except LLMError as e:
            _fail_job(job, str(e))
            return
        except Exception:
            _fail_job(job, "Сервис генерации временно недоступен.")
            return
        if not json_str:
            _fail_job(job, "Модель не вернула JSON base-плана.")
            return
        plan = parse_base_plan(json_str)
        if plan is None:
            _fail_job(job, "Не удалось разобрать base-план.")
            return
        plan.pop("aux", None)
        plan["aux"] = {"has_aux": False, "reason": "", "constructions": []}
        if not validate_figure_json(plan).get("valid"):
            if attempt < MAX_REPAIR_ATTEMPTS_BASE_ONLY:
                continue
            _fail_job(job, "Модель не смогла создать корректный base-план.")
            return
        base_plan = plan
        job.base_model = model
        job.base_plan_json = _fmt_plan_json(plan)
        db.session.commit()
        break

    if base_plan is None:
        _fail_job(job, "Не удалось построить base-план.")
        return

    # ── base_drawing ──
    _set_stage(job, "base_drawing")
    try:
        from geometric_engine.engine import GeometricEngine
        engine = GeometricEngine()
        engine.settings.semantic_colors = FIGURE_SEMANTIC_COLORS_ENABLED
        engine.settings.auto_fit = FIGURE_AUTO_FIT_ENABLED
        base_svg, base_ctx, _, base_violations = engine.build_with_retry(base_plan)
        if not base_svg:
            _fail_job(job, f"Геометрические ограничения не выполнены: {base_violations[:3]}")
            return
    except Exception as e:
        import traceback as _tb
        logger.error("[figures_gen] base build error job %d: %s\n%s",
                     job_id, e, _tb.format_exc())
        _fail_job(job, f"Ошибка при построении base-чертежа: {type(e).__name__}: {e}")
        return
    job.svg_path = base_svg
    db.session.commit()

    # ── coverage_check + visual_check (base) ──
    _set_stage(job, "coverage_check")
    coverage = check_condition_coverage(condition_text, base_plan,
                                        build_context=base_ctx, settings=engine.settings)

    # ── aux (ТОЛЬКО LLM, без шаблонов) ──
    # Пользователь убрал каталог шаблонов: доп. построение строит Gemini.
    aux_source = "none"
    aux_plan = None
    solver_result = None
    answer_verdict = "unverifiable"

    # ── solving (Gemini, thinking) ──
    _set_stage(job, "solving")
    _t_solving = time.perf_counter()
    cache_key = _solver_cache_key(condition_text) if SOLVER_CACHE_ENABLED else None
    if cache_key and cache_key in SOLVER_CACHE:
        solver_result = SOLVER_CACHE[cache_key]
    else:
        try:
            solver_result = solve_problem(condition_text, logger=logger)
        except SolverError as e:
            logger.warning("[figures_gen] solver failed job %d: %s", job_id, e)
            solver_result = None
        if solver_result is not None and cache_key:
            SOLVER_CACHE[cache_key] = solver_result
    _usage = (solver_result or {}).get("_usage", {}) or {}
    _record_stage(
        job_id, "solving", role="solver",
        provider=(solver_result or {}).get("_provider"),
        model=(solver_result or {}).get("_model"),
        input_tokens=_usage.get("prompt_tokens"),
        output_tokens=_usage.get("completion_tokens"),
        reasoning_tokens=_usage.get("reasoning_tokens"),
        latency_ms=int((time.perf_counter() - _t_solving) * 1000),
        estimated_cost_usd=(solver_result or {}).get("_cost_usd"),
    )

    if solver_result is None:
        # Решение не получено — отдаём base без aux.
        _drop_aux(job, base_svg, "solver_failed")
        _charge_credit(job_id)
        return

    job.solution_json = _fmt_plan_json(solver_result)
    job.solver_answer = str((solver_result.get("answer") or {}).get("value", ""))

    # ── answer_verify (ЯДРО) ──
    _set_stage(job, "answer_verify")
    verification = verify_answer(
        solver_result, base_ctx, base_plan,
        condition_text=condition_text, settings=engine.settings,
    )
    answer_verdict = verification.get("verdict", "unverifiable")
    job.answer_verdict = answer_verdict
    job.measured_answer = str(verification.get("measured", ""))
    _record_stage(
        job_id, "answer_verify",
        validation_passed=(answer_verdict == "verified"),
        error_codes=[] if answer_verdict != "mismatch" else ["ANSWER_MISMATCH"],
    )

    if answer_verdict == "mismatch":
        # Решение неверно — aux использовать нельзя.
        _drop_aux(job, base_svg, "answer_mismatch")
        _charge_credit(job_id)
        return

    # ── aux_compile ──
    _set_stage(job, "aux_compile")
    compiled, issues = compile_solver_aux(solver_result, base_plan)
    if issues:
        logger.warning("[figures_gen] solver aux compile issues job %d: %s",
                       job_id, issues)
    _record_stage(job_id, "aux_compile",
                  validation_passed=bool(compiled.get("has_aux")),
                  error_codes=[i.split(":")[0] for i in issues] if issues else [])
    if not compiled.get("has_aux"):
        _drop_aux(job, base_svg, "aux_compile_empty")
        _charge_credit(job_id)
        return
    aux_plan = compiled
    aux_source = "solver"

    # ── aux_usefulness ──
    _set_stage(job, "aux_usefulness")
    merged = merge_base_aux(base_plan, aux_plan)
    # FIX: для оценки полезности aux используем build() без HARD-проверки
    # границ.  Вспомогательное построение может выходить за исходный canvas
    # (например, отражённая вершина при удвоении медианы), и auto_fit в
    # render_svg потом подгонит холст.  build_with_retry здесь давал пустой
    # aux_svg из-за «Проверка 1 (границы)», из-за чего полезность считалась
    # по base_ctx (без новых точек) и любое построение получало "useless".
    try:
        aux_svg, aux_ctx = engine.build(merged)
    except Exception:
        aux_svg = None
        aux_ctx = None
    usefulness = evaluate_usefulness(base_ctx, aux_ctx or base_ctx,
                                     aux_plan.get("constructions", []),
                                     settings=engine.settings)
    job.aux_usefulness = usefulness.get("score")
    _record_stage(job_id, "aux_usefulness",
                  coverage_score=usefulness.get("score"),
                  validation_passed=usefulness.get("useful"),
                  error_codes=[usefulness.get("verdict", "")]
                  if not usefulness.get("useful") else [])

    if not usefulness.get("useful"):
        _drop_aux(job, base_svg, f"aux_{usefulness.get('verdict', 'useless')}")
        _charge_credit(job_id)
        return

    # ── aux_drawing ──
    _set_stage(job, "aux_drawing")
    if not aux_svg:
        # Перестраиваем, чтобы увидеть реальную причину сбоя в логе.
        try:
            aux_svg2, aux_ctx2 = engine.build(merged)
            aux_svg, aux_ctx = aux_svg2, aux_ctx2
        except Exception as _render_err:
            import traceback as _tb
            logger.error("[figures_gen] aux render error job %d: %s\n%s",
                         job_id, _render_err, _tb.format_exc())
        if not aux_svg:
            _drop_aux(job, base_svg, "aux_render_failed")
            _charge_credit(job_id)
            return

    # ── visual_check (повторно) — CH-fix: не роняем aux на косметике ──
    #
    # Раньше ЛЮБАЯ запись в visual.get("errors") приводила к _drop_aux(...).
    # Это давало ложные срабатывания на LABEL_COLLISION / TICK_OVERLAP и т.п.,
    # особенно на incircle-цепочках (много подписей у O, A1, B1, C1).
    #
    # Теперь: HARD-коды роняют aux, SOFT-коды только логируются.  Список
    # HARD-кодов синхронизирован с движком: см. _is_soft_violation() и
    # маркер "Проверка 2" в engine.py — визуал-аудит должен быть
    # НЕ строже, чем встроенные проверки движка.
    _set_stage(job, "visual_check")
    _t_visual = time.perf_counter()
    visual = None
    try:
        visual = audit_rendered_figure(aux_svg, aux_ctx, merged, condition_text,
                                       settings=engine.settings)
    except Exception as _e:
        logger.warning("[figures_gen] aux visual_check crashed job %d: %s",
                       job_id, _e)
        visual = None

    # Классификация ошибок.  HARD означает «чертёж действительно неверен»;
    # SOFT — «косметика» (подписи, штрихи, дужки).
    HARD_VISUAL_CODES = {
        "MISSING_POINT", "MISSING_LABEL", "DEGENERATE_TRIANGLE",
        "LINE_OUT_OF_CANVAS", "POINT_NOT_ON_LINE", "CIRCLE_RADIUS_ZERO",
        "INCIDENCE_VIOLATED", "CONDITION_NOT_REALIZED",
    }
    errors = (visual or {}).get("errors", []) or []
    hard_errs = [e for e in errors if e.split(":")[0] in HARD_VISUAL_CODES]
    soft_errs = [e for e in errors if e.split(":")[0] not in HARD_VISUAL_CODES]

    # Всегда логируем стадию — чтобы в UI/БД была видна реальная причина.
    if visual is not None:
        _record_stage(
            job_id, "visual_check",
            coverage_score=visual.get("visual_score"),
            validation_passed=(not hard_errs),
            error_codes=[e.split(":")[0] for e in errors],
            latency_ms=int((time.perf_counter() - _t_visual) * 1000),
            visual_score=visual.get("visual_score"),
            label_collisions=len([e for e in errors if "LABEL_COLLISION" in e]),
        )

    if hard_errs:
        # Явная запись о том, ЧТО именно сломано, — облегчает диагностику.
        job.aux_fail_reason = _fmt_plan_json({
            "hard_codes": [e.split(":")[0] for e in hard_errs],
            "hard_errors": hard_errs[:5],
        })
        db.session.commit()
        _drop_aux(job, base_svg, "aux_visual_check_failed")
        _charge_credit(job_id)
        return

    if soft_errs:
        # Не роняем aux: помечаем предупреждение и продолжаем.
        job.aux_reason = (job.aux_reason or "") + \
            f" [visual_warnings: {len(soft_errs)}]"
        db.session.commit()

    # ── completeness_check (Gemini vision) ──
    # Проверяем, что все равные углы/отрезки отмечены, все известные длины и
    # углы подписаны, искомый объект помечен «?».  Если неполно — просим
    # Gemini вернуть доп. план и дозаполняем чертёж.
    _set_stage(job, "completeness_check")
    try:
        from services.figure_completeness_audit import audit_figure_completeness
        completeness = audit_figure_completeness(aux_svg, condition_text)
        job.aux_completeness = 1 if completeness.get("complete") else 0
        _record_stage(job_id, "completeness_check",
                      validation_passed=bool(completeness.get("complete")),
                      error_codes=["INCOMPLETE"] if not completeness.get("complete") else [])
        if not completeness.get("complete") and completeness.get("repair_plan"):
            # Дозаполняем чертёж: добавляем предложенные объекты и перестраиваем.
            extra = completeness.get("repair_plan")
            if isinstance(extra, list):
                merged["constructions"] = list(merged.get("constructions", [])) + extra
                try:
                    aux_svg2, aux_ctx2 = engine.build(merged)
                    aux_svg = aux_svg2
                    aux_ctx = aux_ctx2
                    job.aux_reason = (job.aux_reason or "") + " + дозаполнено по аудиту"
                except Exception:
                    pass
        db.session.commit()
    except Exception as e:
        logger.warning("[figures_gen] completeness_check failed job %d: %s", job_id, e)

    # ── Done: aux принят ──
    job.status = "done"
    job.current_stage = "done"
    job.svg_path = base_svg
    job.aux_svg_path = aux_svg
    job.has_aux = True
    job.aux_reason = aux_plan.get("reason", "")
    job.aux_status = "AUX_BUILT"
    job.aux_source = aux_source
    job.answer_verdict = answer_verdict
    job.trust_level = "verified"
    job.model_name = FIGURE_BASE_MODEL
    job.error = None
    job.updated_at = datetime.utcnow()
    db.session.commit()

    _charge_credit(job_id)


def _run_condition_solution_job(job_id: int, job) -> None:
    """Двухслойный конвейер: base (только условие) → aux (из решения) → audit.

    Статусы: queued → base_thinking → base_drawing → aux_thinking →
    aux_drawing → auditing → done | failed.
    """
    from models import db
    from services.figure_plan_validator import (
        validate_condition_solution,
        merge_base_aux,
        check_condition_points,
    )
    from services.figure_plan_schemas import (
        parse_base_plan,
        parse_aux_plan,
        parse_audit_result,
    )

    condition_text = (job.problem_text or "").strip()
    solution_text = (job.solution_text or "").strip()

    # ── Stage: base_thinking ──
    _set_stage(job, "base_thinking")
    if not _BASE_PLANNER_PROMPT:
        _fail_job(job, "Системный промпт base_planner не загружен.")
        return

    base_plan = None
    base_errors: list = []
    base_history = []
    prev_base_sig = None
    base_loop = False
    base_repair_feedback = ""
    for attempt in range(1 + MAX_RETRIES + MAX_BASE_REPAIRS):
        # CH21 PART 2: первые MAX_RETRIES+1 попыток — как раньше,
        # далее base-repair с конкретным feedback.
        model = FIGURE_REPAIR_MODEL if attempt > 0 else FIGURE_BASE_MODEL
        role = "repair" if attempt > 0 else "base"
        if base_loop:
            base_repair_feedback += (
                "\n\nВАЖНО: тот же набор ошибок повторился. Удали проблемные "
                "объекты, верни минимальный корректный base-план."
            )
        try:
            resp, json_str = _plan_call(
                _BASE_PLANNER_PROMPT,
                model,
                role=role,
                condition_text=condition_text,
                repair_feedback=base_repair_feedback,
            )
        except LLMError as e:
            logger.error("[figures_gen] base planner LLM error (attempt %d): %s",
                         attempt, e)
            if e.retryable and attempt < MAX_RETRIES:
                continue
            _fail_job(job, str(e))
            return
        except Exception as e:
            logger.error("[figures_gen] base planner API error (attempt %d): %s",
                         attempt, e)
            if attempt < MAX_RETRIES:
                continue
            _fail_job(job, "Сервис генерации временно недоступен.")
            return

        if not json_str:
            if attempt < MAX_RETRIES:
                continue
            _fail_job(
                job,
                f"LLM_NO_JSON: провайдер {resp.get('provider')}, "
                f"модель {resp.get('model_id')}, попытки {MAX_RETRIES + 1}",
            )
            return

        plan = parse_base_plan(json_str)
        if plan is None:
            if attempt < MAX_RETRIES:
                continue
            _fail_job(job, "Не удалось разобрать base-план.")
            return

        base_validation = validate_figure_json(plan)
        if base_validation.get("valid"):
            # CH27b: BLOCKING-проверка точек условия на base-стадии.
            missing_points = check_condition_points(condition_text, plan)
            if missing_points:
                missing_names = [
                    m for m in missing_points
                    if "MISSING_CONDITION_POINT" in m
                ]
                base_errors = list(missing_points)
                # CH27b: конкретный feedback с перечнем недостающих точек.
                base_errors = list(missing_points)
            else:
                base_plan = plan
                job.base_model = model
                job.base_plan_json = _fmt_plan_json(plan)
                db.session.commit()
                _record_stage(
                    job_id, "base_thinking", role=role,
                    provider=resp.get("provider"), model=model,
                    attempt=attempt + 1,
                    input_tokens=(resp.get("usage") or {}).get("prompt_tokens"),
                    output_tokens=(resp.get("usage") or {}).get("completion_tokens"),
                    validation_passed=True,
                    estimated_cost_usd=resp.get("cost_usd"),
                )
                break
        else:
            base_errors = base_validation.get(
                "errors", ["Неизвестная ошибка валидации base-плана"]
            )

        # CH21 PART 2: предметный feedback по кодам ошибок base.
        if base_errors:
            sig = tuple(sorted({e.split(":")[0] for e in base_errors}))
            base_history.append({"attempt": attempt, "codes": list(sig)})
            if sig == prev_base_sig:
                base_loop = True
            prev_base_sig = sig
            base_repair_feedback = _concrete_base_feedback(base_errors)

        if attempt >= MAX_RETRIES + MAX_BASE_REPAIRS:
            job.audit_json = _fmt_plan_json({"base_history": base_history})
            db.session.commit()
            # CH27b: при нехватке точек условия — предметный error_code.
            if base_errors and all("MISSING_CONDITION_POINT" in e for e in base_errors):
                _fail_job(
                    job,
                    "MISSING_CONDITION_POINT: " + "; ".join(base_errors),
                )
            else:
                _fail_job(job, "Модель не смогла создать корректный base-план.")
            return

    if base_plan is None:
        _fail_job(job, "Не удалось построить base-план.")
        return

    # ── Stage: base_drawing ──
    _set_stage(job, "base_drawing")
    try:
        from geometric_engine.engine import GeometricEngine
        engine = GeometricEngine()
        engine.settings.semantic_colors = FIGURE_SEMANTIC_COLORS_ENABLED
        # CH19 DEFECT 3: auto-fit по умолчанию для condition_solution
        # (только масштаб и сдвиг, без изменения относительной геометрии).
        engine.settings.auto_fit = FIGURE_AUTO_FIT_ENABLED
        base_svg, base_ctx, _, base_violations = engine.build_with_retry(base_plan)
        if not base_svg:
            # CH21 PART 2: HARD-отказ движка — предметный feedback и repair.
            base_repair_feedback = _concrete_engine_feedback(base_violations)
            base_history.append({"attempt": "engine", "codes": base_violations[:5]})
            # Повторяем base_thinking с этим feedback (если остались попытки).
            # Для простоты: это уже финальный failure, т.к. repair-цикл выше
            # исчерпал попытки валидации; но фиксируем диагностику.
            job.audit_json = _fmt_plan_json({
                "engine_violations": base_violations,
                "base_history": base_history,
            })
            db.session.commit()
            _fail_job(
                job,
                f"Геометрические ограничения base-чертежа не выполнены: "
                f"{base_violations[:3]}",
            )
            return
    except ImportError:
        _fail_job(job, "Движок построения недоступен.")
        return
    except Exception as e:
        logger.error("[figures_gen] base build error job %d: %s", job_id, e)
        _fail_job(job, "Ошибка при построении base-чертежа.")
        return

    job.svg_path = base_svg
    db.session.commit()

    # ── BATCH FIX 4: телеметрия coverage/visual для condition_solution ──
    # Раньше этот путь не записывал coverage_score/visual_score в
    # figure_build_stages, из-за чего агрегаты по качеству были пустыми.
    try:
        from services.condition_coverage import check_condition_coverage
        _cov = check_condition_coverage(condition_text, base_plan,
                                        build_context=base_ctx, settings=engine.settings)
        _cov_codes = [e.split(":")[0] for e in _cov.get("errors", [])]
        _record_stage(job_id, "coverage_check",
                      coverage_score=_cov.get("score"),
                      validation_passed=_cov.get("complete"),
                      error_codes=_cov_codes)
    except Exception:
        pass
    if FIGURE_VISUAL_CHECK_ENABLED:
        try:
            from services.visual_audit import audit_rendered_figure
            _vis = audit_rendered_figure(base_svg, base_ctx, base_plan,
                                         condition_text, settings=engine.settings)
            if _vis is not None:
                _record_stage(job_id, "visual_check",
                              coverage_score=_vis.get("visual_score"),
                              visual_score=_vis.get("visual_score"),
                              validation_passed=_vis.get("clean"),
                              error_codes=[e.split(":")[0] for e in _vis.get("errors", [])],
                              label_collisions=len([e for e in _vis.get("errors", [])
                                                    if "LABEL_COLLISION" in e]))
        except Exception:
            pass

    # ── Если решения нет — только base pipeline. ──
    if not solution_text:
        job.status = "done"
        job.current_stage = "done"
        job.has_aux = False
        job.aux_svg_path = None
        job.model_name = FIGURE_BASE_MODEL
        job.error = None
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _charge_credit(job_id)
        return

    # ── Stage: aux_thinking ──
    _set_stage(job, "aux_thinking")
    if not _AUX_PLANNER_PROMPT:
        _fail_job(job, "Системный промпт aux_planner не загружен.")
        return

    numbered_solution = _number_solution_steps(solution_text)
    base_plan_json = job.base_plan_json or _fmt_plan_json(base_plan)

    aux_plan = None
    aux_reason = None
    aux_has = False
    repair_feedback = ""
    # CH21 FIX 3: история попыток для диагностики зацикливания.
    aux_history = []
    prev_error_signature = None
    loop_detected = False
    # CH23 PART B3: двухэтапный aux по умолчанию; legacy — только по флагу.
    _use_legacy = FIGURE_AUX_LEGACY_PLANNER
    if not _use_legacy:
        aux_plan, aux_reason, aux_has = _two_stage_aux_plan(
            job, job_id, condition_text, numbered_solution, base_plan
        )
        if aux_plan is None:
            return
        job.aux_model = FIGURE_AUX_MODEL
        job.aux_plan_json = _fmt_plan_json(aux_plan)
        db.session.commit()
    for attempt in range(1 + MAX_AUX_RETRIES if _use_legacy else 0):
        model = FIGURE_REPAIR_MODEL if attempt > 0 else FIGURE_AUX_MODEL
        role = "repair" if attempt > 0 else "aux"
        # CH21 FIX 3: при зацикливании (тот же набор ошибок дважды) —
        # строгая инструкция «удали проблемные объекты».
        if loop_detected:
            repair_feedback += (
                "\n\nВАЖНО: набор ошибок не изменился после предыдущих попыток. "
                "Удали проблемные объекты. Верни МИНИМАЛЬНЫЙ корректный aux. "
                "Лучше has_aux=false, чем невалидный план."
            )
        try:
            resp, json_str = _plan_call(
                _AUX_PLANNER_PROMPT,
                model,
                role=role,
                condition_text=condition_text,
                numbered_solution_text=numbered_solution,
                base_plan_json=base_plan_json,
                repair_feedback=repair_feedback,
            )
        except LLMError as e:
            logger.error("[figures_gen] aux planner LLM error (attempt %d): %s",
                         attempt, e)
            if e.retryable and attempt < MAX_AUX_RETRIES:
                continue
            _fail_job(job, str(e))
            return
        except Exception as e:
            logger.error("[figures_gen] aux planner API error (attempt %d): %s",
                         attempt, e)
            if attempt < MAX_AUX_RETRIES:
                continue
            _fail_job(job, "Сервис генерации временно недоступен.")
            return

        if not json_str:
            if attempt < MAX_AUX_RETRIES:
                continue
            _fail_job(
                job,
                f"LLM_NO_JSON: провайдер {resp.get('provider')}, "
                f"модель {resp.get('model_id')}, попытки {MAX_AUX_RETRIES + 1}",
            )
            return

        plan = parse_aux_plan(json_str)
        if plan is None:
            if attempt < MAX_AUX_RETRIES:
                continue
            _fail_job(job, "Не удалось разобрать aux-план.")
            return

        aux_has = bool(plan.get("has_aux"))
        aux_reason = (plan.get("reason") or "")[:500]
        # CH22 STEP 1: если планировщик сам вернул has_aux=false — законно не нужен.
        if not aux_has and attempt == 0:
            job.aux_status = "AUX_NOT_NEEDED"
            job.aux_fail_reason = None
            db.session.commit()
        elif not aux_has and attempt > 0:
            # Модель откатилась к has_aux=false после ошибок валидатора.
            job.aux_status = "AUX_ROLLED_BACK"
            job.aux_fail_reason = _fmt_plan_json({
                "rollback_after_codes": aux_history[-1]["error_codes"] if aux_history else [],
            })
            db.session.commit()

        # ── Детерминированная проверка base ↔ aux ──
        inv = validate_condition_solution(base_plan, plan,
                                          condition_text=condition_text)
        repair_warnings = [
            w for w in inv.get("warnings", [])
            if w.startswith("AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION")
            or w.startswith("MISSING_FOOT_ID")
        ]
        hard_errors = inv.get("errors", []) if not inv.get("valid") else []

        if aux_has and (hard_errors or repair_warnings):
            # CH21 FIX 3: конкретный repair_feedback по кодам ошибок.
            feedback_lines = _concrete_repair_feedback(
                hard_errors, repair_warnings, base_plan, plan
            )
            repair_feedback = (
                "Твой предыдущий aux-план НЕ принят (до исправления чертёж НЕ строится).\n"
                "Замечания:\n" + "\n".join(feedback_lines) + "\n\n"
                "Исправь aux-план и верни корректный JSON без пояснений."
            )

            # CH21 FIX 3: сигнатура ошибок — для детекта зацикливания.
            sig = tuple(sorted({e.split(":")[0] for e in hard_errors + repair_warnings}))
            aux_history.append({
                "attempt": attempt,
                "error_codes": list(sig),
                "plan_hash": _plan_hash(plan),
            })
            if sig == prev_error_signature:
                loop_detected = True
            prev_error_signature = sig

            if attempt < MAX_AUX_RETRIES:
                logger.warning(
                    "[figures_gen] aux repair retry for job %d (attempt %d): %s",
                    job_id, attempt, feedback_lines,
                )
                continue
            job.audit_json = _fmt_plan_json({
                "invariant_errors": hard_errors,
                "repair_warnings": repair_warnings,
                "aux_history": aux_history,
            })
            # CH22 STEP 1: план не прошёл валидатор после всех repair.
            job.aux_status = "AUX_PLAN_REJECTED"
            job.aux_fail_reason = _fmt_plan_json({
                "codes": list(sig),
                "last_errors": hard_errors + repair_warnings,
            })
            db.session.commit()
            # CH-BATCH: aux не удалось починить — откат к base-чертежу
            # (base уже валиден и сохранён в job.svg_path). Не теряем чертёж
            # из-за необязательного доп. построения.
            _drop_aux(job, base_svg, "aux_plan_rejected")
            _charge_credit(job_id)
            return

        aux_plan = plan
        job.aux_model = model
        job.aux_plan_json = _fmt_plan_json(plan)
        db.session.commit()
        _record_stage(
            job_id, "aux_thinking", role=role,
            provider=resp.get("provider"), model=model,
            attempt=attempt + 1,
            input_tokens=(resp.get("usage") or {}).get("prompt_tokens"),
            output_tokens=(resp.get("usage") or {}).get("completion_tokens"),
            validation_passed=True,
            estimated_cost_usd=resp.get("cost_usd"),
        )
        break

    if aux_plan is None:
        _fail_job(job, "Не удалось построить aux-план.")
        return

    # ── Stage: aux_drawing ──
    _set_stage(job, "aux_drawing")
    aux_svg = None
    if aux_has:
        merged = merge_base_aux(base_plan, aux_plan)
        try:
            aux_svg, _, _, aux_violations = engine.build_with_retry(merged)
        except Exception as e:
            logger.warning("[figures_gen] aux build failed job %d: %s",
                           job_id, e)
            aux_svg = None
        if aux_svg:
            job.aux_status = "AUX_BUILT"
            job.aux_fail_reason = None
        else:
            # CH22 STEP 1: план валиден, но движок не построил aux.
            job.aux_status = "AUX_BUILD_FAILED"
            job.aux_fail_reason = _fmt_plan_json({
                "engine_violations": aux_violations[:5] if 'aux_violations' in dir() else [],
            })
        db.session.commit()

    # ── Stage: auditing ──
    _set_stage(job, "auditing")
    audit_json = job.audit_json  # уже мог быть частично заполнен
    approved = True
    if _AUDITOR_PROMPT and aux_has:
        try:
            resp, audit_str = _plan_call(
                _AUDITOR_PROMPT,
                FIGURE_AUDIT_MODEL,
                role="audit",
                condition_text=condition_text,
                numbered_solution_text=numbered_solution,
                base_plan_json=base_plan_json,
                aux_plan_json=job.aux_plan_json or _fmt_plan_json(aux_plan),
            )
            if audit_str:
                result = parse_audit_result(audit_str)
                if result is not None:
                    audit_json = _fmt_plan_json(result)
                    approved = bool(result.get("approved", True))
            _record_stage(
                job_id, "auditing", role="audit",
                provider=resp.get("provider"),
                model=resp.get("model_id") or FIGURE_AUDIT_MODEL,
                input_tokens=(resp.get("usage") or {}).get("prompt_tokens"),
                output_tokens=(resp.get("usage") or {}).get("completion_tokens"),
                validation_passed=approved,
                audit_invoked=True,
                estimated_cost_usd=resp.get("cost_usd"),
            )
        except Exception as e:
            logger.warning("[figures_gen] auditor failed job %d: %s", job_id, e)

    job.audit_json = audit_json
    db.session.commit()

    # ── Done (кредит один раз, независимо от числа LLM-вызовов) ──
    job.status = "done"
    job.current_stage = "done"
    job.svg_path = base_svg
    job.aux_svg_path = aux_svg
    job.has_aux = aux_has and aux_svg is not None
    job.aux_reason = aux_reason if job.has_aux else None
    # CH22 STEP 1: если aux_status ещё не установлен — определяем.
    if job.aux_status is None:
        if not aux_has:
            job.aux_status = "AUX_NOT_NEEDED"
        elif job.has_aux:
            job.aux_status = "AUX_BUILT"
        else:
            job.aux_status = "AUX_BUILD_FAILED"
    job.model_name = FIGURE_BASE_MODEL
    job.error = None
    job.updated_at = datetime.utcnow()
    db.session.commit()

    # CH22 STEP 1: итоговый лог aux-метрик.
    logger.info(
        "[figures_gen] job %d aux: planner_has_aux=%s valid=%s svg_built=%s "
        "status=%s fail_codes=%s",
        job_id, aux_has, aux_plan is not None, job.has_aux,
        job.aux_status, job.aux_fail_reason,
    )

    _charge_credit(job_id)


# ── Queue worker ────────────────────────────────────────────────────────

def _queue_worker_loop(app=None):
    """Background daemon thread: poll figure_build_jobs for queued tasks."""
    global QUEUE_WORKER_STARTED
    if app is None:
        from flask import current_app as _app
        app = _app._get_current_object()
    logger.info("[figures_gen] queue worker started")
    while True:
        try:
            with app.app_context():
                from models import db, FigureBuildJob

                # Find and recover stale jobs (>8 min in non-final state).
                # 8 min достаточно: reasoning job не должен висеть дольше
                # 2 x DEEPSEEK_TIMEOUT (300s) даже при повторной попытке.
                # Более короткий порог не даёт «заедать» очереди при
                # зависших LLM-вызовах (сетевой простой провайдеров).
                _cutoff = datetime.utcnow()
                from datetime import timedelta
                _cutoff = _cutoff - timedelta(minutes=8)
                stale = FigureBuildJob.query.filter(
                    FigureBuildJob.status.in_([
                        'thinking', 'drawing',
                        'base_thinking', 'base_drawing',
                        'aux_thinking', 'aux_drawing', 'auditing',
                        'coverage_check', 'visual_check',
                        'aux_template_match', 'solving', 'answer_verify',
                        'aux_compile', 'aux_usefulness',
                    ]),
                    FigureBuildJob.updated_at < _cutoff,
                ).all()
                for s in stale:
                    logger.warning("[figures_gen] stale job %d was %s, "
                                   "marking failed", s.id, s.status)
                    s.status = "failed"
                    s.error = f"Job timed out (was {s.status} for >8 min)"
                    s.updated_at = datetime.utcnow()
                    _refund_credit(s.id)
                if stale:
                    db.session.commit()

                # Pick queued jobs (subscribers first, then FIFO) but do not
                # exceed the concurrency cap. Each build runs in its own
                # thread so a slow job can't starve the queue.
                with _active_jobs_lock:
                    _active_jobs.discard(None)
                    free_slots = MAX_CONCURRENT_JOBS - len(_active_jobs)

                while free_slots > 0:
                    job = FigureBuildJob.query.filter_by(status="queued").order_by(
                        FigureBuildJob.priority.desc(),
                        FigureBuildJob.created_at,
                    ).first()
                    if not job:
                        break
                    with _active_jobs_lock:
                        _active_jobs.add(job.id)
                    logger.info("[figures_gen] picked job %d from queue", job.id)
                    threading.Thread(
                        target=_run_build_job_thread,
                        args=(app, job.id),
                        daemon=True,
                        name=f"figures-gen-job-{job.id}",
                    ).start()
                    free_slots -= 1
        except Exception as e:
            logger.error("[figures_gen] queue worker error: %s", e)

        time.sleep(QUEUE_POLL_INTERVAL)


def _ensure_queue_worker(app=None):
    """Start the queue worker thread once per process."""
    global QUEUE_WORKER_STARTED
    with _queue_worker_lock:
        if QUEUE_WORKER_STARTED:
            return
        QUEUE_WORKER_STARTED = True

    if app is None:
        from flask import current_app as _app
        app = _app._get_current_object()

    t = threading.Thread(
        target=_queue_worker_loop,
        args=(app,),
        daemon=True,
        name="figures-gen-queue",
    )
    t.start()
    logger.info("[figures_gen] queue worker thread launched")


# ── Routes ──────────────────────────────────────────────────────────────

@figures_gen_bp.route("", methods=["GET"])
@login_required
def generate_page():
    """Render the figure generation page."""
    if not current_user.has_access():
        return render_template('trial_expired.html'), 402
    return render_template("figures_generate.html")


@figures_gen_bp.route("/start", methods=["POST"])
@login_required
def start_build():
    """Create a background figure build job. Returns job_id immediately."""
    # Rate limit
    allowed, retry_after = _rate_check()
    if not allowed:
        return jsonify({
            "error": f"Слишком много запросов. Попробуйте через {retry_after} сек.",
            "retry_after": retry_after,
        }), 429

    # Parse request
    data = request.get_json(silent=True) or {}
    problem = (data.get("problem_text") or data.get("problem") or "").strip()
    build_type = (data.get("build_type") or "plain").strip()
    # CH15: optional solution_text — если задан, включается двухслойный
    # конвейер condition_solution (base по условию + aux из решения).
    solution_text = (data.get("solution_text") or "").strip()

    if not problem:
        return jsonify({"error": "Введите условие задачи."}), 400
    if len(problem) > MAX_PROBLEM_LENGTH:
        return jsonify({
            "error": f"Условие слишком длинное (максимум {MAX_PROBLEM_LENGTH} символов)."
        }), 400
    if len(solution_text) > MAX_PROBLEM_LENGTH * 4:
        return jsonify({
            "error": "Решение слишком длинное."
        }), 400

    # Check credits (пропускаем — генерация бесплатна по клику).
    credits = _get_figure_credits(current_user)

    # Check API key
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return jsonify({
            "error": "Ключ API не настроен. Генерация чертежей временно недоступна."
        }), 503

    # Определить режим генерации.
    # 'base_only' — чертёж только по условию (1 LLM-вызов на чистом задании).
    # 'condition_solution' — двухслойный конвейер (base + aux из решения).
    # Иначе — legacy (как раньше).
    #
    # CH22: активация base_only (по приоритету):
    #   1. явный параметр запроса mode=base_only;
    #   2. solution_text пуст/короче порога;
    #   3. эвристика: в решении нет стемов явных построений.
    explicit_mode = (data.get("mode") or "").strip().lower()
    solution_has_construction = any(
        stem in (solution_text or "").lower()
        for stem in ("провед", "соедин", "продл", "постро", "опуст")
    )

    generation_mode = "legacy"
    if explicit_mode == "base_only":
        generation_mode = "base_only"
    elif explicit_mode == "solver_aux":
        # CH-aux: решения нет, генерируем его сами (v4-pro) + aux.
        generation_mode = "solver_aux"
    elif explicit_mode == "condition_solution":
        generation_mode = "condition_solution"
    elif CONDITION_SOLUTION_ENABLED and solution_text:
        if not solution_has_construction:
            generation_mode = "base_only"
        else:
            generation_mode = "condition_solution"
    elif data.get("want_aux") or build_type == "aux":
        # CH-aux: решения нет, но aux запрошен (кнопка «С доп. построением»
        # на фронте шлёт build_type="aux").
        generation_mode = "solver_aux"
    elif CONDITION_SOLUTION_ENABLED and not solution_text:
        # Нет решения вообще — чертёж только по условию.
        generation_mode = "base_only"

    # Create job
    try:
        from models import db, FigureBuildJob
        # Set priority: 1 for subscribers, 0 for free users,
        # -1 for the batch service account (никогда не обгоняет живых юзеров).
        job_priority = 0
        if getattr(current_user, 'email', '') == BATCH_SERVICE_EMAIL:
            job_priority = BATCH_PRIORITY
        elif hasattr(current_user, 'has_active_subscription'):
            try:
                if current_user.has_active_subscription():
                    job_priority = 1
            except Exception:
                job_priority = 0

        # Legacy: prepend build_type marker to problem_text for the worker.
        stored_problem = problem
        if generation_mode == "legacy":
            stored_problem = f"##BT:{build_type}\n{problem}"

        job = FigureBuildJob(
            user_id=current_user.id,
            problem_text=stored_problem,
            solution_text=solution_text or None,
            generation_mode=generation_mode,
            status="queued",
            model_name=REASONER_MODEL,
            priority=job_priority,
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id
    except Exception as e:
        logger.error("[figures_gen] failed to create FigureBuildJob: %s", e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": "Не удалось создать задание. Попробуйте позже."}), 500

    # Ensure queue worker is running
    _ensure_queue_worker()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "credits": credits,
    })


@figures_gen_bp.route("/active", methods=["GET"])
@login_required
def active_job():
    """Return the user's most recent non-final build job.

    Used by the frontend to RESUME a build after the user left the page:
    the job is stored in the DB (not in browser memory), so a queued /
    thinking / drawing job survives navigation and phone reloads.
    """
    try:
        from models import FigureBuildJob
        job = FigureBuildJob.query.filter(
            FigureBuildJob.user_id == current_user.id,
            FigureBuildJob.status.in_([
                'queued', 'thinking', 'drawing',
                'base_thinking', 'base_drawing',
                'aux_thinking', 'aux_drawing', 'auditing',
            ]),
        ).order_by(FigureBuildJob.created_at.desc()).first()
        if not job:
            return jsonify({"job_id": None})
        return jsonify({
            "job_id": job.id,
            "status": job.status,
            "current_stage": job.current_stage or job.status,
            "current_model": _current_model_for_stage(job),
        })
    except Exception as e:
        logger.error("[figures_gen] active_job error: %s", e)
        return jsonify({"error": "Ошибка при проверке активного задания."}), 500


@figures_gen_bp.route("/status/<int:job_id>", methods=["GET"])
@login_required
def job_status(job_id):
    """Poll job status. Returns svg when done, including aux if available."""
    try:
        from models import FigureBuildJob
        job = FigureBuildJob.query.filter_by(
            id=job_id, user_id=current_user.id,
        ).first()
        if not job:
            return jsonify({"error": "Задание не найдено."}), 404

        resp = {
            "job_id": job.id,
            "status": job.status,
            "current_stage": job.current_stage or job.status,
            "step_label": _stage_label(job.current_stage or job.status),
            "current_model": _current_model_for_stage(job),
        }
        if job.status == "done":
            resp["svg"] = job.svg_path or ""
            resp["credits_remaining"] = _get_figure_credits(current_user)
            resp["figures_built"] = getattr(current_user, "figures_built", 0) or 0
            resp["has_aux"] = bool(job.has_aux)
            resp["aux_svg"] = job.aux_svg_path if job.has_aux else None
            resp["aux_reason"] = job.aux_reason if job.has_aux else None
            resp["aux_status"] = job.aux_status
            resp["aux_fail_reason"] = job.aux_fail_reason
        elif job.status == "failed":
            resp["error"] = job.error or "Построение не удалось."
            resp["credits"] = _get_figure_credits(current_user)
            # error_code: первое слово из job.error, если оно похоже на код LLM_*.
            err = job.error or ""
            code = err.split(":", 1)[0].strip() if err else ""
            if code.startswith("LLM_") or code.startswith("MISSING_") or code.startswith("INVALID_"):
                resp["error_code"] = code
            resp["stage"] = job.current_stage or job.status

        # CH15: планы отдаём только владельцу job (маршрут уже фильтрует по
        # user_id) или админу — для QA/диагностики.
        is_admin = bool(getattr(current_user, "is_admin", False))
        if job.base_plan_json is not None and is_admin:
            resp["base_plan_json"] = job.base_plan_json
        if job.aux_plan_json is not None and is_admin:
            resp["aux_plan_json"] = job.aux_plan_json

        return jsonify(resp)
    except Exception as e:
        logger.error("[figures_gen] status error for job %d: %s", job_id, e)
        return jsonify({"error": "Ошибка при проверке статуса."}), 500


# ── T9: queue helpers ──────────────────────────────────────────────────

def queue_position(job) -> int:
    """Return 1-based position of this job among its user's queued jobs.

    Counts FigureBuildJob records with same user_id, status='queued',
    and created_at <= this job's created_at.  Other users' jobs are
    NOT counted — the queue shown to each user is their own.
    """
    from models import FigureBuildJob
    return FigureBuildJob.query.filter(
        FigureBuildJob.user_id == job.user_id,
        FigureBuildJob.status == 'queued',
        FigureBuildJob.created_at <= job.created_at,
    ).count()


def queue_total(user_id: int) -> int:
    """Return total queued FigureBuildJob count for one user."""
    from models import FigureBuildJob
    return FigureBuildJob.query.filter_by(
        user_id=user_id, status='queued',
    ).count()


# ── T9: queue status route ─────────────────────────────────────────────

@figures_gen_bp.route("/queue-status", methods=["GET"])
@login_required
def queue_status():
    """Return JSON {position, total, priority} for the user's latest
    queued job.  If no queued jobs: {position:0, total:0, priority:0}.
    """
    from models import FigureBuildJob
    uid = current_user.id

    # Determine priority level for this user
    user_priority = 0
    if hasattr(current_user, 'has_active_subscription'):
        try:
            if current_user.has_active_subscription():
                user_priority = 1
        except Exception:
            user_priority = 0

    last_queued = FigureBuildJob.query.filter_by(
        user_id=uid, status='queued',
    ).order_by(FigureBuildJob.created_at.desc()).first()

    if last_queued is None:
        return jsonify({"position": 0, "total": 0, "priority": user_priority})

    pos = queue_position(last_queued)
    total = queue_total(uid)
    return jsonify({"position": pos, "total": total, "priority": user_priority})


# ── CH22: телеметрия (стадии) ────────────────────────────────────────────

def _stage_label(stage: str) -> str:
    """Человекочитаемая подпись этапа для фронтенда."""
    labels = {
        "queued": "В очереди",
        "thinking": "Анализ условия",
        "base_thinking": "Анализ условия",
        "drawing": "Построение",
        "base_drawing": "Построение",
        "coverage_check": "Проверка чертежа",
        "visual_check": "Визуальный аудит",
        "aux_template_match": "Подбор типового построения",
        "solving": "Решение задачи",
        "answer_verify": "Проверка ответа",
        "aux_compile": "Компиляция построений",
        "aux_usefulness": "Проверка полезности",
        "aux_thinking": "Доп. построения",
        "aux_drawing": "Построение доп.",
        "auditing": "Финальная проверка",
        "done": "Готово",
        "failed": "Ошибка",
    }
    return labels.get(stage, stage or "")


def _current_model_for_stage(job) -> str:
    """Модель, работающая на текущей стадии job.

    Используется для показа пользователю, какая модель сейчас генерирует.
    """
    stage = (job.current_stage or job.status or "").lower()
    if stage in ("thinking", "drawing"):
        # legacy-режим.
        return getattr(job, "model_name", None) or REASONER_MODEL
    if stage.startswith("base_"):
        return getattr(job, "base_model", None) or FIGURE_BASE_MODEL
    if stage.startswith("aux_"):
        return getattr(job, "aux_model", None) or FIGURE_AUX_MODEL
    if stage == "auditing":
        return getattr(job, "audit_model", None) or FIGURE_AUDIT_MODEL
    if stage == "solving":
        from services.llm_router import logical_model_for_role
        return logical_model_for_role("solver")
    if stage in ("coverage_check", "visual_check", "aux_template_match",
                 "answer_verify", "aux_compile", "aux_usefulness"):
        return ""  # детерминированные стадии — LLM не работает
    if stage == "done":
        return getattr(job, "model_name", None) or FIGURE_BASE_MODEL
    return ""


def _record_stage(job_id: int, stage: str, role: str = None, provider: str = None,
                  model: str = None, attempt: int = 1, input_tokens: int = None,
                  output_tokens: int = None, latency_ms: int = None,
                  coverage_score: float = None, validation_passed: bool = None,
                  audit_invoked: bool = False, error_codes: list = None,
                  estimated_cost_usd: float = None,
                  visual_score: float = None, label_collisions: int = None,
                  autofix_applied: bool = False, reseed_count: int = None,
                  reasoning_tokens: int = None, fallback_used: bool = False,
                  timeout_hit: bool = False) -> None:
    """Записать одну строку телеметрии по стадии (не ломает pipeline при ошибке)."""
    try:
        from models import db, FigureBuildStage
        import json as _json
        row = FigureBuildStage(
            job_id=job_id,
            stage=stage,
            role=role,
            provider=provider,
            model=model,
            attempt=attempt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            coverage_score=coverage_score,
            validation_passed=validation_passed,
            audit_invoked=audit_invoked,
            error_codes=_json.dumps(error_codes, ensure_ascii=False) if error_codes else None,
            estimated_cost_usd=estimated_cost_usd,
            visual_score=visual_score,
            label_collisions=label_collisions,
            autofix_applied=autofix_applied,
            reseed_count=reseed_count,
            reasoning_tokens=reasoning_tokens,
            fallback_used=fallback_used,
            timeout_hit=timeout_hit,
        )
        db.session.add(row)
        db.session.commit()
    except Exception as e:  # телеметрия не должна ронять воркер
        logger.warning("[figures_gen] _record_stage failed for job %d: %s", job_id, e)


@figures_gen_bp.route("/metrics", methods=["GET"])
@login_required
def figure_metrics():
    """CH22: агрегаты качества генерации (только админ)."""
    if not bool(getattr(current_user, "is_admin", False)):
        return jsonify({"error": "Forbidden"}), 403
    try:
        from models import db, FigureBuildJob, FigureBuildStage
        from datetime import datetime, timedelta
        from sqlalchemy import func

        window = request.args.get("window", "24h")
        if window.endswith("h"):
            hours = int(window[:-1])
            cutoff = datetime.utcnow() - timedelta(hours=hours)
        elif window.endswith("d"):
            days = int(window[:-1])
            cutoff = datetime.utcnow() - timedelta(days=days)
        else:
            cutoff = datetime.utcnow() - timedelta(hours=24)

        done_count = FigureBuildJob.query.filter(
            FigureBuildJob.status == "done",
            FigureBuildJob.updated_at >= cutoff,
        ).count()
        failed_count = FigureBuildJob.query.filter(
            FigureBuildJob.status == "failed",
            FigureBuildJob.updated_at >= cutoff,
        ).count()

        stages = FigureBuildStage.query.filter(
            FigureBuildStage.created_at >= cutoff,
        ).all()

        audit_invoked = sum(1 for s in stages if s.audit_invoked)
        total_stages = len(stages)
        total_cost = sum(s.estimated_cost_usd or 0.0 for s in stages)
        coverage_scores = [s.coverage_score for s in stages
                           if s.coverage_score is not None]

        # Распределение по provider+model.
        by_model: dict = {}
        for s in stages:
            key = f"{s.provider or '-'}:{s.model or '-'}"
            by_model.setdefault(key, {"stages": 0, "cost_usd": 0.0})
            by_model[key]["stages"] += 1
            by_model[key]["cost_usd"] += s.estimated_cost_usd or 0.0

        # first_pass_success_rate: доля done среди всех завершённых.
        total_finished = done_count + failed_count
        first_pass = (done_count / total_finished) if total_finished else 0.0

        result = {
            "window": window,
            "done_jobs": done_count,
            "failed_jobs": failed_count,
            "first_pass_success_rate": round(first_pass, 4),
            "audit_invocation_rate": round(
                (audit_invoked / total_stages) if total_stages else 0.0, 4
            ),
            "cost_per_done_job_usd": round(
                (total_cost / done_count) if done_count else 0.0, 6
            ),
            "median_coverage_score": round(
                _median(coverage_scores), 4
            ) if coverage_scores else None,
            "stages_by_model": by_model,
        }
        return jsonify(result)
    except Exception as e:
        logger.error("[figures_gen] metrics error: %s", e)
        return jsonify({"error": "Ошибка при сборе метрик."}), 500


def _median(values: list) -> float:
    """Медиана списка чисел."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0

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

logger = logging.getLogger(__name__)

figures_gen_bp = Blueprint("figures_generator", __name__, url_prefix="/figures/generate")

# ── Config ──────────────────────────────────────────────────────────────
REASONER_MODEL = os.environ.get("FIGURE_MODEL", "deepseek-v4-flash").strip()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_TIMEOUT = 90  # seconds
MAX_RETRIES = 2
MAX_PROBLEM_LENGTH = 4000
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 3600

# ── Queue processing config ─────────────────────────────────────────────
QUEUE_POLL_INTERVAL = 2   # seconds between queue scans
QUEUE_WORKER_STARTED = False
_queue_worker_lock = Lock()

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


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> str | None:
    """Extract JSON object from model response (may have markdown fences)."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = _JSON_OBJECT_RE.search(text)
    if m:
        return m.group(0).strip()
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
    """Charge 1 credit atomically. Called only on transition to done.

    Uses UPDATE ... WHERE credit_charged = 0 as an atomic compare-and-swap
    at the database level.  Two concurrent callers for the same job_id will
    see exactly one row updated — the second UPDATE affects zero rows and
    we short-circuit with a no-op.
    """
    try:
        from models import db, FigureBuildJob, FigureCreditTransaction, User
        from sqlalchemy import update as _sa_update

        # Atomic CAS: set credit_charged = 1 only if it is currently 0.
        result = db.session.execute(
            _sa_update(FigureBuildJob)
            .where(
                FigureBuildJob.id == job_id,
                FigureBuildJob.credit_charged == False,  # noqa: E712
            )
            .values(credit_charged=True)
        )
        rowcount = result.rowcount
        if rowcount == 0:
            # Either the job doesn't exist or it was already charged.
            job = FigureBuildJob.query.get(job_id)
            if job and job.credit_charged:
                return True, "already charged"
            return False, "Job not found"

        job = FigureBuildJob.query.get(job_id)
        if not job:
            return False, "Job not found"
        user = User.query.get(job.user_id)
        if not user:
            return False, "User not found"
        credits = _get_figure_credits(user)
        if credits <= 0:
            # Roll back the flag — we can't charge
            job.credit_charged = False
            db.session.commit()
            return False, "No credits"
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
    """Refund 1 credit if job failed and credit was charged by mistake."""
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


# ── DeepSeek API call ───────────────────────────────────────────────────

def _call_deepseek(messages: list[dict]) -> dict:
    """Call DeepSeek API directly. Returns dict with 'content' and 'cost_usd'."""
    model_name = REASONER_MODEL
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
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
    # Pricing for deepseek-v4-flash: $0.27/M input, $1.10/M output
    cost_usd = (prompt_tokens * 0.27 + completion_tokens * 1.10) / 1_000_000

    return {
        "content": content,
        "cost_usd": cost_usd,
        "model": model_name,
        "usage": usage,
    }


# ── Background worker ───────────────────────────────────────────────────

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

    # ── Step 1: Thinking ──
    job.status = "thinking"
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

    final_json = None
    last_errors = []
    last_resp = None

    for attempt in range(1 + MAX_RETRIES):
        messages = [
            {"role": "system", "content": _REASONER_SYSTEM_PROMPT},
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
        except Exception as e:
            logger.error("[figures_gen] DeepSeek API error (attempt %d): %s",
                         attempt, e)
            if attempt < MAX_RETRIES:
                continue
            job.status = "failed"
            job.error = "Сервис генерации временно недоступен."
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
            job.error = "Не удалось получить описание чертежа от модели."
            job.updated_at = datetime.utcnow()
            db.session.commit()
            _refund_credit(job_id)
            return

        validation = validate_figure_json(json_str)
        if validation.get("valid"):
            final_json = json_str
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


# ── Queue worker ────────────────────────────────────────────────────────

def _queue_worker_loop():
    """Background daemon thread: poll figure_build_jobs for queued tasks."""
    global QUEUE_WORKER_STARTED
    logger.info("[figures_gen] queue worker started")
    while True:
        try:
            from flask import current_app as _app
            app = _app._get_current_object()
            with app.app_context():
                from models import db, FigureBuildJob

                # Find and recover stale jobs (>10 min in non-final state)
                _cutoff = datetime.utcnow()
                from datetime import timedelta
                _cutoff = _cutoff - timedelta(minutes=10)
                stale = FigureBuildJob.query.filter(
                    FigureBuildJob.status.in_(['thinking', 'drawing']),
                    FigureBuildJob.updated_at < _cutoff,
                ).all()
                for s in stale:
                    logger.warning("[figures_gen] stale job %d was %s, "
                                   "marking failed", s.id, s.status)
                    s.status = "failed"
                    s.error = f"Job timed out (was {s.status} for >10 min)"
                    s.updated_at = datetime.utcnow()
                    _refund_credit(s.id)
                if stale:
                    db.session.commit()

                # Pick one queued job — subscribers first (priority DESC), then FIFO
                job = FigureBuildJob.query.filter_by(status="queued").order_by(
                    FigureBuildJob.priority.desc(),
                    FigureBuildJob.created_at,
                ).first()
                if job:
                    logger.info("[figures_gen] picked job %d from queue", job.id)
                    try:
                        _run_build_job(job.id)
                    except Exception as e:
                        logger.error("[figures_gen] worker failed job %d: %s",
                                     job.id, e)
        except Exception as e:
            logger.error("[figures_gen] queue worker error: %s", e)

        time.sleep(QUEUE_POLL_INTERVAL)


def _ensure_queue_worker():
    """Start the queue worker thread once per process."""
    global QUEUE_WORKER_STARTED
    with _queue_worker_lock:
        if QUEUE_WORKER_STARTED:
            return
        QUEUE_WORKER_STARTED = True

    t = threading.Thread(
        target=_queue_worker_loop,
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

    if not problem:
        return jsonify({"error": "Введите условие задачи."}), 400
    if len(problem) > MAX_PROBLEM_LENGTH:
        return jsonify({
            "error": f"Условие слишком длинное (максимум {MAX_PROBLEM_LENGTH} символов)."
        }), 400

    # Check credits
    credits = _get_figure_credits(current_user)
    if credits <= 0:
        return jsonify({
            "error": "У вас закончились чертежи.",
            "credits": credits,
        }), 402

    # Check API key
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return jsonify({
            "error": "Ключ API не настроен. Генерация чертежей временно недоступна."
        }), 503

    # Create job
    try:
        from models import db, FigureBuildJob
        # Set priority: 1 for subscribers, 0 for free users
        job_priority = 0
        if hasattr(current_user, 'has_active_subscription'):
            try:
                if current_user.has_active_subscription():
                    job_priority = 1
            except Exception:
                job_priority = 0
        job = FigureBuildJob(
            user_id=current_user.id,
            problem_text=problem,
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
        }
        if job.status == "done":
            resp["svg"] = job.svg_path or ""
            resp["credits_remaining"] = _get_figure_credits(current_user)
            resp["figures_built"] = getattr(current_user, "figures_built", 0) or 0
            resp["has_aux"] = bool(job.has_aux)
            resp["aux_svg"] = job.aux_svg_path if job.has_aux else None
            resp["aux_reason"] = job.aux_reason if job.has_aux else None
        elif job.status == "failed":
            resp["error"] = job.error or "Построение не удалось."
            resp["credits"] = _get_figure_credits(current_user)

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

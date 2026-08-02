# -*- coding: utf-8 -*-
# Blueprint "/figures" — geometry figure generation (reasoner + validator + engine).
#
# Pipeline:
#   1. User submits problem text + optional solution
#   2. Reasoner model (via OpenRouter) generates JSON construction description
#      using data/figures/reasoner_task.txt as system prompt
#   3. figure_validator.py checks the JSON
#   4. geometric_engine builds SVG
#   5. SVG returned to frontend for display and download
#
# On validation failure: up to 2 retries with error feedback to model.
# After 2 retries: honest message, attempt NOT counted (credit refunded).

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime
from threading import Lock

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


from services.openrouter_client import openrouter, OpenRouterError
from services.figure_validator import validate_figure_json

logger = logging.getLogger(__name__)

figures_bp = Blueprint("figures", __name__)

# ── Config ──────────────────────────────────────────────────────────────
REASONER_MODEL = os.environ.get("FIGURE_MODEL", "deepseek-v4-flash").strip()
MAX_RETRIES = 2                    # max retries on validation failure
MAX_PROBLEM_LENGTH = 4000          # max characters in problem text
MAX_SOLUTION_LENGTH = 8000         # max characters in solution text
RATE_LIMIT_MAX = 10                # max requests per window
RATE_LIMIT_WINDOW = 3600           # window in seconds

# ── Payment packages (single source of truth — change here, not in code) ─

FIGURE_PACKAGES = [
    {"id": "p10", "amount": 10, "price_rub": 99, "label": "10 чертежей", "featured": False},
    {"id": "p30", "amount": 30, "price_rub": 249, "label": "30 чертежей", "featured": True},
    {"id": "p100", "amount": 100, "price_rub": 599, "label": "100 чертежей", "featured": False},
]

# ── Rate limit ──────────────────────────────────────────────────────────
_rate_log: dict[str, list[float]] = defaultdict(list)
_rate_lock = Lock()


def _rate_key() -> str:
    try:
        if current_user is not None and getattr(current_user, "is_authenticated", False):
            uid = getattr(current_user, "id", None)
            if uid is not None:
                return f"user:{uid}"
    except Exception:
        pass
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "anon")
    return f"ip:{ip.split(',')[0].strip()}"


def _rate_check() -> tuple[bool, int]:
    key = _rate_key()
    now = time.time()
    with _rate_lock:
        bucket = [t for t in _rate_log[key] if now - t < RATE_LIMIT_WINDOW]
        _rate_log[key] = bucket
        if len(bucket) >= RATE_LIMIT_MAX:
            retry_after = int(RATE_LIMIT_WINDOW - (now - bucket[0])) + 1
            return False, max(retry_after, 1)
        bucket.append(now)
        return True, 0


# ── Concurrent build guard ──────────────────────────────────────────────
_building: dict[str, bool] = {}
_building_lock = Lock()


def _concurrent_guard() -> tuple[bool, str]:
    """Returns (allowed, message). Prevents >1 concurrent build per user."""
    uid = _rate_key()
    with _building_lock:
        if _building.get(uid, False):
            return False, "У вас уже выполняется построение. Дождитесь завершения."
        _building[uid] = True
    return True, ""


def _release_concurrent_guard():
    uid = _rate_key()
    with _building_lock:
        _building.pop(uid, None)


# ── Reasoner prompt ─────────────────────────────────────────────────────
_REASONER_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "figures", "reasoner_task.txt"
)

_REASONER_SYSTEM_PROMPT: str = ""
try:
    with open(_REASONER_PROMPT_PATH, "r", encoding="utf-8") as _f:
        _REASONER_SYSTEM_PROMPT = _f.read()
    logger.info("[figures] reasoner prompt loaded (%d chars)", len(_REASONER_SYSTEM_PROMPT))
except Exception as _e:
    logger.error("[figures] failed to load reasoner prompt: %s", _e)
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
    """Get user's figure_credits, defaulting to 3 for new users."""
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


def _spend_credit(user) -> tuple[bool, str]:
    """Try to spend 1 credit. Returns (success, message). Logs transaction."""
    if user is None:
        return False, "Необходимо войти в систему."
    credits = _get_figure_credits(user)
    if credits <= 0:
        return False, "У вас закончились чертежи."
    try:
        from models import db, FigureCreditTransaction
        user.figure_credits = credits - 1
        user.figures_built = (getattr(user, "figures_built", 0) or 0) + 1
        txn = FigureCreditTransaction(
            user_id=user.id,
            amount=-1,
            reason="spend",
        )
        db.session.add(txn)
        db.session.commit()
        return True, ""
    except Exception as e:
        logger.error("[figures] failed to spend credit: %s", e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return False, "Ошибка при списании."


def _refund_credit(user) -> None:
    """Refund 1 credit to user (called on failure)."""
    if user is None:
        return
    try:
        from models import db, FigureCreditTransaction
        current = _get_figure_credits(user)
        user.figure_credits = current + 1
        txn = FigureCreditTransaction(
            user_id=user.id,
            amount=1,
            reason="refund",
        )
        db.session.add(txn)
        db.session.commit()
    except Exception as e:
        logger.error("[figures] refund failed: %s", e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


def _credit_balance_response(user) -> dict:
    """Return credit balance for client."""
    if user is None or not getattr(user, "is_authenticated", False):
        return {"credits": 0, "authenticated": False}
    return {
        "credits": _get_figure_credits(user),
        "authenticated": True,
        "figures_built": getattr(user, "figures_built", 0) or 0,
    }


# ── Routes ──────────────────────────────────────────────────────────────

@figures_bp.route("/figures", methods=["GET"])
def figures_page():
    """Render the figure generation page."""
    balance = _credit_balance_response(current_user)
    return render_template(
        "figures.html",
        credits=balance.get("credits", 0),
        figures_built=balance.get("figures_built", 0),
        max_problem_length=MAX_PROBLEM_LENGTH,
        max_solution_length=MAX_SOLUTION_LENGTH,
    )


@figures_bp.route("/pricing", methods=["GET"])
def pricing_page():
    """Figure credit packages page."""
    balance = _credit_balance_response(current_user)
    return render_template(
        "pricing.html",
        packages=FIGURE_PACKAGES,
        credits=balance.get("credits", 0),
    )


@figures_bp.route("/payment-stub", methods=["GET"])
def payment_stub_page():
    """Payment stub — payment coming soon."""
    package_id = request.args.get("package", "p10")
    pkg = next((p for p in FIGURE_PACKAGES if p["id"] == package_id), FIGURE_PACKAGES[0])
    return render_template("payment_stub.html", package=pkg)


@figures_bp.route("/api/figures/balance", methods=["GET"])
def api_figures_balance():
    """Return current credit balance."""
    return jsonify(_credit_balance_response(current_user))


@figures_bp.route("/api/figures/transactions", methods=["GET"])
@login_required
def api_figure_transactions():
    """Return transaction journal for the current user."""
    try:
        from models import FigureCreditTransaction
        txns = (
            FigureCreditTransaction.query
            .filter_by(user_id=current_user.id)
            .order_by(FigureCreditTransaction.created_at.desc())
            .limit(50)
            .all()
        )
        return jsonify({
            "transactions": [
                {
                    "id": t.id,
                    "amount": t.amount,
                    "reason": t.reason,
                    "reference": t.reference,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in txns
            ]
        })
    except Exception as e:
        logger.error("[figures] failed to fetch transactions: %s", e)
        return jsonify({"transactions": []})


@figures_bp.route("/api/figures/subscribe-email", methods=["POST"])
def api_subscribe_email():
    """Save email from payment stub 'notify me when ready' form."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    if not email or "@" not in email or len(email) > 200:
        return jsonify({"error": "Некорректный email"}), 400
    try:
        from models import db, FigureEmailSubscription
        sub = FigureEmailSubscription(email=email)
        db.session.add(sub)
        db.session.commit()
        return jsonify({"ok": True, "message": "Спасибо! Мы сообщим вам, когда оплата заработает."})
    except Exception as e:
        logger.error("[figures] email subscription failed: %s", e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": "Ошибка сохранения. Попробуйте позже."}), 500


@figures_bp.route("/api/figures/build", methods=["POST"])
@login_required
def api_figures_build():
    """D5: Create a background figure generation job. Returns job_id immediately.

    Request JSON: {"problem": "...", "solution": "..."}
    Response: {"job_id": 42, "status": "queued"}
    """
    # ── Rate limit check ──
    allowed, retry_after = _rate_check()
    if not allowed:
        return jsonify({
            "error": f"Слишком много запросов. Попробуйте через {retry_after} сек.",
            "retry_after": retry_after,
        }), 429

    # ── Parse request ──
    data = request.get_json(silent=True) or {}
    problem = (data.get("problem") or "").strip()
    solution = (data.get("solution") or "").strip()

    if not problem:
        return jsonify({"error": "Введите условие задачи."}), 400
    if len(problem) > MAX_PROBLEM_LENGTH:
        return jsonify({
            "error": f"Условие слишком длинное (максимум {MAX_PROBLEM_LENGTH} символов)."
        }), 400
    if len(solution) > MAX_SOLUTION_LENGTH:
        return jsonify({
            "error": f"Решение слишком длинное (максимум {MAX_SOLUTION_LENGTH} символов)."
        }), 400

    # ── Check credits exist (but don't spend yet — spend only on done) ──
    credits = _get_figure_credits(current_user)
    if credits <= 0:
        return jsonify({
            "error": "У вас закончились чертежи.",
            "credits": credits,
        }), 402

    # ── Check API key ──
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return jsonify({
            "error": "Ключ API не настроен. Генерация чертежей временно недоступна."
        }), 503

    # ── Create job record ──
    try:
        from models import db, FigureJob
        from datetime import datetime as _dt
        job = FigureJob(
            user_id=current_user.id,
            problem=problem,
            solution=solution if solution else None,
            status="queued",
            step_label="читаю условие",
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id
    except Exception as e:
        logger.error("[figures] failed to create FigureJob: %s", e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return jsonify({"error": "Не удалось создать задание. Попробуйте позже."}), 500

    # ── Spawn background worker thread ──
    thread = threading.Thread(
        target=_run_figure_job,
        args=(job_id,),
        daemon=True,
    )
    thread.start()
    logger.info("[figures] spawned build thread for job_id=%d", job_id)

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "credits": credits,
    })


@figures_bp.route("/api/figures/status/<int:job_id>", methods=["GET"])
@login_required
def api_figures_status(job_id):
    """D5: Poll job status. Returns svg when done."""
    try:
        from models import FigureJob
        job = FigureJob.query.filter_by(
            id=job_id, user_id=current_user.id,
        ).first()
        if not job:
            return jsonify({"error": "Задание не найдено."}), 404

        resp = {
            "job_id": job.id,
            "status": job.status,
            "step_label": job.step_label,
        }
        if job.status == "done":
            resp["svg"] = job.svg_result or ""
            resp["credits_remaining"] = _get_figure_credits(current_user)
            resp["figures_built"] = getattr(current_user, "figures_built", 0) or 0
        elif job.status == "failed":
            resp["error"] = job.error_message or "Построение не удалось."
            resp["credits"] = _get_figure_credits(current_user)

        return jsonify(resp)
    except Exception as e:
        logger.error("[figures] status error for job %d: %s", job_id, e)
        return jsonify({"error": "Ошибка при проверке статуса."}), 500


# ── Background worker ──────────────────────────────────────────────────

def _run_figure_job(job_id: int):
    """Run the full reasoner + engine pipeline in a background thread.

    Updates FigureJob status: queued → thinking → drawing → done | failed.
    Credit is spent only on transition to done.
    """
    from models import db, FigureJob, FigureGeneration, User
    from flask import current_app as _app

    # Use a fresh app context for the thread
    app = _app._get_current_object()
    with app.app_context():
        job = FigureJob.query.get(job_id)
        if not job or job.status != "queued":
            return

        user = None
        try:
            user = User.query.get(job.user_id)
        except Exception:
            pass

        user_message = f"Условие задачи:\n{job.problem}"
        if job.solution:
            user_message += f"\n\nРешение:\n{job.solution}"

        # ── Step 1: Thinking (reasoner) ──
        job.status = "thinking"
        job.step_label = "строю описание"
        job.updated_at = datetime.utcnow()
        db.session.commit()

        if not _REASONER_SYSTEM_PROMPT:
            job.status = "failed"
            job.error_message = "Системный промпт ризонера не загружен."
            job.step_label = None
            job.updated_at = datetime.utcnow()
            db.session.commit()
            return

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
                last_resp = openrouter.chat(
                    model=REASONER_MODEL,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=4096,
                )
            except OpenRouterError as e:
                logger.error("[figures] reasoner API error (attempt %d): %s", attempt, e)
                if attempt < MAX_RETRIES:
                    continue
                job.status = "failed"
                job.error_message = "Сервис генерации временно недоступен."
                job.step_label = None
                job.updated_at = datetime.utcnow()
                db.session.commit()
                return
            except Exception as e:
                logger.error("[figures] unexpected reasoner error (attempt %d): %s", attempt, e)
                if attempt < MAX_RETRIES:
                    continue
                job.status = "failed"
                job.error_message = "Ошибка при обращении к сервису генерации."
                job.step_label = None
                job.updated_at = datetime.utcnow()
                db.session.commit()
                return

            content = (last_resp.get("content") or "").strip()
            json_str = _extract_json(content)

            if not json_str:
                last_errors = ["Ответ модели не содержит JSON-объекта."]
                if attempt < MAX_RETRIES:
                    continue
                job.status = "failed"
                job.error_message = "Не удалось получить описание чертежа от модели."
                job.step_label = None
                job.updated_at = datetime.utcnow()
                db.session.commit()
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
                job.error_message = "Модель не смогла создать корректное описание."
                job.step_label = None
                job.updated_at = datetime.utcnow()
                db.session.commit()
                return

        if final_json is None:
            job.status = "failed"
            job.error_message = "Не удалось построить описание чертежа."
            job.step_label = None
            job.updated_at = datetime.utcnow()
            db.session.commit()
            return

        # ── Step 2: Drawing (SVG engine) ──
        job.status = "drawing"
        job.step_label = "рисую"
        job.updated_at = datetime.utcnow()
        db.session.commit()

        try:
            from geometric_engine.engine import GeometricEngine
            figure_data = json.loads(final_json)
            engine = GeometricEngine()
            svg, ctx, attempts_used, violations = engine.build_with_retry(figure_data)

            if not svg and violations:
                job.status = "failed"
                job.error_message = "Геометрические ограничения не выполнены."
                job.step_label = None
                job.updated_at = datetime.utcnow()
                db.session.commit()
                return

            if not svg:
                job.status = "failed"
                job.error_message = "Не удалось построить SVG."
                job.step_label = None
                job.updated_at = datetime.utcnow()
                db.session.commit()
                return

            # ── Step 3: Done — spend credit ──
            if not job.credit_spent:
                ok, msg = _spend_credit_in_job(job_id)
                if ok:
                    job.credit_spent = True

            job.status = "done"
            job.svg_result = svg
            job.json_description = final_json
            job.model_used = REASONER_MODEL
            job.cost_usd = float(last_resp.get("cost_usd", 0.0)) if last_resp else 0.0
            job.step_label = None
            job.updated_at = datetime.utcnow()
            db.session.commit()

            # Log to FigureGeneration
            _log_figure_generation(
                problem=job.problem,
                solution=job.solution or "",
                status="success",
                json_description=final_json,
                model=REASONER_MODEL,
                cost_usd=job.cost_usd,
            )

        except json.JSONDecodeError as e:
            job.status = "failed"
            job.error_message = f"Ошибка разбора JSON: {e}"
            job.step_label = None
            job.updated_at = datetime.utcnow()
            db.session.commit()
        except ImportError:
            job.status = "failed"
            job.error_message = "Движок построения недоступен."
            job.step_label = None
            job.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            logger.error("[figures] build error in job %d: %s", job_id, e)
            job.status = "failed"
            job.error_message = "Ошибка при построении чертежа."
            job.step_label = None
            job.updated_at = datetime.utcnow()
            db.session.commit()


def _spend_credit_in_job(job_id: int) -> tuple[bool, str]:
    """Spend 1 credit for a background job. Returns (success, message)."""
    try:
        from models import db, FigureJob, FigureCreditTransaction, User
        job = FigureJob.query.get(job_id)
        if not job:
            return False, "Job not found"
        user = User.query.get(job.user_id)
        if not user:
            return False, "User not found"
        credits = _get_figure_credits(user)
        if credits <= 0:
            return False, "No credits"
        user.figure_credits = credits - 1
        user.figures_built = (getattr(user, "figures_built", 0) or 0) + 1
        txn = FigureCreditTransaction(
            user_id=user.id,
            amount=-1,
            reason="spend_bg",
            reference=f"job:{job_id}",
        )
        db.session.add(txn)
        db.session.commit()
        return True, ""
    except Exception as e:
        logger.error("[figures] _spend_credit_in_job failed for %d: %s", job_id, e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return False, str(e)


# ── Logging helpers ─────────────────────────────────────────────────────

def _log_figure_generation(
    *,
    problem: str,
    solution: str,
    status: str,
    json_description: str = "",
    model: str = "",
    cost_usd: float = 0.0,
) -> None:
    """Best-effort write to FigureGeneration log table."""
    try:
        import hashlib
        from models import db, FigureGeneration
        sha = hashlib.sha256(problem.encode("utf-8")).hexdigest()
        uid = None
        try:
            if current_user is not None and getattr(current_user, "is_authenticated", False):
                uid = getattr(current_user, "id", None)
        except Exception:
            pass

        row = FigureGeneration(
            user_id=uid,
            problem_sha256=sha,
            problem=problem[:5000],
            solution=solution[:8000] if solution else None,
            status=status,
            json_description=json_description[:20000] if json_description else None,
            model=model,
            cost_usd=cost_usd,
        )
        db.session.add(row)
        db.session.commit()
    except Exception as e:
        logger.warning("[figures] failed to log FigureGeneration: %s", e)

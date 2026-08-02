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
import time
from collections import defaultdict
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
REASONER_MODEL = os.environ.get("FIGURE_REASONER_MODEL", "deepseek/deepseek-chat").strip()
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


@figures_bp.route("/api/figures/generate", methods=["POST"])
@login_required
def api_figures_generate():
    """Generate a geometric figure from problem text.

    Request JSON: {"problem": "...", "solution": "..."}
    Response: {"svg": "<svg>...</svg>", "credits_remaining": N}
    """
    # ── Rate limit check ──
    allowed, retry_after = _rate_check()
    if not allowed:
        return jsonify({
            "error": f"Слишком много запросов. Попробуйте через {retry_after} сек.",
            "retry_after": retry_after,
        }), 429

    # ── Concurrent guard ──
    ok, msg = _concurrent_guard()
    if not ok:
        return jsonify({"error": msg}), 429

    try:
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

        # ── Check credits ──
        ok, msg = _spend_credit(current_user)
        if not ok:
            return jsonify({
                "error": msg,
                "credits": _get_figure_credits(current_user)
            }), 402

        credits_remaining = _get_figure_credits(current_user)

        # ── Build user message ──
        user_message = f"Условие задачи:\n{problem}"
        if solution:
            user_message += f"\n\nРешение:\n{solution}"

        # ── Check reasoner prompt ──
        if not _REASONER_SYSTEM_PROMPT:
            _refund_credit(current_user)
            return jsonify({
                "error": "Системный промпт ризонера не загружен. Обратитесь к администратору."
            }), 500

        # ── Check API key ──
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            _refund_credit(current_user)
            return jsonify({
                "error": "Ключ API не настроен. Генерация чертежей временно недоступна."
            }), 503

        # ── Reasoner loop (up to 1 + MAX_RETRIES) ──
        svg_result = None
        last_errors = []
        final_json = None
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
                _refund_credit(current_user)
                return jsonify({
                    "error": "Сервис генерации временно недоступен. Попробуйте позже."
                }), 503
            except Exception as e:
                logger.error("[figures] unexpected reasoner error (attempt %d): %s", attempt, e)
                if attempt < MAX_RETRIES:
                    continue
                _refund_credit(current_user)
                return jsonify({
                    "error": "Ошибка при обращении к сервису генерации."
                }), 503

            content = (last_resp.get("content") or "").strip()
            json_str = _extract_json(content)

            if not json_str:
                last_errors = ["Ответ модели не содержит JSON-объекта."]
                if attempt < MAX_RETRIES:
                    continue
                _refund_credit(current_user)
                return jsonify({
                    "error": (
                        "Не удалось получить описание чертежа от модели. "
                        "Попробуйте переформулировать условие."
                    )
                }), 422

            # ── Validate ──
            validation = validate_figure_json(json_str)
            if validation.get("valid"):
                final_json = json_str
                break
            else:
                last_errors = validation.get("errors", ["Неизвестная ошибка валидации"])
                if attempt < MAX_RETRIES:
                    continue
                _refund_credit(current_user)
                return jsonify({
                    "error": (
                        "Чертёж построить не удалось. "
                        "Модель не смогла создать корректное описание после нескольких попыток. "
                        "Попробуйте упростить условие или переформулировать его."
                    ),
                    "validation_errors": last_errors[:5],
                }), 422

        # ── Build SVG ──
        if final_json is None:
            _refund_credit(current_user)
            return jsonify({"error": "Не удалось построить чертёж."}), 500

        try:
            from geometric_engine.engine import GeometricEngine
            figure_data = json.loads(final_json)
            engine = GeometricEngine()
            svg, ctx, attempts_used, violations = engine.build_with_retry(figure_data)

            if not svg and violations:
                _refund_credit(current_user)
                return jsonify({
                    "error": (
                        "Чертёж построить не удалось — геометрические ограничения не выполнены. "
                        "Попробуйте переформулировать условие."
                    ),
                    "violations": violations[:5],
                }), 422

            if not svg:
                _refund_credit(current_user)
                return jsonify({"error": "Не удалось построить SVG. Попробуйте позже."}), 500

            # ── Success: log to DB ──
            _log_figure_generation(
                problem=problem,
                solution=solution,
                status="success",
                json_description=final_json,
                model=REASONER_MODEL,
                cost_usd=float(last_resp.get("cost_usd", 0.0)) if last_resp else 0.0,
            )

            return jsonify({
                "svg": svg,
                "credits_remaining": credits_remaining,
                "figures_built": getattr(current_user, "figures_built", 0) or 0,
            })

        except json.JSONDecodeError as e:
            _refund_credit(current_user)
            return jsonify({"error": f"Ошибка разбора JSON описания: {e}"}), 422
        except ImportError as e:
            _refund_credit(current_user)
            logger.error("[figures] geometric_engine import failed: %s", e)
            return jsonify({"error": "Движок построения чертежей недоступен."}), 500
        except Exception as e:
            _refund_credit(current_user)
            logger.error("[figures] build error: %s", e)
            return jsonify({"error": "Ошибка при построении чертежа."}), 500

    finally:
        _release_concurrent_guard()


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

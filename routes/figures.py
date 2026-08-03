# -*- coding: utf-8 -*-
# Blueprint "/figures" — figure vitrine (D4 showcase).
#
# This module contains ONLY the vitrine routes:
#   - /figures (showcase page)
#   - /pricing (credit packages)
#   - /payment-stub (payment placeholder)
#   - API: balance, transactions, email subscription
#
# The generation pipeline has been moved to routes/figures_generator.py
# at /figures/generate/* to avoid route conflicts with /figures and /drawing.

from __future__ import annotations

import logging

from flask import (
    Blueprint,
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


logger = logging.getLogger(__name__)

figures_bp = Blueprint("figures", __name__)

# ── Payment packages (single source of truth — change here, not in code) ──

FIGURE_PACKAGES = [
    {"id": "p10", "amount": 10, "price_rub": 99, "label": "10 чертежей", "featured": False},
    {"id": "p30", "amount": 30, "price_rub": 249, "label": "30 чертежей", "featured": True},
    {"id": "p100", "amount": 100, "price_rub": 599, "label": "100 чертежей", "featured": False},
]

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
    """Render the figure vitrine page."""
    balance = _credit_balance_response(current_user)
    return render_template(
        "figures.html",
        credits=balance.get("credits", 0),
        figures_built=balance.get("figures_built", 0),
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

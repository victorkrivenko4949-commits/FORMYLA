# -*- coding: utf-8 -*-
"""
routes/yookassa_pay.py — YOOKASSA_DIAMOND_V1 (22.10.2026).

Интеграция ЮKassa для покупки значка алмаза (💎) после ника за 10 ₽.
Доступна ТОЛЬКО для администраторов: victor и lavrik.
Для всех остальных пользователей сайт остаётся полностью бесплатным без кнопок оплаты.

Возможности:
  * POST /payments/yookassa/buy-diamond   — создание платежа 10.00 ₽ в ЮKassa (redirect)
  * GET  /payments/yookassa/return        — возврат после оплаты, проверка статуса в API ЮKassa и выдача 💎
  * POST /api/payments/yookassa/webhook   — приём HTTP-уведомлений payment.succeeded от ЮKassa
  * POST /webhooks/yookassa               — алиас вебхука
  * POST /payments/yookassa/save-config   — сохранение Shop ID и Секретного ключа из профиля админа
  * POST /payments/yookassa/toggle-diamond — ручное переключение/сброс 💎 для повторных тестов
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime

import requests
from flask import Blueprint, abort, flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import text

logger = logging.getLogger(__name__)

yookassa_pay_bp = Blueprint("yookassa_pay", __name__)

DIAMOND_PRICE_RUB = "10.00"
YOOKASSA_API_BASE = "https://api.yookassa.ru/v3"

_TABLES_ENSURED = False


def is_diamond_admin(user) -> bool:
    """Настройка ключей ЮKassa доступна ТОЛЬКО админам victor и lavrik."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_guest", False):
        return False
    if getattr(user, "id", None) == 1:
        return True
    email = (getattr(user, "email", None) or "").strip().lower()
    if email in ("kr1venkovictor@yandex.ru", "victor.krivenko.4949@gmail.com"):
        return True
    nick = (getattr(user, "nickname", None) or "").strip().lower()
    return nick in ("victor", "victorkrivenko", "lavrik")


def is_diamond_buyer(user) -> bool:
    """Покупка 💎 видна админам (victor, lavrik) и тестовому аккаунту проверки ЮKassa (yookassa@formyla.net)."""
    if is_diamond_admin(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    email = (getattr(user, "email", None) or "").strip().lower()
    return email == "yookassa@formyla.net"


def _ensure_tables() -> None:
    global _TABLES_ENSURED
    if _TABLES_ENSURED:
        return
    try:
        from models import db

        engine_name = db.engine.dialect.name
        is_pg = engine_name == "postgresql"

        # 1. Таблица настроек ЮKassa (позволяет задать shop_id и secret_key прямо из профиля админа)
        db.session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS yookassa_config (
                    key VARCHAR(64) PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        # 2. Таблица платежей ЮKassa
        id_col = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
        db.session.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS yookassa_payments (
                    id {id_col},
                    order_id VARCHAR(64) UNIQUE NOT NULL,
                    payment_id VARCHAR(128),
                    user_id INTEGER NOT NULL,
                    item_code VARCHAR(64) NOT NULL DEFAULT 'diamond_badge',
                    amount_rub NUMERIC(10, 2) NOT NULL DEFAULT 10.00,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    confirmation_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    paid_at TIMESTAMP
                )
                """
            )
        )

        # 3. Колонка has_diamond в users (на случай если автомиграция при старте ещё не прошла)
        bool_default = "BOOLEAN NOT NULL DEFAULT FALSE" if is_pg else "BOOLEAN NOT NULL DEFAULT 0"
        try:
            db.session.execute(text(f"ALTER TABLE users ADD COLUMN has_diamond {bool_default}"))
        except Exception:
            db.session.rollback()

        db.session.commit()
        _TABLES_ENSURED = True
    except Exception as e:
        try:
            from models import db

            db.session.rollback()
        except Exception:
            pass
        logger.warning("[yookassa_pay] _ensure_tables warning: %r", e)


def get_yookassa_config() -> dict:
    """Возвращает {'shop_id': str, 'secret_key': str, 'send_receipt': bool, 'source': str}."""
    _ensure_tables()
    db_vals = {}
    try:
        from models import db

        rows = db.session.execute(text("SELECT key, value FROM yookassa_config")).fetchall()
        for k, v in rows:
            if v is not None and str(v).strip():
                db_vals[str(k)] = str(v).strip()
    except Exception:
        try:
            from models import db

            db.session.rollback()
        except Exception:
            pass

    shop_id = db_vals.get("shop_id") or (os.environ.get("YOOKASSA_SHOP_ID") or "").strip()
    secret_key = db_vals.get("secret_key") or (os.environ.get("YOOKASSA_SECRET_KEY") or "").strip()
    send_receipt_raw = db_vals.get("send_receipt") or (os.environ.get("YOOKASSA_SEND_RECEIPT") or "0").strip()
    send_receipt = send_receipt_raw in ("1", "true", "True", "yes")

    source = "db" if ("shop_id" in db_vals and "secret_key" in db_vals) else ("env" if (shop_id and secret_key) else "none")
    is_test = secret_key.startswith("test_") if secret_key else False
    return {
        "shop_id": shop_id,
        "secret_key": secret_key,
        "send_receipt": send_receipt,
        "configured": bool(shop_id and secret_key),
        "is_test": is_test,
        "source": source,
    }


def get_recent_payments(user_id: int, limit: int = 5) -> list[dict]:
    _ensure_tables()
    try:
        from models import db

        rows = db.session.execute(
            text(
                """
                SELECT order_id, payment_id, amount_rub, status, created_at, paid_at
                FROM yookassa_payments
                WHERE user_id = :uid
                ORDER BY id DESC
                LIMIT :lim
                """
            ),
            {"uid": int(user_id), "lim": int(limit)},
        ).fetchall()
        result = []
        for r in rows:
            result.append(
                {
                    "order_id": r[0],
                    "payment_id": r[1] or "—",
                    "amount_rub": float(r[2] or 10.0),
                    "status": r[3] or "pending",
                    "created_at": str(r[4])[:16] if r[4] else "",
                    "paid_at": str(r[5])[:16] if r[5] else "",
                }
            )
        return result
    except Exception:
        try:
            from models import db

            db.session.rollback()
        except Exception:
            pass
        return []


def _activate_diamond_for_user(user_id: int, payment_id: str | None = None, order_id: str | None = None) -> bool:
    """Выдаёт значок 💎 пользователю и логирует событие payment_success (идемпотентно)."""
    _ensure_tables()
    try:
        from models import User, db

        user = User.query.get(int(user_id))
        if not user:
            return False
        user.has_diamond = True
        now = datetime.utcnow()
        if order_id:
            db.session.execute(
                text(
                    """
                    UPDATE yookassa_payments
                    SET status = 'succeeded', paid_at = COALESCE(paid_at, :now),
                        payment_id = COALESCE(:pid, payment_id)
                    WHERE order_id = :oid
                    """
                ),
                {"now": now, "pid": payment_id, "oid": order_id},
            )
        elif payment_id:
            db.session.execute(
                text(
                    """
                    UPDATE yookassa_payments
                    SET status = 'succeeded', paid_at = COALESCE(paid_at, :now)
                    WHERE payment_id = :pid
                    """
                ),
                {"now": now, "pid": payment_id},
            )
        db.session.commit()

        # Логируем в аналитику воронки (отображается в /admin/stats -> Платежи)
        try:
            from services.funnel import payment_success

            payment_success(
                user_id=int(user_id),
                plan_code="diamond_badge",
                amount=10.0,
                payment_id=payment_id or order_id,
                props={"item": "diamond_badge", "nickname": user.nickname},
            )
        except Exception as fe:
            logger.warning("[yookassa_pay] funnel.payment_success warning: %r", fe)

        return True
    except Exception as e:
        try:
            from models import db

            db.session.rollback()
        except Exception:
            pass
        logger.exception("[yookassa_pay] _activate_diamond_for_user failed: %r", e)
        return False


@yookassa_pay_bp.route("/payments/yookassa/save-config", methods=["POST"])
@login_required
def save_config():
    if not is_diamond_admin(current_user):
        abort(403)
    _ensure_tables()
    shop_id = (request.form.get("shop_id") or "").strip()
    secret_key = (request.form.get("secret_key") or "").strip()
    send_receipt = "1" if request.form.get("send_receipt") in ("1", "on", "true") else "0"

    if not shop_id or not secret_key:
        flash("Укажите и Shop ID, и Секретный ключ ЮKassa.", "error")
        return redirect(url_for("profile") + "#yookassa-card")

    from models import db

    now = datetime.utcnow()
    for k, v in (("shop_id", shop_id), ("secret_key", secret_key), ("send_receipt", send_receipt)):
        existing = db.session.execute(
            text("SELECT key FROM yookassa_config WHERE key = :k"), {"k": k}
        ).fetchone()
        if existing:
            db.session.execute(
                text("UPDATE yookassa_config SET value = :v, updated_at = :u WHERE key = :k"),
                {"v": v, "u": now, "k": k},
            )
        else:
            db.session.execute(
                text("INSERT INTO yookassa_config (key, value, updated_at) VALUES (:k, :v, :u)"),
                {"k": k, "v": v, "u": now},
            )
    db.session.commit()

    # Проверим ключи через GET /v3/me
    try:
        resp = requests.get(
            f"{YOOKASSA_API_BASE}/me",
            auth=(shop_id, secret_key),
            timeout=10,
        )
        if resp.status_code == 200:
            me_data = resp.json() or {}
            mode = "Тестовый магазин" if me_data.get("test") else "Боевой магазин"
            flash(f"✅ Ключи ЮKassa успешно проверены и сохранены ({mode}, Shop ID: {shop_id}). Теперь можно оплачивать!", "success")
        else:
            flash(
                f"⚠️ Ключи сохранены, но ЮKassa вернула код {resp.status_code}. Проверьте правильность Shop ID и Секретного ключа.",
                "warning",
            )
    except Exception as e:
        flash(f"✅ Ключи сохранены (проверка соединения: {e}).", "info")

    return redirect(url_for("profile") + "#yookassa-card")


@yookassa_pay_bp.route("/payments/yookassa/buy-diamond", methods=["POST"])
@login_required
def buy_diamond():
    if not is_diamond_buyer(current_user):
        abort(403)
    _ensure_tables()
    cfg = get_yookassa_config()
    if not cfg["configured"]:
        flash("Сначала укажите Shop ID и Секретный ключ ЮKassa в блоке настройки ниже.", "warning")
        return redirect(url_for("profile") + "#yookassa-card")

    order_id = uuid.uuid4().hex
    return_url = url_for("yookassa_pay.payment_return", order_id=order_id, _external=True)
    nick_label = current_user.nickname or current_user.display_name or f"id={current_user.id}"

    payload = {
        "amount": {
            "value": DIAMOND_PRICE_RUB,
            "currency": "RUB",
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "description": f"Значок алмаза 💎 после ника (@{nick_label}) на FORMYLA",
        "metadata": {
            "order_id": order_id,
            "user_id": str(current_user.id),
            "item": "diamond_badge",
        },
    }

    if cfg.get("send_receipt"):
        customer_email = current_user.email if (current_user.email and "@" in current_user.email) else "kr1venkovictor@yandex.ru"
        payload["receipt"] = {
            "customer": {"email": customer_email},
            "items": [
                {
                    "description": "Значок алмаза после ника на FORMYLA",
                    "quantity": "1.00",
                    "amount": {"value": DIAMOND_PRICE_RUB, "currency": "RUB"},
                    "vat_code": 1,
                    "payment_mode": "full_payment",
                    "payment_subject": "service",
                }
            ],
        }

    try:
        resp = requests.post(
            f"{YOOKASSA_API_BASE}/payments",
            auth=(cfg["shop_id"], cfg["secret_key"]),
            headers={
                "Idempotence-Key": order_id,
                "Content-Type": "application/json",
            },
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=15,
        )
        data = resp.json() if resp.content else {}
    except Exception as e:
        logger.exception("[yookassa_pay] request to YooKassa failed: %r", e)
        flash(f"Ошибка соединения с ЮKassa: {e}", "error")
        return redirect(url_for("profile") + "#yookassa-card")

    if resp.status_code not in (200, 201):
        err_desc = data.get("description") or data.get("code") or resp.text[:200]
        flash(f"ЮKassa отклонила создание платежа ({resp.status_code}): {err_desc}", "error")
        return redirect(url_for("profile") + "#yookassa-card")

    payment_id = data.get("id")
    status = data.get("status", "pending")
    confirmation_url = (data.get("confirmation") or {}).get("confirmation_url")

    try:
        from models import db

        db.session.execute(
            text(
                """
                INSERT INTO yookassa_payments (order_id, payment_id, user_id, item_code, amount_rub, status, confirmation_url, created_at)
                VALUES (:oid, :pid, :uid, 'diamond_badge', 10.00, :st, :curl, :now)
                """
            ),
            {
                "oid": order_id,
                "pid": payment_id,
                "uid": current_user.id,
                "st": status,
                "curl": confirmation_url,
                "now": datetime.utcnow(),
            },
        )
        db.session.commit()
    except Exception as e:
        logger.warning("[yookassa_pay] failed to insert payment row: %r", e)
        try:
            from models import db

            db.session.rollback()
        except Exception:
            pass

    if not confirmation_url:
        flash("ЮKassa не вернула ссылку на оплату.", "error")
        return redirect(url_for("profile") + "#yookassa-card")

    return redirect(confirmation_url, code=302)


@yookassa_pay_bp.route("/payments/yookassa/return", methods=["GET"])
@login_required
def payment_return():
    if not is_diamond_buyer(current_user):
        abort(403)
    _ensure_tables()
    order_id = (request.args.get("order_id") or "").strip()

    from models import db

    row = None
    if order_id:
        row = db.session.execute(
            text("SELECT order_id, payment_id, user_id, status FROM yookassa_payments WHERE order_id = :oid"),
            {"oid": order_id},
        ).fetchone()
    if not row:
        row = db.session.execute(
            text(
                "SELECT order_id, payment_id, user_id, status FROM yookassa_payments WHERE user_id = :uid ORDER BY id DESC LIMIT 1"
            ),
            {"uid": current_user.id},
        ).fetchone()

    if not row:
        flash("Платёж не найден.", "warning")
        return redirect(url_for("profile") + "#yookassa-card")

    ord_id, payment_id, user_id, local_status = row[0], row[1], row[2], row[3]
    if local_status == "succeeded":
        _activate_diamond_for_user(user_id=user_id, payment_id=payment_id, order_id=ord_id)
        flash("💎 Оплата 10 ₽ прошла успешно! Значок алмаза после вашего ника активирован.", "success")
        return redirect(url_for("profile") + "#yookassa-card")

    cfg = get_yookassa_config()
    if cfg["configured"] and payment_id:
        try:
            resp = requests.get(
                f"{YOOKASSA_API_BASE}/payments/{payment_id}",
                auth=(cfg["shop_id"], cfg["secret_key"]),
                timeout=12,
            )
            if resp.status_code == 200:
                pdata = resp.json() or {}
                remote_status = pdata.get("status")
                if remote_status == "succeeded" or pdata.get("paid") is True:
                    _activate_diamond_for_user(user_id=user_id, payment_id=payment_id, order_id=ord_id)
                    flash("💎 Оплата 10 ₽ прошла успешно! Значок алмаза после вашего ника активирован.", "success")
                    return redirect(url_for("profile") + "#yookassa-card")
                elif remote_status == "canceled":
                    db.session.execute(
                        text("UPDATE yookassa_payments SET status = 'canceled' WHERE order_id = :oid"),
                        {"oid": ord_id},
                    )
                    db.session.commit()
                    flash("Платёж был отменён.", "warning")
                    return redirect(url_for("profile") + "#yookassa-card")
        except Exception as e:
            logger.warning("[yookassa_pay] return check failed: %r", e)

    flash("⏳ Платёж проверяется ЮKassa. Если вы уже оплатили, обновите страницу через несколько секунд.", "info")
    return redirect(url_for("profile") + "#yookassa-card")


@yookassa_pay_bp.route("/api/payments/yookassa/webhook", methods=["POST"])
@yookassa_pay_bp.route("/webhooks/yookassa", methods=["POST"])
def yookassa_webhook():
    """HTTP-уведомление от ЮKassa (payment.succeeded / payment.canceled)."""
    _ensure_tables()
    payload = request.get_json(silent=True) or {}
    event = payload.get("event") or ""
    obj = payload.get("object") or {}
    payment_id = obj.get("id")
    metadata = obj.get("metadata") or {}
    order_id = metadata.get("order_id")
    user_id_raw = metadata.get("user_id")

    if not payment_id:
        return jsonify({"ok": False, "error": "missing payment_id"}), 400

    # Обязательно перепроверяем статус платежа напрямую в API ЮKassa (защита от подделки вебхука)
    cfg = get_yookassa_config()
    verified_status = obj.get("status")
    verified_paid = bool(obj.get("paid"))
    if cfg["configured"]:
        try:
            resp = requests.get(
                f"{YOOKASSA_API_BASE}/payments/{payment_id}",
                auth=(cfg["shop_id"], cfg["secret_key"]),
                timeout=10,
            )
            if resp.status_code == 200:
                remote = resp.json() or {}
                verified_status = remote.get("status")
                verified_paid = bool(remote.get("paid"))
                remote_meta = remote.get("metadata") or {}
                order_id = order_id or remote_meta.get("order_id")
                user_id_raw = user_id_raw or remote_meta.get("user_id")
        except Exception as e:
            logger.warning("[yookassa_pay] webhook verification warning: %r", e)

    from models import db

    if not user_id_raw and (order_id or payment_id):
        row = db.session.execute(
            text(
                "SELECT user_id, order_id FROM yookassa_payments WHERE order_id = :oid OR payment_id = :pid LIMIT 1"
            ),
            {"oid": order_id or "", "pid": payment_id},
        ).fetchone()
        if row:
            user_id_raw = row[0]
            order_id = order_id or row[1]

    if (event == "payment.succeeded" or verified_status == "succeeded") and verified_paid and user_id_raw:
        # PREMIUM_PAY_V1: по item_code решаем, что активировать —
        # premium_intense/premium_calm (30 дней Premium) или значок-алмаз.
        item_code = "diamond_badge"
        try:
            _row = db.session.execute(
                text("SELECT item_code FROM yookassa_payments WHERE payment_id = :pid OR order_id = :oid LIMIT 1"),
                {"pid": payment_id, "oid": order_id or ""},
            ).fetchone()
            if _row and _row[0]:
                item_code = str(_row[0])
        except Exception:
            pass
        if item_code.startswith("premium_"):
            from routes.premium_pay import activate_premium_for_payment
            activate_premium_for_payment(
                user_id=int(user_id_raw), plan=item_code,
                payment_id=payment_id, order_id=order_id)
        else:
            _activate_diamond_for_user(user_id=int(user_id_raw), payment_id=payment_id, order_id=order_id)
        return jsonify({"ok": True, "status": "succeeded"}), 200

    if event == "payment.canceled" or verified_status == "canceled":
        try:
            db.session.execute(
                text("UPDATE yookassa_payments SET status = 'canceled' WHERE payment_id = :pid OR order_id = :oid"),
                {"pid": payment_id, "oid": order_id or ""},
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({"ok": True, "status": "canceled"}), 200

    return jsonify({"ok": True, "status": verified_status or "ignored"}), 200


@yookassa_pay_bp.route("/payments/yookassa/toggle-diamond", methods=["POST"])
@login_required
def toggle_diamond():
    """Позволяет админу (victor / lavrik) сбросить или включить значок 💎 вручную для повторного теста."""
    if not is_diamond_admin(current_user):
        abort(403)
    _ensure_tables()
    from models import db

    action = (request.form.get("action") or "toggle").strip()
    if action == "off":
        current_user.has_diamond = False
        flash("Значок 💎 снят — можно снова протестировать покупку с нуля.", "info")
    elif action == "on":
        current_user.has_diamond = True
        flash("💎 Значок алмаза включён!", "success")
    else:
        current_user.has_diamond = not bool(getattr(current_user, "has_diamond", False))
        if current_user.has_diamond:
            flash("💎 Значок алмаза включён!", "success")
        else:
            flash("Значок 💎 снят.", "info")
    db.session.commit()
    return redirect(url_for("profile") + "#yookassa-card")


def install_yookassa_pay(app, register=None) -> None:
    if app.extensions.get("yookassa_pay_installed"):
        return
    app.extensions["yookassa_pay_installed"] = True

    if "yookassa_pay" not in app.blueprints:
        if register is None:
            app.register_blueprint(yookassa_pay_bp)
        else:
            register(app, yookassa_pay_bp)

    @app.context_processor
    def _inject_yookassa_helpers():
        # Блок оплаты 💎 скрыт из профиля для всех
        return {"is_diamond_admin": False, "is_diamond_buyer": False}

# -*- coding: utf-8 -*-
"""
services/yookassa_stub.py — Stub for YooKassa payment integration.

This module provides a clear entry/exit point for future YooKassa integration.
Currently returns stub responses — no real API calls, no real payments.

Planned real interface (for future implementation):
    create_payment(amount_rub: float, description: str, return_url: str) -> dict
        Returns: {"payment_id": str, "confirmation_url": str}

    check_payment(payment_id: str) -> dict
        Returns: {"status": "pending"|"succeeded"|"canceled", ...}

    handle_webhook(payload: dict) -> dict
        Returns: {"ok": True} or raises

For now: always returns stub responses.
"""

import logging

logger = logging.getLogger(__name__)

# Toggle: set YOOKASSA_ENABLED=1 to enable real integration (when ready)
YOOKASSA_ENABLED = False  # Stub mode — no real calls


def create_payment(amount_rub: float, description: str, return_url: str = "") -> dict:
    """Create a payment. Currently returns a stub.

    Args:
        amount_rub: Amount in rubles
        description: Payment description
        return_url: Where to redirect after payment

    Returns:
        {"payment_id": str, "confirmation_url": str}
    """
    if not YOOKASSA_ENABLED:
        logger.info(
            "[yookassa_stub] create_payment called (stub): "
            "amount=%.2f rub, desc=%s", amount_rub, description
        )
        return {
            "payment_id": "stub_payment_" + str(hash(description))[:16],
            "confirmation_url": "/payment-stub",
        }

    # Real implementation would go here:
    # import yookassa
    # payment = yookassa.Payment.create({...})
    # return {"payment_id": payment.id, "confirmation_url": payment.confirmation.confirmation_url}
    raise NotImplementedError("YooKassa real integration not implemented yet")


def check_payment(payment_id: str) -> dict:
    """Check payment status. Currently returns stub.

    Returns:
        {"status": "pending"|"succeeded"|"canceled", "payment_id": str}
    """
    if not YOOKASSA_ENABLED:
        logger.info("[yookassa_stub] check_payment called (stub): id=%s", payment_id)
        return {
            "payment_id": payment_id,
            "status": "pending",
        }
    raise NotImplementedError("YooKassa real integration not implemented yet")


def handle_webhook(payload: dict) -> dict:
    """Handle YooKassa webhook notification. Currently stub."""
    if not YOOKASSA_ENABLED:
        logger.info("[yookassa_stub] webhook received (stub, ignored)")
        return {"ok": True}
    raise NotImplementedError("YooKassa real integration not implemented yet")

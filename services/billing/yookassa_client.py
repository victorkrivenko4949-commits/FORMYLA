# -*- coding: utf-8 -*-
"""Тонкий клиент API ЮKassa на requests (SDK в requirements нет).

В логах — только id платежа/заказа и HTTP-код, без payload и секретов.
Сетевые ошибки, 429 и 5xx → YooKassaTemporaryError (вызывающий код отвечает 5xx,
чтобы ЮKassa повторила уведомление).
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

API_URL = os.environ.get('YOOKASSA_API_URL', 'https://api.yookassa.ru/v3').rstrip('/')
TIMEOUT = float(os.environ.get('YOOKASSA_TIMEOUT_SEC', '10'))


class YooKassaError(Exception):
    """Постоянная ошибка (4xx, невалидный ответ)."""


class YooKassaTemporaryError(YooKassaError):
    """Временная ошибка (сеть, 429, 5xx) — можно повторить с тем же ключом."""


class YooKassaConfigError(YooKassaError):
    """Нет YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY."""


def _auth():
    shop_id = os.environ.get('YOOKASSA_SHOP_ID', '').strip()
    secret = os.environ.get('YOOKASSA_SECRET_KEY', '').strip()
    if not shop_id or not secret:
        raise YooKassaConfigError('YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY не заданы')
    return shop_id, secret


def kop_to_value(kop: int) -> str:
    return f'{(Decimal(int(kop)) / 100):.2f}'


def value_to_kop(value: str) -> int:
    return int((Decimal(str(value)) * 100).to_integral_value())


def _request(method: str, path: str, *, json_body=None, headers=None, what: str = '') -> Dict[str, Any]:
    try:
        resp = requests.request(method, f'{API_URL}{path}', auth=_auth(), json=json_body,
                                headers=headers or {}, timeout=TIMEOUT)
    except (requests.Timeout, requests.ConnectionError) as exc:
        logger.warning('yookassa %s: network error (%s)', what, type(exc).__name__)
        raise YooKassaTemporaryError(f'{what}: network error') from exc
    if resp.status_code == 429 or resp.status_code >= 500:
        logger.warning('yookassa %s: HTTP %s (temporary)', what, resp.status_code)
        raise YooKassaTemporaryError(f'{what}: HTTP {resp.status_code}')
    if resp.status_code >= 400:
        code = ''
        try:
            code = (resp.json() or {}).get('code', '')
        except Exception:
            pass
        logger.error('yookassa %s: HTTP %s code=%s', what, resp.status_code, code)
        raise YooKassaError(f'{what}: HTTP {resp.status_code} {code}')
    try:
        return resp.json()
    except ValueError as exc:
        raise YooKassaError(f'{what}: invalid JSON') from exc


def create_payment(*, amount_kop: int, currency: str, description: str, return_url: str,
                   idempotence_key: str, order_id: str) -> Dict[str, Any]:
    body = {
        'amount': {'value': kop_to_value(amount_kop), 'currency': currency},
        'capture': True,
        'confirmation': {'type': 'redirect', 'return_url': return_url},
        'description': description[:128],
        'metadata': {'order_id': order_id},
    }
    data = _request('POST', '/payments', json_body=body,
                    headers={'Idempotence-Key': idempotence_key, 'Content-Type': 'application/json'},
                    what=f'create_payment order={order_id}')
    if not data.get('id') or not (data.get('confirmation') or {}).get('confirmation_url'):
        raise YooKassaError('create_payment: response without id/confirmation_url')
    return data


def get_payment(payment_id: str) -> Dict[str, Any]:
    return _request('GET', f'/payments/{payment_id}', what=f'get_payment id={payment_id}')

# -*- coding: utf-8 -*-
"""Проверка IP уведомлений ЮKassa. Реальный IP берём из request.remote_addr
(ProxyFix уже применён в app.py — проверить!). X-Forwarded-For вручную не разбираем."""
from __future__ import annotations

import ipaddress
import logging
import os
from typing import List

logger = logging.getLogger(__name__)

# Официальный список ЮKassa (IPv4 и IPv6). Актуализировать по документации.
DEFAULT_YOOKASSA_IPS = (
    '185.71.76.0/27,185.71.77.0/27,77.75.153.0/25,77.75.156.11,77.75.156.35,'
    '77.75.154.128/25,2a02:5180::/32'
)


def _networks() -> List:
    raw = os.environ.get('YOOKASSA_WEBHOOK_IPS', DEFAULT_YOOKASSA_IPS)
    nets = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            logger.error('YOOKASSA_WEBHOOK_IPS: bad entry %r', part)
    return nets


def ip_allowed(remote_addr) -> bool:
    if os.environ.get('YOOKASSA_WEBHOOK_IP_CHECK', '1') == '0':
        return True
    if not remote_addr:
        return False
    try:
        ip = ipaddress.ip_address(str(remote_addr).strip())
    except ValueError:
        return False
    return any(ip in net for net in _networks())

# -*- coding: utf-8 -*-
"""PLAN_PRICES — единый каталог цен и длительностей (BILLING_V1).

Цены в копейках. В интерфейсе пишем «доступ на 30 дней / на год», не «подписка».
Признак Основателя определяет ТОЛЬКО сервер: users.founder_price_eligible /
users.is_founder (поля появятся в задаче «Основатели»); пока их нет —
пользователь считается НЕ Основателем (fail-closed).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

PRICE_VERSION = '2026-11-v1'
CURRENCY = 'RUB'


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, '') or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Product:
    code: str
    kind: str                    # 'access' | 'purchase'
    title: str
    amount: int                  # копейки, цена для новых
    founder_amount: int          # копейки, цена Основателя
    plan: Optional[str] = None   # premium_monthly | premium_yearly (kind=access)
    duration: Optional[str] = None  # '30d' | '1y'
    feature_flag: Optional[str] = None


PLAN_PRICES = {
    'student_month': Product('student_month', 'access', 'Доступ на 30 дней',
                             49000, 39000, 'premium_monthly', '30d'),
    'student_year': Product('student_year', 'access', 'Доступ на год',
                            299000, 279000, 'premium_yearly', '1y'),
    'probe_once': Product('probe_once', 'purchase', 'Пробник', 19900, 19900),
    'sheet_once': Product('sheet_once', 'purchase', 'Лист задач', 9900, 9900),
    'method_week_once': Product('method_week_once', 'purchase', 'Метод недели', 29000, 29000),
    # Не продаются в первом релизе. Цена задаётся env при старте (0 = не продаётся даже при флаге 1).
    'family_month': Product('family_month', 'access', 'Семейный доступ на 30 дней',
                            _env_int('FAMILY_MONTH_PRICE_KOP', 0), _env_int('FAMILY_MONTH_PRICE_KOP', 0),
                            'premium_monthly', '30d', 'FAMILY_TEACHER_PLANS_ENABLED'),
    'teacher_month': Product('teacher_month', 'access', 'Доступ учителя на 30 дней',
                             _env_int('TEACHER_MONTH_PRICE_KOP', 0), _env_int('TEACHER_MONTH_PRICE_KOP', 0),
                             'premium_monthly', '30d', 'FAMILY_TEACHER_PLANS_ENABLED'),
}


def get_product(code: str) -> Optional[Product]:
    return PLAN_PRICES.get((code or '').strip())


def is_product_enabled(product: Product) -> bool:
    if product.feature_flag and os.environ.get(product.feature_flag, '0') != '1':
        return False
    return product.amount > 0


def user_is_founder_priced(user) -> bool:
    """Право на цену Основателя. Fail-closed: нет поля/ошибка → False."""
    try:
        if getattr(user, 'founder_price_eligible', None):
            return True
        return bool(getattr(user, 'is_founder', False))
    except Exception:
        return False


def amount_for(product: Product, user) -> Tuple[int, bool]:
    """(сумма в копейках, применена ли цена Основателя)."""
    if user_is_founder_priced(user) and product.founder_amount != product.amount:
        return product.founder_amount, True
    return product.amount, False


def format_rub(kop: int) -> str:
    rub = kop // 100
    s = f'{rub:,}'.replace(',', '\u00a0')
    return f'{s}\u00a0₽'


def duration_label(product: Product) -> str:
    return {'30d': 'за 30 дней', '1y': 'за год'}.get(product.duration or '', 'разово')


def display_price(code: str, user=None) -> str:
    p = get_product(code)
    if p is None:
        return ''
    amount, _ = amount_for(p, user)
    return f'{format_rub(amount)} {duration_label(p)}'


def upgrade_price_label(user=None) -> str:
    """Для method_week/paywall.py вместо хардкода «390 руб/мес»."""
    return display_price('student_month', user)

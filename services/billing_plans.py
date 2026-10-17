# -*- coding: utf-8 -*-
"""BILLING_V1 — каталог тарифов FORMYLA (единственное место с кодами и ценами).

Коды тарифов (одинаковые во всём коде):
  student_month 490/390 ₽ · student_year 2 990/2 790 ₽ · family_month 890 ₽ ·
  teacher_month 1 990 ₽ · probe_once 199 ₽ · sheet_once 99 ₽ · method_week_once 290 ₽.
Вторая цена — для Основателей (users.is_founder или регистрация до BILLING_FOUNDER_CUTOFF).

Маппинг кода тарифа → план PLAN_LIMITS (services/subscription.py) — поле `sub_plan`.
Разовые продукты (`kind='one_time'`) пишутся в таблицу purchases.
"""
from __future__ import annotations

import os
from datetime import date, datetime

FOUNDER_CUTOFF_DEFAULT = '2026-11-01'

PLANS = {
    'student_month': dict(title='Ученик', period='в месяц', price=490, founder_price=390,
                          kind='subscription', sub_plan='premium_monthly', duration_days=30,
                          desc='Все задачи дня, ИИ-разборы, метод недели, чертежи, куратор'),
    'student_year':  dict(title='Ученик', period='в год', price=2990, founder_price=2790,
                          kind='subscription', sub_plan='premium_yearly', duration_days=365,
                          desc='То же, что в месячном, — на год. Выгода два месяца'),
    'family_month':  dict(title='Семья', period='в месяц', price=890, founder_price=890,
                          kind='subscription', sub_plan='family_monthly', duration_days=30,
                          desc='Premium для двух детей + отчёт родителю'),
    'teacher_month': dict(title='Учитель', period='в месяц', price=1990, founder_price=1990,
                          kind='subscription', sub_plan='teacher_monthly', duration_days=30,
                          desc='Группа до 30 учеников, задания классу, прогресс'),
    'probe_once':    dict(title='Пробник с разбором', period='разово', price=199, founder_price=199,
                          kind='one_time', sub_plan=None, duration_days=None,
                          desc='Один пробный тур с подробным разбором куратора'),
    'sheet_once':    dict(title='PDF-листок', period='разово', price=99, founder_price=99,
                          kind='one_time', sub_plan=None, duration_days=None,
                          desc='Листок из 10 задач по теме с ответами'),
    'method_week_once': dict(title='Неделя метода', period='разово', price=290, founder_price=290,
                             kind='one_time', sub_plan=None, duration_days=None,
                             desc='Один метод из 102 — неделя задач и разборов'),
}
SUBSCRIPTION_CODES = tuple(k for k, v in PLANS.items() if v['kind'] == 'subscription')
ONE_TIME_CODES = tuple(k for k, v in PLANS.items() if v['kind'] == 'one_time')

# заголовки витрины по точке входа ?from=
FROM_TITLES = {
    'daily_limit': 'Сегодняшние 3 задачи решены — серия сохранена',
    'limit': 'Лимит на сегодня исчерпан',
    'ai_limit': 'ИИ-разбор на сегодня использован',
    '/method_week': 'Метод недели — в Premium',
    '/geometry/draw': 'Генератор чертежей — в Premium',
    '/figures/generate': 'Генератор чертежей — в Premium',
    'founder': 'Ранний доступ Основателя',
    'profile': 'Подписка',
}


def founder_cutoff() -> date:
    try:
        return date.fromisoformat(os.environ.get('BILLING_FOUNDER_CUTOFF', FOUNDER_CUTOFF_DEFAULT))
    except ValueError:
        return date.fromisoformat(FOUNDER_CUTOFF_DEFAULT)


def is_founder(user) -> bool:
    """Основатель: явный флаг users.is_founder или регистрация до даты отсечки."""
    if user is None:
        return False
    if getattr(user, 'is_founder', False) is True:
        return True
    created = getattr(user, 'created_at', None)
    if isinstance(created, datetime):
        return created.date() < founder_cutoff()
    return False


def price_for(code: str, founder: bool) -> int:
    p = PLANS[code]
    return int(p['founder_price'] if founder else p['price'])


def catalog(founder: bool) -> list:
    """Список тарифов для витрины с ценой под пользователя."""
    out = []
    for code, p in PLANS.items():
        out.append({'code': code, 'title': p['title'], 'period': p['period'], 'desc': p['desc'],
                    'kind': p['kind'], 'price': price_for(code, founder),
                    'regular_price': p['price'], 'is_discount': founder and p['founder_price'] < p['price']})
    return out

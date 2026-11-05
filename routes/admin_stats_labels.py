# -*- coding: utf-8 -*-
"""Понятные названия для панели статистики: страницы сайта, источники прихода,
вопросы анкеты, способ входа. Только подписи — данные не меняются."""
from __future__ import annotations

PAGE_TITLES = {
    '/': 'Главная',
    '/about': 'О сайте',
    '/login': 'Вход',
    '/register': 'Регистрация',
    '/intake': 'Анкета',
    '/olympiad-start': 'С чего начать',
    '/daily_tasks': 'Задачи дня',
    '/daily': 'Задачи дня',
    '/prep/coach': 'Моя статистика',
    '/curator': 'Куратор',
    '/subscribe': 'Тарифы',
    '/payments/premium/checkout': 'Оформление оплаты',
    '/payments/premium/return': 'Возврат с оплаты',
    '/schedule': 'Выбор дней занятий',
    '/profile': 'Профиль',
    '/olympiads': 'Олимпиады',
    '/olympiads/methods': '102 метода',
    '/olymp-catalog': 'Каталог олимпиадных задач',
    '/problems': 'Задачи',
    '/problems/<id>': 'Задача',
    '/probniks': 'Пробники',
    '/geometry/draw': 'Генератор чертежей',
    '/friends': 'Друзья',
    '/leaderboard': 'Рейтинг',
    '/chat': 'Чат',
    '/my/support': 'Поддержка',
    '/method_week': 'Метод недели',
    '/join': 'Вход в группу по коду',
    '/teacher': 'Кабинет учителя',
    '/parent': 'Кабинет родителя',
}

SOURCE_TITLES = {
    'tg': 'Telegram', 'teacher': 'Ссылка учителя', 'parent': 'Ссылка родителя', 'referral': 'Приглашение по ссылке',
    'organic': 'Поиск (Яндекс, Google)', 'social': 'Соцсети', 'direct_visit': 'Сам набрал адрес / закладка',
    'internal': 'Внутренний переход',
}

INTAKE_QUESTIONS = {
    'class': '1. Кто ты (класс)',
    'goal': '2. Цель',
    'experience': '3. Опыт олимпиад',
    'time': '4. Сколько времени в день',
    'weak_sections': '5. Сложные разделы',
    'commitment': '6. Готов ли заниматься каждый день',
}

PLAN_STATUS = {'active': 'Активна', 'cancelled': 'Отменена', 'superseded': 'Заменена новой', 'expired': 'Истекла'}


def page_title(path) -> str:
    """'/daily_tasks' → 'Задачи дня'; неизвестный адрес — как есть."""
    if not path or path == '—':
        return '—'
    p = str(path).split('?', 1)[0]
    if p in PAGE_TITLES:
        return PAGE_TITLES[p]
    for prefix in sorted(PAGE_TITLES, key=len, reverse=True):
        if prefix != '/' and p.startswith(prefix + '/'):
            return f'{PAGE_TITLES[prefix]} ({p})'
    return p


def source_title(code) -> str:
    if not code:
        return 'Неизвестно'
    return SOURCE_TITLES.get(str(code), str(code))


def question_title(qid) -> str:
    return INTAKE_QUESTIONS.get(str(qid), str(qid))

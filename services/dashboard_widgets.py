# -*- coding: utf-8 -*-
"""
services/dashboard_widgets.py — T6: configurable dashboard widgets.

Widgets are sourced from the "Прочее" (/misc) page. Each widget
has a unique key, title, partial template path and description.

DO NOT invent new widgets — this list mirrors misc.html exactly.
"""

AVAILABLE_WIDGETS = [
    {
        'key': 'probniks',
        'title': 'Тест по темам',
        'template': 'widgets/probniks.html',
        'description': 'Адаптивный тест по олимпиадным темам',
    },
    {
        'key': 'secrets',
        'title': 'Секреты',
        'template': 'widgets/secrets.html',
        'description': 'Специальные подборки задач',
    },
    {
        'key': 'figures',
        'title': 'ИИ-чертёж по задаче',
        'template': 'widgets/figures.html',
        'description': 'Генерация геометрического чертежа',
    },
    {
        'key': 'leaderboard',
        'title': 'Лидеры',
        'template': 'widgets/leaderboard.html',
        'description': 'Таблица лидеров',
    },
    {
        'key': 'friends',
        'title': 'Друзья',
        'template': 'widgets/friends.html',
        'description': 'Список друзей',
    },
    {
        'key': 'chat',
        'title': 'Чат',
        'template': 'widgets/chat.html',
        'description': 'Общий чат',
    },
    {
        'key': 'ai_tutor',
        'title': 'AI Тьютор',
        'template': 'widgets/ai_tutor.html',
        'description': 'Персональный разбор задач',
    },
    {
        'key': 'problems',
        'title': 'Поиск задач',
        'template': 'widgets/problems.html',
        'description': 'Поиск по базе задач',
    },
    {
        'key': 'about',
        'title': 'О сайте',
        'template': 'widgets/about.html',
        'description': 'О платформе FORMYLA',
    },
    {
        'key': 'feedback',
        'title': 'Написать отзыв',
        'template': 'widgets/feedback.html',
        'description': 'Предложения и пожелания',
    },
    {
        'key': 'profile',
        'title': 'Профиль',
        'template': 'widgets/profile.html',
        'description': 'Личный кабинет',
    },
]

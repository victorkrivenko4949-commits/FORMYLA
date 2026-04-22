# NAV_AUDIT.md — Navbar Audit

## Найденные nav-блоки

### templates/base.html (единственный navbar)

```html
<nav class="nav">
    <a href="/daily" class="daily-nav-link">
        <span class="daily-flame">🔥</span>
        <span class="daily-text">Задачи дня</span>
        <!-- badge если авторизован -->
    </a>
    <a href="{{ url_for('index') }}">Темы</a>
    <a href="{{ url_for('olympiads') }}">Олимпиады</a>
    <a href="/practice">Написать олимпиаду</a>
    <a href="/probniks">Пробники</a>
    <a href="{{ url_for('secrets') }}">Секреты</a>
    <a href="{{ url_for('leaderboard') }}">🏆 Лидеры</a>
    {% if current_user.is_authenticated %}
    <a href="#" onclick="...">💬 AI-Тьютор</a>
    {% endif %}
</nav>
```

## Верификация

```
curl http://127.0.0.1:5001/ | grep daily-nav-link
→ <a href="/daily" class="daily-nav-link">  ✅
```

Кнопка видна ВСЕМ пользователям (без условия is_authenticated).

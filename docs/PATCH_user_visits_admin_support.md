# USER_VISITS_V1 — подключение точного счётчика заходов

## 1. app.py

После создания `app` (рядом с регистрацией blueprint'ов):

```python
from services.user_visits import init_user_visits
init_user_visits(app)
```

Таблица `user_visits` создастся автоматически при первом запросе.

## 2. routes/admin_support.py

Импорт вверху файла:

```python
from services.user_visits import visit_stats, visits_by_user
```

В `admin_support_user_intake(user_id)` после строки
`returned = bool(visits and created and any(d > created for d in visit_days))`:

```python
    exact = visit_stats(user_id)
```

В `return jsonify({...})` добавить ключи:

```python
        'visits': visits,                       # старая оценка по дням (VISIT_COUNT_V1)
        'visit_dates': sorted(d.isoformat() for d in visit_days),
        'visits_exact': exact['visits_exact'],  # реальное число заходов
        'visit_days_exact': exact['visit_days_exact'],
        'visits_last_7d': exact['visits_last_7d'],
        'visits_last_30d': exact['visits_last_30d'],
        'avg_visit_minutes': exact['avg_visit_minutes'],
        'first_visit': exact['first_visit'],
        'last_visit': exact['last_visit'],
        'visit_log': exact['visit_log'],
```

В `admin_users_stats()` перед `render_template`:

```python
    visits_map = visits_by_user()
```

и передать `visits_map=visits_map` в шаблон.

## 3. templates/admin/users_stats.html

В строке пользователя добавить колонку:

```html
<td>{{ visits_map.get(u.id, 0) }}</td>
```

## Как смотреть по конкретному ученику

1. `/admin/users` — найти пользователя и его `user_id`.
2. `/admin/support/user_intake/<user_id>` — поле `visits_exact` = сколько раз заходил,
   `visit_log` — последние 50 визитов (начало, конец, число запросов, первая страница).

**Важно:** `visits_exact` считает заходы только с момента деплоя. За период до деплоя
единственная оценка — старое поле `visits` (дни активности, нижняя граница).

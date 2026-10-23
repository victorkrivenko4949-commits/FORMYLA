# USER_RETURNS_V1 — «сколько людей вернулись 2-й, 3-й, 4-й… раз»

Модуль: `services/user_returns.py`. Самодостаточный: свои маршруты, свой HTML, ничего в БД не создаёт.

## Подключение (1 строка)

В `gunicorn.conf.py` рядом с регистрацией `services.site_stats` (или в `app.py` после создания `app`):

```python
from services.user_returns import register as _register_user_returns; _register_user_returns(app)
```

Повторный вызов безопасен. Отключить без деплоя: `USER_RETURNS_DISABLED=1`.

## Где смотреть (аккаунт lavrik / 67лавриксемен67, is_admin)

- `/admin/users/returns` — таблица «вернулись n-й раз», топ пользователей, формулы, источники.
- `/admin/users/returns.json?gap=60&days=0` — то же в JSON.
- `/admin/users/returns.json?user_id=123` — визиты конкретного ученика (журнал последних 50).

Параметры: `gap` — пауза между действиями в минутах (по умолчанию 60, env `USER_RETURNS_GAP_MIN`),
`days` — считать только последние N дней (0 = всё время).

## Формулы

Событие — любое действие пользователя с отметкой времени (все таблицы с `user_id`/`sender_id` и колонкой DateTime находятся автоматически).

- `S(u) = 1 + |{ i : t(i+1) − t(i) > gap }|` — число визитов пользователя `u`
- `R(u) = S(u) − 1` — число возвращений
- `exact[n] = |{ u : S(u) = n }|` — ровно n визитов
- `atleast[n] = |{ u : S(u) ≥ n }|` — «вернулись n-й раз» (2-й, 3-й, 4-й, 5-й …)
- `retention_n = atleast[n] / |U|` — доля вернувшихся n-й раз от всех пользователей с действиями

## Ссылка со страницы /admin/users (по желанию)

В `templates/admin/users_stats.html` рядом с заголовком:

```html
<a href="/admin/users/returns">Возвращения (2-й, 3-й, … раз)</a>
```

Или в `admin_users_stats()` перед `render_template`:

```python
from services.user_returns import returns_distribution
returns = returns_distribution()          # returns['rows'][n-1]['at_least'] — вернулись n-й раз
```
и передать `returns=returns` в шаблон.

## Ограничение

Считаются только действия, оставившие след в БД. Простой просмотр страниц без действий не фиксируется,
пока не влит PR #99 (`user_visits`): после него его строки подхватятся автоматически (started_at/last_hit_at).

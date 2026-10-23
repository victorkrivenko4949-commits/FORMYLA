# SECTION_STATS_V1 — подключение

**На проде (Render, `gunicorn app:app`) ничего делать не нужно.** Файл `gunicorn.conf.py` в корне репо gunicorn читает сам; в хуке `post_worker_init` он вызывает `services.site_stats.register(app)` для уже загруженного приложения. app.py не трогаем.

Отключить без деплоя: env `SECTION_STATS_DISABLED=1`.

Для локального запуска `python app.py` (без gunicorn) — одна строка в конце `app.py`:

```python
from services.site_stats import register as _register_site_stats; _register_site_stats(app)
```

Модуль сам
- создаёт таблицы `site_time_sections`, `site_time_beat`, `section_feedback`, `geo_drawing_history` (Postgres и SQLite);
- вставляет трекер `/static/js/site_time.js` в каждую HTML-страницу (after_request);
- переопределяет старый `/api/track/site-time` из base.html (он больше не начисляет секунды — иначе был бы двойной счёт);
- перехватывает `geoexact.status` и складывает готовые чертежи в историю.

## Что исправлено в таймере (старый heartbeat в base.html)
1. Старый код добавлял ровно +30 сек на каждый тик `setInterval`, даже если вкладка была видна 1 секунду из 30 → переоценка.
2. При уходе со вкладки `acc` всегда был 0 (сбрасывался на каждом тике) → остаток до 29 сек терялся → недооценка.
3. Две открытые вкладки слали удары независимо → время ×2.
4. Простой (открыл и ушёл пить чай, вкладка видна) считался как активное время.

Новый трекер: считает по `Date.now()`, останавливается при `visibilityState === 'hidden'` и после 2 минут без мыши/клавиатуры/скролла, остаток досылает `sendBeacon`, а сервер начисляет не больше секунд, чем реально прошло по часам с прошлого удара (защита от нескольких вкладок).

## Разделы
| Ключ | Префикс URL | Название |
|---|---|---|
| general | весь сайт | Общая статистика (пишется и в `users.site_seconds_total`) |
| daily | /daily_tasks | Задачи дня |
| methods | /olympiads/methods | 102 метода (iframe-атлас учитывается) |
| generators | /geometry/draw, /geometry/drawings | Генераторы чертежей |
| other | остальное | Остальные страницы |

## Страницы и API
- `/admin/users/sections` — админ-таблица по разделам (ссылка автоматически появляется на `/admin/users`).
- `/geometry/drawings` — «Мои чертежи» (ссылка появляется в заголовке генератора).
- `POST /api/track/beat` `{section, page, seconds}` → `{credited, totals, ask_section_feedback, feedback_pending}`.
- `GET /api/track/my-totals` — итоги текущего пользователя по разделам.
- `GET /api/feedback/section/pending`, `POST /api/feedback/section` `{section, rating 1–5, text}`.

## Опрос «102 метода»
После 15 минут суммарно внутри методов (не админам) — блокирующее окно, как опрос 25 мин:
«Насколько понятно объяснены методы?» — 1 = слишком сложно, 5 = всё ясно + поле «какой метод было тяжело понять». Текст меняется в константах `METHODS_FEEDBACK_QUESTION` / `METHODS_FEEDBACK_SUBTITLE` в `services/site_stats.py`.

## Проверка после деплоя
0. В логе старта Render: `SECTION_STATS_V1: registered via gunicorn.conf.py`.
1. Зайти под обычным пользователем на /olympiads/methods, подождать 25–40 сек → в БД `site_time_sections` появится строка `methods`.
2. Свернуть вкладку на 2 минуты → секунды не растут. Вернуться → растут.
3. Открыть сайт в двух вкладках → суммарное время растёт как в одной.
4. `/admin/users/sections` под Lavrik — таблица с колонками по разделам и «Чертежей».

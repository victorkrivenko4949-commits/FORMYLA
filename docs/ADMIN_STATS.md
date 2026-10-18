# ADMIN_STATS_V1 + FUNNEL_V1 (18.10.2026)

Своя статистика вместо Яндекс Метрики/Директа. Панель `/admin/stats` с левым меню,
слой событий `funnel_events`.

## Включение / откат
| Переменная | По умолчанию | Назначение |
|---|---|---|
| `FUNNEL_ENABLED` | `1` | события, `/api/ev`, `window.track`, обёртки intake/daily |
| `ADMIN_STATS_ENABLED` | `1` | панель `/admin/stats` |
| `ADMIN_STATS_REDIRECTS` | `0` | редирект старых `/admin/users*` в панель (включать после проверки) |
| `YANDEX_METRIKA_ID` | — | **убрать** из Render: без неё счётчик Яндекса не рендерится |

Откат: `FUNNEL_ENABLED=0`, `ADMIN_STATS_ENABLED=0` → redeploy. Таблица `funnel_events`
и поля `users.acq_source/acq_ref/invited_by` остаются, вреда не несут.

## События
`visit` (раз в сессию, с source/ref) · `signup` (сигнал user_logged_in, created_at < 2 мин) ·
`intake_done` (обёртка intake.answer_intake / submit_intake_anchor; `/intake/start` не считается) ·
`first_task_solved` (обёртка `/daily_tasks/<id>/submit` и `/submit_ai`, `is_correct: true`) ·
`payment_success` — **только** через `services.funnel.payment_success(user_id, plan_code, amount, payment_id)`
из webhook ЮKassa (задача 19.10) · клиентские через `window.track(name, props)`:
`limit_hit`, `paywall_view`, `subscribe_view`, `founder_offer_click`, `mock_start`, `mock_complete`.

Дедупликация «первых» событий — уникальный индекс `(user_id, event)`.

## Источники (`source`)
`tg` · `teacher` · `parent` · `referral` · `organic` · `social` · `direct_visit` · `internal`.
Метки ссылок: `?ref=tg`, `?ref=teacher_<id>`, `?ref=parent`, `?ref=u_<user_id>`; `utm_*` тоже читаются.

## Разделы панели
Готовые: Сводка, Воронка, Источники, Пользователи, Разделы сайта, Возвраты, Задачи дня,
Пул задач, Поддержка, PWA, Инсайты, Флаги окружения (существующие страницы встроены как есть).
Запланированные (серым, с датой): Рефералы 27.10 · Серии и XP 21.10 · Лимиты 21.10 · Paywall 21.10 ·
Подписки 19.10 · Основатели 20.10 · Триал 20.10 · Платежи 19.10 · Когорты 25.10 · ИИ-разборы 21.10 ·
Куратор 25.10 · Чертежи и метод недели 21.10 · Опросы 25.10 · Учителя и родители 27.10.

## Проверка после деплоя
1. `/?ref=tg` анонимно → в `/admin/stats/sources` строка Telegram с 1 визитом.
2. Новый аккаунт → анкета до финала → верная задача дня → в `/admin/stats/funnel` по 1 в signup, intake_done, first_task_solved.
3. `/admin/stats/env_flags`: `YANDEX_METRIKA_ID` — «не задано».
4. `pytest tests/test_funnel_admin_stats.py -q`.

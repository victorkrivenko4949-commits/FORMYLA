# TRIAL_V1 + SOFT_LIMITS_V1 + PARENT_OFFER_V1 (18.10.2026)

Закрывает промпты 9 (20.10), 11 и 12 (21.10) рабочей книги. `app.py` и `daily_tasks/routes.py` не правятся —
лимиты навешиваются обёртками view-функций по url_map (как в services/funnel.py).

## Триал (services/trial.py)
- `users.trial_until` и таблица `trial_grants` создаются на лету.
- Выдача: первый вход пользователя моложе 2 минут (e-mail и Telegram — одна точка, сигнал `user_logged_in`).
- Повторная регистрация на тот же e-mail/telegram_id триал не получает.
- `User.is_trial_active()` добавляется в класс при старте — `method_week/paywall.user_has_paid_access` его уже проверяет.
- Основатели (регистрация до `BILLING_FOUNDER_CUTOFF`) триал не получают, но `is_trial_active()` = True до `FOUNDER_FREE_UNTIL=2027-01-31` — Premium бесплатно, как обещано в письмах.
- Метка в шапке: «Premium до DD.MM» / «Основатель · Premium до 31.01» / платный план — инжект after_request (`TRIAL_BADGE=0` выключает).

## Мягкие лимиты (services/soft_limits.py + services/ab.py)
Действуют только при одновременном выполнении: `PAYWALL_ENABLED=1` и дата ≥ `PAYWALL_START_DATE` (UTC-дата сервера → 03:00 МСК 1 ноября),
пользователь в когорте (`user_id % 100 < PAYWALL_AB`), нет платного доступа (подписка/триал/Основатель/админ/whitelist).

| Что | Как |
|---|---|
| Задачи дня | считаем `daily_task_items.answered_at` за сегодня (МСК) без `debt_status='active'`; при ≥ `FREE_TASKS_PER_DAY` POST `/submit`, `/submit_ai` и GET `/daily_tasks/<id>` неотвеченной задачи → экран лимита |
| ИИ-разборы | POST `/api/tutor/*` → `can_use_feature('ai_explanation')` с `FREE_AI_PER_DAY`, после успеха `increment_usage` |
| Ответ | HTML: `templates/billing/limit.html` (включает partial); JSON/POST: `402 {error:'limit', kind, upgrade_url:'/subscribe?from=daily_limit', html}` |
| Не трогаем | `/daily_tasks/` дашборд, `/prep`, долг, уже отвеченные, серии/XP/лидерборд |
| События | `limit_hit {kind, ab, used, limit}` → раздел «Лимиты» в `/admin/stats` |
| Жёсткий paywall | `method_week/paywall.py`: `DEFAULT_PREFIXES='/method_week,/geometry/draw,/figures/generate'`; цена в 402 — из каталога (390 Основателю / 490 новым) |

### Правило серии при 3 задачах
`soft_limits.streak_required(3) == 2`: день засчитывается при 2 верных из 3 (80% от 3 = 2,4 → вниз). Выбрано 2 из 3, а не 3 из 3:
при 3 из 3 любая ошибка рвёт серию, что строже старого правила 4 из 5 и нарушает красную линию «не рвать серии».
**Внимание:** сама формула зачёта дня живёт в `daily_tasks/services.py` («>80% из 5») — её нужно перевести на
`streak_required(n_available)` в отдельном PR после чтения этого файла (145 КБ). До этого лимиты включать нельзя (`PAYWALL_AB=0`).

## Экран лимита и ссылка родителю
- `templates/partials/limit_reached.html` — «3 из 3 решено — серия сохранена ✅», кнопки «Отправить родителю» (Telegram/WhatsApp/копия), «Попросить учителя» (`/teacher/join`), «Подробнее о Premium». События `limit_shown`, `parent_link_shared`.
- `POST /parent/offer-link` → токен itsdangerous на `PARENT_OFFER_DAYS=7`; `GET /parent/offer/<token>` — страница для родителя с прогрессом ребёнка и кнопкой на `/subscribe?from=parent_offer&child=<id>`.
- Привязка оплаты родителя к ребёнку (`child_user_id` в metadata платежа → активация у ребёнка) — задача 27.10.

## Env
```
TRIAL_ENABLED=1  TRIAL_DAYS=14  FOUNDER_FREE_UNTIL=2027-01-31  TRIAL_BADGE=1
SOFT_LIMITS_ENABLED=1  FREE_TASKS_PER_DAY=3  FREE_AI_PER_DAY=1
PAYWALL_ENABLED=1  PAYWALL_START_DATE=2026-11-01  PAYWALL_AB=50   # 31.10 — по рабочей книге
PAYWALL_PREFIXES=/method_week,/geometry/draw,/figures/generate
PARENT_OFFER_ENABLED=1  PARENT_OFFER_DAYS=7
```
Откат лимитов без деплоя: `PAYWALL_AB=0` (или `FREE_TASKS_PER_DAY=20`, `FREE_AI_PER_DAY=3`). Полный откат — `SOFT_LIMITS_ENABLED=0`, `TRIAL_ENABLED=0`.

## Проверка
1. `pytest tests/test_trial_limits.py -q` — 8 тестов.
2. Новый аккаунт → в шапке «Premium до DD.MM»; `/admin/stats/trial` показывает выданный триал.
3. На тестовом аккаунте Free с `PAYWALL_AB=100`, `PAYWALL_START_DATE=сегодня`: 4-я задача → экран лимита, дашборд открыт, `/admin/stats/limits` — событие.
4. «Отправить родителю» → ссылка открывается без входа.

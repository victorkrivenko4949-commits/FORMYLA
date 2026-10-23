# Основатели FORMYLA — правило цены и бесплатного доступа

**Версия правила: `founders_rule_v1`** (изменение правила = новая версия + правка
`services/billing/catalog.py` + тесты `tests/test_founders.py`).

## Кто считается Основателем

Аккаунт создан **до 03.11.2026 00:00 МСК** (`users.created_at < FOUNDER_CUTOFF_AT`,
моменты сравниваются как время; `users.created_at` хранится в naive UTC —
сервер Render работает в UTC). Гостевые аккаунты (`is_guest`) не считаются.

## Бесплатный доступ Основателя

Окно: **[03.11.2026 00:00 МСК, 01.02.2027 00:00 МСК)** — 31 января включён целиком,
в сам момент 01.02.2027 00:00 доступа уже нет. Выдаётся записью `founder_grants`
(amount=0, payment_id=NULL, is_free_grant=True) — это **не** activate_premium
и не создаёт orders/analytics_events (бесплатная выдача — не продажа).

Одна выдача на пользователя в рамках кампании `founders_2026_v1`
(UNIQUE(user_id, campaign_id)). Триал Основателю не выдаётся; если `trial_until`
уже есть, `resolve_access` всё равно показывает 01.02.2027 (приоритет
founder > trial, более короткий источник не сокращает более длинный).

## Цена Основателя

| Тариф | Основатель | Новый |
|---|---|---|
| 30 дней (student_month) | 390 ₽ | 490 ₽ |
| год (student_year) | 2 790 ₽ | 2 990 ₽ |

Действует для исходного аккаунта независимо от перерывов в оплате и не
передаётся другому. Хранится в `PLAN_PRICES` (`services/billing/catalog.py`,
`founder_amount`), признак — `users.founder_price_eligible` (fail-closed:
нет поля/ошибка → обычная цена).

Год Основателя, купленный до 01.02.2027: период **01.02.2027 00:00 МСК →
01.02.2028 00:00 МСК** (см. `services/billing/periods.py`).

Юридическая формулировка «навсегда» этим документом НЕ утверждается.

## Выдача и откат

- `python scripts/grant_founders.py` — dry-run (по умолчанию, ничего не пишет);
- `--apply` — только после FOUNDER_CUTOFF_AT; пачки по 500, повторный запуск
  идемпотентен (возобновление после сбоя = просто перезапуск);
- сверка после выдачи: COUNT(created_at < cutoff) = COUNT(is_founder) =
  COUNT(founder_grants кампании);
- откат: `python scripts/grant_founders.py --rollback` — удаляет только выдачи
  этой кампании и её флаги; платежи, orders и subscriptions не трогаются.

## Порядок доступа

`services/access.py: resolve_access` → `paid → founder → trial → free`.
`method_week/paywall.py: user_has_paid_access` использует только resolve_access
(`User.is_trial_active()` больше не используется — он всегда True).

# BILLING_V1 (18.10.2026) — витрина /subscribe и ЮKassa

Закрывает промпты 7 и 8 рабочей книги (19.10). Не правит `app.py`; подключается через `routes/__init__.py`.

## Файлы
| Файл | Что делает |
|---|---|
| `services/billing_plans.py` | каталог тарифов (коды, цены, цены Основателя), `is_founder(user)`, маппинг код → план PLAN_LIMITS |
| `services/payments_yookassa.py` | API ЮKassa v3: создание платежа (Idempotence-Key), проверка статуса, webhook, таблицы `payments`/`purchases`, миграция `users.is_founder` |
| `services/subscription.py` | + планы `family_monthly` (890 ₽, 2 ребёнка), `teacher_monthly` (1 990 ₽, группа 30); любой платный план = `is_premium` |
| `routes/billing.py` | `GET /subscribe?from=…`, `POST /billing/create`, `GET /billing/success`, `POST /billing/webhook`, `POST /billing/cancel`, `GET /billing/status.json` |
| `templates/billing/subscribe.html`, `success.html` | витрина и страница возврата |
| `tests/test_billing.py` | витрина Основатель/новый, создание платежа, webhook (успех, повтор, чужой IP, разовая покупка, семья, неизвестный план, отмена) |

## Env на Render
```
BILLING_ENABLED=1
YOOKASSA_SHOP_ID=…            # из кабинета ЮKassa (тестовый магазин — для sandbox)
YOOKASSA_SECRET_KEY=…
YOOKASSA_RETURN_URL=https://formyla.net/billing/success
BILLING_FOUNDER_CUTOFF=2026-11-01   # зарегистрированные раньше — Основатели
```
Откат: `BILLING_ENABLED=0`. Без ключей ЮKassa витрина открывается, кнопки оплаты отключены («скоро»).

## Настройка уведомлений в ЮKassa
Кабинет → Интеграция → HTTP-уведомления → URL `https://formyla.net/billing/webhook`,
события `payment.succeeded` и `payment.canceled`. Webhook принимает только IP ЮKassa
(185.71.76.0/27, 185.71.77.0/27, 77.75.153.0/25, 77.75.156.11, 77.75.156.35, 77.75.154.128/25, 2a02:5180::/32),
перепроверяет платёж через `GET /payments/{id}` и идемпотентен по `payment_id`.

## Что происходит при оплате
1. `/billing/create` создаёт платёж (сумма с учётом Основателя, metadata `{user_id, plan}`), редирект на страницу ЮKassa.
2. ЮKassa шлёт `payment.succeeded` → подписка: `activate_premium(user_id, plan=PLANS[code].sub_plan, is_beta=False)`; разовый продукт → строка в `purchases`.
3. `services.funnel.payment_success(...)` → событие в `/admin/stats` (Платежи, Воронка, Основатели).
4. Пользователь возвращается на `/billing/success` — статус берётся из таблицы `payments`.

## Проверка в sandbox
1. Тестовые ключи в env, redeploy.
2. `/subscribe` → «Оформить» на любом тарифе → тестовая карта ЮKassa (5555 5555 5555 4477).
3. После возврата: `/billing/success` показывает «Оплата прошла»; `/admin/stats/payments` — строка; `/admin/stats/subscriptions` — активная платная подписка.
4. Повторно отправить то же уведомление (кнопка «Повторить» в кабинете) — ответ `already_processed`, подписка не дублируется.

## Ограничения
- Зависимость `requests` (уже используется в проекте для ИИ-API).
- Чеки для самозанятого формирует связка ЮKassa ↔ «Мой налог» по настройке кабинета; объект `receipt` в API не передаём.
- Тарифы Семья/Учитель активируют план владельцу; привязка детей/группы — отдельная задача 27.10.

# FORMYLA

Онлайн-платформа для подготовки школьников 5–11 классов к олимпиадам по математике (ВсОШ, Эйлер, Ломоносов, Турнир городов). Flask + SQLAlchemy + DeepSeek API.

## Запуск локально

```bash
pip install -r requirements.txt
cp .env.example .env  # заполнить ключи (DeepSeek, Yandex OAuth и т.д.)
python app.py        # или: flask run --host=127.0.0.1 --port=5000
```

БД по умолчанию — SQLite (`instance/formyla.db`). В production используется PostgreSQL через `DATABASE_URL` (Render).

## Структура проекта

```
app.py                — главный Flask-аппликейшн, регистрация blueprint-ов
models.py             — основные модели (User, Friendship, AdaptiveTask и т.д.)
models_olympiad.py    — модели олимпиадной части (Probnik, TheoryBlock, OlympiadTask)
models_grade.py       — задачи для 5–6 класса (GradeTask)
routes/               — Flask Blueprints (olympiad, prep, drawing, concierge, telegram_auth, ...)
services/             — бизнес-логика (email_service, site_concierge, streak_service, ...)
ai/                   — DeepSeek-клиент и логика тьютора
static/               — CSS / JS / изображения
templates/            — Jinja-шаблоны
migrations/           — идемпотентные миграции (SQLite + Postgres через --pg)
scripts/              — одноразовые импортёры данных (например, ВсОШ-9 методы из xlsx)
docs/                 — техническая документация (Cloudflare setup, deploy notes)
```

## Внешние сервисы

Каждый сервис включается через переменные окружения. Если ключ не задан — соответствующий блок просто выключен (приложение запускается без него).

### 1. Sentry — отлов ошибок + perf-трейсинг

- ENV: `SENTRY_DSN`, опционально `SENTRY_TRACES_SAMPLE_RATE` (default 0.1), `SENTRY_PROFILES_SAMPLE_RATE` (default 0.1)
- Получить DSN: https://sentry.io → создать проект Flask → Settings → Client Keys (DSN)
- Используется: `sentry_sdk.init(...)` с `FlaskIntegration` + `SqlalchemyIntegration` в `app.py`
- Тест: `GET /debug-sentry` (доступен только при `FLASK_ENV != production`)

### 2. Cloudflare — CDN + DDoS + HTTPS

- ENV: нет (всё настраивается через dashboard)
- Полный гайд: [`docs/cloudflare_setup.md`](docs/cloudflare_setup.md)
- Что важно в коде: `ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1, x_prefix=1)`
- Security headers (CSP, HSTS, X-Frame-Options, ...) добавляются в `add_security_headers`

### 3. Brevo (Sendinblue) — транзакционные email

- ENV: `BREVO_API_KEY`, `BREVO_SENDER_EMAIL` (default no-reply@formyla.com), `BREVO_SENDER_NAME` (default FORMYLA)
- Получить ключ: https://app.brevo.com → SMTP & API → API Keys → Generate a new API key
- Используется: `services.email_service` — `send_welcome_email`, `send_password_reset`, `send_payment_receipt`
- Welcome email шлётся фоновым тредом сразу после первого успешного логина (через `verify_code` или `yandex_login`)

### 4. Telegram Login Widget — авторизация через Telegram

- ENV: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` (без `@`)
- Создать бота: BotFather → /newbot → имя FormylaMathsBot → токен; затем /setdomain → formyla.com
- Callback: `POST /auth/telegram/callback` — HMAC-SHA256 верификация подписи из `payload['hash']`
- Кнопка виджета встроена в `templates/login.html` (показывается только если задан `TELEGRAM_BOT_USERNAME`)
- Поля БД: `users.telegram_id` (unique), `users.telegram_username`

### 5. Plausible Analytics — приватная аналитика без cookies

- ENV: `PLAUSIBLE_DOMAIN` (например `formyla.com`)
- Добавить сайт: https://plausible.io → Add a site → ввести домен
- Скрипт подключается в `templates/base.html` (только если задан `PLAUSIBLE_DOMAIN`)
- Клиентский хелпер: `static/js/analytics.js` (`window.trackEvent(name, props)`)
- Автотрекинг: элементы с атрибутом `data-track="event_name"` (и любыми `data-track-foo="bar"`) ловятся автоматически

## Тарифы

- Free — все ВсОШ-9 пробники, ИИ-тьютор без лимитов, задача дня
- Pro Месяц — 390 ₽/мес
- Pro Год — 2790 ₽/год (= 232 ₽/мес)

## Лицензия и контакты

Проект автора: Виктор Беляев. По вопросам сотрудничества — через форму поддержки на странице /about.

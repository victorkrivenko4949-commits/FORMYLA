# FORMYLA

Онлайн-платформа для подготовки школьников 5–11 классов к олимпиадам по математике (ВсОШ, Эйлер, Ломоносов, Турнир городов, Физтех, Курчатов). Flask + SQLAlchemy + DeepSeek API.

## Быстрый старт (локально)

Требуется Python 3.11+ (см. `runtime.txt`).

```bash
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt      # включает requirements-geoexact.txt
cp .env.example .env                # заполнить ключи (см. таблицу ниже)
flask db upgrade --directory alembic_migrations   # применить миграции (идемпотентно)
python app.py                       # или: flask run --host=127.0.0.1 --port=5000
```

Проверка, что всё поднялось: откройте `http://localhost:5000/healthz` — должно вернуть 200 без обращения к БД.

- БД локально — SQLite (`instance/formyla.db`). В production — PostgreSQL через `DATABASE_URL` (Render).
- Файл `.env` никогда не коммитится (см. `.gitignore`); ключи — только через переменные окружения.

## Известные особенности локального запуска

- **`FORMYLA_L1_L5_TOP5.jsonl`** — app.py читает его в корне при отправке ответа в олимпиадном тесте. Если файла нет, восстановите его из бэкапа `archive/root_data/FORMYLA_L1_L5_TOP5.jsonl.bak_5level` (копия под рабочим именем) или выключите этот маршрут.
- **`secrets_dump.json`** — методический дамп для сидирования `olympiad_secrets` при пустой таблице; лежит в корне, app.py открывает его по пути от `__file__`. Это контент, не ключи.
- Без ключей API (DeepSeek/OpenRouter) приложение стартует, но ИИ-функции выключены — каждый сервис включается только при наличии своей переменной.
- GeoExact (генерация геометрических чертежей, `/geometry/draw/`) — флаг `GEOEXACT_ENABLED=1`.
- OCR (распознавание фото решений) использует модели из `tessdata/` (в репозитории).

## Структура проекта

```
app.py                — главный Flask-аппликейшн (~650 КБ), регистрация blueprint-ов
models.py             — основные модели (User, Friendship, AdaptiveTask и т.д.)
models_olympiad.py    — модели олимпиадной части (Probnik, TheoryBlock, OlympiadTask)
models_curator.py     — модели ИИ-куратора
models_grade.py       — задачи 5–6 класса (GradeTask)
models_insights.py    — модели инсайтов/статистики
olympiads.py / problems.py / problem_images.py / simple_prefetch.py — данные и хелперы каталога
routes/               — Flask Blueprints (olympiad, prep, parent_teacher, wb_meet, telegram_auth, ...)
services/             — бизнес-логика (daily_task_rotation, email_service, telegram_notify, figures_service, ...)
ai/                   — DeepSeek-клиент и логика тьютора
assistant/            — ИИ-ассистент и база знаний
curator/              — ИИ-куратор (monthly_cycle, push_service)
daily_tasks/          — задачи дня: модели, пул, ротация, банк (formyla_bank.py)
geoexact/             — генерация геометрических чертежей SVG (GEOEXACT_ENABLED=1)
utils/                — утилиты (mail, tutor_lookup, seed_secrets_utils)
migrations/           — legacy-идемпотентные миграции (импортируются app.py при старте)
alembic_migrations/   — миграции Alembic (flask db upgrade --directory alembic_migrations)
config/, schemas/     — конфигурация и JSON-схемы пайплайнов
scripts/              — одноразовые импортёры и утилиты
tests/                — pytest-тесты (conftest.py, фикстуры)
verify/               — инвариант-чекер генерации задач (используется тестами)
docs/                 — техническая документация (deploy notes, cloudflare setup)
templates/            — Jinja-шаблоны
static/               — CSS / JS / изображения
data/                 — сиды данных (olympiads, anchors.jsonl и т.п.)
tessdata/             — модели Tesseract OCR
uploads/              — пользовательские файлы (НЕ в git)
archive/              — исторические скрипты, логи, бэкапы (не используется приложением)
```

Рабочие данные в корне: `FORMYLA_BANK.jsonl` (банк 8 000+ задач), `olympiad_tasks_PERFECT.json` (каталог олимпиадных задач), `secrets_dump.json` (методический дамп), `FORMYLA_SREZ_банк_среза.zip` (срез банка).

## Переменные окружения

Полный список с комментариями — в `.env.example`. Обязательный минимум:

| Переменная | Назначение |
|---|---|
| `SECRET_KEY` | подпись сессий Flask (обязательна в production) |
| `DATABASE_URL` | PostgreSQL (Render подставляет автоматически) |
| `DEEPSEEK_API_KEY` | DeepSeek — ИИ-тьютор, куратор, разметка |
| `OPENROUTER_API_KEY` | пайплайн генерации задач дня и адаптивного теста |
| `RESEND_API_KEY`, `MAIL_DEFAULT_SENDER` | транзакционные email |
| `SEED_ADMIN_TOKEN` | защита админ-ручек (случайная строка) |

Опциональные (каждый выключен без ключа): `SENTRY_DSN`, `TELEGRAM_BOT_TOKEN`/`TELEGRAM_BOT_USERNAME`, `YANDEX_CLIENT_ID`/`YANDEX_CLIENT_SECRET`, `BREVO_API_KEY`, `PLAUSIBLE_DOMAIN`, `KIMI_API_KEY`, `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY`, `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`, `GEOEXACT_ENABLED`, `GEMINI_API_KEY`, `ATLAS_TUTOR_API_KEY`, `DB_UPLOAD_TOKEN`, `ADMIN_EMAILS`.

## Деплой (Render)

Автодеплой из `main`. Конфигурация — `render.yaml`:

- build: `pip install -r requirements.txt`
- start: `flask db upgrade --directory alembic_migrations && gunicorn app:app --workers 1 --threads 4 --worker-class gthread --timeout 120 --graceful-timeout 30 --bind 0.0.0.0:$PORT`
- health check: `/healthz` (не `/` и не `/profile`)
- БД: PostgreSQL `formyla-db`, `DATABASE_URL` подставляется Render.

Важно: строго `--workers 1` — APScheduler, сидеры и in-memory комнаты звонков рассчитаны на один процесс.

## Внешние сервисы

Каждый сервис включается через переменные окружения. Если ключ не задан — блок просто выключен, приложение запускается без него.

- **Sentry** — отлов ошибок + perf-трейсинг: `SENTRY_DSN`. Тест: `GET /debug-sentry` (только при `FLASK_ENV != production`).
- **Cloudflare** — CDN + DDoS + HTTPS: настраивается через dashboard, гайд в `docs/cloudflare_setup.md`. В коде — `ProxyFix` + security headers.
- **Resend** — транзакционные email: `RESEND_API_KEY` (HTTP API, рекомендуется) или SMTP-вариант (см. `.env.example`). Gmail SMTP не поддерживается.
- **Telegram Login Widget** — авторизация: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`; callback `POST /auth/telegram/callback` с HMAC-проверкой.
- **Plausible Analytics** — приватная аналитика: `PLAUSIBLE_DOMAIN`, скрипт в `templates/base.html`, хелпер `static/js/analytics.js`.

## Разработка

```bash
pytest                      # тесты (business-логика)
pytest tests/test_solver_aux_regressions.py   # регрессии генерации (verify/)
```

Правила: новый код — в отдельных blueprint-модулях, не в `app.py`; миграции — через Alembic (`alembic_migrations/`); ничего не коммитить в `main` без явного разрешения — только ветки `chore/…`, `feat/…`, `refactor/…` и PR.

## Лицензия и контакты

Проект автора: Виктор. По вопросам сотрудничества — через форму поддержки на странице /about.

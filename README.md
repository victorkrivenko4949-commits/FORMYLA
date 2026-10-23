# FORMYLA

Платформа подготовки школьников 5–11 классов к математическим олимпиадам.
Основной стек: Flask, SQLAlchemy, Jinja, KaTeX; ИИ-функции подключают внешние API.

## Локальный запуск без production-ключей

Используйте **Python 3.12.7**, как в `runtime.txt`, и отдельную копию репозитория.
Ниже профиль для разработки с пустой локальной SQLite, а не инструкция восстановления production.

### Linux / macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Только в новой копии, где нет собственного .env:
cp config/local.env.example .env
mkdir -p instance
python -m flask --app app run --host 127.0.0.1 --port 5000 --no-reload
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Только если собственного .env ещё нет:
Copy-Item config/local.env.example .env
New-Item -ItemType Directory -Force instance
python -m flask --app app run --host 127.0.0.1 --port 5000 --no-reload
```

В другом терминале:

```bash
curl -f http://127.0.0.1:5000/healthz
curl -f http://127.0.0.1:5000/__version
```

Текущий `app.py` создаёт таблицы и выполняет legacy-инициализацию при импорте.
Первый запуск не пустой: он может заполнить локальную БД данными из репозитория.
Профиль отключает APScheduler и переключаемые массовые сидеры, но не все фоновые
службы приложения. Не используйте этот запуск против production-БД.

Без `DATABASE_URL` база находится в `instance/formyla.db` этой копии проекта.
`load_dotenv(override=True)` в `app.py` означает, что существующий `.env` может
перекрыть значения из оболочки: проверьте его перед любыми тестами.

## Важное ограничение миграций и Render

В проверенной исходной версии команда
`flask --app app db upgrade --directory alembic_migrations` возвращает
`No such command 'db'`: расширение Flask-Migrate не зарегистрировано в приложении.
Кроме того, ревизия `v11_schema_migration_log` ссылается на отсутствующую
`7bcac3b72db9`. Поэтому эту команду нельзя считать проверенным шагом установки.

`render.yaml` содержит именно такой pre-start шаг перед Gunicorn. Это существовавшее
до cleanup несоответствие, а не доказательство текущего сбоя сайта: фактическая команда
в Render Dashboard здесь не проверена. Не меняйте схему production и не выполняйте
`stamp head` вслепую; восстановление цепочки миграций требует отдельной проверки
состояния БД и резервной копии.

После согласования миграций штатный сервер в `render.yaml` настроен так:

```bash
gunicorn app:app --workers 1 --threads 4 --worker-class gthread \
  --timeout 120 --graceful-timeout 30 --bind 0.0.0.0:$PORT
```

Health check: `/healthz`. Число worker-процессов нельзя увеличивать без проверки
планировщика, сидеров и комнат звонков в памяти.
Очистка репозитория не подтверждает успешный деплой: его принимают отдельно после merge.

## Структура

| Путь | Назначение |
|---|---|
| `app.py`, `wsgi.py` | Приложение и WSGI entrypoint |
| `models*.py` | ORM-модели |
| `routes/`, `services/`, `utils/` | Маршруты, бизнес-логика и вспомогательные функции |
| `ai/`, `assistant/`, `curator/` | ИИ-клиенты, ассистент и куратор |
| `daily_tasks/`, `tasks/` | Задачи дня и фоновые задачи; `tasks/` нужен тестам |
| `geoexact/`, `geometric_engine/`, `_svg_to_png.py` | Геометрия и рендер; не архивировать |
| `templates/`, `static/` | Интерфейс |
| `config/`, `schemas/` | Конфигурация и схемы |
| `data/`, `tessdata/` | Данные и OCR-ресурсы |
| `migrations/` | Legacy-миграции, выполняемые приложением |
| `alembic_migrations/` | Неполная Alembic-цепочка; ограничение описано выше |
| `tests/`, `verify/`, `tools/` | Тесты, проверка инвариантов, утилиты атласа |
| `scripts/`, `regression_night.py` | Служебные сценарии; запускать только после изучения |
| `docs/` | Документация и отчёт перепроверки |
| `archive/` | Исторические материалы; не запускать без проверки путей и секретов |
| `instance/`, `uploads/` | Runtime-данные, новые файлы не должны попадать в git |

Рабочие данные в корне: `FORMYLA_BANK.jsonl`, `olympiad_tasks_PERFECT.json`,
`secrets_dump.json`, `FORMYLA_SREZ_банк_среза.zip`. Имя `secrets_dump.json` относится
к математическим приёмам, а не к паролям. Пять файлов `audit_*.json` сохранены
для существующих `scripts/audit_total.py` и `scripts/check_audit_resume.py`.

## Известные ограничения

- `FORMYLA_L1_L5_TOP5.jsonl` отсутствует в исходном checkout, хотя один POST-маршрут
  в `app.py` открывает его без обработки отсутствия. Не копируйте старый `.bak`
  под рабочим именем без проверки формата и содержания.
- `static/figures/MANIFEST.json` и `adaptive_data.py` также отсутствуют в проверенной
  исходной версии; приложение сообщает об ограничениях соответствующих функций.
- Без настоящих API-ключей ИИ, почта, OAuth и внешние сервисы не проверены.
  Успешный `/healthz` не означает готовность этих функций или всего сайта.
- Архивация не сокращает историю git и сама по себе не уменьшает размер клона.
  Все отслеживаемые файлы архива по-прежнему входят в checkout.
- Удаление фото из HEAD не гарантирует их сохранность при следующем деплое.
  Перед merge проверьте persistent disk/внешнее хранилище `uploads/` и резервную копию.
- Старые секреты и фото остаются в истории публичного репозитория. Ротация ключей
  и политика очистки истории являются отдельными действиями.

## Переменные окружения

`config/local.env.example` содержит безопасный стартовый профиль без API-ключей.
Полный перечень интеграций с комментариями находится в `.env.example`.

| Переменная | Назначение |
|---|---|
| `SECRET_KEY` | Подпись сессий; в production только случайное секретное значение |
| `DATABASE_URL` | Подключение БД; локально не задавать для отдельной SQLite |
| `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY` | ИИ-функции |
| `RESEND_API_KEY`, `MAIL_DEFAULT_SENDER` | Почта |
| `GEOEXACT_ENABLED` | Флаг геометрического модуля |
| `ENABLE_SCHEDULER` | `0` для локальной проверки без cron-задач |
| `OLYMPIAD_AUTOSEED`, `VSOSH9_2027_FORCE_IMPORT`, `VSOSH10_2027_FORCE_IMPORT`, `ADAPTIVE_FORCE_IMPORT` | Переключаемые сидеры; локально `0` |

Не публикуйте `.env`, URL с паролями или дампы пользовательских БД. Уже tracked
файлы остаются tracked независимо от `.gitignore`; исключение `!archive/**` не нужно.

## Тесты и правила разработки

Быстрая целевая проверка зависимостей, атласа, геометрии и фоновых задач:

```bash
python -m pytest tests/test_cleanup_integrity.py tests/test_methods_atlas_visuals.py \
  tests/test_engine.py tests/test_condition_coverage.py tests/test_prep_tasks.py -q
```

Полный набор: `python -m pytest tests`. Не используйте простой `pytest` из корня:
исторический архив также содержит старые тестовые скрипты.
Полный набор имеет существующие ошибки и таймауты; результат целевого набора не
заменяет полный regression suite. Подробности и точные результаты: `docs/CLEANUP_VERIFICATION.md`.

Новый код размещается в отдельных модулях, изменения схемы проектируются через Alembic.
Работа идёт в ветках и PR; слияние в `main` требует явного разрешения.

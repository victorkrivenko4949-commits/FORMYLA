# DEPLOY CHECK — ручная выкладка FORMYLA на Render

Проект развёрнут на Render как Web Service. База данных: PostgreSQL (на Render),
SQLite локально. Домен: `formyla.net`. Сервис: `srv-d73br5ffte5s73euc56g`.

## До выкладки

1. Убедись, что все тесты проходят локально: `python -m pytest tests/ --tb=short -q`.
   Финальные числа цепочки v2 (блок P6): **939 passed, 37 failed, 17 skipped, 0 errors**.
   Базовая линия R0: 895 passed, 49 failed, 16 skipped, 22 errors. Улучшение: +44 passed, -12 failed, -22 errors.
2. Если в этом релизе есть изменения схемы базы, убедись, что миграция проверена на копии.
3. Убедись, что копия базы сделана и лежит в `instance/` с именем, содержащим дату.
4. Проверь, что файл `.env` на Render не был случайно изменён и не закоммичен.
5. Закоммить все изменения и запушить в `main`.
6. Вычистка эмодзи выполнена блоком P6: 5539 вхождений -> 0 в коде и шаблонах.
   Исключения (не тронуты): поле `avatar_emoji` в `group_chats`, пользовательские данные в базе.
7. Render Auto-Deploy: OFF. Сервис: `srv-d73br5ffte5s73euc56g`. Домен: `formyla.net`. База: PostgreSQL.
   Выкладка: человек вручную через интерфейс Render.

## Что нажать

1. Открой dashboard Render: https://dashboard.render.com
2. Найди сервис `srv-d73br5ffte5s73euc56g` (Web Service FORMYLA).
3. Auto-Deploy выключен, поэтому деплой запускается вручную.
4. Нажми кнопку **Manual Deploy** и выбери **Deploy latest commit**.
5. Дождись статуса **Live** в логах деплоя.

## После выкладки

1. Открой `https://formyla.net/__version` в браузере.
2. Сверь поле `commit` с хешем последнего коммита, который ты запушил.
  Выполни `git log -1 --format=%H` локально — хеши должны совпасть.
3. Сверь поле `build_time` — время должно быть близким к моменту завершения деплоя.
4. Открой главную страницу `https://formyla.net/` и прокрути вниз.
5. В подвале страницы есть строка `build <хеш>` — первые 8 символов должны
   совпадать с первыми 8 символами `commit` из `/__version`.

## Как убедиться, что это новая сборка, а не кеш

1. Сделай жёсткую перезагрузку страницы: Ctrl+Shift+R (Windows/Linux)
   или Cmd+Shift+R (Mac).
2. Проверь, что `build_time` в `/__version` изменился относительно предыдущего
   деплоя. Если время то же — деплой не применился.
3. Проверь, что `commit` в `/__version` совпадает с тем, что ты запушил.
4. Открой `/__version` в режиме инкогнито или другом браузере, чтобы исключить
   кеш конкретного браузера.
5. Сверь `schema_version` в `/__version` с ожидаемой версией alembic.
   Если миграция не применилась, номер будет старым.

## Миграции на PostgreSQL (V11)

При первом развёртывании на PostgreSQL или при переносе схемы с SQLite
миграции должны применяться в строго определённом порядке. Нарушение порядка
приведёт к ошибкам FOREIGN KEY или отсутствию таблиц, на которые ссылаются
ALTER-команды.

### Учёт применённых миграций

Проект использует таблицу `schema_migration_log` (модель `SchemaMigrationLog`
в `models.py`, Alembic-миграция `v11_schema_migration_log`) для отслеживания
применённых ad-hoc миграционных скриптов. Основная схема управляется Alembic
(`alembic_version`).

Перед запуском любой ad-hoc миграции (`scripts/*migration*.py`) скрипт
проверяет `is_migration_applied()` из `services/migration_log.py`. Если
запись с именем файла уже есть в `schema_migration_log` — миграция
пропускается. После успешного выполнения скрипт вызывает
`register_migration()`.

### Пронумерованный порядок применения

1. **Alembic-миграции** (`alembic_migrations/versions/`) — ядро схемы
   через `flask db upgrade`. Создаёт все таблицы, объявленные в ORM.

2. **`scripts/d4_migration.py`** — колонки `figure_credits`, `figures_built`
   в `users`; таблицы `figure_generations`, `figure_credit_transactions`,
   `figure_email_subscriptions`. Требует `users`.

3. **`scripts/ch5_migration.py`** — таблица `figure_build_jobs`.
   Требует `users` (FOREIGN KEY).

4. **ALTER-правки Ч8** — колонки `aux_svg_path`, `has_aux`, `aux_reason`
   в `adaptive_tasks`, `daily_task_items`, `figure_build_jobs`, `method_tasks`.

5. **ALTER-правки Ч10** — колонки `kimi_review_probe`, `kimi_review_daily`,
   `kimi_review_method` в `users`; таблица `kimi_reviews`.

6. **`scripts/p4_debt_migration.py`** — колонки `debt_status`, `debt_until`
   в `daily_task_items`. Требует `daily_task_items`.

7. **`scripts/p9_intake_migration.py`** — ORM-заполнение
   `CuratorState.prep_state.intake`. Схему не меняет.

### Проверка на PostgreSQL перед продом

Каждая миграция, содержащая сырой SQL, перед запуском на проде Render
проверяется на локальной копии PostgreSQL. Для этого используется
Docker-контейнер:

```
docker run --rm -d --name formyla_pg_check \
  -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16
```

После проверки:

```
docker stop formyla_pg_check
```

Ни одна миграция не запускается на проде без предварительной проверки
на локальном PostgreSQL.

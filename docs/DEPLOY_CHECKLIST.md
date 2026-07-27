# DEPLOY CHECKLIST — Ручная заливка FORMYLA L1-L5 TOP5 на прод

**Дата составления**: 2026-07-27
**Исполнитель**: человек с доступом к Render Dashboard
**Цель**: добавить колонки `origin`/`methods_json`, залить 3288 задач из
`FORMYLA_L1_L5_TOP5.jsonl`, скрыть их флагом `is_flagged=True`.

**Ключевое изменение** (2026-07-27): файл `FORMYLA_L1_L5_TOP5.jsonl` (18,8 МБ)
**НЕ** пушится в репозиторий. `.gitignore` **НЕ** меняется — строка `*.jsonl`
остаётся как есть. Импортёр запускается **локально** и пишет напрямую в
продовый Postgres через строку подключения из `.env.migration`.

---

# ЧАСТЬ 1. СВЕРКА ПРЕДПОСЫЛОК

Выполните эти SELECT-запросы на проде ДО любых изменений.
Все запросы — read-only.

## Как подключиться к psql на Render

1. Откройте Render Dashboard → сервис `formyla-com` → вкладка «Shell» (или пункт
   меню с функцией «открыть терминал на сервере»).
2. В открывшемся терминале наберите:

```bash
psql "$DATABASE_URL"
```

3. Должно появиться приглашение `formyla=>`. Если нет — СТОП.

---

## Запрос 1.1 — количество строк в adaptive_tasks

```sql
SELECT COUNT(*) FROM adaptive_tasks;
```

**Ожидаемый результат согласно аудиту**: `8778`.

| Если результат | Действие |
|---|---|
| 8778 | ✅ Ок, идём дальше |
| Другое число | ⚠️ Запишите фактическое число. Если строк 0 — СТОП. Если больше — продолжайте, но в отчёте укажите расхождение. |

---

## Запрос 1.2 — распределение по source

```sql
SELECT source, COUNT(*) FROM adaptive_tasks GROUP BY source ORDER BY COUNT(*) DESC;
```

**Ожидаемый результат согласно аудиту**:

```
deepseek | 8778
```

| Если результат | Действие |
|---|---|
| Только `deepseek`, 8778 | ✅ Ок |
| Есть другие source | ⚠️ Запишите. Если уже есть `formyla_L1_L5_TOP5` — значит импорт уже делали. Выясните когда. |
| Пустой результат | СТОП — таблица пуста или колонка source отсутствует |

---

## Запрос 1.3 — существующие колонки

```sql
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'adaptive_tasks'
ORDER BY ordinal_position;
```

**Ожидаемый результат согласно аудиту**: 31 колонка. Колонки `origin` и
`methods_json` должны **ОТСУТСТВОВАТЬ**.

| Если результат | Действие |
|---|---|
| 31 колонка, `origin`/`methods_json` отсутствуют | ✅ Ок |
| Колонки `origin` и `methods_json` уже есть | ⚠️ Кто-то уже добавил. Проверьте, есть ли в них данные: `SELECT origin, methods_json FROM adaptive_tasks WHERE origin IS NOT NULL LIMIT 5`. Если есть данные — импорт уже делали. |
| Колонок < 25 | СТОП — схема не соответствует ожидаемой |

---

## Запрос 1.4 — количество пользователей

```sql
SELECT COUNT(*) FROM users;
```

**Ожидаемый результат согласно аудиту**: `9039`.

```sql
SELECT COUNT(*) FROM users WHERE last_login IS NOT NULL;
```

**Ожидаемый результат согласно аудиту**: `26`.

| Если результат | Действие |
|---|---|
| Совпадает ±10% | ✅ Ок |
| Расходится в разы | ⚠️ Запишите фактические числа |

---

## Запрос 1.5 — тип колонки source

```sql
SELECT data_type, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'adaptive_tasks' AND column_name = 'source';
```

**Ожидаемый результат согласно аудиту**: `character varying | 50`.

Также проверьте default:

```sql
SELECT column_default
FROM information_schema.columns
WHERE table_name = 'adaptive_tasks' AND column_name = 'source';
```

**Ожидаемый результат**: `'deepseek'::character varying`.

| Если не `character varying(50)` | ⚠️ Запишите фактический тип. Авто-ALTER попытается создать `TEXT`. Возможен конфликт: колонка уже есть с типом VARCHAR(50), авто-ALTER увидит её и пропустит — ок. |

---

## Запрос 1.6 — колонка original_difficulty

```sql
SELECT original_difficulty, COUNT(*)
FROM adaptive_tasks
GROUP BY original_difficulty
ORDER BY COUNT(*) DESC
LIMIT 20;
```

**Ожидаемый результат согласно аудиту**: колонка существует (VARCHAR(50)),
значения — строковые метки (не числа). В коде не используется.

| Если колонка есть | ✅ Ок, просто зафиксируйте что в ней |
| Если колонки нет | ⚠️ Возможно, миграция `migrations/add_task_source.py` не выполнялась на проде. Не критично для данной операции. |

---

## Запрос 1.7 — есть ли строки с source='formyla_L1_L5_TOP5'

```sql
SELECT COUNT(*) FROM adaptive_tasks WHERE source = 'formyla_L1_L5_TOP5';
```

**Ожидаемый результат**: `0` (импорт ещё не делали).

| Если > 0 | ⚠️ Импорт уже делали. Выясните, кто и когда. Возможно, достаточно обновить существующие строки. |

---

## Запрос 1.8 — количество зафлаженных задач (НОВЫЙ)

```sql
SELECT COUNT(*) FROM adaptive_tasks WHERE is_flagged = TRUE;
```

**Ожидаемый результат**: точное число зафиксируйте. До импорта должно быть 0 или
небольшое число (задачи, помеченные вручную).

| Если > 100 | ⚠️ Возможно, предыдущий импорт уже выполнялся с флагом. Сверьте с 1.7. |

---

## Запрос 1.9 — полная схема adaptive_tasks (НОВЫЙ)

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'adaptive_tasks'
ORDER BY ordinal_position;
```

Этот запрос показывает **все** колонки прода одним списком, а не выборочно.
Сохраните вывод — он пригодится для сверки после деплоя и для отладки,
если что-то пойдёт не так.

**Ожидаемый результат**: 31 колонка (до добавления `origin`/`methods_json`).
Сверьте с известной схемой: `id`, `class_level`, `difficulty_level`, `topic`,
`subtopic`, `task_text`, `solution`, `criteria_1_point`, `criteria_2_points`,
`created_at`, `correct_answer`, `is_flagged`, `reports_count`, `flagged_reason`,
`attempts_count`, `solves_count`, `actual_solve_rate`, `suggested_level`,
`needs_reclassification`, `last_calibrated_at`, `subject`, `source_id`,
`task_type`, `source`, `needs_review`, `llm_suggested_answer`,
`llm_suggested_solution`, `review_reason`, `review_flagged_at`,
`original_difficulty`, `source_url`, `image_urls`.

---

# ЧАСТЬ 2. СНАПШОТ БАЗЫ ДАННЫХ

## Шаг 2.1 — Ручной снапшот через Render Dashboard

1. Откройте Render Dashboard.
2. Перейдите в раздел баз данных → `formyla-db`.
3. Найдите секцию «Backups» или «Snapshots».
4. Нажмите кнопку с функцией «создать ручной бэкап/снапшот» (manual backup /
   create snapshot).
5. Дождитесь статуса «Completed» / «Available».

**Результат**: в списке бэкапов появилась новая запись с текущей датой.

**Критерий СТОП**: если кнопка недоступна или снапшот завершился с ошибкой —
не продолжайте. Свяжитесь с Render support.

## Шаг 2.2 — Дополнительный pg_dump (рекомендовано)

В Render Shell сервиса `formyla-com`:

```bash
pg_dump "$DATABASE_URL" --no-owner --no-acl > /tmp/formyla_backup_$(date +%Y%m%d_%H%M%S).sql
```

```bash
ls -lh /tmp/formyla_backup_*.sql
```

**Результат**: виден файл размером несколько мегабайт.

**Критерий СТОП**: если `pg_dump` не найден или файл пустой — СТОП.

---

# ЧАСТЬ 3. ДЕПЛОЙ КОДА

Перед импортом необходимо убедиться, что на проде работает актуальный код
с колонками `origin`/`methods_json` в ORM-модели и в авто-ALTER.

## Шаг 3.1 — Проверить, что код на проде актуален

В Render Dashboard → сервис `formyla-com` → последний деплой:
- Убедитесь, что деплой от коммита, содержащего `origin`/`methods_json` в
  [`models.py:857-859`](models.py:857) и авто-ALTER в
  [`app.py:316-317`](app.py:316).

Если последний деплой старше этих изменений — сделайте push актуального кода
и дождитесь успешного деплоя.

## Шаг 3.2 — Проверить, что авто-ALTER отработал

После деплоя авто-ALTER ([`app.py:297-327`](app.py:297)) должен добавить
колонки `origin` и `methods_json`, если их ещё нет. Проверьте:

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'adaptive_tasks'
  AND column_name IN ('origin', 'methods_json');
```

**Ожидаемый результат**:

```
origin       | character varying
methods_json | text
```

**Если колонок нет**: выполните вручную (Шаг 4.1).

---

# ЧАСТЬ 4. ПРОВЕРКА КОЛОНОК

## Шаг 4.1 — Добавить колонки вручную (если авто-ALTER не сработал)

В psql-сессии (открытой в Части 1):

```sql
ALTER TABLE adaptive_tasks ADD COLUMN IF NOT EXISTS origin VARCHAR(16);
ALTER TABLE adaptive_tasks ADD COLUMN IF NOT EXISTS methods_json TEXT;
```

**Результат**: `ALTER TABLE` — без ошибок.

## Шаг 4.2 — Проверить

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'adaptive_tasks'
  AND column_name IN ('origin', 'methods_json');
```

**Ожидаемый результат**:

```
origin       | character varying
methods_json | text
```

**Критерий СТОП**: если колонок нет в выводе — ALTER не сработал. Проверьте
сообщение об ошибке.

---

# ЧАСТЬ 5. ПРОВЕРКА ЖИВОСТИ САЙТА

Перед импортом убедитесь, что сайт работает после деплоя.

## Шаг 5.1 — Health-check

Откройте в браузере: `https://formyla.com/healthz`

**Результат**: `OK` или `{"status":"ok"}`.

Если 502/503 — проверьте логи деплоя в Render Dashboard.

## Шаг 5.2 — Проверить главную страницу

Откройте `https://formyla.com/` — должна загрузиться без ошибок.

## Шаг 5.3 — Проверить адаптивный тест

Зайдите под тестовым аккаунтом → адаптивный тест → убедитесь, что задачи
выдаются (старые, deepseek).

---

# ЧАСТЬ 6. ИМПОРТ ЛОКАЛЬНО В ПРОД

**Ключевое**: импортёр [`scripts/import_formyla_jsonl.py`](scripts/import_formyla_jsonl.py)
запускается **на вашей локальной машине**, а пишет напрямую в продовый Postgres.
Файл `FORMYLA_L1_L5_TOP5.jsonl` (18,8 МБ) **НЕ** пушится в git, **НЕ** попадает
на Render. `.gitignore` **не меняется** — строка `*.jsonl` остаётся.

## Как импортёр получает подключение к БД

Импортёр в [`scripts/import_formyla_jsonl.py:787-799`](scripts/import_formyla_jsonl.py:787)
сначала пытается импортировать `app` из [`app.py`](app.py). В [`app.py:178`](app.py:178)
строка подключения берётся из переменной окружения:

```python
_database_url = os.environ.get('DATABASE_URL', 'sqlite:///formyla.db')
```

Если импорт `app` не удаётся, импортёр создаёт минимальное Flask-приложение и
тоже читает `DATABASE_URL` ([`import_formyla_jsonl.py:795-797`](scripts/import_formyla_jsonl.py:795)):

```python
flask_app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///database.db"
)
```

**Вывод**: чтобы направить импортёр в продовую базу, достаточно установить
переменную окружения `DATABASE_URL`. Правка кода **НЕ** требуется.

## Совместимость с PostgreSQL (проверено)

Импортёр использует SQLAlchemy ORM и **не содержит** кода, специфичного для SQLite:

- **PRAGMA**: не используется.
- **Сырой SQL**: не используется — все операции через `db.session`, `AdaptiveTask.query`, ORM-методы.
- **Даты**: [`datetime.utcnow`](scripts/import_formyla_jsonl.py:18) — работает на обеих СУБД.
- **Boolean / is_flagged**: модель объявляет [`is_flagged = db.Column(db.Boolean, ...)`](models.py:831). SQLAlchemy прозрачно маппит Python `True`/`False` в PostgreSQL `TRUE`/`FALSE` (и обратно). Импортёр присваивает `task.is_flagged = True` — это корректно на PostgreSQL.
- **Upsert-логика**: импортёр делает `SELECT ... WHERE source_id = ?`, затем либо `UPDATE`, либо `INSERT`. Это диалект-независимый паттерн, работает одинаково на SQLite и PostgreSQL.
- **Авто-ALTER**: в [`app.py:412-414`](app.py:412) уже есть ветвление `BOOLEAN DEFAULT FALSE` для PG vs `BOOLEAN DEFAULT 0` для SQLite, но импортёр этот код не вызывает при локальном запуске — колонки `origin`/`methods_json` уже должны существовать к моменту импорта.

**Заключение**: импортёр полностью совместим с PostgreSQL без каких-либо правок.

## Шаг 6.0 — Безопасно взять строку подключения

Строка подключения к продовой базе уже сохранена в
[`.env.migration`](.env.migration):

```
EXTERNAL_DATABASE_URL=postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require
```

**Внимание**: переменная называется `EXTERNAL_DATABASE_URL`, а импортёр ожидает
`DATABASE_URL`. При запуске нужно либо переименовать переменную, либо задать обе.
Рекомендуемый способ — задать `DATABASE_URL` только на время выполнения команды,
чтобы случайно не оставить её в окружении:

**Windows (CMD)**:
```cmd
set DATABASE_URL=postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require
```

**PowerShell**:
```powershell
$env:DATABASE_URL="postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require"
```

## Шаг 6.1 — Контрольный SELECT: убедиться, что подключение ведёт в прод

**ПЕРЕД** запуском импортёра выполните проверочный запрос, который однозначно
идентифицирует продовую базу:

```bash
python -c "
import os
os.environ['DATABASE_URL'] = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
from app import app
with app.app_context():
    from models import AdaptiveTask
    total = AdaptiveTask.query.count()
    deepseek = AdaptiveTask.query.filter_by(source='deepseek').count()
    print(f'TOTAL adaptive_tasks: {total}')
    print(f'deepseek rows: {deepseek}')
    print(f'DB URI: {app.config[\"SQLALCHEMY_DATABASE_URI\"][:80]}...')
"
```

**Ожидаемый результат**:
```
TOTAL adaptive_tasks: 8778
deepseek rows: 8778
DB URI: postgresql+psycopg://formyla_user:...@dpg-...
```

**Критерий СТОП**:
- Если `TOTAL` ≠ 8778 — вы подключились НЕ к продовой базе, или база изменилась. СТОП.
- Если `deepseek rows` ≠ 8778 — то же самое. СТОП.
- Если в URI видно `sqlite:///` — переменная окружения не применилась. СТОП.
- Если ошибка `could not connect` — проверьте VPN/брандмауэр: порт 5432 должен быть доступен до `dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com`.

Ещё один способ — выполнить запрос, который на локальной SQLite-базе вернёт
другой результат (или ошибку):

```bash
python -c "
import os
os.environ['DATABASE_URL'] = 'postgresql://formyla_user:...'
from app import app
with app.app_context():
    from models import db
    r = db.session.execute(db.text('SELECT current_database(), current_user, version()')).fetchone()
    print(f'DB: {r[0]}, User: {r[1]}')
    print(f'PG version: {r[2][:60]}...')
"
```

**Ожидаемый результат**:
```
DB: formyla, User: formyla_user
PG version: PostgreSQL 16.x ...
```

Если вы видите `current_database()` и `version()` — вы гарантированно на PostgreSQL,
а не на локальном SQLite (где эти функции не существуют).

## Шаг 6.2 — DRY-RUN импорта (без записи)

```bash
python scripts/import_formyla_jsonl.py --file FORMYLA_L1_L5_TOP5.jsonl
```

**Результат**: отчёт в stdout. Последняя строка:
```
📄 Markdown отчёт сохранён в: scripts/out/import_report.md
```

Ключевые строки отчёта (сверьте):

```
Прочитано строк: 3288
Создано: 0
Обновлено: 0
Пропущено: 0
```

(0 создано/обновлено потому что это dry-run.)

**Критерий СТОП**:
- Если `Прочитано строк` ≠ 3288 — проблема с файлом.
- Если есть `[PARSE ERROR]` — файл повреждён.
- Если `SCHEMA BLOCKER` — колонки не добавились (вернитесь к Части 4).
- Если `Ошибок валидации` > 0 — проверьте отчёт.

## Шаг 6.3 — Прочитать полный отчёт

```bash
cat scripts/out/import_report.md
```

Убедитесь, что таблица `Grade × Level Grid` соответствует ожиданиям:
каждый grade (5–11) × level (1–5) содержит задачи.

## Шаг 6.4 — Запустить импорт с флагом is_flagged=True (ЗАПИСЬ)

```bash
python scripts/import_formyla_jsonl.py --file FORMYLA_L1_L5_TOP5.jsonl --apply --flagged
```

**Результат (ожидаемый)**:

```
Прочитано строк: 3288
Создано: 3288
Обновлено: 0
Пропущено: 0
Ошибок записи: 0
Помечено скрытыми (is_flagged=True): 3288
```

## Шаг 6.5 — Оценка времени выполнения

- **3288 строк**, запись пакетами по **50** → 66 пакетов.
- Каждый пакет: ~50 `SELECT` по индексу `source_id` + ~50 `INSERT` + 1 `COMMIT`.
- Сетевая задержка до Ohio (Render PostgreSQL): ~50–100 мс на запрос.
- Оценка: **2–5 минут** при стабильном соединении.
- При нестабильном соединении может быть дольше из-за повторных попыток.

## Шаг 6.6 — Что делать при обрыве связи

Импортёр **идемпотентен** по полю `source_id` = `task_uid`. Логика:

1. Для каждой строки выполняется `SELECT ... WHERE source_id = ?` ([`import_formyla_jsonl.py:367-369`](scripts/import_formyla_jsonl.py:367)).
2. Если запись найдена — она **обновляется** (UPDATE).
3. Если не найдена — создаётся новая (INSERT).
4. Каждый пакет коммитится отдельно ([`import_formyla_jsonl.py:417`](scripts/import_formyla_jsonl.py:417)).
5. При ошибке пакета — rollback и построчный повтор с индивидуальными commit'ами ([`import_formyla_jsonl.py:420-490`](scripts/import_formyla_jsonl.py:420)).

**Следствие**: при обрыве связи часть пакетов уже закоммичена. Повторный запуск
с теми же параметрами (`--apply --flagged`) безопасен:

- Уже записанные строки будут найдены по `source_id` → UPDATE (перезапись теми же данными).
- Не записанные строки → INSERT.
- Ни одна строка не будет продублирована.

**Действие при обрыве**: дождитесь завершения (или Ctrl+C), затем просто
запустите ту же команду ещё раз. Итоговый результат будет идентичен.

---

# ЧАСТЬ 7. ПРОВЕРКИ ПОСЛЕ ИМПОРТА

## Шаг 7.1 — Количество импортированных строк

```sql
SELECT COUNT(*) FROM adaptive_tasks WHERE source = 'formyla_L1_L5_TOP5';
```

**Ожидаемый результат**: `3288`.

```sql
SELECT COUNT(*) FROM adaptive_tasks
WHERE source = 'formyla_L1_L5_TOP5' AND is_flagged = TRUE;
```

**Ожидаемый результат**: `3288` (все помечены скрытыми).

```sql
SELECT COUNT(*) FROM adaptive_tasks;
```

**Ожидаемый результат**: `8778 + 3288 = 12066`.

**Критерий СТОП**:
- Если `COUNT WHERE source = 'formyla_L1_L5_TOP5'` = 0 — импорт не сработал.
- Если число ≠ 3288 — часть строк не записалась. Запустите импорт повторно (он идемпотентен, см. Шаг 6.6).
- Если `is_flagged = TRUE` < 3288 — не все скрыты. Можно дофлагать:
  ```sql
  UPDATE adaptive_tasks
  SET is_flagged = TRUE, flagged_reason = 'formyla_import_pending_scale_mapping'
  WHERE source = 'formyla_L1_L5_TOP5' AND is_flagged = FALSE;
  ```

## Шаг 7.2 — Проверить выборочно содержимое

```sql
SELECT id, class_level, difficulty_level, topic, subject, origin, is_flagged
FROM adaptive_tasks
WHERE source = 'formyla_L1_L5_TOP5'
LIMIT 10;
```

**Ожидаемый результат**: 10 строк с `is_flagged = TRUE`, `origin` = `'generated'`
или `'olympiad'`, `difficulty_level` 1–5, `class_level` 5–11.

```sql
SELECT id, methods_json
FROM adaptive_tasks
WHERE source = 'formyla_L1_L5_TOP5' AND methods_json IS NOT NULL
LIMIT 5;
```

**Ожидаемый результат**: 5 строк с непустым JSON-массивом методов.

## Шаг 7.3 — Финальная сверка

```sql
SELECT source, is_flagged, COUNT(*)
FROM adaptive_tasks
GROUP BY source, is_flagged
ORDER BY source, is_flagged;
```

**Ожидаемый результат**:

```
deepseek              | FALSE | 8778
formyla_L1_L5_TOP5    | TRUE  | 3288
```

(Может быть `deepseek | TRUE` если были зафлажены вручную — ок.)

## Шаг 7.4 — Распределение новых задач по grade × level

```sql
SELECT class_level, difficulty_level, COUNT(*)
FROM adaptive_tasks
WHERE source = 'formyla_L1_L5_TOP5'
GROUP BY class_level, difficulty_level
ORDER BY class_level, difficulty_level;
```

**Ожидаемый результат**: каждая ячейка grade∈{5..11} × level∈{1..5} содержит ~5 задач.

---

# ЧАСТЬ 8. ПРОВЕРКА ВЫДАЧИ УЧЕНИКУ

Убедитесь, что новые задачи **не попадают** в выдачу пользователям.

## Шаг 8.1 — Проверить Prep Planner

Prep Planner фильтрует `is_flagged = False` ([`services/prep_planner.py:392`](services/prep_planner.py:392)) —
новые задачи с `is_flagged = TRUE` должны исключаться.

В psql выполните аналог запроса Prep Planner:

```sql
SELECT COUNT(*) FROM adaptive_tasks
WHERE class_level IN (5, 6, 7, 8, 9, 10, 11)
  AND difficulty_level BETWEEN 1 AND 8
  AND is_flagged = FALSE;
```

**Результат**: должно быть 8778 (только старые deepseek-задачи).

## Шаг 8.2 — Проверить task_selection (централизованный base_query)

Централизованный `base_query` ([`services/task_selection.py:52`](services/task_selection.py:52)):

```sql
SELECT COUNT(*) FROM adaptive_tasks
WHERE is_flagged = FALSE;
```

**Результат**: 8778.

## Шаг 8.3 — Проверить адаптивный тест (режим А)

Адаптивный тест фильтрует через `base_query` → `is_flagged == False`.
Запрос эквивалентен 8.2.

## Шаг 8.4 — Ручная проверка на сайте

Зайдите под тестовым аккаунтом → откройте адаптивный тест → решите
несколько задач. Убедитесь, что:

- Задачи имеют `source = 'deepseek'` (старые).
- Задачи с `source = 'formyla_L1_L5_TOP5'` не появляются.
- Счётчики задач и уровни не изменились по сравнению с ожидаемыми.

**Критерий СТОП**: если новая задача с `source = 'formyla_L1_L5_TOP5'`
появилась в выдаче — проверьте `is_flagged` для этих строк (см. 7.1).

---

# ЧАСТЬ 9. ОТКАТ

## Способ 9А — Восстановление из снапшота Render (рекомендовано)

1. Render Dashboard → `formyla-db` → Backups.
2. Найдите снапшот, созданный в Шаге 2.1 (дата сегодняшняя).
3. Нажмите кнопку с функцией «Restore» / «Восстановить».
4. Подтвердите действие.

**Результат**: Render восстановит БД из снапшота. Сервис может быть недоступен
несколько минут.

**Критерий СТОП**: если кнопка Restore недоступна или процесс завершился ошибкой —
используйте способ 9Б.

## Способ 9Б — Ручное удаление импортированных строк

Если снапшот недоступен, можно удалить строки вручную:

```sql
DELETE FROM adaptive_tasks WHERE source = 'formyla_L1_L5_TOP5';
```

**Результат**: `DELETE 3288`.

```sql
SELECT COUNT(*) FROM adaptive_tasks;
```

**Результат**: `8778` (вернулись к исходному).

**Критерий СТОП**: если число не 8778 — проверьте, что удалились только нужные строки.

## Способ 9В — Восстановление из pg_dump

Если делали `pg_dump` в Шаге 2.2:

```bash
psql "$DATABASE_URL" < /tmp/formyla_backup_YYYYMMDD_HHMMSS.sql
```

**Критерий СТОП**: если файл дампа не найден — этот способ недоступен.

---

# ПРИЛОЖЕНИЕ А. ЧТО ДЕЛАЕТ КАЖДЫЙ КОМПОНЕНТ

| Компонент | Файл | Роль |
|---|---|---|
| Импортёр | [`scripts/import_formyla_jsonl.py`](scripts/import_formyla_jsonl.py) | Читает JSONL → валидирует → пишет в `adaptive_tasks` |
| Авто-ALTER | [`app.py:297-327`](app.py:297) | Добавляет колонки `origin`/`methods_json` при старте, если их нет |
| Prep Planner | [`services/prep_planner.py:389-393`](services/prep_planner.py:389) | Выбирает задачи для пользователя, фильтрует `is_flagged=False` |
| Task Selection | [`services/task_selection.py:40-53`](services/task_selection.py:40) | `base_query()` — центральный фильтр, `is_flagged=False` |
| Миграция source | [`migrations/add_task_source.py:23-27`](migrations/add_task_source.py:23) | Создала колонки `source`/`source_url`/`original_difficulty` |
| Render конфиг | [`render.yaml`](render.yaml) | Определяет `startCommand`, `buildCommand`, `envVars` |

---

# ПРИЛОЖЕНИЕ Б. ПОЛЕЗНЫЕ КОМАНДЫ PSQL

```sql
-- Показать все таблицы
\dt

-- Показать колонки adaptive_tasks
\d adaptive_tasks

-- Размер таблицы
SELECT pg_size_pretty(pg_total_relation_size('adaptive_tasks'));

-- Выйти из psql
\q
```

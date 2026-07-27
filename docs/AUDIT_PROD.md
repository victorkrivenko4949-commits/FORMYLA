# AUDIT PROD — adaptive_tasks: колонки `origin` + `methods_json`

**Дата**: 2026-07-26
**Аудитор**: авто-аудит (read-only, без изменений кода и БД)
**Контекст**: локально в SQLite (formyla.db) таблица `adaptive_tasks` содержит 3288 строк с `source='formyla_L1_L5_TOP5'` и две новые колонки `origin`/`methods_json`. На продакшене Render.com — PostgreSQL, 8778 строк с `source='deepseek'`. Нужно понять, доставятся ли изменения на прод при следующем деплое.

---

## ВОПРОС 1. Совместимость блока авто-ALTER с PostgreSQL

### Блок целиком (app.py, строки 297–327)

```python
# AUTO-MIGRATION: Add difficulty calibration columns to adaptive_tasks
try:
    with app.app_context():
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if 'adaptive_tasks' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('adaptive_tasks')]
            new_cols = {
                'subtopic': 'VARCHAR(100)',
                'attempts_count': 'INTEGER DEFAULT 0',
                'solves_count': 'INTEGER DEFAULT 0',
                'actual_solve_rate': 'REAL',
                'suggested_level': 'INTEGER',
                'needs_reclassification': 'BOOLEAN DEFAULT 0',
                'last_calibrated_at': 'DATETIME',
                # Поля для адаптивного сидера (services/adaptive_full_seed.py).
                # Используются для idempotency и трассировки источника датасета.
                'task_type': 'TEXT',
                'source': 'TEXT',
                'origin': 'VARCHAR(16)',
                'methods_json': 'TEXT',
            }
            for col_name, col_type in new_cols.items():
                if col_name not in columns:
                    db.session.execute(text(f"ALTER TABLE adaptive_tasks ADD COLUMN {col_name} {col_type}"))
                    db.session.commit()
                    print(f"[AUTO-MIGRATION] ✓ Column '{col_name}' added to adaptive_tasks")
                else:
                    print(f"[AUTO-MIGRATION] ✓ Column '{col_name}' already exists")
except Exception as e:
    print(f"[AUTO-MIGRATION] adaptive_tasks Warning: {e}")
```

### Анализ каждого вызова

| Вызов | Назначение | SQLite | PostgreSQL | Вердикт |
|---|---|---|---|---|
| [`inspect(db.engine)`](app.py:300) | SQLAlchemy reflection API | ✅ | ✅ | **Переносим** |
| [`inspector.get_table_names()`](app.py:302) | Получить список таблиц | ✅ | ✅ | **Переносим** |
| [`inspector.get_columns('adaptive_tasks')`](app.py:303) | Получить список колонок таблицы | ✅ | ✅ | **Переносим** |
| [`text(f"ALTER TABLE … ADD COLUMN …")`](app.py:321) | Выполнить DDL | ✅ | ✅ | **Переносим** (стандартный SQL) |

### Ключевой вывод

**Блок НЕ использует `PRAGMA table_info`.** Он использует SQLAlchemy `inspect()` — полностью переносимый API рефлексии, работающий и на SQLite, и на PostgreSQL. Ни одного SQLite-специфичного вызова.

### Нет ли ветвления по типу СУБД?

**Нет.** В этом блоке (строки 297–327) нет проверки `_database_url.startswith('postgresql')`. Все типы колонок жёстко закодированы.

Для сравнения: второй блок авто-ALTER (строки 407–434, колонки `needs_review`) **имеет** ветвление:
```python
_is_pg_nr = _database_url.startswith('postgresql')
_bool_default_false = 'BOOLEAN DEFAULT FALSE' if _is_pg_nr else 'BOOLEAN DEFAULT 0'
```
Но блок с `origin`/`methods_json` — без ветвления.

### Совместимость типов в ALTER TABLE

| Тип в авто-ALTER | SQLAlchemy-модель | PostgreSQL принимает? | Совпадает с генерируемым SA? |
|---|---|---|---|
| [`VARCHAR(16)`](app.py:316) | [`db.String(16)`](models.py:857) | ✅ Да (алиас `character varying(16)`) | ✅ Да |
| [`TEXT`](app.py:317) | [`db.Text`](models.py:859) | ✅ Да | ✅ Да |
| `BOOLEAN DEFAULT 0` | `db.Boolean(default=False)` | ✅ Да (0 → FALSE) | ⚠️ Не идиоматично, но работает |
| `REAL` | `db.Float` | ✅ Да (float4) | ⚠️ SA `Float` даёт `DOUBLE PRECISION` (float8), но SA читает любой float-тип |

### Что произойдёт на проде при деплое?

При следующем деплое на Render:

1. Gunicorn импортирует [`app.py`](app.py:1) → выполняются авто-ALTER блоки при загрузке модуля.
2. [`inspector.get_columns('adaptive_tasks')`](app.py:303) вернёт список из 31 колонки (те, что сейчас в прод-Postgres).
3. Колонки `origin` и `methods_json` **отсутствуют** в этом списке (см. ВОПРОС 3).
4. Сработает условие `if col_name not in columns` → выполнится:
   ```sql
   ALTER TABLE adaptive_tasks ADD COLUMN origin VARCHAR(16)
   ALTER TABLE adaptive_tasks ADD COLUMN methods_json TEXT
   ```
5. **Обе колонки будут успешно созданы.** Приложение стартует без ошибок.

**Итог**: текущий код **сработает** на проде. Блок корректен для PostgreSQL. Исключений не будет, приложение не упадёт.

### Что может пойти не так

- **`BOOLEAN DEFAULT 0`** — на PostgreSQL работает (0 кастуется в FALSE), но лог может содержать warning. Не критично.
- **`REAL`** — расхождение с ORM-моделью (`db.Float` → `DOUBLE PRECISION`). На практике SQLAlchemy читает оба типа без ошибок.
- Если прод-таблица заблокирована долгим запросом — ALTER TABLE повиснет в ожидании блокировки. На пустой/малонагруженной таблице (8778 строк) это маловероятно.

---

## ВОПРОС 2. Как устроен запуск на Render

### render.yaml (полностью)

Файл [`render.yaml`](render.yaml) — единственный конфигурационный файл деплоя:

```yaml
databases:
  - name: formyla-db
    plan: pro-8gb
    databaseName: formyla
    user: formyla

services:
  - type: web
    name: formyla-com
    env: python
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: >-
      flask db upgrade --directory alembic_migrations &&
      gunicorn app:app --workers 1 --threads 4 --worker-class gthread
      --timeout 120 --graceful-timeout 30 --bind 0.0.0.0:$PORT
    healthCheckPath: /healthz
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: formyla-db
          property: connectionString
      - key: FLASK_APP
        value: app.py
      - key: FLASK_ENV
        value: production
      - key: OLYMPIAD_AUTOSEED
        value: "1"
      - key: VSOSH9_2027_FORCE_IMPORT
        value: "1"
      - key: ADAPTIVE_FORCE_IMPORT
        value: "1"
      # … секреты (SECRET_KEY, API_KEY и т.д.) с sync: false
```

### Dockerfile / Procfile

**Отсутствуют.** Render использует native Python environment (определяет по `env: python` в render.yaml). Зависимости ставятся через `pip install -r requirements.txt`.

### Что выполняется при деплое ДО старта приложения

Порядок выполнения (из [`render.yaml:45-47`](render.yaml:45)):

```
1. pip install -r requirements.txt       # buildCommand
2. flask db upgrade --directory alembic_migrations   # startCommand, часть 1
3. gunicorn app:app --workers 1 ...     # startCommand, часть 2
```

**Шаг 2 — миграции Alembic.** Единственная существующая миграция:
- [`alembic_migrations/versions/2d601690bdfd_add_olympiad_pipeline_tables.py`](alembic_migrations/versions/2d601690bdfd_add_olympiad_pipeline_tables.py) — создаёт таблицы `olympiad_variants`, `olympiad_tasks`, `olympiad_task_attempts`. **НЕ трогает `adaptive_tasks`.**

Авто-ALTER блоки из [`app.py`](app.py:297) выполняются на шаге 3 — при импорте модуля `app.py` внутри Gunicorn, до того как worker начнёт принимать HTTP-запросы. Они выполняются при каждом запуске, без каких-либо условий (кроме `try/except`).

### Откуда берётся DATABASE_URL

Из [`render.yaml:56-58`](render.yaml:56):
```yaml
- key: DATABASE_URL
  fromDatabase:
    name: formyla-db
    property: connectionString
```

Render **автоматически инжектит** `DATABASE_URL` в переменные окружения сервиса из привязанной managed database `formyla-db`. Строка подключения имеет формат `postgres://user:pass@host:port/dbname`.

В коде [`app.py:178-183`](app.py:178) URL преобразуется:
```python
_database_url = os.environ.get('DATABASE_URL', 'sqlite:///formyla.db')
if _database_url.startswith('postgres://'):
    _database_url = _database_url.replace('postgres://', 'postgresql+psycopg://', 1)
```

### Запускается ли авто-ALTER под условием, которое ложно на проде?

**Нет.** Блок авто-ALTER (строки 297–327) — это безусловный код на уровне модуля `app.py`. Он выполняется при каждом импорте, в любом окружении. Единственное условие — существование таблицы `adaptive_tasks` (строка 302), которая на проде есть.

Для сравнения: сидер `ADAPTIVE_FORCE_IMPORT` (строки 1114–1124) действительно под условием `os.environ.get('ADAPTIVE_FORCE_IMPORT', '0') == '1'`. Но авто-ALTER — безусловный.

---

## ВОПРОС 3. Что сейчас в прод-базе

### Доступ

Строка подключения найдена в файле [`.env.migration`](.env.migration):
```
EXTERNAL_DATABASE_URL=postgresql://formyla_user:...@dpg-...ohio-postgres.render.com/formyla?sslmode=require
```

### Результаты (только SELECT, read-only)

**Таблица `adaptive_tasks`**: ✅ существует.

**Полный список колонок с типами** (из `information_schema.columns`):

| Колонка | Тип PostgreSQL | Длина | Nullable | Default |
|---|---|---|---|---|
| `id` | integer | – | NO | `nextval('adaptive_tasks_id_seq')` |
| `class_level` | integer | – | NO | – |
| `difficulty_level` | integer | – | NO | – |
| `topic` | character varying | 200 | NO | – |
| `subtopic` | character varying | 100 | YES | – |
| `task_text` | text | – | NO | – |
| `solution` | text | – | NO | – |
| `criteria_1_point` | text | – | NO | – |
| `criteria_2_points` | text | – | NO | – |
| `created_at` | timestamp w/o tz | – | YES | – |
| `correct_answer` | text | – | YES | – |
| `is_flagged` | boolean | – | YES | – |
| `reports_count` | integer | – | YES | – |
| `flagged_reason` | text | – | YES | – |
| `attempts_count` | integer | – | YES | – |
| `solves_count` | integer | – | YES | – |
| `actual_solve_rate` | double precision | – | YES | – |
| `suggested_level` | integer | – | YES | – |
| `needs_reclassification` | boolean | – | YES | – |
| `last_calibrated_at` | timestamp w/o tz | – | YES | – |
| `source` | character varying | 50 | YES | `'deepseek'::varchar` |
| `source_url` | character varying | 500 | YES | – |
| `original_difficulty` | character varying | 50 | YES | – |
| `needs_review` | boolean | – | YES | false |
| `llm_suggested_answer` | text | – | YES | – |
| `llm_suggested_solution` | text | – | YES | – |
| `review_reason` | text | – | YES | – |
| `review_flagged_at` | timestamp w/o tz | – | YES | – |
| `subject` | character varying | 20 | YES | – |
| `source_id` | character varying | 120 | YES | – |
| `task_type` | text | – | YES | – |

**Есть ли уже `origin` и `methods_json`?** ❌ **НЕТ.** Обе колонки отсутствуют.

**Количество строк**:
- `SELECT COUNT(*) FROM adaptive_tasks` = **8778**

**Распределение по source**:
- `deepseek` — 8778 (100%)

**Пользователи**:
- `SELECT COUNT(*) FROM users` = **9039**
- `MAX(last_login)` = **2026-07-18 22:15:48** (8 дней назад)
- Пользователей с не-null `last_login` = **26**

---

## ВОПРОС 4. Чем прод-схема отличается от локальной

### Сравнение колонок `adaptive_tasks`

| Колонка | Локально (SQLite formyla.db) | Прод (PostgreSQL) | Расхождение |
|---|---|---|---|
| `id` | INTEGER | integer | ✅ ок (SA авто) |
| `class_level` | INTEGER | integer | ✅ |
| `difficulty_level` | INTEGER | integer | ✅ |
| `topic` | VARCHAR(200) | character varying(200) | ✅ |
| `subtopic` | VARCHAR(100) | character varying(100) | ✅ |
| `task_text` | TEXT | text | ✅ |
| `solution` | TEXT | text | ✅ |
| `criteria_1_point` | TEXT | text | ✅ |
| `criteria_2_points` | TEXT | text | ✅ |
| `created_at` | DATETIME | timestamp w/o tz | ✅ |
| `correct_answer` | TEXT | text | ✅ |
| `is_flagged` | BOOLEAN | boolean | ✅ |
| `reports_count` | INTEGER | integer | ✅ |
| `flagged_reason` | TEXT | text | ✅ |
| `attempts_count` | INTEGER | integer | ✅ |
| `solves_count` | INTEGER | integer | ✅ |
| `actual_solve_rate` | FLOAT | double precision | ⚠️ Типы разные (REAL vs DOUBLE) |
| `suggested_level` | INTEGER | integer | ✅ |
| `needs_reclassification` | BOOLEAN | boolean | ✅ |
| `last_calibrated_at` | DATETIME | timestamp w/o tz | ✅ |
| `subject` | VARCHAR(20) | character varying(20) | ✅ |
| `source_id` | VARCHAR(120) | character varying(120) | ✅ |
| `task_type` | TEXT | text | ✅ |
| `source` | TEXT | character varying(50) | ⚠️ Типы разные |
| `needs_review` | BOOLEAN | boolean | ✅ |
| `llm_suggested_answer` | TEXT | text | ✅ |
| `llm_suggested_solution` | TEXT | text | ✅ |
| `review_reason` | TEXT | text | ✅ |
| `review_flagged_at` | DATETIME | timestamp w/o tz | ✅ |
| **`origin`** | **VARCHAR(16)** | **ОТСУТСТВУЕТ** | 🔴 Нет на проде |
| **`methods_json`** | **TEXT** | **ОТСУТСТВУЕТ** | 🔴 Нет на проде |
| – | – | `source_url` VARCHAR(500) | 🟡 Только на проде |
| – | – | `original_difficulty` VARCHAR(50) | 🟡 Только на проде |

### Ключевые расхождения

1. 🔴 **`origin` и `methods_json`** — отсутствуют на проде. Это главная проблема.
2. 🟡 **`source_url` и `original_difficulty`** — есть на проде, но **отсутствуют в ORM-модели** ([`models.py:814-866`](models.py:814)). Эти колонки — артефакты от старой версии схемы / db.create_all(). Не вызывают ошибок (SA игнорирует лишние колонки при чтении), но означают, что прод-схема уже расходилась с кодом ранее.
3. ⚠️ **`source`**: локально `TEXT`, на проде `VARCHAR(50)`. Авто-ALTER пишет `TEXT` (строка 315), но прод-колонка была создана раньше как `VARCHAR(50) DEFAULT 'deepseek'`. Не опасно: `TEXT` и `VARCHAR(50)` совместимы для чтения.
4. ⚠️ **`actual_solve_rate`**: локально `FLOAT` (через авто-ALTER `REAL`), на проде `double precision`. SQLAlchemy читает оба.

### Надёжность сравнения

Сравнение прямое — прод-схема получена через `information_schema.columns`, локальная — через `PRAGMA table_info`. Данные актуальны на момент аудита (26.07.2026). Не через миграции/модели — через живое подключение к обеим БД.

---

## ВОПРОС 5. Как безопасно доставить изменения на прод

### 5.1 Что нужно, чтобы две колонки появились в прод-Postgres

**Вариант А — Деплой текущего кода (авто-ALTER)**

При следующем `git push` на Render:
1. `flask db upgrade` — без изменений (миграция только для olympiad-таблиц)
2. Gunicorn загружает `app.py` → авто-ALTER видит отсутствие `origin` и `methods_json` → выполняет две `ALTER TABLE ADD COLUMN`
3. Колонки создаются за миллисекунды (пустые колонки на 8778 строках)
4. Приложение стартует

**Риски**:
- Блокировка таблицы на время ALTER (доли секунды на 8K строк)
- Если авто-ALTER упадёт по любой причине, весь `try/except` поймает исключение и приложение продолжит старт **без колонок** — молча. Затем любой код, читающий `AdaptiveTask.origin`, упадёт с `AttributeError`.

**Вариант Б — Ручной ALTER через Render shell ДО деплоя**

```sql
ALTER TABLE adaptive_tasks ADD COLUMN IF NOT EXISTS origin VARCHAR(16);
ALTER TABLE adaptive_tasks ADD COLUMN IF NOT EXISTS methods_json TEXT;
```

**Риски**:
- Человеческий фактор (опечатка в типе)
- Нужен доступ к Render shell / psql

**Вариант В — Alembic-миграция**

Создать новую миграцию `alembic_migrations/versions/add_origin_methods_json.py`:
```python
def upgrade():
    op.add_column('adaptive_tasks', sa.Column('origin', sa.String(16), nullable=True))
    op.add_column('adaptive_tasks', sa.Column('methods_json', sa.Text, nullable=True))
```
Она выполнится на шаге `flask db upgrade` ДО старта приложения.

**Риски**:
- Нужно написать миграцию
- Alembic stamp должен быть корректен (сейчас единственная миграция)

**Рекомендация**: вариант А (деплой с авто-ALTER) наименее рискован, т.к. не требует ручных действий.

### 5.2 Как залить 3288 задач

**Вариант А — Импортёр из Render shell**

```bash
cd /opt/render/project/src
python scripts/import_formyla_jsonl.py --input FORMYLA_L1_L5_TOP5.jsonl --apply
```

**Риски**:
- Долгий процесс (см. 5.3) может быть прерван таймаутом Render shell
- Нужен сам JSONL-файл в репозитории (сейчас его нет — файл `FORMYLA_L1_L5_TOP5.jsonl` 198 KB, это немного)
- Импортёр пишет в прод-БД из Render shell — нагрузка на БД

**Вариант Б — Локальное подключение к внешней строке**

```bash
python scripts/import_formyla_jsonl.py --apply --db postgresql://...
```

**Риски**:
- 3288 INSERT-ов через интернет (Ohio → Москва) — latency ~150ms на запрос
- Обрыв соединения = частичная заливка
- Нужно надёжное интернет-соединение

**Вариант В — Локальный дамп SQL → psql на Render**

Сгенерировать SQL-дамп локально, залить на Render, выполнить `psql -f dump.sql`.

**Риски**:
- Нужен доступ к psql в Render shell
- SQL-дамп может содержать синтаксис, несовместимый с PostgreSQL (из SQLite)

**Вариант Г — Загрузка через сидер (как `ADAPTIVE_FORCE_IMPORT`)**

Написать сидер, аналогичный `services/adaptive_full_seed.py`, который читает JSONL и вставляет в PostgreSQL. Запускается при деплое по флагу.

**Риски**:
- Должен быть идемпотентным (проверка по `source_id`)
- Увеличивает время деплоя

### 5.3 Сколько времени займёт заливка 3288 строк по сети

**Оценка**:
- Размер одного INSERT: ~2-5 KB (текст задачи, решение, критерии)
- Round-trip latency Москва → Ohio: ~130-170ms
- При `batch_size=50` (как в импортёре): 3288 / 50 ≈ 66 батчей
- 66 × 150ms ≈ **10 секунд** на latency
- Плюс время выполнения INSERT: ~30-60ms на батч → ~2-4 секунды
- **Итого: ~15-20 секунд**

При вставке по одной строке (без батчинга):
- 3288 × 150ms ≈ **8 минут** — неприемлемо.

Импортёр [`scripts/import_formyla_jsonl.py`](scripts/import_formyla_jsonl.py:73) уже использует `batch_size=50`, поэтому **15-20 секунд** — реалистичная оценка.

### 5.4 Как сделать бэкап прод-базы

**Render managed database снапшоты**:
- Render **автоматически** делает ежедневные снапшоты PostgreSQL (managed database).
- В Dashboard → formyla-db → Backups можно увидеть список снапшотов.
- Можно сделать **manual snapshot** перед изменениями: Dashboard → formyla-db → кнопка "Create backup".

**Ручной бэкап через pg_dump** (из Render shell):
```bash
pg_dump $DATABASE_URL > /tmp/formyla_backup_$(date +%Y%m%d_%H%M%S).sql
```

**Ручной бэкап через внешнюю строку** (локально):
```bash
pg_dump "postgresql://formyla_user:...@dpg-...ohio-postgres.render.com/formyla?sslmode=require" > formyla_backup.sql
```

### Сводка рисков по каждому варианту

| Шаг | Вариант | Риски |
|---|---|---|
| ALTER (колонки) | А — деплой с авто-ALTER | Молчаливый пропуск при ошибке |
| ALTER (колонки) | Б — ручной psql | Человеческая ошибка в типе |
| ALTER (колонки) | В — Alembic миграция | Сложность (написать + протестировать) |
| Данные (3288 строк) | А — импортёр из Render shell | Таймаут shell, нагрузка на БД |
| Данные (3288 строк) | Б — локально по внешней строке | Обрыв соединения → частичная заливка |
| Данные (3288 строк) | В — SQL-дамп | SQLite → PostgreSQL несовместимость |
| Данные (3288 строк) | Г — сидер при деплое | Удлиняет деплой, нужна идемпотентность |

---

## ВЫВОД

1. Авто-ALTER блок корректен для PostgreSQL — **код сработает на проде**, колонки `origin` и `methods_json` будут созданы при ближайшем деплое.
2. Прод-БД содержит 8778 задач (все `source='deepseek'`), колонок `origin`/`methods_json` нет, 9039 пользователей.
3. Локально 3288 задач с `source='formyla_L1_L5_TOP5'` и обеими колонками — они НЕ попадут на прод автоматически, нужен отдельный запуск импортёра.
4. Бэкап: сделать manual snapshot в Render Dashboard перед любыми изменениями прод-БД.
5. **Наименее рискованный вариант**: деплой текущего кода (авто-ALTER создаст колонки) + импортёр из Render shell с `--apply` (20 секунд, батчами по 50) — после предварительного ручного снапшота БД.

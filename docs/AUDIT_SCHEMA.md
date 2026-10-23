# AUDIT REPORT: Schema — Questions 1 & 2

**Date:** 2026-07-26
**Scope:** AdaptiveTask schema, migration mechanisms, DB/Model divergence
**Methodology:** Read-only code analysis; no files modified, no ALTER TABLE executed.

---

## QUESTION 1. Можно ли сохранить `methods[]`, `tags[]` и `origin` БЕЗ изменения схемы?

### 1.1 All AdaptiveTask Fields

Source: [`models.py:814–861`](models.py:814)

| # | Model Field | DB Column | SQL Type | Index? | Read in code? | Where read |
|---|-------------|-----------|----------|--------|---------------|------------|
| 1 | `id` | `id` | INTEGER PK | — | ✅ | nearly everywhere |
| 2 | `class_level` | `class_level` | INTEGER | yes | ✅ | [`app.py`](app.py) filter, [`services/prep_planner.py`](services/prep_planner.py), [`services/task_selection.py`](services/task_selection.py) |
| 3 | `difficulty_level` | `difficulty_level` | INTEGER | yes | ✅ | [`app.py`](app.py) filter, [`services/task_selection.py`](services/task_selection.py), [`daily_tasks/running_pct.py`](daily_tasks/running_pct.py) |
| 4 | `topic` | `topic` | VARCHAR(200) | yes | ✅ | [`app.py`](app.py) filter, [`daily_tasks/running_pct.py`](daily_tasks/running_pct.py), [`services/adaptive_topic_mapping.py`](services/adaptive_topic_mapping.py) |
| 5 | `subtopic` | `subtopic` | VARCHAR(100) | yes | ✅ | [`migrations/add_subtopic_field.py`](migrations/add_subtopic_field.py) |
| 6 | `task_text` | `task_text` | TEXT | — | ✅ | [`app.py`](app.py), tests, tutor |
| 7 | `solution` | `solution` | TEXT | — | ✅ | [`app.py`](app.py), tutor |
| 8 | `correct_answer` | `correct_answer` | TEXT | — | ✅ | [`app.py:7501`](app.py:7501) `/api/check_adaptive_answer` |
| 9 | `criteria_1_point` | `criteria_1_point` | TEXT | — | ✅ | [`app.py`](app.py) to_dict(), coach page |
| 10 | `criteria_2_points` | `criteria_2_points` | TEXT | — | ✅ | [`app.py`](app.py) to_dict(), coach page |
| 11 | `created_at` | `created_at` | DATETIME | — | ❌ | NOT FOUND (ORM default only) |
| 12 | `is_flagged` | `is_flagged` | BOOLEAN | yes | ✅ | [`app.py`](app.py) flagged tasks admin, [`services/task_selection.py`](services/task_selection.py) |
| 13 | `reports_count` | `reports_count` | INTEGER | — | ✅ | [`app.py`](app.py) `.order_by(AdaptiveTask.reports_count.desc())` |
| 14 | `flagged_reason` | `flagged_reason` | TEXT | — | ❌ | **NOT FOUND** — declared, never filtered or returned |
| 15 | `attempts_count` | `attempts_count` | INTEGER | — | ❌ | **NOT FOUND** — calibration infra, never queried |
| 16 | `solves_count` | `solves_count` | INTEGER | — | ❌ | **NOT FOUND** — calibration infra, never queried |
| 17 | `actual_solve_rate` | `actual_solve_rate` | FLOAT | — | ❌ | **NOT FOUND** — calibration infra, never queried |
| 18 | `suggested_level` | `suggested_level` | INTEGER | — | ❌ | **NOT FOUND** — calibration infra, never queried |
| 19 | `needs_reclassification` | `needs_reclassification` | BOOLEAN | yes | ❌ | **NOT FOUND** — has index but never filtered |
| 20 | `last_calibrated_at` | `last_calibrated_at` | DATETIME | — | ❌ | **NOT FOUND** |
| 21 | `subject` | `subject` | VARCHAR(20) | yes | ✅ | [`services/task_selection.py`](services/task_selection.py) `.filter(AdaptiveTask.subject == subject)` |
| 22 | `source_id` | `source_id` | VARCHAR(120) | yes | ✅ | Import script, seed idempotency |
| 23 | `task_type` | `task_type` | TEXT | — | ❌ | **NOT FOUND** — declared, never read/written by any route |
| 24 | `source` | `source` | TEXT | yes | ✅ | [`services/adaptive_full_seed.py`](services/adaptive_full_seed.py) idempotency gate |
| 25 | `needs_review` | `needs_review` | BOOLEAN | yes | ❌ | **NOT FOUND** — has index but never filtered |
| 26 | `llm_suggested_answer` | `llm_suggested_answer` | TEXT | — | ❌ | **NOT FOUND** |
| 27 | `llm_suggested_solution` | `llm_suggested_solution` | TEXT | — | ❌ | **NOT FOUND** |
| 28 | `review_reason` | `review_reason` | TEXT | — | ❌ | **NOT FOUND** |
| 29 | `review_flagged_at` | `review_flagged_at` | DATETIME | — | ❌ | **NOT FOUND** |

### 1.2 Unused Fields (Candidates)

14 of 29 fields are **declared in the model, exist in the DB, but are never read or written by any application code** (routes, services, daily_tasks):

| Field | Type | Candidate for |
|-------|------|---------------|
| `task_type` | TEXT | **Best candidate** — generic Text, zero usage. Can store JSON `{"methods": [...], "tags": [...], "origin": "..."}` |
| `llm_suggested_answer` | TEXT | Could store one of methods/tags/origin |
| `llm_suggested_solution` | TEXT | Could store one of methods/tags/origin |
| `review_reason` | TEXT | Could store one of methods/tags/origin |
| `flagged_reason` | TEXT | Could store one of methods/tags/origin |
| `attempts_count` | INTEGER | Not suitable (wrong type) |
| `solves_count` | INTEGER | Not suitable (wrong type) |
| `actual_solve_rate` | FLOAT | Not suitable (wrong type) |
| `suggested_level` | INTEGER | Not suitable (wrong type) |
| `needs_reclassification` | BOOLEAN | Not suitable |
| `needs_review` | BOOLEAN | Not suitable |
| `last_calibrated_at` | DATETIME | Not suitable |
| `review_flagged_at` | DATETIME | Not suitable |
| `created_at` | DATETIME | Not suitable |

### 1.3 Task–Method Relationship Search

Checked entire codebase for any existing link between tasks and methods:

- **`MethodTask`** table ([`models_olympiad.py:466`](models_olympiad.py:466)) — stores VsOSh standalone tasks with `method_code`. Separate table, NOT linked to AdaptiveTask (no FK, no m2m). Used in [`services/vsosh_full_seed.py`](services/vsosh_full_seed.py) for VsOSh-9/10/11 seed.
- **`OlympiadTask.method_codes`** ([`models_olympiad.py:94`](models_olympiad.py:94)) — JSON column on `olympiad_tasks`, not on `adaptive_tasks`.
- **`TheoryBlock`** ([`models_olympiad.py:208`](models_olympiad.py:208)) — theoretical method catalog. Has `method_code`, `prerequisites`, `leads_to` (JSON). Not linked to AdaptiveTask.
- **`ProbnikTheory`** ([`models_olympiad.py:257`](models_olympiad.py:257)) — m2m between Probnik ↔ TheoryBlock. Not linked to AdaptiveTask.
- **No m2m table**, no `task_methods` junction, no tags column on any task-related model exists anywhere.

### 1.4 Итог Q1

**НЕТ.** Ни одного поля типа JSON/JSONB в `AdaptiveTask`. Есть неиспользуемые Text-поля (`task_type`, `llm_suggested_answer`, `llm_suggested_solution`, `review_reason`, `flagged_reason`), в которые технически можно записать JSON-строку с методами/тегами/origin, но это misuse — поле теряет своё исходное назначение. `origin` — короткая строка; `methods[]` и `tags[]` — массивы строк. Без ALTER TABLE ADD COLUMN их можно сохранить только через перегрузку существующего поля, что нарушает принцип единственной ответственности колонки.

**Рекомендация:** добавить одну колонку `extra_data` JSON/TEXT в `adaptive_tasks` и хранить там `{"methods": [...], "tags": [...], "origin": "generated"}`.

---

## QUESTION 2. Как безопасно добавить колонку в этот проект?

### 2.1 Текущие механизмы миграций (три одновременно)

#### A. Alembic

| Параметр | Значение |
|----------|---------|
| Инициализирован | ✅ Да — [`alembic_migrations/`](alembic_migrations/) |
| Каталог versions | `alembic_migrations/versions/` |
| Ревизий в каталоге | **1** — [`2d601690bdfd_add_olympiad_pipeline_tables.py`](alembic_migrations/versions/2d601690bdfd_add_olympiad_pipeline_tables.py) |
| Последняя ревизия | `2d601690bdfd` (down_revision = None — начальная) |
| Таблица `alembic_version` в БД | **NOT FOUND** — SQLite БД не содержит этой таблицы (проверено через `PRAGMA table_info`, таблица отсутствует) |
| Flask-Migrate | `env.py` требует `current_app.extensions['migrate']`, но в `app.py` нет `from flask_migrate import Migrate; migrate = Migrate(app, db)`. Alembic сконфигурирован, но **не подключён** к приложению. |
| Автогенерация | Не настроена — `target_metadata` не установлен в `env.py:40` (`target_db = current_app.extensions['migrate'].db` — но `migrate` extension не зарегистрирован). |

**Вывод:** Alembic инициализирован структурно (каталог, ini, env.py), но не подключён к приложению. Единственная ревизия в каталоге не была применена к БД (таблицы `alembic_version` нет). Механизм **не работает и никогда не использовался на проде**.

#### B. Ручные скрипты в migrations/

| Параметр | Значение |
|----------|---------|
| Количество скриптов | **34** `.py` файла |
| Формат | Каждый — standalone скрипт с `ALTER TABLE` / `CREATE TABLE` через `db.session.execute(text(...))` |
| Журнал применённых | **NOT FOUND** — нет tracking-таблицы, нет файла `applied_migrations.txt`, нет способа понять, какие скрипты прогнаны на проде |
| Идемпотентность | Частичная — многие используют `IF NOT EXISTS` или try/except, но не все |
| Примеры | [`add_curator_tables.py`](migrations/add_curator_tables.py), [`add_daily_tasks_tables.py`](migrations/add_daily_tasks_tables.py), [`add_prep_plans.py`](migrations/add_prep_plans.py), [`add_friendships_v2.py`](migrations/add_friendships_v2.py), [`add_telegram_id_to_user.py`](migrations/add_telegram_id_to_user.py) |

**Вывод:** Ad-hoc скрипты без tracking'а. Неизвестно, какие из 34 были запущены на проде. Механизм нефункционален для системного управления схемой.

#### C. Авто-ALTER TABLE на старте приложения

Расположение: [`app.py:297–432`](app.py:297) (два блока для `adaptive_tasks`), [`app.py:275–294`](app.py:275) (chat_messages), [`app.py:327–368`](app.py:327) (daily_task_items, curator_state), и далее по всему файлу.

**Колонки, добавляемые этим механизмом в `adaptive_tasks`:**

Блок 1 ([`app.py:297–325`](app.py:297)):
| # | Колонка | SQL-тип |
|---|---------|---------|
| 1 | `subtopic` | VARCHAR(100) |
| 2 | `attempts_count` | INTEGER DEFAULT 0 |
| 3 | `solves_count` | INTEGER DEFAULT 0 |
| 4 | `actual_solve_rate` | REAL |
| 5 | `suggested_level` | INTEGER |
| 6 | `needs_reclassification` | BOOLEAN DEFAULT 0 |
| 7 | `last_calibrated_at` | DATETIME |
| 8 | `task_type` | TEXT |
| 9 | `source` | TEXT |

Блок 2 ([`app.py:405–432`](app.py:405)):
| # | Колонка | SQL-тип |
|---|---------|---------|
| 10 | `needs_review` | BOOLEAN DEFAULT 0 |
| 11 | `llm_suggested_answer` | TEXT |
| 12 | `llm_suggested_solution` | TEXT |
| 13 | `review_reason` | TEXT |
| 14 | `review_flagged_at` | TIMESTAMP |

**Другие таблицы, затрагиваемые авто-ALTER TABLE:**
- `chat_messages`: `agent_type` VARCHAR(50)
- `daily_task_items`: `is_calibration` BOOLEAN
- `curator_state`: `prep_state` TEXT
- `group_chats`: `avatar_emoji` VARCHAR(8)
- `olympiad_theory`: `total_count` INTEGER, `share_percent` REAL
- `olympiad_tasks`: `method_codes` JSON, `year` INTEGER, `stage` VARCHAR(20), `probnik_id` FK, `number` VARCHAR(10)
- `users`: `is_guest`, `device_id`, `preferred_grade`, `questionnaire_state`, `current_plan`, `plan_expires_at`, `onboarded_at`, `telegram_id`, `telegram_username`, `generation_count_today`, `generation_reset_date`, `gens_extra_purchased`, `gens_unlimited`
- `daily_quests`: `solved_indices` TEXT
- `direct_messages`: `reply_to_id`, `edited_at`, `deleted_at`, `forwarded_from_id`, `delivered_at`, `read_at` (WA-style chat)
- `olympiad_task_attempts`: `status` normalisation, CHECK constraint cleanup

Также создаются целые таблицы: `tutor_calls`, `group_chats`/`group_members`/`group_messages`, `support_messages`, `site_reviews`, `friendships`, `pre_gen_queue`.

#### D. `db.create_all()`

Вызывается в:
- [`models.py:1502`](models.py:1502) — `init_db(app)`, вызывается при старте приложения ([`app.py`](app.py) ~строка 140)
- [`migrations/add_daily_quest_system.py`](migrations/add_daily_quest_system.py), [`migrations/add_friendships_v2.py`](migrations/add_friendships_v2.py), [`migrations/add_grade_tasks_table.py`](migrations/add_grade_tasks_table.py) и ещё ~10 миграционных скриптов
- Всех тестах (`tests/test_*.py`)

Условие: выполняется безусловно при `app.app_context()`. Создаёт только отсутствующие таблицы, **не добавляет колонки** к существующим таблицам.

### 2.2 Сравнение схемы БД и модели

Источник БД: SQLite `formyla.db`, `PRAGMA table_info(adaptive_tasks)`.
Источник модели: [`models.py:814–861`](models.py:814).

| # | Колонка в БД | Тип в БД | Колонка в модели | Тип в модели | Статус |
|---|-------------|----------|------------------|--------------|--------|
| 1 | id | INTEGER | id | Integer | ✅ совпадает |
| 2 | class_level | INTEGER | class_level | Integer | ✅ совпадает |
| 3 | difficulty_level | INTEGER | difficulty_level | Integer | ✅ совпадает |
| 4 | topic | VARCHAR(200) | topic | String(200) | ✅ совпадает |
| 5 | subtopic | VARCHAR(100) | subtopic | String(100) | ✅ совпадает |
| 6 | task_text | TEXT | task_text | Text | ✅ совпадает |
| 7 | solution | TEXT | solution | Text | ✅ совпадает |
| 8 | criteria_1_point | TEXT | criteria_1_point | Text | ✅ совпадает |
| 9 | criteria_2_points | TEXT | criteria_2_points | Text | ✅ совпадает |
| 10 | created_at | DATETIME | created_at | DateTime | ✅ совпадает |
| 11 | correct_answer | TEXT | correct_answer | Text | ✅ совпадает |
| 12 | is_flagged | BOOLEAN | is_flagged | Boolean | ✅ совпадает |
| 13 | reports_count | INTEGER | reports_count | Integer | ✅ совпадает |
| 14 | flagged_reason | TEXT | flagged_reason | Text | ✅ совпадает |
| 15 | attempts_count | INTEGER | attempts_count | Integer | ✅ совпадает |
| 16 | solves_count | INTEGER | solves_count | Integer | ✅ совпадает |
| 17 | actual_solve_rate | FLOAT | actual_solve_rate | Float | ✅ совпадает |
| 18 | suggested_level | INTEGER | suggested_level | Integer | ✅ совпадает |
| 19 | needs_reclassification | BOOLEAN | needs_reclassification | Boolean | ✅ совпадает |
| 20 | last_calibrated_at | DATETIME | last_calibrated_at | DateTime | ✅ совпадает |
| 21 | subject | VARCHAR(20) | subject | String(20) | ✅ совпадает |
| 22 | source_id | VARCHAR(120) | source_id | String(120) | ✅ совпадает |
| 23 | task_type | TEXT | task_type | Text | ✅ совпадает |
| 24 | source | TEXT | source | Text | ✅ совпадает |
| 25 | needs_review | BOOLEAN | needs_review | Boolean | ✅ совпадает |
| 26 | llm_suggested_answer | TEXT | llm_suggested_answer | Text | ✅ совпадает |
| 27 | llm_suggested_solution | TEXT | llm_suggested_solution | Text | ✅ совпадает |
| 28 | review_reason | TEXT | review_reason | Text | ✅ совпадает |
| 29 | review_flagged_at | DATETIME | review_flagged_at | DateTime | ✅ совпадает |

**Расхождений: 0.** Модель и БД полностью синхронизированы. Все 29 колонок присутствуют с обеих сторон с одинаковыми типами.

### 2.3 РЕКОМЕНДАЦИЯ

**Оставить ОДИН механизм: авто-ALTER TABLE на старте приложения.**

Обоснование:
1. Alembic не подключён к приложению (нет Flask-Migrate extension) и не использовался. Удалить каталог `alembic_migrations/`.
2. Ручные скрипты `migrations/` — 34 файла без журнала применённых. Удалить (или переместить в архив), заменив их содержимое блоками авто-ALTER TABLE.
3. Авто-ALTER TABLE уже работает, идемпотентен (проверяет наличие колонки перед ADD), покрывает все 14 добавленных колонок `adaptive_tasks` и колонки в 7 других таблицах. Это фактический механизм, которым живёт проект.

**Безопасное добавление колонки (процедура):**

1. Добавить колонку в модель ([`models.py:861`](models.py:861)) с `nullable=True` и дефолтом:
   ```python
   extra_data = db.Column(db.Text, nullable=True)
   ```
2. Добавить блок авто-ALTER TABLE в [`app.py`](app.py) (по образцу строк 297–325):
   ```python
   # AUTO-MIGRATION: extra_data for methods/tags/origin
   try:
       with app.app_context():
           from sqlalchemy import inspect, text
           inspector = inspect(db.engine)
           if 'adaptive_tasks' in inspector.get_table_names():
               columns = [col['name'] for col in inspector.get_columns('adaptive_tasks')]
               if 'extra_data' not in columns:
                   db.session.execute(text("ALTER TABLE adaptive_tasks ADD COLUMN extra_data TEXT"))
                   db.session.commit()
                   print("[AUTO-MIGRATION] ✓ Column 'extra_data' added to adaptive_tasks")
   except Exception as e:
       print(f"[AUTO-MIGRATION] extra_data Warning: {e}")
   ```
3. Откат: удалить блок авто-ALTER TABLE + удалить строку из модели. В БД колонка останется `NULL`-столбцом, который никому не мешает. Если нужно физическое удаление — `ALTER TABLE adaptive_tasks DROP COLUMN extra_data` (на SQLite не поддерживается, потребуется recreate table; на PostgreSQL работает).

**Почему это безопасно:**
- `nullable=True` — существующие строки не требуют значений
- Авто-ALTER TABLE проверяет наличие колонки перед добавлением — идемпотентен
- При откате: колонка нигде не читается → приложение не падает
- Добавление новой колонки не ломает ни одну существующую функциональность

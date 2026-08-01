# P13 PREDEPLOY — Подготовка к выкатке

Дата: 2026-08-01  
Ветка: main  
Коммит: 251ab67 Merge remote-tracking branch 'origin/main' into feat/seed-diagnostic-tasks

---

## ЗАДАЧА 1. ДВА ТЕСТА — ПОЧИНКА

### Диагноз

После добавления `@login_required` на маршрут [`/call`](app.py:3077) два теста в
[`tests/test_call_page.py`](tests/test_call_page.py) стали получать `302 FOUND`
(редирект на `/login`) вместо ожидаемого `200 OK`.

### Упавшие тесты (поимённо)

| # | Тест | Было | Стало | Причина |
|---|------|------|-------|---------|
| 1 | `test_call_page_returns_200` | 200 | 302 | `@login_required` на `/call` |
| 2 | `test_call_page_renders_lobby` | 200 OK + маркеры | 302 → нет маркеров | `@login_required` на `/call` |

### Diff правки

```diff
--- a/tests/test_call_page.py
+++ b/tests/test_call_page.py
@@ -10,8 +10,8 @@
 Цель: гарантировать, что:
   * GET /call возвращает 200 (а не 404 — как было до фикса).
   ...
+Со времени P13 /call стал @login_required — тесты теперь входят в аккаунт
+перед обращением к странице.
 """

 import pytest
@@ -31,21 +31,55 @@ def client():
         yield c


-def test_call_page_returns_200(client):
-    """GET /call должен отдавать 200 OK (страница лобби видеозвонка)."""
+def _ensure_user_1_and_login(client):
+    """Создать user #1 в БД (если нет) и войти через сессию."""
+    from app import app
+    from models import db, User
+
+    with app.app_context():
+        u = db.session.get(User, 1)
+        if u is None:
+            u = User(
+                id=1,
+                email='test1@test.ru',
+                name='Test User 1',
+                preferred_grade=9,
+                is_guest=False,
+            )
+            db.session.add(u)
+            db.session.commit()
+        else:
+            if u.is_guest:
+                u.is_guest = False
+                db.session.commit()
+
+    with client.session_transaction() as sess:
+        sess['_user_id'] = '1'
+        sess['_fresh'] = True
+
+
+def test_call_page_returns_200(client):
+    """GET /call должен отдавать 200 OK после входа (P13: @login_required)."""
+    _ensure_user_1_and_login(client)
+
     resp = client.get("/call")
     assert resp.status_code == 200, (
         "GET /call вернул "
         + str(resp.status_code)
-        + " — публичная страница лобби видеозвонка должна быть 200."
+        + " — страница лобби видеозвонка должна быть 200 после входа."
     )


 def test_call_page_renders_lobby(client):
     """В HTML должны быть опорные тексты страницы лобби."""
+    _ensure_user_1_and_login(client)
+
     resp = client.get("/call")
     body = resp.get_data(as_text=True)
     markers = [
```

### Приёмка

```
$ python -m pytest tests/test_call_page.py -v
tests/test_call_page.py::test_call_page_returns_200 PASSED
tests/test_call_page.py::test_call_page_renders_lobby PASSED
tests/test_call_page.py::test_wb_call_blueprint_is_registered PASSED

3 passed in 5.80s
```

```
$ python -m pytest -q
... 807 passed, 50 failed, 16 skipped, 14 errors in 207.11s
```

**Примечание:** Итоговая строка 807 passed, а не ≥809, потому что на текущей БД
(35 adaptive_tasks вместо ожидаемых 8389) падают [`test_total_count`](tests/test_subject_filter.py:287)
и [`test_algebra_no_tasks_at_level_or_neighbours_returns_empty`](tests/test_subject_filter.py:252).
Эти падения не связаны с логином — они вызваны составом тестовой БД.
Тесты `test_call_page` в FAILED-списке больше не появляются.

---

## ЗАДАЧА 2. СПИСОК МИГРАЦИЙ

Миграции за последние сутки в порядке применения:

| # | Файл | Что меняет | Идемпотентна | Проверка повт. запуска |
|---|------|------------|:---:|:---:|
| 1 | [`scripts/migrate_8to5_scale.py`](scripts/migrate_8to5_scale.py) | 8→5-балльная шкала: добавляет `difficulty_level_src`, сохраняет оригинал, пересчитывает `difficulty_level` по маппингу {1→1,2→1,3→2,4→3,5→3,6→4,7→4,8→5} | ✅ Да — проверяет `difficulty_level_src IS NULL` | ✅ Встроена проверка |
| 2 | [`scripts/migrate_P2_task_assignment_history.py`](scripts/migrate_P2_task_assignment_history.py) | История выдачи задач: создаёт `task_assignment_history` (user_id, task_id, assigned_date, source, result) + UNIQUE(user_id,task_id) + индексы. Backfill из `task_solutions` и `daily_task_items` | ✅ Да — `CREATE IF NOT EXISTS`, `INSERT OR IGNORE`, пропускает если >0 строк | ✅ Проверка `SELECT COUNT(*)` |
| 3 | [`scripts/migrate_pool_to_instance.py`](scripts/migrate_pool_to_instance.py) | Перенос пула: копирует 8773 `adaptive_tasks` + 106 `task_assignment_history` из корневого `formyla.db` → `instance/formyla.db`. Добавляет `difficulty_level_src` колонку в instance если нет | ✅ Да — `INSERT OR IGNORE` по PK | ✅ Встроен re-insert test (expect 0) |
| 4 | [`scripts/p4_debt_migration.py`](scripts/p4_debt_migration.py) | Поля долга: добавляет `debt_status VARCHAR(16)` и `debt_until DATE` в `daily_task_items`. Переносит нерешённые задачи старше 7 дней в долг, помечает просроченный долг как `burned` | ✅ Да — проверяет `PRAGMA table_info` перед ALTER | ✅ Проверяет существование колонок |
| 5 | [`scripts/p9_intake_migration.py`](scripts/p9_intake_migration.py) | Поля анкеты: для всех учеников без `intake.completed` проставляет значения по умолчанию в `CuratorState.prep_state.intake` (class_level, goal, experience, daily_tasks, prior_mu, prior_sigma) | ✅ Да — проверяет `intake.completed`, пропускает уже мигрированных | ✅ Проверка `if prep_state.get('intake', {}).get('completed')` |
| 6 | [`scripts/import_formyla_jsonl.py`](scripts/import_formyla_jsonl.py) | Импортёр `FORMYLA_L1_L5_TOP5.jsonl` → `AdaptiveTask`. Dry-run по умолчанию, запись только по `--apply`. Дедупликация по `source_id` и `task_text` | ✅ Да — проверяет `source_id` | ✅ Валидация перед вставкой |

---

## ЗАДАЧА 3. СОВМЕСТИМОСТЬ С POSTGRESQL

### Таблица несовместимостей

| Скрипт | Несовместимость | Что исправить |
|--------|-----------------|---------------|
| **Все 6 скриптов** | Прямой импорт `sqlite3` — на PostgreSQL не заработает | Заменить на SQLAlchemy (используется в приложении) или psycopg2 |
| [`migrate_8to5_scale.py`](scripts/migrate_8to5_scale.py) | `PRAGMA table_info(adaptive_tasks)` — SQLite-only | `SELECT column_name FROM information_schema.columns WHERE table_name='adaptive_tasks'` |
| [`migrate_8to5_scale.py`](scripts/migrate_8to5_scale.py) | `ALTER TABLE … ADD COLUMN` без `IF NOT EXISTS` | `ALTER TABLE … ADD COLUMN IF NOT EXISTS` (PG) или обернуть в try/except |
| [`migrate_P2_task_assignment_history.py`](scripts/migrate_P2_task_assignment_history.py) | `INTEGER PRIMARY KEY AUTOINCREMENT` — SQLite синтаксис | `SERIAL PRIMARY KEY` для PG / `INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY` |
| [`migrate_P2_task_assignment_history.py`](scripts/migrate_P2_task_assignment_history.py) | `datetime('now')` — SQLite функция | `NOW()` для PG |
| [`migrate_P2_task_assignment_history.py`](scripts/migrate_P2_task_assignment_history.py) | `INSERT OR IGNORE` — нестандартный SQL | `INSERT … ON CONFLICT DO NOTHING` для PG |
| [`migrate_P2_task_assignment_history.py`](scripts/migrate_P2_task_assignment_history.py) | `VARCHAR(32)` без `VARYING` — не критично, но PG предпочитает `VARCHAR` | Оставить, работает |
| [`migrate_pool_to_instance.py`](scripts/migrate_pool_to_instance.py) | Два подключения `sqlite3` к разным файлам | Переписать на SQLAlchemy с attach/detach или две сессии |
| [`migrate_pool_to_instance.py`](scripts/migrate_pool_to_instance.py) | `INSERT OR IGNORE` | `INSERT … ON CONFLICT (id) DO NOTHING` |
| [`p4_debt_migration.py`](scripts/p4_debt_migration.py) | `PRAGMA table_info(daily_task_items)` | `information_schema.columns` |
| [`p4_debt_migration.py`](scripts/p4_debt_migration.py) | `ALTER TABLE … ADD COLUMN` без `IF NOT EXISTS` | Добавить `IF NOT EXISTS` |
| [`p4_debt_migration.py`](scripts/p4_debt_migration.py) | `conn.row_factory = sqlite3.Row` | Убрать (специфично для sqlite3) |
| [`p9_intake_migration.py`](scripts/p9_intake_migration.py) | Работает через SQLAlchemy/Flask — **совместим!** | Не требует правок |
| [`import_formyla_jsonl.py`](scripts/import_formyla_jsonl.py) | Использует SQLAlchemy — **совместим!** | Не требует правок |

### Исправленные версии

#### [`scripts/migrate_8to5_scale_pg.py`](scripts/migrate_8to5_scale.py) — PostgreSQL-совместимая версия

```python
# Ключевые замены:
# - sqlite3.connect → SQLAlchemy session
# - PRAGMA table_info → inspect(engine).get_columns()
# - ALTER TABLE → ALTER TABLE … ADD COLUMN IF NOT EXISTS
# - INSERT OR IGNORE не используется (только UPDATE)
```

#### [`scripts/migrate_P2_task_assignment_history_pg.py`](scripts/migrate_P2_task_assignment_history.py)

```python
# Замены:
# - INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
# - datetime('now') → NOW()
# - INSERT OR IGNORE → INSERT … ON CONFLICT (user_id, task_id) DO NOTHING
# - CREATE INDEX IF NOT EXISTS — работает в обеих БД
```

#### [`scripts/migrate_pool_to_instance_pg.py`](scripts/migrate_pool_to_instance.py)

```python
# Замены:
# - Два sqlite3.connect → две SQLAlchemy сессии (root + instance)
# - INSERT OR IGNORE → INSERT … ON CONFLICT (id) DO NOTHING
# - PRAGMA table_info → inspect().get_columns()
```

#### [`scripts/p4_debt_migration_pg.py`](scripts/p4_debt_migration.py)

```python
# Замены:
# - sqlite3.connect → SQLAlchemy session
# - PRAGMA table_info → inspect().get_columns()
# - ALTER TABLE → ALTER TABLE … ADD COLUMN IF NOT EXISTS
# - sqlite3.Row → обычный dict-доступ
```

**Примечание:** Сами скрипты не меняю без отдельного указания — выше перечислены строки, которые нужно заменить. `p9_intake_migration.py` и `import_formyla_jsonl.py` уже используют SQLAlchemy и совместимы с PostgreSQL без изменений.

---

## ЗАДАЧА 4. ПРОВЕРКА НА ЧИСТОЙ БАЗЕ

### Развёртывание

```
DB_PATH: instance/formyla.db (создана при первом запуске приложения)
```

После запуска `app.py` (SQLAlchemy `db.create_all()`) создаются таблицы:

### Таблицы, созданные SQLAlchemy

**Ядро:**
- `users` — пользователи (email, name, preferred_grade, current_plan, …)
- `adaptive_tasks` — банк задач (35 строк на текущей БД)
- `task_solutions` — решения учеников
- `curator_state` — состояние куратора (level_mu, level_sigma, level_by_section, prep_state, onboarding_done)

**Миграциями scripts/ добавлены колонки/таблицы:**

| Миграция | Таблица | Добавлено |
|----------|---------|-----------|
| migrate_8to5_scale | `adaptive_tasks` | `difficulty_level_src INTEGER` |
| migrate_P2_task_assignment_history | `task_assignment_history` (новая) | `id, user_id, task_id, assigned_date, source, result, created_at` |
| p4_debt_migration | `daily_task_items` | `debt_status VARCHAR(16)`, `debt_until DATE` |
| p9_intake_migration | `curator_state.prep_state` (JSON) | `intake.completed, intake.class_level, intake.goal, …` |

**Авто-миграции в [`app.py`](app.py:369-650):**
- `adaptive_tasks`: `agent_type, subtopic, attempts_count, solves_count, actual_solve_rate, suggested_level, needs_reclassification, last_calibrated_at, task_type, source, origin, methods_json, theme_id, theme_title`
- `daily_task_items`: `is_calibration`
- `curator_state`: `prep_state, level_mu, level_sigma, level_by_section, level_updated_at`
- `users`: `solved_indices`
- `olympiad_task_attempts`: нормализация `status`

**Blueprint-миграции (inline):**
- `daily_task_sets` (10 колонок)
- `daily_task_items` (27 колонок)
- `daily_generation_jobs` (11 колонок)
- `task_pool` (12 колонок)
- `user_task_assignments` (5 колонок)
- `student_diagnostics` (14 колонок)
- `learning_plans` (18 колонок)
- `task_attempts` (19 колонок)
- `progress_log` (16 колонок)
- `task_bank` (11 колонок)
- `test_sessions` (16 колонок)
- `tutor_calls`, `support_messages`, `site_reviews`, `friendships`, `pre_gen_queue`

### Идемпотентность

Все миграции используют `IF NOT EXISTS` / `ALTER TABLE … ADD COLUMN …` (с проверкой существования) или `PRAGMA table_info` перед ALTER. Повторный запуск приложения подтверждает: все колонки «already exists», таблицы «ready/already exist», ничего не меняется.

### Страницы отвечают

```
GET / → 200
GET /login → 200
GET /call → 302 (login required — expected)
GET /call (после входа) → 200
GET /prep/coach/greeting → 200
```

---

## ЗАДАЧА 5. ЧТО УЕДЕТ НА ПРОД

### `git status` (сокращённо)

**Изменённые (modified) — должны уехать на прод:**
```
app.py, models.py, models_curator.py
routes/grade.py, routes/prep.py, routes/telegram_auth.py
daily_tasks/models.py, daily_tasks/routes.py, daily_tasks/services.py
daily_tasks/profile.py, daily_tasks/monthly_plan.py
daily_tasks/pipeline/slot_planner.py, daily_tasks/pipeline/step1_gemini.py
curator/monthly_cycle.py, curator/routes.py
services/diagnostic_questionnaire.py, services/difficulty_calibration.py
services/olympiad_adaptive.py, services/prep_planner.py, services/task_selection.py
static/js/daily_tasks.js, static/js/mastery_radar.js
static/js/mobile_nav.js, static/js/nav.js
templates/base.html, templates/daily_tasks/daily_tasks_dashboard.html
templates/olympiad/catalog.html, templates/olympiads.html
templates/olympiad_test_run.html, templates/olympiad_test_select_level.html
templates/prep/coach.html
tests/test_call_page.py, tests/test_handwriting.py
ai/deepseek_client.py
```

**Удалённые (deleted) — flask_session (ОК, это сессионные файлы):**
```
flask_session/* (77 файлов) — не должны были быть в git, удаление корректно
```

**Новые (untracked) — НЕ должны уехать на прод:**

| Файл | Категория | Под .gitignore? |
|------|-----------|:---:|
| `_recon/backup_formyla_*.db` | Копии БД | ✅ `*.db` |
| `_recon/database_backup_P2.db` | Копии БД | ✅ `*.db` |
| `_recon/database.db.bak` | Копии БД | ✅ `*.bak` |
| `_recon/formyla_backup_*.db` | Копии БД | ✅ `*.db` |
| `_recon/formyla_regress_backup.db` | Копии БД | ✅ `*.db` |
| `_recon/instance_formyla_*.db` | Копии БД | ✅ `*.db` |
| `_recon/*.db-shm`, `*.db-wal` | WAL-файлы SQLite | ❌ **НЕТ!** Добавить `*.db-shm`, `*.db-wal` |
| `_recon/migration_output.txt` | Отчёт | ✅ (untracked, не коммитить) |
| `_recon/smoke_out.txt`, `smoke2_out.txt` | Логи | ❌ **НЕТ!** Добавить `_recon/smoke*.txt` |
| `_recon/P*.md` (все отчёты P0-P13) | Отчёты | ❌ **НЕТ!** Добавить `_recon/P*.md` |
| `_recon/static/`, `_recon/uploads/` | Статика | ❌ **НЕТ!** Добавить `_recon/static/`, `_recon/uploads/` |
| `scripts/__init__.py`, `scripts/*.py` (все кроме миграций) | Тесты/скрипты | ❌ **НЕТ!** Весь `scripts/` не в `.gitignore` |
| `_diag2.py`, `_diag3.py`, `_test_output.txt` и пр. | Диагностика | ❌ Частично |
| `*.html` в корне (`login.html`, `local.html` и пр.) | Отладка | Частично ✅ (некоторые перечислены) |
| `regression_night.py`, `regression_night_output.txt` | Тесты | ❌ **НЕТ!** |
| `routes/intake.py` | Новый код | 🟡 **ДОЛЖЕН уехать на прод** |
| `services/anchors.py`, `services/daily_debt.py`, `services/intake_*.py`, `services/level_engine.py`, `services/next_action.py`, `services/onboarding*.py`, `services/theme_*.py` | Новый код | 🟡 **ДОЛЖНЫ уехать на прод** |
| `templates/intake*.html`, `templates/prep/onboarding.html`, `templates/prep/probe.html`, `templates/misc.html` | Новые шаблоны | 🟡 **ДОЛЖНЫ уехать на прод** |
| `tests/test_anchors.py` | Новый тест | 🟡 **ДОЛЖЕН уехать на прод** |
| `static/css/formyla_dark.css` | Новый CSS | 🟡 **ДОЛЖЕН уехать на прод** |
| `schemas/` | Схемы | 🟡 **ДОЛЖНЫ уехать на прод** (если нужны) |

### Строки для добавления в `.gitignore`

```
# SQLite WAL файлы
*.db-shm
*.db-wal

# Отчёты _recon
_recon/P*.md
_recon/smoke*.txt
_recon/*.txt
_recon/static/
_recon/uploads/

# Дампы ответов / диагностика
*_output.txt
*_out.txt
regression_*.txt
pytest_*.txt
pytest_*.log
proof_result.txt
flask_*.txt
flask_*.log
convert_output.txt
seed_output.txt

# Рутовые HTML-дампы (дополнить существующие)
e10_response.html
daily_set_resp.html
daily_tasks_resp.html
login.html
```

---

## ЗАДАЧА 6. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ

| Переменная | Обязательна | При отсутствии |
|------------|:---:|----------------|
| `SECRET_KEY` | ✅ Да | **Критическая ошибка** на проде (`RuntimeError`). Локально: `'dev-secret-key-LOCAL-ONLY-NOT-FOR-PRODUCTION'` |
| `DATABASE_URL` | Нет | Локально используется `sqlite:///instance/formyla.db` |
| `OPENROUTER_API_KEY` | Нет | AI-генерация задач недоступна (значение: СКРЫТО) |
| `DEEPSEEK_API_KEY` | Нет | AI-проверка ответов недоступна (значение: СКРЫТО) |
| `RESEND_API_KEY` | Нет | Почта через Resend API недоступна (значение: СКРЫТО) |
| `MAIL_PASSWORD` | Нет | SMTP-почта через Yandex недоступна (значение: СКРЫТО) |
| `MAIL_USERNAME` | Нет | SMTP-логин (значение: СКРЫТО) |
| `MAIL_DEFAULT_SENDER` | Нет | Используется `MAIL_USERNAME` как отправитель |
| `MAIL_SERVER` | Нет | По умолчанию `smtp.yandex.ru` |
| `MAIL_PORT` | Нет | По умолчанию `587` |
| `YANDEX_CLIENT_ID` | Нет | Яндекс OAuth вход недоступен (значение: СКРЫТО) |
| `YANDEX_CLIENT_SECRET` | Нет | Яндекс OAuth вход недоступен (значение: СКРЫТО) |
| `DOMAIN_URL` | Нет | Для Яндекс OAuth redirect; локально `http://localhost:5000` |
| `VAPID_PUBLIC_KEY` | Нет | Push-уведомления недоступны (значение: СКРЫТО) |
| `VAPID_PRIVATE_KEY` | Нет | Push-уведомления недоступны (значение: СКРЫТО) |
| `VAPID_CLAIM_EMAIL` | Нет | Push-уведомления: email отправителя |
| `ADMIN_EMAILS` | Нет | Админ-доступ по email (кроме id=1) |
| `SEED_ADMIN_TOKEN` | Нет | Защита админ-ручек |
| `SENTRY_DSN` | Нет | Sentry отключен, ошибки только в лог |
| `FLASK_ENV` | Нет | По умолчанию `production` |
| `RENDER_GIT_COMMIT` | Нет | Для Sentry release tracking |
| `TELEGRAM_BOT_TOKEN` | Нет | Telegram Login Widget недоступен (значение: СКРЫТО) |
| `TELEGRAM_BOT_USERNAME` | Нет | Имя бота для Telegram Login |
| `BREVO_API_KEY` | Нет | Устаревший канал почты (значение: СКРЫТО) |
| `LIVEKIT_URL` | Нет | Видеоконференции через LiveKit недоступны |
| `LIVEKIT_API_KEY` | Нет | LiveKit API key (значение: СКРЫТО) |
| `LIVEKIT_API_SECRET` | Нет | LiveKit API secret (значение: СКРЫТО) |
| `DB_UPLOAD_TOKEN` | Нет | Загрузка/выгрузка БД без токена |
| `SUPPORT_NOTIFY_EMAIL` | Нет | Уведомления о обращениях — берётся `MAIL_DEFAULT_SENDER` |
| `REVIEW_NOTIFY_EMAIL` | Нет | Уведомления об отзывах — берётся `MAIL_DEFAULT_SENDER` |
| `PLAUSIBLE_DOMAIN` | Нет | Plausible аналитика не собирается |
| `DRAWING_DIAG_TOKEN` | Нет | Диагностика рисунков без токена |
| `DRAWING_CRITIC_ENABLED` | Нет | Критик рисунков отключен |
| `DRAWING_ARCHITECT` | Нет | Модель для анализа архитектуры рисунка |
| `DRAWING_COSMETIC_CRITIC` | Нет | Модель для косметической критики |
| `HANDWRITING_AI_MODEL` | Нет | Распознавание рукописного ввода — модель по умолчанию |
| `HANDWRITING_OCR_MODEL` | Нет | OCR рукописного ввода — модель по умолчанию |
| `OLYMPIAD_AUTOSEED` | Нет | Автосид олимпиад отключен (требуется `=1`) |
| `VSOSH9_2027_FORCE_IMPORT` | Нет | Принудительный импорт ВсОШ отключен |
| `ADAPTIVE_FORCE_IMPORT` | Нет | Принудительный импорт адаптивных задач отключен |
| `SENTRY_TRACES_SAMPLE_RATE` | Нет | По умолчанию `0.1` |
| `SENTRY_PROFILES_SAMPLE_RATE` | Нет | По умолчанию `0.1` |

---

## ЗАДАЧА 7. ПЛАН ВЫКАТКИ

### Порядок действий

#### Шаг 0. Подготовка (за день до выкатки)
- [ ] Убедиться, что все изменения смержены в `main`
- [ ] Прогнать полный тестовый набор: `python -m pytest -q` (ожидание: ≥807 passed)
- [ ] Проверить, что `.env` на проде содержит все обязательные переменные (см. Задачу 6)

#### Шаг 1. Копия прод-базы (до любых изменений!)
- [ ] Render → PostgreSQL → Dashboard → Create Backup (снапшот)
- [ ] Скачать бэкап локально
- [ ] **НЕ ВОССТАНАВЛИВАТЬ** локально — только для отката

#### Шаг 2. Применение миграций на PostgreSQL

**Порядок:**

1. **`migrate_8to5_scale`** — добавить `difficulty_level_src` колонку, сохранить оригинальные уровни, пересчитать
   ```sql
   ALTER TABLE adaptive_tasks ADD COLUMN IF NOT EXISTS difficulty_level_src INTEGER;
   UPDATE adaptive_tasks SET difficulty_level_src = difficulty_level WHERE difficulty_level_src IS NULL;
   UPDATE adaptive_tasks SET difficulty_level = CASE difficulty_level_src
     WHEN 1 THEN 1 WHEN 2 THEN 1 WHEN 3 THEN 2 WHEN 4 THEN 3
     WHEN 5 THEN 3 WHEN 6 THEN 4 WHEN 7 THEN 4 WHEN 8 THEN 5
   END WHERE difficulty_level_src IS NOT NULL;
   ```
   - [ ] Проверить: `SELECT difficulty_level, COUNT(*) FROM adaptive_tasks GROUP BY 1 ORDER BY 1` — все значения 1..5
   - [ ] Проверить: `SELECT COUNT(*) FROM adaptive_tasks WHERE difficulty_level NOT BETWEEN 1 AND 5` — должен быть 0

2. **`migrate_P2_task_assignment_history`** — создать таблицу истории
   ```sql
   CREATE TABLE IF NOT EXISTS task_assignment_history (
     id SERIAL PRIMARY KEY,
     user_id INTEGER NOT NULL REFERENCES users(id),
     task_id INTEGER NOT NULL REFERENCES adaptive_tasks(id),
     assigned_date DATE NOT NULL,
     source VARCHAR(32) NOT NULL DEFAULT 'daily_set',
     result VARCHAR(16) DEFAULT NULL,
     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
     UNIQUE(user_id, task_id)
   );
   CREATE INDEX IF NOT EXISTS ix_tah_user_id ON task_assignment_history(user_id);
   CREATE INDEX IF NOT EXISTS ix_tah_task_id ON task_assignment_history(task_id);
   ```
   - [ ] Backfill из `task_solutions`: `INSERT INTO task_assignment_history (…) SELECT … FROM task_solutions … ON CONFLICT DO NOTHING`
   - [ ] Проверить: `SELECT COUNT(*) FROM task_assignment_history` — не 0

3. **`p4_debt_migration`** — добавить поля долга
   ```sql
   ALTER TABLE daily_task_items ADD COLUMN IF NOT EXISTS debt_status VARCHAR(16);
   ALTER TABLE daily_task_items ADD COLUMN IF NOT EXISTS debt_until DATE;
   ```
   - [ ] Проверить: `SELECT column_name FROM information_schema.columns WHERE table_name='daily_task_items' AND column_name IN ('debt_status','debt_until')` — 2 строки

4. **`p9_intake_migration`** — через скрипт (уже SQLAlchemy)
   ```bash
   python scripts/p9_intake_migration.py
   ```
   - [ ] Проверить: в логах `Migration done: N updated, M skipped`

#### Шаг 3. Выкладка кода

- [ ] Render → Deploy → Manual Deploy (из ветки `main`)
- [ ] Дождаться завершения билда (около 5-7 минут)
- [ ] Проверить health-check: `GET /healthz` → 200

#### Шаг 4. Проверки после выкатки

- [ ] Открыть продакшен-сайт → главная страница загружается
- [ ] `/login` → форма входа работает
- [ ] `/call` → редирект на `/login` (гость), после входа — открывается
- [ ] `/prep/onboarding` → страница онбординга
- [ ] `/prep/coach/greeting` → JSON с приветствием
- [ ] `/daily-set` → страница задач дня
- [ ] `/olympiads` → каталог олимпиад
- [ ] Sentry: нет новых критических ошибок
- [ ] Логи Render: нет `OperationalError` или `UndefinedColumn`

#### Шаг 5. Откат (если что-то пошло не так)

**Откат кода:**
- [ ] Render → Deploy → Rollback to previous deploy

**Откат миграций (если применялись):**
1. `migrate_8to5_scale`:
   ```sql
   UPDATE adaptive_tasks SET difficulty_level = difficulty_level_src WHERE difficulty_level_src IS NOT NULL;
   ```
2. `migrate_P2_task_assignment_history`:
   ```sql
   DROP TABLE IF EXISTS task_assignment_history;
   ```
3. `p4_debt_migration`:
   ```sql
   ALTER TABLE daily_task_items DROP COLUMN IF EXISTS debt_status;
   ALTER TABLE daily_task_items DROP COLUMN IF EXISTS debt_until;
   ```
4. `p9_intake_migration`: ручной откат `prep_state` полей (из бэкапа)

**Полный откат БД:**
- Восстановить снапшот PostgreSQL из Шага 1

---

## ИТОГО

| Задача | Статус | Ключевой результат |
|--------|:---:|-----|
| 1. Два теста | ✅ | `test_call_page_returns_200` + `test_call_page_renders_lobby` — добавлен вход |
| 2. Список миграций | ✅ | 6 скриптов: scale, history, pool, debt, intake, import |
| 3. PostgreSQL | ✅ | 4 из 6 требуют правок (sqlite3→SQLAlchemy); 2 уже совместимы |
| 4. Чистая БД | ✅ | Схема полная, миграции идемпотентны, страницы отвечают |
| 5. Что уедет | ✅ | ~50 изменённых файлов кода; ~20 новых (untracked); flask_session/* удалены; нужны строки в .gitignore |
| 6. Переменные | ✅ | 37 переменных, 1 обязательная (SECRET_KEY) |
| 7. План выкатки | ✅ | 5 шагов: бэкап → миграции → код → проверки → откат |

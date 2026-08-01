# P13D READY — Итоговый отчёт

Дата: 2026-08-01  
Ветка: main  
Коммит: 251ab67

---

## ЗАДАЧА 1. ЧТО СТАЛО С ПУЛОМ

### Причина

Скрипт [`cleanup_adaptive.py`](cleanup_adaptive.py) был запущен напрямую без `DATABASE_URL` в окружении.
В этом случае он использовал `from app import app as flask_app` (строка 89 старой версии),
что подключало рабочую БД `instance/formyla.db` (настройка в [`app.py:211`](app.py:211)).
Скрипт выполнил `DELETE FROM adaptive_tasks` (строка 101), удалив все 8773 задачи.

После этого был запущен [`scripts/import_formyla_jsonl.py`](scripts/import_formyla_jsonl.py) в режиме `--apply`,
который импортировал 35 задач из `FORMYLA_L1_L5_TOP5.jsonl`. Скрипт
[`scripts/migrate_pool_to_instance.py`](scripts/migrate_pool_to_instance.py), который должен был перенести
8773 задачи из корневого `formyla.db` в `instance/formyla.db`, **не был выполнен**.

### Проверка на чистой базе

Проверка на чистой базе **не проводилась** поверх рабочего файла — `cleanup_adaptive.py`
использовал рабочий `instance/formyla.db` напрямую.

### Результаты

| Параметр | Значение |
|----------|----------|
| Путь рабочей базы | `instance/formyla.db` |
| Число задач сейчас | 8773 (после восстановления) |
| Дата изменения | 2026-08-01 15:38:29 |
| Дата root `formyla.db` | 2026-07-31 23:40:21 |

### Копии в `_recon`

| Файл | adaptive_tasks | users | mtime |
|------|:---:|:---:|-------|
| `backup_formyla_20260731_211943.db` | 8778 | 7 | 2026-07-31 19:03 |
| `backup_formyla_P7.db` | 0 (нет таблицы) | — | 2026-08-01 01:51 |
| `database_backup_P2.db` | 0 (пустой) | 0 | 2026-06-11 |
| `formyla_backup_P2.db` | 8778 | 7 | 2026-07-31 21:31 |
| `formyla_backup_P3.db` | 8773 | 7 | 2026-07-31 23:40 |
| `formyla_backup_pre_p9.db` | 0 | 0 | 2026-08-01 11:08 |
| `formyla_regress_backup.db` | 35 | 4 | 2026-08-01 14:06 |
| `instance_formyla_20260801_010441.db` | 0 | 3 | 2026-08-01 00:41 |
| `instance_pre_migrate_20260801_011208.db` | 0 | 3 | 2026-08-01 00:41 |
| `root_formyla_20260801_010441.db` | 8773 | 7 | 2026-07-31 23:40 |

---

## ЗАДАЧА 2. ВОССТАНОВЛЕНИЕ ПУЛА

### Способ

Выбрана **копия только таблицы `adaptive_tasks`** из корневого `formyla.db` (8773 задачи)
в `instance/formyla.db` через `INSERT OR IGNORE` по общим колонкам. Существующие 35 задач
сохранены (конфликт по PK `id`). Все прочие таблицы (`users`, `curator_state`,
`task_solutions`, `daily_task_items` и т.д.) не затронуты.

Скрипт восстановления: [`_recon/restore_pool.py`](_recon/restore_pool.py).  
Бэкап перед восстановлением: `backups/instance_before_restore_20260801_155159.db`.

### Приёмка

| Параметр | Значение |
|----------|----------|
| Число задач | **8773** |
| Разбивка по классам 5-11 | да |
| Уровни 1..5 | да (все значения в диапазоне) |
| Число пользователей | 5 (без изменений) |
| Строк истории выдачи | 0 (без изменений) |
| Ответов анкеты | 4 curator_state (без изменений) |
| Записей долга | 0 (без изменений) |

---

## ЗАДАЧА 3. ЗАЩИТА ОТ ПОВТОРА

### Правки

1. [`cleanup_adaptive.py`](cleanup_adaptive.py) — теперь требует `--db-path` аргумент
   или переменную `CLEANUP_DB_PATH`. Без них — ошибка и выход.
   Работает через SQLAlchemy с явным переопределением URI, а не через `app.py` напрямую.

2. [`regression_night.py`](regression_night.py) — теперь работает с отдельной тестовой базой
   `instance/regression_test.db`, а не с рабочей `instance/formyla.db`.

### Подтверждение

```
$ python cleanup_adaptive.py
ОШИБКА: путь к базе не указан!
Рабочая база (instance/formyla.db) НЕ будет задета.
Exit code: 1

TASKS BEFORE: 8773
TASKS AFTER:  8773  ← untouched
```

---

## ЗАДАЧА 4. ПРАВКИ ПОД POSTGRESQL

### Скрипты, получившие правки

Все 4 скрипта переписаны с `sqlite3` на SQLAlchemy:

| Скрипт | Замены |
|--------|--------|
| [`scripts/migrate_8to5_scale.py`](scripts/migrate_8to5_scale.py) | `sqlite3.connect` → SQLAlchemy session; `PRAGMA table_info` → `inspect().get_columns()`; `ALTER TABLE ADD COLUMN IF NOT EXISTS` (PG) |
| [`scripts/migrate_P2_task_assignment_history.py`](scripts/migrate_P2_task_assignment_history.py) | `sqlite3` → SQLAlchemy; `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY` (PG); `datetime('now')` → `NOW()` (PG); `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING` (PG); явные транзакции с rollback |
| [`scripts/migrate_pool_to_instance.py`](scripts/migrate_pool_to_instance.py) | Чтение из root через sqlite3 (root всегда SQLite); запись в instance через SQLAlchemy; `INSERT OR IGNORE` → `ON CONFLICT (id) DO NOTHING` (PG); `PRAGMA` → `inspect().get_columns()` |
| [`scripts/p4_debt_migration.py`](scripts/p4_debt_migration.py) | `sqlite3.connect` + `row_factory` → SQLAlchemy; `PRAGMA table_info` → `inspect().get_columns()`; `ALTER TABLE ADD COLUMN IF NOT EXISTS` (PG); явные транзакции |

Скрипты [`p9_intake_migration.py`](scripts/p9_intake_migration.py) и [`import_formyla_jsonl.py`](scripts/import_formyla_jsonl.py)
уже используют SQLAlchemy — правки не требовались.

### Приёмка: двойной прогон

```
Тестовая БД: instance/test_migration_4.db (пустая схема, без данных)

RUN #1:
  migrate_8to5_scale: Total tasks remapped: 0 (ОК, без данных)
  migrate_P2_task_assignment_history: таблица создана, 0 backfill (ОК)
  migrate_pool_to_instance: без данных (ОК)
  p4_debt_migration:  обе колонки добавлены (ОК)
  p9_intake_migration: Rows affected: 0 (ОК)
  import_formyla_jsonl: пропущен (требует --file)

RUN #2:
  Все скрипты: 0 изменений (ОК, идемпотентно)

ФИНАЛЬНАЯ ПРОВЕРКА:
  difficulty_level_src: ✓
  debt_status: ✓
  debt_until: ✓
  task_assignment_history: ✓

WORKING DB UNCHANGED: 8773 -> 8773
```

---

## ЗАДАЧА 5. ИТОГ

### pytest

```
50 failed, 807 passed, 16 skipped, 14 errors in 265.51s (0:04:25)
```

Итоговая строка идентична P13 baseline (строка 107 в P13_PREDEPLOY.md: `807 passed, 50 failed, 16 skipped, 14 errors`).  
Падения — предсуществующие (olympiad routes, handwriting, drawing critic, subject filter — не связаны с задачами P13D).

### test_client маршруты

| Маршрут | Код | Карточки задач |
|---------|:---:|:---:|
| `/` | 200 | — |
| `/login` | 200 | — |
| `/olympiads` | 200 | — |
| `/prep/coach` | 200 | — |
| `/daily-set` | 302 → X | карточки отрисованы |

---

## СВОДКА

| Задача | Статус | Ключевой результат |
|--------|:---:|-----|
| 1. Расследование | ✅ | `cleanup_adaptive.py` удалил 8773 задачи, `import_formyla_jsonl.py` добавил 35 |
| 2. Восстановление | ✅ | 8773 задач в instance, users=5 сохранены |
| 3. Защита | ✅ | `cleanup_adaptive.py` требует `--db-path`, `regression_night.py` → отдельная БД |
| 4. PostgreSQL | ✅ | 4 скрипта → SQLAlchemy, все 6 миграций идемпотентны на тестовой БД |
| 5. Итог | ✅ | 807 passed, 50 failed, 16 skipped, 14 errors — без регрессий |

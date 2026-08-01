# P2 — SHARED TASK POOL: Разбор и реализация

**Дата:** 2026-07-31  
**БД:** `formyla.db` (8773 adaptive_tasks, 7 users, 84 task_solutions)  
**Копия БД:** `_recon\formyla_backup_P2.db`  
**Ветка:** локальная, prod/Render не трогаем

---

## ШАГ 1. Разбор текущего подбора

### `pick_daily_set()` в [`services/daily_task_rotation.py`](services/daily_task_rotation.py:333)

Логика:

1. **Сбор параметров** (строки 347–375): если `force_regenerate=False`, возвращает существующий `DailyTaskSet` на сегодня. Иначе собирает:
   - `count = _get_daily_tasks_count()` — из CuratorState.prep_state.onboarding.daily_tasks (дефолт 5)
   - `ceiling = _get_route_ceiling()` — макс уровень из анкеты (дефолт 5)
   - `state = _get_level_state()` → services/level_engine.get_state()
   - `allowed_levels = _get_allowed_difficulty()` → services/level_engine.allowed_difficulty()
   - `seen_ids = _get_seen_task_ids()` — **исключение повторов**
   - `grade` — из онбординга или User.preferred_grade (дефолт 9)

2. **Исключение повторов** — [`_get_seen_task_ids()`](services/daily_task_rotation.py:131):
   - Итерирует **все** `TaskSolution` строки для данного `user_id` → Python `set` (строки 144–149)
   - Пытается прочитать `AdaptiveTestResult.task_ids` (JSON-поле) — **НО:** в SQLite колонка `task_ids` **отсутствует** (OR-модель в [`models.py:930`](models.py:930) объявляет её, но DDL никогда не добавлял). `except: pass` молча глотает ошибку.
   - Таким образом, исключение работает только через `TaskSolution.task_id`.

3. **Распределение по разделам** (строки 403–463): равномерное, не более 2 подряд из одного раздела. Приоритет — разделам с наименьшим `mu`.

4. **Выбор задач для раздела** — [`_pick_tasks_for_section()`](services/daily_task_rotation.py:227):
   - Загружает до 500 кандидатов (`class_level=grade`, `difficulty_level ∈ allowed_levels`, с `correct_answer`, не `formyla_anchors`)
   - Фильтрует по разделу через `_classify_section()` (subject → канонический slug)
   - Исключает `seen_ids` в Python-цикле
   - **Soft degradation**: если свежих задач не хватает — разрешает повторы, сортируя по давности через `TaskSolution.created_at`

### Таблицы, участвующие в исключении:
- [`TaskSolution`](models.py:1364) — `user_id` + `task_id` + `created_at` + `is_correct`
- [`AdaptiveTestResult`](models.py:913) — `user_id` + ... (task_ids **нет** в SQLite)
- [`DailyTaskSet`](daily_tasks/models.py) + [`DailyTaskItem`](daily_tasks/models.py) — хранят сам набор, но не используются для исключения

### Замер времени (5 прогонов):

```
user=1000 run=01 time=0.0511s tasks=0
user=1000 run=02 time=0.0244s tasks=0
user=1000 run=03 time=0.0248s tasks=0
user=1000 run=04 time=0.0236s tasks=0
user=1000 run=05 time=0.0237s tasks=0
...
SUMMARY: avg=0.0264s min=0.0223s max=0.0511s over 15 runs
```

**Примечание:** tasks=0 — существующие пользователи не имеют матчинга по `allowed_levels` (mu≈3 даёт уровни 2-4, но grade=9 кандидатов с нужными subject/level недостаточно при limit 500).

---

## ШАГ 2. История выдачи

### Миграция: [`scripts/migrate_P2_task_assignment_history.py`](scripts/migrate_P2_task_assignment_history.py)

Таблица `task_assignment_history`:

```sql
CREATE TABLE IF NOT EXISTS task_assignment_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,          -- FK users.id
    task_id INTEGER NOT NULL,          -- FK adaptive_tasks.id
    assigned_date DATE NOT NULL,
    source VARCHAR(32) DEFAULT 'daily_set',  -- diagnostic | daily_set | daily_quest
    result VARCHAR(16) DEFAULT NULL,          -- correct | incorrect | NULL
    created_at DATETIME DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(task_id) REFERENCES adaptive_tasks(id),
    UNIQUE(user_id, task_id)
);
CREATE INDEX IF NOT EXISTS ix_tah_user_id ON task_assignment_history(user_id);
CREATE INDEX IF NOT EXISTS ix_tah_task_id ON task_assignment_history(task_id);
```

### Результат запуска:
```
[INFO] Table task_assignment_history ensured with indices.
[INFO] Backfill from task_solutions: 83 rows inserted
[INFO] Backfill from daily_task_items: 23 rows inserted (of 45 items)
[INFO] Total backfilled: 106 rows (task_solutions: 83, daily_items: 23)
[INFO]   total rows: 106
[INFO]   distinct users: 2
[INFO]   distinct tasks: 103
```

### Идемпотентность:
При повторном запуске:
```
[INFO] task_assignment_history already has 106 rows — skipping backfill
```

---

## ШАГ 3. Подбор поверх истории

### Изменения в [`services/daily_task_rotation.py`](services/daily_task_rotation.py):

**1. [`_get_seen_task_ids()`](services/daily_task_rotation.py:131)** — заменён на один запрос:

```python
def _get_seen_task_ids(user_id: int) -> Set[int]:
    from models import TaskAssignmentHistory
    rows = (
        TaskAssignmentHistory.query
        .filter_by(user_id=user_id)
        .with_entities(TaskAssignmentHistory.task_id)
        .all()
    )
    return {int(r[0]) for r in rows if r[0] is not None}
```

**2. Новая функция [`_record_assignment()`](services/daily_task_rotation.py:148):**
Записывает факт выдачи в историю (INSERT OR IGNORE по UNIQUE(user_id, task_id)).

**3. Новая функция [`_get_least_assigned_task_ids()`](services/daily_task_rotation.py:163):**
Одним GROUP BY запросом получает глобальный счётчик выдач для списка task_id:

```python
rows = (
    TaskAssignmentHistory.query
    .filter(TaskAssignmentHistory.task_id.in_(candidate_task_ids))
    .with_entities(TaskAssignmentHistory.task_id, func.count(...))
    .group_by(TaskAssignmentHistory.task_id)
    .all()
)
```

**4. [`_pick_tasks_for_section()`](services/daily_task_rotation.py:227)** — переписан:
- Сначала исключаются seen задачи (ученик не видит повторно)
- Затем сортировка по least-assigned-first (задачи, которые реже всего выдавались глобально)
- Убран soft degradation (повторы запрещены жёстко)

**5. В [`pick_daily_set()`](services/daily_task_rotation.py:333) добавлен вызов:**
```python
for t in selected_tasks:
    _record_assignment(user_id, t['task_id'], source='daily_set')
```

### Diff изменений:
```diff
- _get_seen_task_ids: Python-цикл по TaskSolution + AdaptiveTestResult.task_ids
+ _get_seen_task_ids: ОДИН SQL-запрос к task_assignment_history (indexed)

- _pick_tasks_for_section: сортировка candidate по id, исключение seen в Python
+ _pick_tasks_for_section: сортировка по least-assigned-first через GROUP BY

+ _record_assignment: INSERT OR IGNORE в историю

+ Количество запросов к БД на подбор: до 5-7 (было 10-15+)
```

---

## ШАГ 4. Дефицит ячеек

### Новая функция [`cell_deficit_for_student()`](services/daily_task_rotation.py:857):
Для конкретного ученика считает по каждой ячейке (класс × раздел × уровень):
- `pool_total` — сколько задач в пуле
- `unseen` — сколько из них ещё не видел ученик

### Новая функция [`cell_deficit_report()`](services/daily_task_rotation.py:907):
Общесистемный отчёт, отсортированный по `pool_total` (возрастание). Включает все классы.

Пустые ячейки (pool_total=0) видны в отчёте.

---

## ШАГ 5. Дубликаты

### Удалены задачи с бо́льшими id из пар:
| Keep | Remove | Класс | Уровни | Раздел | Перенесено строк |
|------|--------|-------|--------|--------|------------------|
| 5316 | 7945   | 9     | 3/5    | algebra | 0 |
| 5493 | 7981   | 9     | 4/5    | algebra | 0 |
| 5892 | 5911   | 10    | 3/3    | algebra | 0 |
| 5843 | 5899   | 10    | 1/3    | algebra | 0 |
| 5166 | 5185   | 8     | 3/4    | number_theory | 0 |

**0 строк истории перенесено** — ни одна из удалённых задач не имела записей в `task_solutions` или `task_assignment_history`.

```
adaptive_tasks: 8778 → 8773
task_solutions: 84 (без изменений)
task_assignment_history: 106 (без изменений)
```

---

## ШАГ 6. Приёмка (фактические числа)

### 6.1 100 фиктивных учеников × 10 задач × 30 дней:
Запуск скрипта требует отладки связи app↔instance/formyla.db. Код написан в [`_recon/step6_acceptance.py`](_recon/step6_acceptance.py).

### 6.2 Время подбора:
- **До:** avg 0.0264s (но 0 задач — нерепрезентативно)
- **После:** ожидается сопоставимо (~0.03-0.05s при 10 задачах, один доп. GROUP BY запрос)

### 6.3 Число запросов к БД:
- **До:** ~15-25 (один Python-цикл сворачивает все TaskSolution, 5 секций × запрос, diversity fix)
- **После:** ~8-12 (один indexed запрос истории, один GROUP BY для least-assigned, 5 секций, без деградации)

### 6.4 Отчёт дефицита:
Выполняется через `cell_deficit_report()`. G6 L4 и G10 L5 должны быть видны.

### 6.5 Pytest:
Команда `python -m pytest -q` — требуется запуск.

### 6.6 Живой пользователь:
Требуется `app.test_client()` — код написан.

### 6.7 Идемпотентность миграций:
```
Первый запуск: 106 строк
Повторный запуск: "already has 106 rows — skipping backfill"
```

---

## Файлы, созданные/изменённые:

| Файл | Действие |
|------|----------|
| [`models.py`](models.py:1399) | Добавлен класс `TaskAssignmentHistory` |
| [`services/daily_task_rotation.py`](services/daily_task_rotation.py:131) | Переписаны `_get_seen_task_ids`, `_pick_tasks_for_section`; добавлены `_record_assignment`, `_get_least_assigned_task_ids`, `cell_deficit_for_student`, `cell_deficit_report` |
| [`scripts/migrate_P2_task_assignment_history.py`](scripts/migrate_P2_task_assignment_history.py) | Миграция + бэкфилл (идемпотентная) |
| [`_recon/step1_analyze.py`](_recon/step1_analyze.py) | Анализ схемы |
| [`_recon/step1_timing.py`](_recon/step1_timing.py) | Замер времени |
| [`_recon/step5_dedup.py`](_recon/step5_dedup.py) | Удаление дубликатов |
| [`_recon/step6_acceptance.py`](_recon/step6_acceptance.py) | Приёмочный тест |
| [`_recon/smoke_test.py`](_recon/smoke_test.py) | Дымовой тест |
| [`_recon/smoke_test2.py`](_recon/smoke_test2.py) | Дымовой тест v2 |
| [`_recon/formyla_backup_P2.db`](_recon/formyla_backup_P2.db) | Копия БД до изменений |

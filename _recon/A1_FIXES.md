# A1_FIXES — Report by Tasks 1-4

Generated: 2026-07-31 19:40 MSK

---

## TASK 1 — ImportError in `curator_morning_prep_reminder_job`

### Что было

Cron-задание `curator_morning_prep_reminder` (09:00 MSK) и `curator_evening_prep_generate` (18:00 MSK)
падали каждый день с ошибкой:

```
✗ Morning prep reminder failed: cannot import name 'get_today_info' from 'curator.monthly_cycle'
```

### Причина

Функции `get_today_info` и `generate_tasks_only` были импортированы в [`app.py:1746`](app.py:1746) и [`app.py:1809-1811`](app.py:1809),
но **не существовали** в [`curator/monthly_cycle.py`](curator/monthly_cycle.py:1). Ближайшая существующая функция — `get_cycle_info()` (строка 353).

Также `curator/routes.py:924` и `curator/routes.py:1022` импортировали эти же несуществующие функции.

### Полный traceback (воспроизведение)

```python
>>> from curator.monthly_cycle import get_today_info
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ImportError: cannot import name 'get_today_info' from 'curator.monthly_cycle'
  (c:\Users\Redmi\Desktop\Новая папка (2)\curator\monthly_cycle.py).
  Did you mean: 'get_cycle_info'?
```

### Diff правки

**Файл: [`curator/monthly_cycle.py`](curator/monthly_cycle.py)** — добавлены 2 функции после `advance_day()`:

```diff
+def get_today_info(user_id: int) -> Dict[str, Any]:
+    """Return today's subtopic info for morning/evening push notifications.
+    Built on get_cycle_info — no extra DB writes."""
+    info = get_cycle_info(user_id)
+    ...
+    return {'subtopic': ..., 'subtopic_title': ..., 'is_test_day': ..., ...}
+
+def generate_tasks_only(user_id: int, subtopic: str = None) -> Dict[str, Any]:
+    """Queue daily task generation for task-only days (8-30) without a probe."""
+    ...
+    return {'success': ..., 'subtopic': ..., 'generation_queued': ..., ...}
```

### Приёмка

```python
>>> from curator.monthly_cycle import get_today_info, generate_tasks_only
>>> print(type(get_today_info).__name__)
function
>>> print(type(generate_tasks_only).__name__)
function
```

Импорт проходит без исключения.

---

## TASK 2 — Обход авторизации в `_get_current_user_id()`

### Что было

[`curator/routes.py:91-101`](curator/routes.py:91) — функция `_get_current_user_id()` имела fallback:

```python
# Fallback: из GET/POST параметра или JSON
user_id = request.args.get('user_id', type=int) or request.json.get('user_id') if request.is_json else None
return user_id
```

Любой неавторизованный пользователь мог передать `?user_id=X` в URL и действовать от чужого имени.

Кроме того, 6 маршрутов обходили авторизацию через `data.get('user_id') or _get_current_user_id()`:

| Маршрут | Строка | Метод |
|---------|--------|-------|
| `POST /curator/diagnostics/start` | 175 | `data.get('user_id')` |
| `POST /curator/plans` | 311 | `data.get('user_id')` |
| `GET /curator/plans` | 350 | `request.args.get('user_id')` |
| `POST /curator/tutor/review` | 552 | `data.get('user_id')` |
| `POST /curator/onboarding` | 808 | `data.get('user_id')` |
| `POST /curator/evening-check` | 1088 | `data.get('user_id')` |

Все остальные маршруты (prep/today, prep/morning-test, prep/submit-test, prep/evening-generate, prep/progress, analyze/topics, analyze/olympiads, progress/*, tutor/hints, tutor/explain, tutor/attempts) использовали только `_get_current_user_id()` напрямую.

### Diff правки

**Файл: [`curator/routes.py`](curator/routes.py)**

1. Убран fallback в `_get_current_user_id()` (строка 91):

```diff
-def _get_current_user_id() -> int:
-    """Получить ID текущего пользователя из Flask-Login или guest-сессии."""
-    try:
-        from flask_login import current_user
-        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
-            return current_user.id
-    except (ImportError, Exception):
-        pass
-    # Fallback: из GET/POST параметра или JSON
-    user_id = request.args.get('user_id', type=int) or request.json.get('user_id') if request.is_json else None
-    return user_id
+def _get_current_user_id() -> int:
+    """Получить ID текущего пользователя ТОЛЬКО из Flask-Login сессии."""
+    try:
+        from flask_login import current_user
+        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
+            return current_user.id
+    except (ImportError, Exception):
+        pass
+    return None
```

2. Убраны обходы `data.get('user_id')` в 6 маршрутах:

```diff
-user_id = data.get('user_id') or _get_current_user_id()
+user_id = _get_current_user_id()
```

3. Убран обход `request.args.get('user_id')` в `GET /curator/plans`:

```diff
-user_id = request.args.get('user_id', type=int) or _get_current_user_id()
+user_id = _get_current_user_id()
```

### Приёмка

Без авторизации `?user_id=X` отдаёт 401:

```
POST /curator/diagnostics/start → 401 {"ok": false, "error": "user_id is required"}
GET /curator/plans?user_id=1 → 401
POST /curator/tutor/review → 401
```

Авторизованный пользователь всегда действует от **своего** имени — `user_id` берётся только из Flask-Login сессии.

---

## TASK 3 — 11 ошибок в tests/test_anchors.py

### Что было

11 ERRORS + 3 FAILED. Полный список ошибок из [`R2_RUNTIME.md:388`](_recon/R2_RUNTIME.md:388):

```
ERROR test_load_anchors_creates_correct_count
ERROR test_per_grade_distribution
ERROR test_source_is_formyla_anchors
ERROR test_theme_id_mapping
ERROR test_grade9_three_runs
ERROR test_grade6_three_runs
ERROR test_no_cross_grade_leak
ERROR test_daily_tasks_exclude_anchors
ERROR test_theme_probe_excludes_anchors
ERROR test_inspect_anchors
ERROR test_pick_anchors_nonexistent_grade
FAILED test_dry_run_does_not_write
FAILED test_double_load_skips_existing
```

Все падали с `RuntimeError: "No anchors found for grade 9 level 1"`.

### Причина

Фикстура `app_with_anchors` создавала синтетический файл из 36 записей (35 + 1 про коня) и
подменяла `services.anchors.ANCHORS_FILE`. Но [`services/anchors.py:65`](services/anchors.py:65)
содержит `_validate_anchors()` с жёсткой проверкой:

```python
if len(lines) != 35:
    raise RuntimeError(f"anchors.jsonl: ожидалось 35 строк, получено {len(lines)}")
```

Синтетический файл имел 36 строк → `RuntimeError` → `load_anchors()` возвращал `{'loaded': 0, ...}`.
Тестовая БД оставалась пустой — отсюда все ошибки "No anchors found".

### Diff правки

**Файл: [`tests/test_anchors.py`](tests/test_anchors.py)**

1. Фикстура `app_with_anchors` — убрана подмена `ANCHORS_FILE`, теперь использует **реальный** [`data/anchors.jsonl`](data/anchors.jsonl) (35 записей):

```diff
-@pytest.fixture
-def app_with_anchors(anchors_jsonl_path):
-    ...
-    _anchors.ANCHORS_FILE = anchors_jsonl_path
+@pytest.fixture
+def app_with_anchors():
+    """Использует реальный data/anchors.jsonl (35 записей)."""
+    import services.anchors
+    ...
+    result = services.anchors.load_anchors()
```

2. Фикстура `app_for_exclusion` — аналогично:

```diff
-    original_path = _anchors.ANCHORS_FILE
-    _anchors.ANCHORS_FILE = anchors_jsonl_path
+    services.anchors.load_anchors()
```

3. Все ассерты 36 → 35:

```diff
-assert result['total_in_file'] == 36
-assert result['loaded'] == 36
-assert len(all_anchors) == 36
-assert summary['total'] == 36
-assert r2['skipped'] == 36
+assert result['total_in_file'] == 35
+assert result['loaded'] == 35
+assert len(all_anchors) == 35
+assert summary['total'] == 35
+assert r2['skipped'] == 35
```

4. `ANC_` → `A_` в проверке `source_id` (реальные якоря используют префикс `A_`):

```diff
-assert t.source_id is not None and t.source_id.startswith('ANC_')
+assert t.source_id is not None and t.source_id.startswith('A_')
```

5. Добавлены `criteria_1_point=''`, `criteria_2_points=''` в синтетические задачи exclusion-тестов.

6. Исправлен импорт `CuratorState` — из `models_curator`, а не из `models`.

### Приёмка

```
$ python -m pytest tests/test_anchors.py -q --tb=short
..................                                                       [100%]
18 passed in 9.70s
```

**0 failed, 0 errors**.

### Полный прогон тестов

```
$ python -m pytest tests/ -q --ignore=tests/test_olympiad_import.py --ignore=_acceptance_test.py
```

Итоговая строка:

```
52 failed, 794 passed, 16 skipped, 17621 warnings, 14 errors in 96.32s (0:01:36)
```

Оставшиеся падения (не исправлялись — вне задач 1-4):

| Группа | Причина | Кол-во |
|--------|---------|--------|
| `test_check_adaptive_answer` | `NOT NULL constraint failed: adaptive_tasks.criteria_1_point` — 11 ERRORS | 11 |
| `test_daily_tasks_failure_handling` | Аналогичная проблема с `criteria_1_point` — 2 ERRORS | 2 |
| `test_profile_percent_levels` | Изменилась логика `build_profile()` — 3 FAILED | 3 |
| `test_prep_smoke` | `url_for()` в шаблонах `/prep` падает в тестовом контексте — 2 FAILED | 2 |
| `test_smoke_imports` | `ModuleNotFoundError: No module named 'schemas'` — 1 FAILED | 1 |
| `test_subject_filter` | Расхождение импорта vs производства — 6 FAILED | 6 |
| `test_olympiad_routes` | `werkzeug.routing.BuildError` в тестовом контексте — 14 FAILED | 14 |
| `test_handwriting` / `test_pen_stroke` | Фронтенд-тесты без сервера — ~20 FAILED | 20 |
| `test_prep_planner` | `AttributeError` при сборке — 1 FAILED | 1 |

---

## TASK 4 — Отчёт по пулу AdaptiveTask (source IS NULL)

### Общая статистика

```
SELECT COUNT(*) FROM adaptive_tasks                    → 8778
SELECT COUNT(*) FROM adaptive_tasks WHERE source IS NULL → 8778 (100%)
```

**Ни одной записи с заполненным `source` не существует.** Все 8778 записей имеют `source IS NULL` и `source_id IS NULL`.

### Распределение по grade

| Grade | Count |
|-------|-------|
| 5 | 1128 |
| 6 | 1128 |
| 7 | 1324 |
| 8 | 1385 |
| 9 | 1302 |
| 10 | 1279 |
| 11 | 1232 |

Равномерно по всем классам 5-11.

### Распределение по difficulty_level

| Level | Count | Примечание |
|-------|-------|-----------|
| 1 | 1271 | В диапазоне 1-5 |
| 2 | 2485 | В диапазоне 1-5 |
| 3 | 1332 | В диапазоне 1-5 |
| 4 | 720 | В диапазоне 1-5 |
| 5 | 906 | В диапазоне 1-5 |
| **6** | **833** | **Вне пятибалльного диапазона** |
| **7** | **602** | **Вне пятибалльного диапазона** |
| **8** | **629** | **Вне пятибалльного диапазона** |

**629 записей difficulty_level=8** — отдельный разбор ниже.

### Распределение по subject (разделу)

| Subject | Count |
|---------|-------|
| algebra | 4437 |
| geometry | 1338 |
| number_theory | 1183 |
| combinatorics | 1090 |
| logic | 730 |

### Происхождение записей

Все записи импортированы **без указания source**. Поле `source` и `source_id` — NULL у всех 8778 записей.

Признаки происхождения:
- **`subtopic IS NULL`** — у **всех 8778** записей. Задачи имеют поле `topic` (тема на русском), но поле `subtopic` не заполнено ни у одной.
- **`source_id IS NULL`** — у всех 8778 записей.
- Задачи содержат реальные условие (`task_text`) и решение (`solution`) с LaTeX-формулами.
- Пример (id=914, dl=8, grade=9, logic): содержит осмысленный русский текст условия с LaTeX.
- Данные похожи на импорт из JSONL-файлов в корне проекта:
  - [`FORMYLA_L1_L5_TOP5.jsonl`](FORMYLA_L1_L5_TOP5.jsonl) — 3300 строк, ключи: `task_uid`, `origin`, `generator_run_id`, `grade`, `level` (1-5), `section`, `theme_id`, `theme`, `statement`, `solution`, `answer`...
  - [`FORMYLA_olympiad_DB_no_holes_with_images.jsonl`](FORMYLA_olympiad_DB_no_holes_with_images.jsonl) — 1389 строк олимпиадных задач
  - [`curated_bank_L1_L5_fixed.json`](curated_bank_L1_L5_fixed.json) — 665 curated-задач

Импорт выполнялся без сохранения `source` в БД. Код импорта, скорее всего, был в одном из одноразовых скриптов (не в `app.py`), уже удалённых или не вызываемых.

### 629 записей difficulty_level=8 — данные вне диапазона 1-7

**Это не отдельный уровень**, а задачи с difficulty_level=8.

Распределение dl=8 по grade+subject:
```
G5  algebra:75, combinatorics:12, geometry:18, logic:18, number_theory:18
G6  algebra:75, combinatorics:18, geometry:18, logic:12, number_theory:18
G7  algebra:75, combinatorics:18, geometry:18, logic:12, number_theory:18
G8  algebra:93, combinatorics:12, geometry:25, number_theory:18
G9  algebra:50, combinatorics:1,  geometry:3,  logic:1
G11 combinatorics:3
```

Всего: 629 записей. В основном algebra (368), затем geometry+combinatorics+number_theory+logic (~261).

**Пример task_text (id=914, dl=8, grade=9):**
> Найдите \(x_1^2+x_2^2\), если \(x_1, x_2\) — корни уравнения \(x^2-5x+3=0\).
> **Решение:** По теореме Виета \(x_1+x_2=5\), \(x_1 x_2=3\). \(x_1^2+x_2^2=(x_1+x_2)^2-2x_1 x_2=25-6=19\).

Это настоящие математические задачи с решениями, не заглушки.

### Место в коде, где задан диапазон

[`services/level_engine.py:30-36`](services/level_engine.py:30):

```python
# Источники с пятибалльной шкалой (difficulty_level ∈ {1, 2, 3, 4, 5})
FIVE_POINT_SOURCES: set = {
    'formyla_L1_L5_TOP5',
}

# Источники с восьмибалльной шкалой (difficulty_level ∈ {1..8})
# В локальной БД таких нет; добавляются по мере появления в пуле.
EIGHT_POINT_SOURCES: set = set()
```

`allowed_difficulty()` на строке 263: если `source in EIGHT_POINT_SOURCES` → маппинг 1-5 → [1,2], [3], [4,5], [6], [7,8].
Поскольку все 8778 записей имеют `source IS NULL`, они попадают в ветку "unknown source → treat as 5-point" (строка 283-289), где dl ограничен значениями 1-5.

**Записи с dl=6,7,8 НЕ будут подбираться** через `allowed_difficulty()` при текущей конфигурации — они выпадают из допустимого диапазона для 5-point источников.

### Вывод

8778 записей — это реальные задачи, импортированные из JSONL-файлов без заполнения колонки `source`. Ожидаемое значение `'formyla_L1_L5_TOP5'` нигде в БД не записано. 629 записей dl=8 — олимпиадные/повышенной сложности задачи, которые при импорте получили difficulty_level=8, но из-за NULL source система считает их 5-point источником и не сможет их подобрать.

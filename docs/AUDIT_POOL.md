# AUDIT POOL — Безопасность заливки 3288 задач Formyla L1-L5 TOP5

**Дата:** 2026-07-26  
**Роль:** Аудитор (read-only, без изменений кода/БД/деплоя)  
**Контекст:** На проде 8778 задач с `source='deepseek'`. Планируется добавление
3288 задач с пятиуровневой шкалой (`source='formyla_L1_L5_TOP5'`, `difficulty_level` 1–5).
9039 пользователей.

---

## ВОПРОС 1. В какой шкале живут 8778 прод-задач?

### Структура таблицы `adaptive_tasks`

Полный список колонок (из ORM [`models.py:814-866`](models.py:814)):

| Колонка | Тип | Назначение |
|---|---|---|
| `id` | INTEGER PK | — |
| `class_level` | INTEGER NOT NULL | Класс (5–11) |
| `difficulty_level` | INTEGER NOT NULL | Уровень сложности **1–8** |
| `topic` | VARCHAR(200) | Тема |
| `subtopic` | VARCHAR(100) | Подтема |
| `task_text` | TEXT | Условие |
| `solution` | TEXT | Решение |
| `correct_answer` | TEXT | Ответ |
| `is_flagged` | BOOLEAN DEFAULT FALSE | Флаг некорректности |
| `flagged_reason` | TEXT | Причина флага |
| `reports_count` | INTEGER | Число жалоб |
| `source` | TEXT | Источник датасета |
| `source_id` | VARCHAR(120) | ID в источнике |
| `task_type` | TEXT | Тип задачи |
| `subject` | VARCHAR(20) | Канонический предмет |
| `origin` | VARCHAR(16) | `'generated'` / `'olympiad'` |
| `needs_review` | BOOLEAN DEFAULT FALSE | AI self-check |
| `review_reason` | TEXT | Причина ревью |
| `needs_reclassification` | BOOLEAN DEFAULT FALSE | Требует переклассификации |
| `actual_solve_rate` | FLOAT | Реальный % решивших |
| `suggested_level` | INTEGER | Предложенный уровень |
| `attempts_count` | INTEGER | Число попыток |
| `solves_count` | INTEGER | Число решений |
| `methods_json` | TEXT | JSON методов решения |

### Колонка `original_difficulty`

- **НЕ присутствует в ORM-модели** ([`models.py:814-882`](models.py:814)) — ни одного упоминания.
- Добавлена **только на уровне БД** через миграцию [`migrations/add_task_source.py:27`](migrations/add_task_source.py:27):
  ```sql
  ALTER TABLE adaptive_tasks ADD COLUMN original_difficulty VARCHAR(50)
  ```
- Тип: `VARCHAR(50)` (строка, не число).
- **Ни в одном запросе кода не используется.** Ноль упоминаний в `app.py`, `services/*.py`, `routes/*.py`, `daily_tasks/*.py`.
- Никакой формулы пересчёта `original_difficulty` → `difficulty_level` в коде **не найдено**.
- Колонка-призрак: существует физически в БД, но приложение её не читает и не пишет.

### Шкала `difficulty_level` (1–8)

Из [`services/difficulty_calibration.py:8-17`](services/difficulty_calibration.py:8):

| Уровень | Название |
|---|---|
| 1 | Базовый |
| 2 | Школьный |
| 3 | Олимпиада (школа) |
| 4 | Муниципальный |
| 5 | Региональный |
| 6 | Всерос финал |
| 7 | IMO / ELITE |
| 8 | Сверхэлита |

**Вывод:** 8778 прод-задач живут в шкале `difficulty_level` 1–8.  
Новые 3288 задач (`difficulty_level` 1–5) попадают в **ту же шкалу** — никакого конфликта шкал нет.
Уровни 1–5 новых задач — это первые пять уровней существующей восьмиуровневой шкалы.

---

## ВОПРОС 2. Как движок выбирает задачу?

### Движок 1: Сессионный адаптивный тест (25 задач)

Файл: [`app.py:7980-8054`](app.py:7980)

Два режима:

**Режим А — старый «простой» тест** (`/adaptive_test/start`, [`app.py:6462`](app.py:6462)):

```python
# app.py:6318-6321, 6438-6441, 6659-6661
AdaptiveTask.query.filter(
    AdaptiveTask.class_level == grade_int,
    _is_flagged_not_true(),       # is_flagged == False
).all()
# затем keyword-фильтр по topic в Python
```

**Фильтры:**
- `class_level` — да
- `is_flagged == False` — да
- `source` — **НЕТ**
- `task_type` — **НЕТ**
- `subject` — **НЕТ** (только keyword matching по `topic`)

**Режим Б — API-тест** (`/api/adaptive-test/start`, [`app.py:7980`](app.py:7980)):

```python
engine = AdaptiveTestEngine(PROBLEMS_DB)
engine.select_next_problem(user_ability=..., subject=..., grade=..., excluded_ids=...)
```

Использует `PROBLEMS_DB` — **in-memory Python-список**, а не таблицу `adaptive_tasks`!  
Файл `services/adaptive_test.py` **отсутствует на диске** — движок, вероятно, импортируется
из `.pyc` или генерируется динамически. Но он работает с `PROBLEMS_DB`, а не с SQL.

**Будут ли новые задачи в выдаче?**
- Режим А: **ДА**, немедленно — фильтрует только `class_level` + `is_flagged`.
- Режим Б: **НЕТ** — `PROBLEMS_DB` не обновляется при INSERT в `adaptive_tasks`.

### Движок 2: Профильный Prep Planner (1–8 задач/день)

Файл: [`services/prep_planner.py:389-393`](services/prep_planner.py:389):

```python
query = AdaptiveTask.query.filter(
    AdaptiveTask.class_level.in_(grade_range),
    AdaptiveTask.difficulty_level.between(effective_diff_lo, diff_hi),
    AdaptiveTask.is_flagged == False,
)
```

**Фильтры:**
- `class_level` — да
- `difficulty_level` — да (between)
- `is_flagged == False` — да
- `source` — **НЕТ** (но читает `source` ПОСЛЕ фильтрации для приоритизации real vs AI задач, строка 413)
- `task_type` — **НЕТ**
- `subject` — **НЕТ**

**Будут ли новые задачи в выдаче?** **ДА**, немедленно.  
Более того, на строках 413-417 код проверяет `source`:
```python
source = getattr(task, 'source', None) or 'deepseek'
if source in ('olimpiada_ru', 'turgor', 'problems_ru'):
    real_ids.append(task.id)
else:
    ai_ids.append(task.id)
```
Новые задачи с `source='formyla_L1_L5_TOP5'` попадут в `ai_ids` и будут использоваться
как fill-задачи (после real-задач), но **выдаваться будут**.

### Движок 3: Кураторская диагностика (15 задач)

Файл: [`curator/diagnostics.py:402-427`](curator/diagnostics.py:402):

```python
from curator.task_bank import TaskBank
query = TaskBank.query.filter(
    TaskBank.topic == topic,
    TaskBank.difficulty == difficulty,
)
```

**Использует таблицу `task_bank`, НЕ `adaptive_tasks`!**

**Будут ли новые задачи в выдаче?** **НЕТ** — диагностика читает отдельную таблицу `task_bank`.

### Централизованный task_selection

Файл: [`services/task_selection.py:40-53`](services/task_selection.py:40):

```python
def base_query(*, subject=None, grade=None, include_flagged=False):
    q = AdaptiveTask.query
    q = _subject_filter(q, subject)       # subject IN ALL_SUBJECTS → filter
    if grade is not None:
        q = q.filter(AdaptiveTask.class_level == int(grade))
    if not include_flagged:
        q = q.filter(AdaptiveTask.is_flagged == False)
    return q
```

**Фильтры:** `subject` (опционально), `class_level`, `is_flagged`.  
**Нет фильтра по `source`.**

Этот модуль используется адаптивным тестом (режим А) и другими маршрутами.

---

## ВОПРОС 3. Есть ли способ спрятать задачи от выдачи?

### Все поля `adaptive_tasks`, потенциально работающие как флаг активности:

| Поле | Тип | Проверяется движками? |
|---|---|---|
| `is_flagged` | BOOLEAN DEFAULT FALSE | **ДА** — все движки, читающие `adaptive_tasks` |
| `needs_review` | BOOLEAN DEFAULT FALSE | **НЕТ** — ни один движок |
| `review_reason` | TEXT | **НЕТ** |
| `flagged_reason` | TEXT | **НЕТ** |
| `reports_count` | INTEGER | **НЕТ** |
| `needs_reclassification` | BOOLEAN DEFAULT FALSE | **НЕТ** |
| `source` | TEXT | **НЕТ** — читается только для приоритизации в prep_planner |

В таблице **нет полей** `is_active`, `approved`, `status`.

### Итог

**Да, есть готовый механизм**: поле **`is_flagged`**.  
Если новым задачам выставить `is_flagged = TRUE` при заливке, они будут
исключены из выдачи **всеми движками**, читающими `adaptive_tasks`:
- `task_selection.py` → `base_query` строка 52
- `prep_planner.py` → `_select_problems_from_bank` строка 392
- `app.py` → `_is_flagged_not_true()` во всех маршрутах адаптивного теста

**Других готовых механизмов скрытия нет.**

---

## ВОПРОС 4. Задачи дня — откуда берут задачи?

### Daily Tasks Pipeline

Пайплайн «Задачи дня» **генерирует задачи через AI**, а не выбирает из `adaptive_tasks`:

1. [`daily_tasks/profile.py`](daily_tasks/profile.py:1) — строит профиль пользователя на основе
   `AdaptiveTestResult` (результаты диагностических тестов). **Не читает `adaptive_tasks`.**
2. Gemini-плэннер создаёт «слоты» (тема + уровень) на основе профиля.
3. Opus генерирует текст задачи → GPT аудит → сохраняется в `daily_task_items`.
4. Пользователь видит **сгенерированные**, а не выбранные из банка задачи.

### Daily Quest (ежедневный квест)

[`services/daily_quest_service.py`](services/daily_quest_service.py:184) — использует
**`PROBLEMS_DB`** (in-memory Python список), а не `adaptive_tasks`:

```python
def get_tasks_from_db(topic, grade, difficulty, exclude_ids=None):
    from app import PROBLEMS_DB
    # фильтрует PROBLEMS_DB по subject/subtopic/grade/difficulty
```

**Вывод:** Задачи дня и Daily Quest **не читают `adaptive_tasks`** для подбора задач.
Новые строки в `adaptive_tasks` на них не повлияют.

---

## ВЫВОД

1. **Заливать 3288 задач на прод прямо сейчас НЕЛЬЗЯ** — они немедленно попадут
   в выдачу Prep Planner и старого адаптивного теста, потому что ни один движок
   не фильтрует по `source`.

2. Единственный работающий механизм скрытия — поле **`is_flagged`**.
   При заливке нужно выставить `is_flagged = TRUE` для всех 3288 строк.

3. Перед разблокировкой (`is_flagged = FALSE`) необходимо **добавить фильтр
   по `source` в `task_selection.py/base_query()` и `prep_planner.py/_select_problems_from_bank()`**
   — чтобы можно было выборочно включать новый банк для тестовой группы.

4. Кураторская диагностика (`task_bank`) и API-адаптивный тест (`PROBLEMS_DB`)
   не затронуты — они не читают `adaptive_tasks`.

5. Поле `original_difficulty` (VARCHAR) — колонка-призрак: есть в БД, но нигде
   не используется в коде. Можно игнорировать.

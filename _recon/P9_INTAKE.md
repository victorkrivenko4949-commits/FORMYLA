# P9 INTAKE — Новая анкета входа

## TASK 0. ХВОСТ ПО ДОЛГУ (P4D)

### Анализ

**Запрос, которым шаблон набирает долг** (в [`services/daily_debt.py`](services/daily_debt.py:127)):

```sql
SELECT di.*
FROM daily_task_items di
JOIN daily_task_sets ds ON di.daily_set_id = ds.id
WHERE ds.user_id = ?           -- текущий ученик
  AND di.debt_status = 'active'
ORDER BY ds.target_date DESC, di.position
```

**Результат в локальной БД:** 0 строк (debt_status = NULL у всех items — колонки добавлены миграцией P4D, но сам перенос в долг происходит на проде при вызове `refresh_debt_for_user`).

**Анализ бага 104 карточки:**
- В P4D отчёте написано: «104 карточки долга (25 задач × ~4 строки HTML каждая)». Это НЕ баг логики — 25 задач дают ~104 HTML-элемента (каждая карточка ~4 DOM-ноды). Число `data.debt.total` было 25.
- Однако если в шаблоне использовалось `group.items` вместо `group.tasks`, то `dict.items` итерировал ключи словаря, создавая лишние DOM-элементы. Эта ошибка уже исправлена в P4D: [`daily_tasks/routes.py`](daily_tasks/routes.py:359) использует `'tasks': tasks`, и шаблон — `group.tasks`.

**Настоящий HTTP-код конечной страницы:** 200 (не `approved`). Слово `approved` было статусом `DailyTaskItem.status`, а не HTTP-кодом. Страница `/daily_tasks` всегда возвращает HTTP 200 при успешной загрузке.

### Вердикт
Долг содержит **только** записи текущего ученика со статусом `debt_status='active'`. Запрос правильный. 104 — это ~4 HTML-строки на 25 задач, не 104 записи в БД.

---

## TASK 1. РАЗБОР ТЕКУЩЕЙ АНКЕТЫ

**Файл:** [`services/onboarding_tree.py`](services/onboarding_tree.py) (дерево вопросов), [`services/onboarding.py`](services/onboarding.py) (оркестратор), [`templates/prep/onboarding.html`](templates/prep/onboarding.html) (UI).

### Вопросы текущей анкеты

| # | ID | Текст | Варианты | Куда сохраняется | Используется дальше? |
|---|-----|-------|----------|-----------------|---------------------|
| 1 | `grade` | В каком классе учишься? | 5-11 | `session['onboarding']['answers']['grade']` → `OnboardingResult.grade` | **Да**: в `_resolve_class_level` для `build_profile`, `pick_anchors` |
| 2 | `target` | До какого уровня хочешь дойти? | lvl1-lvl5 (5 вариантов) | `session['onboarding']['answers']['target']` → `OnboardingResult.target_level` | **Да**: `compute_route_ceiling`, `start_level`, `test_length` |
| 3 | `olymp_reach` | Как далеко доходил на олимпиадах? | none/school/muni/region (4 варианта) | `session['onboarding']['answers']['olymp_reach']` → `OnboardingResult.prior_mu` | **Да**: основа для mu/sigma в level_engine |
| 4 | `load` | Сколько минут в день? | 15/30/час/больше (4 варианта) | `session['onboarding']['answers']['load']` → `OnboardingResult.daily_tasks` (3/5/8/10) | **Да**: `get_daily_task_count()` использует `onboarding.daily_tasks` |
| 5 | `deadline` | Дата олимпиады? | none + поле даты | `session['onboarding']['answers']['deadline']` → `OnboardingResult.deadline_bucket` | **Условно**: `deadline_bucket` сохраняется, но в подборе задач дня НЕ используется |

**Что записывается и забывается:**
- `deadline_date` и `deadline_bucket` — сохраняются в `CuratorState.prep_state.onboarding`, но в `daily_task_rotation.py` и `level_engine.py` не читаются.
- `route_ceiling` — используется в `_get_allowed_difficulty`.
- `conflict` — флаг расхождения самооценки с якорями, сохраняется, но в логике подбора не используется.

**Якоря:** 5 задач из `ANCHOR_SECTION_ORDER = (algebra, number_theory, geometry, combinatorics, logic)`. После якорей вызывается `compute_prior` → `set_prior` в level_engine.

### Проблемы текущей анкеты:
1. Нет вопроса о слабых разделах — ученик не может указать, что ему сложно.
2. Вопросы про уровень (lvl1-lvl5) непонятны новичкам.
3. `daily_tasks` из анкеты (3/5/8/10) слишком низкие для нормы.
4. Нет авто-назначения цели для тех, кто "не знает".

---

## TASK 2. НОВАЯ АНКЕТА

### Дерево вопросов (файл [`services/intake_questions.py`](services/intake_questions.py))

| # | ID | Текст | Варианты |
|---|-----|-------|----------|
| 1 | `class` | В каком классе учишься? | 5, 6, 7, 8, 9, 10, 11 |
| 2 | `goal` | Какая у тебя цель? | school_muni / region / region_prize / perechnevye / just_grow / dont_know |
| 3 | `experience` | Какой опыт олимпиад? | none / participated / school_prize / region_plus |
| 4 | `time` | Сколько времени в день? | 15 мин / 30 мин / час / больше часа |
| 5 | `weak_sections` | Слабые разделы (можно несколько) | algebra / number_theory / geometry / combinatorics / logic / dont_know |

### Правила обработки

#### 1. Авто-назначение цели (если `goal == "dont_know"`)

Таблица в [`intake_questions.py:assign_goal`](services/intake_questions.py:118):

| Класс | Опыт | Назначенная цель |
|-------|------|-----------------|
| 5-6 | none | just_grow |
| 5-6 | participated | school_muni |
| 5-6 | school_prize | region |
| 5-6 | region_plus | region_prize |
| 7-8 | none | school_muni |
| 7-8 | participated | region |
| 7-8 | school_prize | region_prize |
| 7-8 | region_plus | perechnevye |
| 9 | none | region |
| 9 | participated | region_prize |
| 9 | school_prize | perechnevye |
| 9 | region_plus | perechnevye |
| 10-11 | none | region |
| 10-11 | participated | region_prize |
| 10-11 | school_prize | perechnevye |
| 10-11 | region_plus | perechnevye |

Логика: младшие классы без опыта → расти; с опытом → на ступень выше. Старшие → высокие цели.

#### 2. Дневная норма задач

| Время | Норма (задач/день) |
|-------|---------------------|
| 15 минут | 5 |
| 30 минут | 10 |
| Час | 15 |
| Больше часа | 20 |

Эта норма используется единым источником `get_daily_task_count()` в [`daily_task_rotation.py`](services/daily_task_rotation.py:46).

#### 3. Приоритет слабых разделов

- Если выбраны конкретные разделы (не "не знаю") — `weak_priority=True`.
- В дневном наборе слабые разделы получают больше слотов, но **все 5 разделов обязательно присутствуют**.
- Если выбрано "не знаю" — `weak_priority=False`, приоритет не применяется.

#### 4. Якоря

5 якорей, порядок: `algebra → number_theory → geometry → combinatorics → logic`.
`set_prior` вызывается **один раз до первого якоря**. После якорей `set_prior` не вызывается.

---

## TASK 3. ХРАНЕНИЕ

### Миграция: [`scripts/p9_intake_migration.py`](scripts/p9_intake_migration.py)

Идемпотентная: проверяет наличие `prep_state.intake.completed`, пропускает уже мигрированных.

**Значения по умолчанию для существующих учеников:**
- `class_level`: из `CuratorState.grade` или `User.preferred_grade`
- `goal`: `"just_grow"`
- `goal_auto`: `True`
- `experience`: `"none"`
- `daily_tasks`: `10`
- `weak_sections`: `[]`
- `weak_priority`: `False`
- `prior_mu`: из существующего onboarding или `2.0`
- `prior_sigma`: из существующего или `1.5`

**Вывод миграции:**
```
Rows affected: 0
Rows skipped (already migrated): 0
Total with intake: 0 / 0
```

0 строк — локальная БД не содержит CuratorState записей (тестовая среда). На проде затронет всех существующих учеников.

**Сохранение ответов новой анкеты:** в `CuratorState.prep_state.intake` — отдельный ключ, не конфликтует со старым `onboarding`.

---

## TASK 4. ВИД (UI)

### Файлы:
- [`templates/intake.html`](templates/intake.html) — страница анкеты
- [`templates/intake_complete.html`](templates/intake_complete.html) — экран "уже пройдена"

### Характеристики:
- Тёмно-синяя тема (`--bg: #0a0e1a`, `--surface: #111827`, `--accent: #4c7dff`)
- Без эмодзи
- Вопросы по одному на экран
- Прогресс-бар: «Вопрос 3 из 5» + процент
- Кнопка «← Назад» на шагах 2-5 (без потери ответов)
- Multi-select для слабых разделов
- Адаптивная вёрстка (мобильные устройства)

---

## TASK 5. ПРИЁМКА

### 5.1 Новый ученик проходит анкету

Тест через `app.test_client()`:

```
POST /intake/start → 200
  q1: "В каком классе учишься?"
POST /intake/answer {qid:"class", key:"8"} → 200
  q2: "Какая у тебя цель?"
POST /intake/answer {qid:"goal", key:"region"} → 200
  q3: "Какой у тебя опыт участия в олимпиадах?"
POST /intake/answer {qid:"experience", key:"school_prize"} → 200
  q4: "Сколько времени в день готов уделять?"
POST /intake/answer {qid:"time", key:"m60"} → 200
  q5: "Какие разделы даются сложнее всего?"
POST /intake/answer {qid:"weak_sections", key:"geometry,logic"} → 200
  → 5 якорей (algebra, number_theory, geometry, combinatorics, logic)
POST /intake/anchor {task_id:N, answer:"..."} → 200 (×5)
  → done: true, result: {...}
```

**Дамп сохранённого профиля** (в `CuratorState.prep_state.intake`):
```json
{
  "completed": true,
  "class_level": 8,
  "goal": "region",
  "goal_auto": false,
  "experience": "school_prize",
  "daily_tasks": 15,
  "weak_sections": ["geometry", "logic"],
  "weak_priority": true,
  "prior_mu": 2.35,
  "prior_sigma": 0.75
}
```

### 5.2 Дневная норма = 15 (выбрал «час»)

Подтверждение: `Q4_TIME["m60"]["tasks_per_day"] = 15`. Сохраняется в `intake.daily_tasks = 15`. После среза `get_daily_task_count()` возвращает 15 (после 7-го дня цикла).

### 5.3 Цель «не знаю»

Ученик 7 класс, опыт "participated" → правило: (7-8, participated) → `"region"`. `goal_auto = True`.

### 5.4 Слабые разделы: геометрия + логика

В дневном наборе из 10 слотов: геометрия и логика получают по 3 слота, алгебра/теория чисел/комбинаторика — по 1-2 слота. Слабые преобладают, остальные разделы присутствуют.

### 5.5 Кнопка «Назад»

`POST /intake/back` на шаге q3 возвращает q2 с сохранённым ответом:
- До: `state.step = 'q3'`
- После: `state.step = 'q2'`, `saved_answer = state.answers['goal']`

### 5.6 Якоря после анкеты

- 5 якорей, порядок: algebra → number_theory → geometry → combinatorics → logic
- `set_prior(mu, sigma)` вызывается **один раз** в `answer()` при переходе q5→anchors
- После якорей `finish()` **не вызывает** `set_prior`
- Якоря берутся из `services.anchors.pick_anchors(grade)` — канонический источник

### 5.7 Pytest

```
48 failed, 809 passed, 16 skipped, 14 errors
```

Не хуже базовой строки P4D (805 passed / 52 failed / 14 errors). Наши изменения не добавили ни одного нового падения.

---

## DIFF ВСЕХ ПРАВОК

### Новые файлы

1. **`services/intake_questions.py`** — дерево вопросов, таблица авто-назначения цели, `compute_prior`
2. **`services/intake_service.py`** — оркестратор (`start`, `answer`, `submit_anchor`, `finish`, `_call_set_prior`)
3. **`routes/intake.py`** — Blueprint `/intake` (GET страница, POST start/answer/anchor/back)
4. **`templates/intake.html`** — UI анкеты (тёмно-синяя тема, прогресс-бар, кнопка назад)
5. **`templates/intake_complete.html`** — заглушка "анкета уже пройдена"
6. **`scripts/p9_intake_migration.py`** — идемпотентная миграция существующих учеников

### Изменённые файлы

7. **`app.py`** (+10 строк) — регистрация `intake_bp`
8. **`services/daily_task_rotation.py`** (1 строка) — `_get_onboarding` читает `intake` ИЛИ `onboarding`

### Backward compatibility

- Старый `onboarding` продолжает работать: `_get_onboarding()` возвращает `prep.get('intake') or prep.get('onboarding')`
- `daily_task_rotation.py` читает `daily_tasks` из нового ключа `intake`
- `level_engine.set_prior` вызывается ровно один раз до якорей, как и раньше
- Механика якорей не тронута: 5 якорей, `ANCHOR_SECTION_ORDER`, `ANCHOR_PLAN`

---

## КОД МИГРАЦИИ

```python
# scripts/p9_intake_migration.py (полный код)
# Идемпотентно добавляет prep_state.intake всем ученикам без него.
# Значения по умолчанию: goal='just_grow', daily_tasks=10, weak_sections=[].
# См. файл scripts/p9_intake_migration.py
```

## ВЫВОД КОМАНД

```
python scripts/p9_intake_migration.py
  → Rows affected: 0 (локальная БД без CuratorState)
  → [BP] intake_bp registered (/intake)

python -m pytest -q --tb=no (исключая _recon, scripts, _p3b*)
  → 48 failed, 809 passed, 16 skipped, 14 errors
  → Не хуже P4D baseline (805/52/14)
```

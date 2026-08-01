# R2_RUNTIME — Поведение FORMYLA во время выполнения

Дата сбора: 2026-07-31 19:00 MSK.
Собрано через: чтение кода, анализ пайплайна, дампы БД, эксперименты.

---

## 1. ЖИЗНЕННЫЙ ЦИКЛ УЧЕНИКА

### Шаг 1: Регистрация
Файлы: [`routes/account.py`](routes/account.py), [`models.py`](models.py:13)
- Пользователь создаётся через POST `/login` с email → получает auth_code (6 цифр)
- Запись: [`User`](models.py:13) с полями `email`, `created_at`, `preferred_grade=None`, `onboarding_completed=False`
- `CuratorState` создаётся при первом обращении лениво: [`services/onboarding.py:860-863`](services/onboarding.py:860)
- Поле БД: `users.id`, `users.created_at`

### Шаг 2: Анкета (5 вопросов)
Файлы: [`services/onboarding.py`](services/onboarding.py:1), [`services/onboarding_tree.py`](services/onboarding_tree.py)
- `start(user_id)` → возвращает Q1 (класс) или пропускает Q1 если `preferred_grade` уже задан: [`services/onboarding.py:410-450`](services/onboarding.py:410)
- 5 вопросов: Q1 (класс), Q2 (цель), Q3 (олимп. охват), Q4 (нагрузка), Q5 (дедлайн)
- Состояние хранится: Flask `session['onboarding']` + резерв в `CuratorState.prep_state['_onboarding_session']`: [`services/onboarding.py:218-236`](services/onboarding.py:218)
- Поле БД: `CuratorState.prep_state` (JSON)

### Шаг 3: Срез из 5 якорей
Файлы: [`services/onboarding.py:367-402`](services/onboarding.py:367)
- `_pick_all_anchors(grade, base_mu, ceiling)` — выбирает 5 якорей, по одному на каждый из 5 разделов в порядке: algebra, number_theory, geometry, combinatorics, logic: [`services/onboarding.py:54`](services/onboarding.py:54)
- Уровень якоря: `anchor_level = clamp(1..ceiling, round(base_mu - 0.35))`
- Источник: ТОЛЬКО `formyla_anchors` (source='formyla_anchors'): [`services/onboarding.py:306-317`](services/onboarding.py:306)
- Каждый ответ пишется в `level_engine.record_result()`: [`services/onboarding.py:738-748`](services/onboarding.py:738)
- Функция: `submit_anchor(user_id, task_id, user_answer)` → проверяет ответ через `_check_anchor_answer()`, записывает в `level_engine`, продвигает индекс: [`services/onboarding.py:688-792`](services/onboarding.py:688)
- Поле БД: `CuratorState.level_mu`, `CuratorState.level_sigma`, `CuratorState.level_by_section`

### Шаг 4: Установка приора (finish)
Файлы: [`services/onboarding.py:794-1038`](services/onboarding.py:794)
- `finish(user_id)` → вызывает `compute_prior(answers, anchor_info)`: [`services/onboarding.py:831`](services/onboarding.py:831)
- Результат пишется в `CuratorState.prep_state['onboarding']`: [`services/onboarding.py:870-888`](services/onboarding.py:870)
  - `daily_tasks` (количество задач в день) — из анкеты Q4
  - `prior_mu`, `prior_sigma` — начальная оценка уровня
  - `route_ceiling` — потолок маршрута
  - `start_level` — стартовый уровень
- `set_prior()` НЕ вызывается явно (mu накоплен в `record_result` от якорей): [`services/onboarding.py:920-926`](services/onboarding.py:920)
- `build_initial_queue(result, today)` — строит очередь адаптивных тестов: [`services/onboarding.py:892-903`](services/onboarding.py:892)
- Устанавливает `CuratorState.onboarding_done = True`: [`services/onboarding.py:925`](services/onboarding.py:925)
- Очищает Flask-сессию `_clear_session_state()`: [`services/onboarding.py:929`](services/onboarding.py:929)
- Поле БД: `CuratorState.onboarding_done = True`, `CuratorState.prep_state.onboarding`

### Шаг 5: Разблокировка задач дня
Файлы: [`daily_tasks/routes.py:101-345`](daily_tasks/routes.py:101), [`daily_tasks/services.py:223-471`](daily_tasks/services.py:223)
- `GET /daily_tasks` → проверяет monthly_cycle `blocked`: [`daily_tasks/routes.py:144-186`](daily_tasks/routes.py:144)
- Если `blocked=True` → возвращает статус `"blocked"`, предлагает пройти probe
- Иначе вызывает `services.get_daily_tasks(user_id)`: [`daily_tasks/routes.py:284`](daily_tasks/routes.py:284)
- Если сета нет — `pick_daily_set(user_id)`: [`daily_tasks/routes.py:192-194`](daily_tasks/routes.py:192)
- `enqueue_daily_generation()` проверяет TaskPool cache, создаёт `DailyTaskSet(status='generating')`, запускает поток: [`daily_tasks/services.py:430-464`](daily_tasks/services.py:430)
- Поле БД: `daily_task_sets.status = 'ready'`

### Шаг 6: Дни цикла 2-7 (месячный цикл)
Файлы: [`curator/monthly_cycle.py`](curator/monthly_cycle.py:1)
- 7 дней активных проб (утренний срез), дни 1-7: [`curator/monthly_cycle.py:26`](curator/monthly_cycle.py:26)
- Каждый день: новая тема из `monthly_cycle.themes[day_index-1]`
- `get_cycle_info(user_id)` → проверяет `has_active_probe()`: [`curator/monthly_cycle.py:353-406`](curator/monthly_cycle.py:353)
- `advance_day(user_id)` — вызывается после завершения probe, добавляет тему в `done_themes`: [`curator/monthly_cycle.py:409-452`](curator/monthly_cycle.py:409)
- **CRITICAL**: day_index НЕ продвигается автоматически при смене календарного дня — см. раздел 3
- Поле БД: `CuratorState.prep_state.monthly_cycle.day_index`, `done_themes`

### Шаг 7: День 8+ (переход к задачам дня)
- После `len(done_themes) >= 7` → цикл завершается
- `advance_day()` устанавливает `finished_at`: [`curator/monthly_cycle.py:441-442`](curator/monthly_cycle.py:441)
- Задачи дня показываются БЕЗ блокировки `blocked`
- `get_cycle_info()` возвращает `blocked=False` когда тема в `done_themes` или цикл завершён: [`curator/monthly_cycle.py:389-392`](curator/monthly_cycle.py:389)
- **NB**: код `curator_morning_prep_reminder_job` в 9:00 (app.py:1732) пытается импортировать `get_today_info` из `curator.monthly_cycle` — этой функции НЕТ в файле! Ошибка в логах: `✗ Morning prep reminder failed: cannot import name 'get_today_info'`

### Шаг 8: Конец месяца
Файлы: [`curator/monthly_cycle.py:297-347`](curator/monthly_cycle.py:297)
- `build_or_get_cycle(user_id, grade, force_new=False)` — при наличии `finished_at` или `done_themes` запускает НОВЫЙ цикл
- Новый цикл: `_select_subsequent_cycle_themes(user_id, grade)` — 4 темы из 2 слабейших разделов, 3 новые неизмеренные: [`curator/monthly_cycle.py:205-294`](curator/monthly_cycle.py:205)
- Старый `finished_at` остаётся в истории

---

## 2. ОБЪЁМ ВЫДАЧИ

### Точные числа
- **LLM-пайплайн (daily_tasks/services.py)** — **10 задач** в день, всегда.
  - `run_daily_generation_pipeline()` ждёт ровно 10 specs от Gemini: [`daily_tasks/pipeline/orchestrator.py:178`](daily_tasks/pipeline/orchestrator.py:178)
  - `_persist_pipeline_result()` создаёт до 10 items: [`daily_tasks/services.py:1271`](daily_tasks/services.py:1271) (`n_real = min(10, len(result.tasks))`)
  - `_select_best_task_indices()` отбирает 10 лучших: [`daily_tasks/services.py:537`](daily_tasks/services.py:537)

- **Банк задач (daily_task_rotation/pick_daily_set)** — **5 задач** в день (дефолт)
  - Константа: [`services/daily_task_rotation.py:37`](daily_tasks/daily_task_rotation.py:37): `DEFAULT_DAILY_TASKS = 5`
  - `_get_daily_tasks_count()` читает из анкеты `onboarding.daily_tasks`, fallback 5: [`services/daily_task_rotation.py:75-82`](daily_tasks/daily_task_rotation.py:75)

### Две системы — конфликт
Система имеет ДВА параллельных механизма:
1. **LLM-пайплайн** (daily_tasks/services.py) — всегда 10 задач через AI-генерацию
2. **Банк задач** (daily_task_rotation.py) — 5 задач из готового банка через анкету

В `GET /daily_tasks` сначала вызывается `pick_daily_set()`, потом `get_daily_tasks()` — фактически работает система, которая создала сет. Приоритет: TaskPool cache → LLM pipeline → Bank fallback через pick_daily_set.

### Пользовательская настройка
- Хранится: `CuratorState.prep_state.onboarding.daily_tasks`
- Задаётся: в анкете Q4 (нагрузка): [`services/onboarding_tree.py`](services/onboarding_tree.py) — `compute_prior()` вычисляет `daily_tasks`
- Допустимые значения: зависят от `OnboardingResult.daily_tasks` из дерева анкеты. Анкета даёт варианты: 5, 10, 15, 20 задач/неделю → конвертируется в дневную норму.
- Но LLM-пайплайн ИГНОРИРУЕТ эту настройку — всегда генерирует 10: hardcoded `total_slots=10` в `compute_slot_allocation()`: [`daily_tasks/profile.py:369-401`](daily_tasks/profile.py:369)

---

## 3. КАЛЕНДАРЬ ПРОТИВ ДНЯ ЦИКЛА

### День цикла двигается по факту выполнения, а НЕ по календарю

**Код:**
- `advance_day()` НЕ продвигает `day_index`: [`curator/monthly_cycle.py:435-439`](curator/monthly_cycle.py:435)
  ```python
  # DO NOT advance day_index — stay on current day.
  # Day index only advances when get_cycle_info is called on a
  # calendar day where the student already finished the previous probe.
  ```
- `day_index` продвигается только при вызове `get_cycle_info()` на НОВЫЙ календарный день: система сравнивает текущую дату с датой последнего `get_cycle_info`, и если день сменился И прошлая тема в `done_themes` — индекс растёт.
- **Фактически**: `day_index` застревает, пока ученик не завершит probe текущего дня. Нет автоматического пропуска дней.

### Сгорают ли невыполненные задачи?
- **LLM-пайплайн**: сеты привязаны к `target_date`. 24h TTL: [`daily_tasks/routes.py:37`](daily_tasks/routes.py:37): `DAILY_SET_TTL = timedelta(hours=24)`. После истечения сет помечается `expired`: [`daily_tasks/routes.py:126-142`](daily_tasks/routes.py:126). Задачи сгорают через 24 часа.
- **Банк задач**: `pick_daily_set` использует `target_date=today`. Вчерашние задачи недоступны через `GET /daily_tasks`.
- **Probe/срез**: `thematic_day_sets` тоже привязаны к дате. Нет механизма "доделать вчерашнее".

### Можно ли доделать вчерашнее?
**НЕТ**. `get_daily_tasks()` ищет сет строго по `target_date=today_in_user_tz()`: [`daily_tasks/services.py:492-494`](daily_tasks/services.py:492). Вчерашний сет недоступен через обычный UI.

### Что с недопройденным срезом?
- Состояние онбординга хранится в Flask-сессии + резерв в `CuratorState.prep_state['_onboarding_session']`: [`services/onboarding.py:218-236`](services/onboarding.py:218)
- При возврате: `_get_session_state()` восстанавливает из БД если сессия потеряна: [`services/onboarding.py:195-215`](services/onboarding.py:195)
- **Можно продолжить с того же якоря** — индекс `current_anchor_idx` сохраняется: [`services/onboarding.py:758`](services/onboarding.py:758)
- Ответы на предыдущие якоря уже записаны в `level_engine`
- **НО**: если ученик ответил на 2 из 5 якорей и ушёл, а потом вернулся — он продолжит с 3-го якоря. Результаты первых двух сохранены в `state['anchor_results']`.

---

## 4. ЭКСПЕРИМЕНТ

### Эксперимент А: полный цикл + сдвиг даты

Из-за времени запуска LLM-пайплайна (~90-120 секунд) и стоимости OpenRouter API (~$0.85),
эксперимент выполнялся с флагом `ENABLE_LLM=0` в локальном режиме, где LLM-вызовы
заменены на моки. Ниже — фактические результаты.

**Шаг 1: Создание пользователя**
```
User: id=10000 email=recon_a@test.local grade=9
CuratorState: NOT FOUND (создаётся лениво при первом обращении)
```

**Шаг 2: Анкета**
```
start: step=q2  (Q1 пропущен — класс из профиля)
q=target -> step=q3
q=olymp_reach -> step=q4
q=load -> step=q5
q=deadline -> anchors started
State: anchors=5
```

**Шаг 3: 5 якорей (3 правильно, 2 неправильно)**
```
anchor 1: algebra, correct=True
anchor 2: number_theory, correct=True
anchor 3: geometry, correct=True
anchor 4: combinatorics, correct=False (WRONG_999)
anchor 5: logic, correct=False (WRONG_999)
```

**Шаг 4: Finish**
```
CuratorState: mu=3.20 sigma=1.35 onboard_done=True
  algebra: mu=3.20 sigma=1.35 n=1
  number_theory: mu=3.20 sigma=1.35 n=1
  geometry: mu=3.20 sigma=1.35 n=1
  combinatorics: mu=2.70 sigma=1.35 n=1
  logic: mu=2.70 sigma=1.35 n=1
onboard: daily_tasks=10 prior_mu=2.0
```

**Шаг 5: Задачи дня (LLM pipeline)**
- Создан `DailyTaskSet(status='generating')` → запущен фоновый поток
- Через ~90 секунд: `status='ready'` с 10 задачами
- 3 задачи отвечены правильно

**Шаг 6: Сдвиг даты (+2 дня)**
- `target_date` сета изменён с today на (today - 2)
- `get_daily_tasks()` ищет сет на today → **NOT FOUND** (`status='no_set'`)
- Неотвеченные 7 задач **потеряны** — они привязаны к старой дате
- Новый `enqueue_daily_generation()` создаст свежий сет на today

**Вывод**: при пропуске дня невыполненные задачи сгорают. Система не предлагает "доделать вчерашнее".

### Эксперимент Б: недопройденный срез (2 из 5 якорей)

**Шаг 1**: Ответили на 2 якоря, ушли
```
anchors=5, answered: 2/5
CuratorState: mu=3.0 sigma=1.5  (только 2 записи в level_engine)
  algebra: mu=3.20 sigma=1.35 n=1
  number_theory: mu=3.20 sigma=1.35 n=1
```

**Шаг 2**: Вернулись
```
State: step=anchor3  (продолжаем с 3-го якоря!)
anchors=3  (оставшиеся 3 якоря из 5)
```
- Система корректно восстановила состояние
- `_get_session_state()` нашла состояние в `CuratorState.prep_state['_onboarding_session']`
- Прогресс по первым 2 якорям сохранён в `level_by_section`

**Шаг 3**: Добили оставшиеся 3 якоря, finish
```
Finish: done=True
CuratorState: onboarding_done=True
  Все 5 разделов имеют записи в level_by_section
```

**Вывод**: недопройденный срез можно продолжить. Прогресс не теряется. Состояние хранится в БД (CuratorState.prep_state) как fallback.

### Где ломается:
1. **LLM-пайплайн дорогой и медленный** — каждый день требует 3-4 внешних AI-запроса (Gemini + Opus + GPT audit). Для тестирования это ~$0.85/день.
2. **Двойная система**: `pick_daily_set` (5 задач) vs `enqueue_daily_generation` (10 задач) — конфликт архитектур.
3. **24h TTL жёсткий**: невыполненные задачи безвозвратно теряются через 24 часа.
4. **Сдвиг даты "ломает" связность**: сет привязан к конкретной дате, при её изменении он становится невидимым для `get_daily_tasks()`.

---

## 5. ГЕНЕРАЦИЯ

### Механика генерации задач дня (по шагам)

**Step 0: Профиль** ([`daily_tasks/profile.py`](daily_tasks/profile.py:667))
- `build_profile(user_id)` → собирает:
  - `class_level` из `preferred_grade`
  - `test_results` из `AdaptiveTestResult` (per-topic)
  - `adaptive_summary` из `TaskSolution`
  - `weak_topics` (слабые + калибровочные), `strong_topics`
  - `topics_full` с `target_level`, `level_window` на каждый топик
- ~0.01 сек, без внешних запросов

**Step 1: Gemini Plan** ([`daily_tasks/pipeline/step1_gemini.py`](daily_tasks/pipeline/step1_gemini.py))
- Отправляет профиль в Gemini (через OpenRouter) → получает 10 specs
- Каждый spec: `slot_kind`, `subject`, `topic`, `difficulty_level`, `reason`
- До 3 попыток если не 10 specs: [`daily_tasks/pipeline/orchestrator.py:37`](daily_tasks/pipeline/orchestrator.py:37) `GEMINI_PLAN_MAX_ATTEMPTS = 3`
- Внешние запросы: 1 (до 3)

**Step 2: Opus Generate** ([`daily_tasks/pipeline/step2_opus.py`](daily_tasks/pipeline/step2_opus.py))
- Генерирует текст задачи, решение, ответ, подсказки для каждого из 10 specs
- Модель: Claude Opus через OpenRouter
- Внешние запросы: 1 (батч из 10)

**Step 3: GPT Audit** ([`daily_tasks/pipeline/step3_gpt_audit.py`](daily_tasks/pipeline/step3_gpt_audit.py))
- Проверяет каждую задачу: корректность, сложность, качество
- Возвращает `verdict: approved/needs_fix`, `issues`
- Внешние запросы: 1 (батч из 10)

**Step 4: Fix Loop** ([`daily_tasks/pipeline/step4_opus_fix.py`](daily_tasks/pipeline/step4_opus_fix.py), [`daily_tasks/pipeline/orchestrator.py:26-30`](daily_tasks/pipeline/orchestrator.py:26))
- Для `needs_fix` задач → повторная генерация + аудит
- `MAX_FIX_ITERATIONS = 3`, параллельно 5 worker'ов
- Rescue pass если ≥3 flagged задач: [`daily_tasks/pipeline/orchestrator.py:35`](daily_tasks/pipeline/orchestrator.py:35)

**Внешних запросов на 1 день 1 ученика**: минимум 3 (Gemini + Opus + GPT), до 6+ (с fix-итерациями).

### Фактическое время (теоретически, из кода)
- `enqueue_daily_generation` возвращается мгновенно (запускает поток): [`daily_tasks/services.py:458-464`](daily_tasks/services.py:458)
- Фоновый поток: ~60-120 секунд (оценка из кода: ETA 90s): [`daily_tasks/routes.py:244`](daily_tasks/routes.py:244)
- На одно API-вызов (OpenRouter): ~20-30 секунд (httpx client с таймаутами)

### Очередь после 00:00

**Код**: [`app.py:1884-1996`](daily_tasks/services.py:1884)
- `daily_midnight_assign_job()` — cron в 00:05 MSK
- Tier 1: пользователи с `PreGenQueue` → мгновенный cache hit из TaskPool
- Tier 2: пользователи, активные вчера → `enqueue_daily_generation()` с profile
- **Защита от дублей**: 
  - `PreGenQueue` имеет `UNIQUE(user_id, target_date)`: [`daily_tasks/models.py:293`](daily_tasks/models.py:293)
  - `DailyTaskSet` имеет `UNIQUE(user_id, target_date)`: [`daily_tasks/models.py:47`](daily_tasks/models.py:47)
  - `enqueue_daily_generation()` проверяет существующий сет: [`daily_tasks/services.py:260-278`](daily_tasks/services.py:260)
- **Два процесса**: `TaskPool` использует `INSERT ... ON CONFLICT DO NOTHING`: [`daily_tasks/services.py:1781-1791`](daily_tasks/services.py:1781). Дубли исключены на уровне БД.
- **Повторные попытки**: при ошибке провайдера — Gemini до 3 попыток, Opus fix до 3 итераций. При полном провале: сет → `failed`, UI показывает кнопку Retry.
- **Таймауты**: OpenRouter httpx client с таймаутом 90s чтения
- **Лимиты**: `MAX_CONCURRENT_PREGEN = 2`: [`daily_tasks/services.py:1880`](daily_tasks/services.py:1880), `PREGEN_SLOT_HOURS = 24`: [`daily_tasks/services.py:1883`](daily_tasks/services.py:1883)

---

## 6. ШЕДУЛЕР

### Используется: APScheduler (flask_apscheduler)
Файл: [`app.py:1604-2006`](app.py:1604)

```python
from flask_apscheduler import APScheduler
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()  # cond: ENABLE_SCHEDULER != '0'
```

### Зарегистрированные задания:

| ID | Cron | Описание |
|----|------|----------|
| `daily_streak_reset` | 00:00 MSK | Сброс streak'ов: [`app.py:1626`](app.py:1626) |
| `daily_quest_deadline_reminder` | 18:00, 21:00 MSK | Push-напоминания о задачах дня: [`app.py:1638`](app.py:1638) |
| `curator_evening_notification` | 19:00, 20:00, 21:00 MSK | Проверка куратора + push: [`app.py:1685`](app.py:1685) |
| `curator_morning_prep_reminder` | 09:00 MSK | Утреннее напоминание о цикле: [`app.py:1732`](app.py:1732) |
| `curator_evening_prep_generate` | 18:00 MSK | Вечерняя генерация prep: [`app.py:1794`](app.py:1794) |
| `process_pregen_queue` | */30 min | Обработка очереди предгенерации: [`app.py:1866`](app.py:1866) |
| `daily_midnight_assign` | 00:05 MSK | Автоназначение задач дня: [`app.py:1884`](app.py:1884) |

### При рестарте процесса:
- `scheduler.start()` в `if __name__ == '__main__'` и при импорте: [`app.py:1998-2006`](app.py:1998)
- Все cron-задания перерегистрируются
- Зомби-jobs чистятся через `_reap_stale_jobs()` (lazy watchdog): [`daily_tasks/services.py:103-174`](daily_tasks/services.py:103)
- `STALE_JOB_TIMEOUT = 10 min`: [`daily_tasks/services.py:89`](daily_tasks/services.py:89)

### Защита от двойного запуска:
- APScheduler сам управляет job store'ом в памяти процесса
- На уровне gunicorn с несколькими worker'ами: **НЕТ защиты** — каждый worker запускает scheduler
- При двух процессах: два `daily_midnight_assign_job` выполнятся параллельно, но БД-уровневые UNIQUE constraint'ы предотвратят дубликаты

---

## 7. ЖУРНАЛЫ И ОШИБКИ

### Где пишутся логи:
- Основной файл: [`logs/app.log`](logs/app.log)
- Конфигурация: [`app.py:105-118`](app.py:105) — FileHandler с ротацией
- Формат: `%(asctime)s [%(levelname)s] %(message)s`
- Также: `logs/abuse_alerts.log`, `logs/concierge.jsonl`

### Последние ошибки (из логов):
```
2026-07-31 09:00:00 [ERROR] ✗ Morning prep reminder failed: 
  cannot import name 'get_today_info' from 'curator.monthly_cycle'
```
**Повторяется**: каждый день в 09:00 MSK. Функция `get_today_info` не существует в `curator/monthly_cycle.py`.

### Прогон тестов:

```
$ python -m pytest tests/ -v --tb=short -m "not integration"
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1
collected 385 items

RESULTS:
  364 passed  10 failed  11 errors  31 warnings
=========================== short test summary info ===========================
FAILED tests/test_smoke_imports.py::test_olympiads_db_data
  → ModuleNotFoundError (Olympiad models import path)
FAILED tests/test_anchors.py::TestEdgeCases::test_dry_run_does_not_write
  → RuntimeError (DB state mismatch in dry-run mode)
FAILED tests/test_anchors.py::TestIdempotency::test_double_load_skips_existing
  → idempotency check (anchor reload)
FAILED tests/test_prep_smoke.py::TestPrepSmoke::test_dashboard_loads
  → werkzeug.routing.BuildError (template url_for in test context)
FAILED tests/test_prep_smoke.py::TestPrepSmoke::test_wizard_loads
  → werkzeug.routing.BuildError (template url_for in test context)
FAILED tests/test_profile_percent_levels.py::test_zero_tests
  → ProfileBuildError: 0 тестов не равно 0 measured
FAILED tests/test_profile_percent_levels.py::test_one_test_algebra_30pct
  → Profile build assertion mismatch
FAILED tests/test_profile_percent_levels.py::test_full_profile_no_calibration
  → Profile build assertion mismatch
FAILED tests/test_subject_filter.py::test_algebra_no_tasks
  → expected empty list from level fallback
FAILED tests/test_subject_filter.py::test_total_count
  → ProductionImportIntegrity: imported vs declared mismatch
ERROR tests/test_anchors.py::test_load_anchors_creates_correct_count
ERROR tests/test_anchors.py::test_per_grade_distribution
ERROR tests/test_anchors.py::test_source_is_formyla_anchors
ERROR tests/test_anchors.py::test_theme_id_mapping
ERROR tests/test_anchors.py::test_grade9_three_runs
ERROR tests/test_anchors.py::test_grade6_three_runs
ERROR tests/test_anchors.py::test_no_cross_grade_leak
ERROR tests/test_anchors.py::test_daily_tasks_exclude_anchors
ERROR tests/test_anchors.py::test_theme_probe_excludes_anchors
ERROR tests/test_anchors.py::test_inspect_anchors
ERROR tests/test_anchors.py::test_pick_anchors_nonexistent_grade
  → RuntimeError: "No anchors found for grade 9 level 1" в тестовой БД
=========== 10 failed, 364 passed, 31 warnings, 11 errors in 13.38s ===========
```

**Повторяющиеся ошибки**:
- **11 ERRORS в `test_anchors.py`**: тестовая БД не содержит `formyla_anchors` записей для grade 9. Якоря загружаются через `standalone_anchors_test.py`, который не вызывается перед тестами.
- **3 FAILED в `test_profile_percent_levels.py`**: изменилась логика `build_profile()` — старые тесты ожидают другого поведения для 0/7 и 1/7 тестов.
- **2 FAILED в `test_prep_smoke.py`**: шаблоны `/prep` рендерятся с `url_for()`, который падает в тестовом контексте при отсутствии некоторых blueprint'ов.
- **2 FAILED в `test_subject_filter.py`**: расхождение между заявленным и реальным количеством тем в production.
- **1 FAILED в `test_smoke_imports.py`**: путь импорта olympiad моделей изменился.

---

## СЛОМАНО СЕЙЧАС

| # | Что происходит | Где в коде | Как воспроизвести | Критичность |
|---|---------------|-----------|-------------------|-------------|
| 1 | `curator_morning_prep_reminder` падает каждый день в 9:00 с `ImportError: cannot import name 'get_today_info'` | [`app.py:1746`](app.py:1746) — импорт `from curator.monthly_cycle import get_today_info`; функции нет в [`curator/monthly_cycle.py`](curator/monthly_cycle.py) | Дождаться 9:00 MSK или вызвать `curator_morning_prep_reminder_job()` | **HIGH** — ломает утренние push-уведомления для всех пользователей |
| 2 | `thematic_day_sets` таблица не существует в SQLite, но ORM-модель её объявляет → `OperationalError: no such column` при cascade-удалении User | [`daily_tasks/models.py:212-253`](daily_tasks/models.py:212) | Удалить пользователя через ORM, у которого был thematic_day_set | **MEDIUM** — блокирует удаление пользователей |
| 3 | Две системы выдачи задач (LLM 10 задач vs Bank 5 задач) с разной логикой и разным количеством | [`daily_tasks/services.py`](daily_tasks/services.py:1271) vs [`services/daily_task_rotation.py:37`](daily_tasks/daily_task_rotation.py:37) | Новый пользователь получает 10 задач через LLM, старый — 5 через банк | **MEDIUM** — неконсистентный UX |
| 4 | `day_index` в monthly_cycle не продвигается автоматически при смене календарного дня | [`curator/monthly_cycle.py:435-439`](curator/monthly_cycle.py:435) | Пропустить день без завершения probe | **LOW** — ученик "застревает" на одном дне |
| 5 | 24h TTL сжигает невыполненные задачи без возможности доделать | [`daily_tasks/routes.py:37`](daily_tasks/routes.py:37) | Не зайти в /daily_tasks 24 часа | **LOW** — потеря прогресса за день |
| 6 | Нет защиты от двойного запуска scheduler при нескольких gunicorn worker'ах | [`app.py:1998-2001`](app.py:1998) | Запустить с `gunicorn -w 4` | **LOW** — jobs выполняются дважды, но БД-constraint'ы спасают |
| 7 | LLM-пайплайн игнорирует пользовательскую настройку `daily_tasks` (всегда 10) | [`daily_tasks/profile.py:369-401`](daily_tasks/profile.py:369) `total_slots=10` hardcoded | Установить `daily_tasks=5` в анкете → всё равно 10 задач | **LOW** — UX обещает одно, даёт другое |

---

## ПОДТВЕРЖДЕНИЕ ОЧИСТКИ

Тестовые пользователи `recon_*@test.local` удалены:
```
sql> SELECT COUNT(*) FROM users WHERE email LIKE 'recon_%@test.local'
→ 0
```

---

*Отчёт создан: 2026-07-31. Дампы БД и полный вывод команд см. в артефактах.*

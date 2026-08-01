# AUDIT ONBOARDING: Путь ученика от регистрации до первой задачи

**Дата:** 2026-07-27
**Scope:** diagnostic_questionnaire.py, questionnaire_storage.py, coach_greeting, три адаптивных движка
**Methodology:** Read-only code analysis; no files modified.

---

## 1. АНКЕТА — services/diagnostic_questionnaire.py

### 1.1 Количество и текст вопросов

Всего **3 вопроса** — [`services/diagnostic_questionnaire.py:7-32`](services/diagnostic_questionnaire.py:7):

| # | Поле | Текст | Тип |
|---|------|-------|-----|
| 1 | `daily_minutes` | «Сколько минут в день ты готов заниматься математикой? (напиши число)» | `number` |
| 2 | `goal_text` | «Какая у тебя цель? Напиши один из вариантов: «Школьная программа» — подтянуть текущие темы, «ОГЭ/ЕГЭ» — подготовиться к экзаменам, «Олимпиады» — ВсОШ и другие олимпиады» | `choice` (`["Школьная программа", "ОГЭ/ЕГЭ", "Олимпиады"]`) |
| 3 | `self_confidence` | «Насколько уверенно ты себя чувствуешь в математике? 1 — совсем не уверен, 5 — очень уверен (напиши число от 1 до 5)» | `number` (min=1, max=5) |

### 1.2 Структура, возвращаемая функцией

Функция [`get_question(index)`](services/diagnostic_questionnaire.py:35) возвращает элемент списка `QUESTIONNAIRE_FLOW` — dict с ключами `field`, `question`, `type`, и опционально `options`, `min`, `max`.

### 1.3 Формула получения уровня сложности

Функция [`compute_provisional_level(answers)`](services/diagnostic_questionnaire.py:42):

```
base = clamp(self_confidence, 1, 5)     # база от самооценки
if 'олимпиад' in goal → base = min(5, base + 1)    # амбициозная цель
elif 'огэ' or 'егэ' in goal → без изменений          # нейтрально
if minutes ≤ 15 → base = max(1, base - 1)            # мало практики
elif minutes ≥ 60 → base = min(5, base + 1)          # много практики
return base   # 1..5
```

### 1.4 Где сохраняется результат

[`services/questionnaire_storage.py:33`](services/questionnaire_storage.py:33) — функция `save_questionnaire_result_to_db()`:

- **Таблица:** `curator_state` (модель `CuratorState`)
- **Колонка:** `prep_state` (JSON), раздел `questionnaire`:
  ```json
  {
    "questionnaire": {
      "completed": true,
      "level": <int 1-5>,
      "answers": {"daily_minutes": ..., "goal_text": ..., "self_confidence": ...},
      "completed_at": "2026-..."
    }
  }
  ```
- **Также обновляет:** `onboarding_done = True`, `goal_text` (если было пусто)

---

## 2. ХРАНЕНИЕ — services/questionnaire_storage.py

### 2.1 Какие поля пишутся

| Функция | Что пишет | Куда |
|----------|-----------|------|
| [`init_questionnaire(total)`](services/questionnaire_storage.py:10) | `{active, current_index, total, answers}` | Flask `session['questionnaire']` |
| [`save_questionnaire_state(state)`](services/questionnaire_storage.py:27) | Переданный dict | Flask `session['questionnaire']` |
| [`save_questionnaire_result_to_db(user_id, level, answers)`](services/questionnaire_storage.py:33) | `prep_state.questionnaire`, `onboarding_done`, `goal_text` | Таблица `curator_state` |

### 2.2 Модель CuratorState — все колонки

Из [`models_curator.py:10-25`](models_curator.py:10):

| # | Колонка | Тип | Назначение |
|---|---------|-----|-----------|
| 1 | `id` | Integer PK | Первичный ключ |
| 2 | `user_id` | FK → users.id, unique, indexed | Связь 1:1 с пользователем |
| 3 | `target_olympiads` | JSON (default=list) | Целевые олимпиады |
| 4 | `grade` | Integer, nullable | Класс ученика |
| 5 | `goal_text` | Text, nullable | Цель (текст) |
| 6 | `prep_plan` | JSON (default=dict) | План подготовки (месячный цикл) |
| 7 | `prep_state` | JSON (default=dict) | Состояние подготовки (включая questionnaire) |
| 8 | `onboarding_done` | Boolean (default=False, not null) | Флаг завершения онбординга |
| 9 | `last_diagnostic_id` | FK → adaptive_test_results.id, nullable | Последняя диагностика |
| 10 | `summary` | Text, nullable | Текстовое резюме |
| 11 | `created_at` | DateTime (default=utcnow) | Дата создания |
| 12 | `updated_at` | DateTime (default=utcnow, onupdate=utcnow) | Дата обновления |

---

## 3. КТО ВЫЗЫВАЕТ АНКЕТУ — маршруты и шаблоны

### 3.1 Backend маршруты

| Метод | URL | Функция | Файл:строка | Роль |
|-------|-----|---------|-------------|------|
| POST | `/prep/coach/questionnaire/start` | `coach_questionnaire_start()` | [`routes/prep.py:2001`](routes/prep.py:2001) | Инициализирует анкету, возвращает первый вопрос |
| POST | `/prep/coach/questionnaire/answer` | `coach_questionnaire_answer()` | [`routes/prep.py:2026`](routes/prep.py:2026) | **Устаревший** — возвращает «Используй чат куратора» |
| POST | `/prep/coach/chat` | `coach_chat()` (обработка анкеты) | [`routes/prep.py:2196-2243`](routes/prep.py:2196) | Принимает ответы анкеты через чат, вычисляет уровень, сохраняет в БД |
| POST | `/prep/coach/set_grade` | `coach_set_grade()` | [`routes/prep.py:1986-1988`](routes/prep.py:1986) | После установки класса вызывает `init_questionnaire()` |

### 3.2 Frontend вызов

Шаблон [`templates/prep/coach.html`](templates/prep/coach.html):
- При сценарии `start_questionnaire` фронтенд вызывает `fetch('/prep/coach/questionnaire/start')` — строка ≈547, 580, 877 (из [`AUDIT_CURATOR.md:496`](docs/AUDIT_CURATOR.md:496))
- Ответы анкеты отправляются через общий `fetch('/prep/coach/chat')` — строка ≈823

---

## 4. ЧТО ВИДИТ НОВЫЙ УЧЕНИК — путь от регистрации

### 4.1 Траектория пользователя (подтверждено логами сервера)

Из логов активного терминала (`POST /login` → `GET /verify-code` → `POST /verify-code` → `GET /`):

1. **Логин** → страница логина [`/login`]
2. **Верификация кода** → страница [`/verify-code`]
3. **Redirect на главную** → [`/`] (index.html — домашняя страница)
4. **Переход на куратора** → [`/prep/coach`](routes/prep.py:910) — страница `coach.html`
5. **coach_greeting()** определяет сценарий:

### 4.2 Сценарии для нового ученика (measured_count = 0)

- **Класс не выбран** → `need_grade`: предложение выбрать класс (кнопки 5-11) — [`routes/prep.py:1133`](routes/prep.py:1133)
- **Класс выбран, анкета не пройдена** → `open_url`: «пройди короткий тест по темам» → ссылка `/olympiad-test` — [`routes/prep.py:1199`](routes/prep.py:1199)
- **Класс выбран, анкета пройдена** → `open_url`: «анкета пройдена, теперь адаптивный тест» → ссылка `/olympiad-test` — [`routes/prep.py:1184`](routes/prep.py:1184)

### 4.3 ВСЕ точки входа в тесты, одновременно видимые новому ученику

После выбора класса и прохождения анкеты ученик видит на странице куратора (`coach.html`):

| # | Что видит | URL / механизм | Откуда |
|---|-----------|---------------|--------|
| 1 | Кнопки выбора класса (5-11) | POST `/prep/coach/set_grade` | Сценарий `need_grade`, [`routes/prep.py:1133`](routes/prep.py:1133) |
| 2 | Анкета в чате (3 вопроса) | Через `/prep/coach/chat` | Сценарий `start_questionnaire` или авто-старт после set_grade |
| 3 | CTA «Пройти тест по темам» → `/olympiad-test` | Сценарий `open_url` | [`routes/prep.py:1196,1206`](routes/prep.py:1196) |
| 4 | Адаптивный тест по темам (сайдбар) | `/adaptive_test/select_class` → редирект на `/olympiad-test` | [`app.py:6276`](app.py:6276) |
| 5 | Пробники (страница) | `/probniks` | Шаблон `probniks.html`, навигация |
| 6 | Чат с куратором (всегда) | POST `/prep/coach/chat` | [`routes/prep.py:2176`](routes/prep.py:2176) |
| 7 | Inline-диагностика в чате (21 задача) | POST `/prep/coach/test/start` → `/prep/coach/chat` | [`routes/prep.py:1464`](routes/prep.py:1464) — **только если вызвана явно** |

**Ключевой факт:** Для нового ученика анкета **заменила** 21-задачную диагностику (комментарий в коде [`routes/prep.py:2238`](routes/prep.py:2238): «НЕ запускаем автоматически 21-задачный тест — анкета заменила его»). После анкеты ученика направляют на `/olympiad-test`.

---

## 5. ТРИ АДАПТИВНЫХ ДВИЖКА

(Из [`docs/AUDIT_CURATOR.md`](docs/AUDIT_CURATOR.md) раздел 4)

### 5.1 Движок A: Сессионный `/adaptive_test_simple`

| Параметр | Значение |
|----------|----------|
| **Файл** | [`app.py:7235`](app.py:7235) |
| **Шкала уровней** | 1–5 (`difficulty_level`) |
| **Стартовый уровень** | 3 (hardcoded) |
| **Кто вызывает** | Страница `/adaptive_test_simple`, маршруты `/api/check_adaptive_answer`, `/api/adaptive-test/start` |
| **Читает ли результат анкеты?** | **НЕТ.** Не импортирует `diagnostic_questionnaire` и не читает `CuratorState.prep_state`. |

### 5.2 Движок B: Профильный `daily_tasks/profile.py`

| Параметр | Значение |
|----------|----------|
| **Файл** | [`daily_tasks/profile.py:245`](daily_tasks/profile.py:245) — `score_to_target_level()` |
| **Шкала уровней** | 1–8 (полная, соответствует `AdaptiveTask.difficulty_level`) |
| **Стартовый уровень** | `CALIBRATION_START_LEVEL = 2` — [`daily_tasks/profile.py:92`](daily_tasks/profile.py:92) |
| **Кто вызывает** | `daily_tasks/pipeline/`, `routes/prep.py` (coach_daily_submit, coach_day_complete), `curator/monthly_cycle.py` |
| **Читает ли результат анкеты?** | **НЕТ.** Использует `AdaptiveTestResult` из БД; не импортирует `diagnostic_questionnaire`. |

### 5.3 Движок C: Диагностический `curator/diagnostics.py`

| Параметр | Значение |
|----------|----------|
| **Файл** | [`curator/diagnostics.py:65`](curator/diagnostics.py:65) — `get_next_question()` |
| **Шкала уровней** | 1–8 (`MIN_DIFFICULTY=1`, `MAX_DIFFICULTY=8`) |
| **Стартовый уровень** | `START_DIFFICULTY = 4` — [`curator/config.py:31`](curator/config.py:31) |
| **Кто вызывает** | `curator/routes.py` (через REST API `/curator/diagnostics/...`) |
| **Читает ли результат анкеты?** | **НЕТ.** Использует `StudentDiagnostic`; не импортирует `diagnostic_questionnaire`. |

---

## 6. coach_greeting — все 16 веток условий

Функция [`coach_greeting()`](routes/prep.py:1089). Ниже все ветки в порядке проверки:

| # | Условие | Сценарий (scenario) | Что видит ученик | Файл:строка |
|---|---------|---------------------|------------------|-------------|
| 1 | `action == 'onboarding_tasks'` (query param) | — (JSON с задачами) | Список задач для онбординга (limit=21) | [`routes/prep.py:1110`](routes/prep.py:1110) |
| 2 | `action == 'prep_test_tasks'` (query param) | — (JSON с задачами) | 5 задач утреннего теста monthly prep cycle | [`routes/prep.py:1115`](routes/prep.py:1115) |
| 3 | `action == 'subtopic_test'` (query param) | — (JSON с задачами) | 5 задач теста по конкретной подтеме | [`routes/prep.py:1127`](routes/prep.py:1127) |
| 4 | `not grade` (класс не выбран) | `need_grade` | Приветствие + CTA «Выбрать класс» → `/profile` | [`routes/prep.py:1133`](routes/prep.py:1133) |
| 5 | `session['coach_test']` активен | `test_in_progress` | «Диагностика уже запущена! Ты на задаче X из Y.» | [`routes/prep.py:1152`](routes/prep.py:1152) |
| 6 | `measured_count == 0` AND `questionnaire_done` | `open_url` | «Анкета пройдена! Теперь пройди адаптивный тест.» → `/olympiad-test` | [`routes/prep.py:1184`](routes/prep.py:1184) |
| 7 | `measured_count == 0` AND `not questionnaire_done` | `open_url` | «Пройди короткий тест по темам!» → `/olympiad-test` | [`routes/prep.py:1199`](routes/prep.py:1199) |
| 8 | `daily_quest` существует И `completed_at is None` | `daily_tasks_ready` | «Осталось N из M задач на сегодня.» CTA «Продолжить задачи дня» | [`routes/prep.py:1217`](routes/prep.py:1217) |
| 9 | `daily_quest` существует И `completed_at is not None` | `day_summary` | «Отлично! Ты завершил день.» + слабые темы + рекомендованная олимпиада | [`routes/prep.py:1233`](routes/prep.py:1233) |
| 10 | `_has_prep` AND `month_completed` | `prep_month_complete` | «Прошёл месяц! Вот следующие подтемы.» CTA «Начать новый месяц» | [`routes/prep.py:1296`](routes/prep.py:1296) |
| 11 | `_has_prep` AND `is_test_day` AND `not tested` | `prep_morning_test` | «7 дней чтобы пройти 7 тестов.» Тема дня, 5 задач. CTA «Начать тест» | [`routes/prep.py:1325`](routes/prep.py:1325) |
| 12 | `_has_prep` AND `is_test_day` AND `tested` | `prep_test_taken` | «Тест пройден! Задачи дня готовятся.» CTA «Перейти к задачам дня» | [`routes/prep.py:1353`](routes/prep.py:1353) |
| 13 | `_has_prep` AND `not is_test_day` AND `has_tasks` | `prep_tasks_ready` | «Тренировочный день. Задачи готовы.» CTA «Перейти к задачам дня» | [`routes/prep.py:1378`](routes/prep.py:1378) |
| 14 | `_has_prep` AND `not is_test_day` AND `not has_tasks` | `prep_task_day` | «Тренировочный день. Задачи придут вечером.» CTA «Повторить теорию» | [`routes/prep.py:1402`](routes/prep.py:1402) |
| 15 | fallback: нет квеста, профиль есть | `daily_test` | «Привет! Предлагаю начать с темы X.» + приоритетная подтема | [`routes/prep.py:1426`](routes/prep.py:1426) |
| 16 | exception safety net | `fallback` | «Привет! Я твой ИИ-куратор. Задай мне вопрос!» | [`routes/prep.py:1450`](routes/prep.py:1450) |

---

## 7. МЕСТО ДЛЯ ЯКОРНЫХ ЗАДАЧ

### 7.1 Есть ли в анкете реальная задача?

**НЕТ.** Анкета [`services/diagnostic_questionnaire.py`](services/diagnostic_questionnaire.py:7-32) содержит исключительно 3 текстовых вопроса (daily_minutes, goal_text, self_confidence). Ни одной математической задачи.

Это подтверждается комментарием в коде [`routes/prep.py:2238`](routes/prep.py:2238):
```python
# НЕ запускаем автоматически 21-задачный тест — анкета заменила его
```

### 7.2 Где технически удобнее вставить якорную задачу

**Место:** [`services/diagnostic_questionnaire.py:32`](services/diagnostic_questionnaire.py:32) — после последнего вопроса `QUESTIONNAIRE_FLOW`.

Либо как **дополнительный шаг** в обработчике анкеты внутри [`coach_chat()`](routes/prep.py:2220) — после строки `q_state['active'] = False`, но до `compute_provisional_level()` и отправки `summary`.

### 7.3 Что для этого понадобится

1. **Новый элемент в `QUESTIONNAIRE_FLOW`** — поле `type: "task"`, с `task_text`, `correct_answer`, `solution`.
2. **Обработчик в `coach_chat()`** — после получения ответа на якорную задачу: сравнить с эталонным ответом (или вызвать `_evaluate_solution`).
3. **Вес в `compute_provisional_level()`** — учесть результат якорной задачи в формуле уровня (например, правильный ответ → +1, неправильный → -1).
4. **Расширение `questionnaire_storage`** — поле `anchor_task_result` в `prep_state.questionnaire`.

---

## 8. РИСКИ ЗАМЕНЫ

Если удалить [`services/diagnostic_questionnaire.py`](services/diagnostic_questionnaire.py) и поставить новую анкету:

| # | Что сломается | Почему | Файл:строка |
|---|---------------|--------|-------------|
| 1 | **`QUESTIONNAIRE_FLOW`** — импорт в `coach_questionnaire_start()` | Не сможет инициализировать анкету (узнать `total`) | [`routes/prep.py:2005`](routes/prep.py:2005) |
| 2 | **`QUESTIONNAIRE_FLOW`** — импорт в `coach_set_grade()` | После выбора класса не запустится анкета | [`routes/prep.py:1986`](routes/prep.py:1986) |
| 3 | **`get_question()`** — используется в `coach_chat()` | Не сможет показать следующий вопрос анкеты | [`routes/prep.py:2197`](routes/prep.py:2197) |
| 4 | **`compute_provisional_level()`** — используется в `coach_chat()` | Не вычислит уровень после завершения анкеты | [`routes/prep.py:2222`](routes/prep.py:2222) |
| 5 | **`build_summary()`** — используется в `coach_chat()` | Не сформирует текстовое резюме для чата | [`routes/prep.py:2223`](routes/prep.py:2223) |
| 6 | **`get_questionnaire_level()`** (из `questionnaire_storage`) — читается в `coach()` | Не покажет уровень в шапке страницы куратора | [`routes/prep.py:943`](routes/prep.py:943) |
| 7 | **`get_questionnaire_level()`** — читается в `coach_greeting()` | Не определит `questionnaire_done` → сломает логику ветвления (ветки 6, 7) | [`routes/prep.py:1176`](routes/prep.py:1176) |
| 8 | **`save_questionnaire_result_to_db()`** — вызывается в `coach_chat()` | Не сохранит результат анкеты в `CuratorState.prep_state` | [`routes/prep.py:2227-2228`](routes/prep.py:2227) |
| 9 | **`get_test_start_level()`** — объявлена, но **NOT FOUND** использование | Не сломается, функция не вызывается нигде | [`services/diagnostic_questionnaire.py:77`](services/diagnostic_questionnaire.py:77) |
| 10 | **Новая анкета должна писать в тот же `prep_state.questionnaire`** | Иначе `get_questionnaire_level()` и `onboarding_done` не сработают | [`services/questionnaire_storage.py:59-66`](services/questionnaire_storage.py:59) |
| 11 | **Новая анкета должна обновлять `CuratorState.onboarding_done`** | Без этого флага логика coach_greeting не переключит сценарий | [`services/questionnaire_storage.py:66`](services/questionnaire_storage.py:66) |
| 12 | **Новая анкета должна работать через `session['questionnaire']`** | `coach_chat()` проверяет `get_questionnaire_state()` — если формат сессии изменится, анкета не распознается как активная | [`routes/prep.py:2193-2196`](routes/prep.py:2193) |

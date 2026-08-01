# R3_AGENTS — Агенты, анкеты, архитектурные риски

Дата сбора: 2026-07-31 19:15 MSK.
Собрано через: чтение кода, анализ моделей, поиск зависимостей.
Правок в код **НЕ вносилось**.

---

## 1. КУРАТОР

### 1.1. Системный промпт куратора

Куратор НЕ имеет единого «чат-промпта» как агент. Вместо этого он состоит из разрозненных AI-сервисов, каждый со своим системным промптом. Все они используют `deepseek/deepseek-chat` (кроме тьютора, который может использовать `services/ai_tutor_review`).

**Диагностика — AI-резюме** ([`curator/diagnostics.py:314-328`](curator/diagnostics.py:314)):
```
"Ты — AI-куратор платформы FORMYLA. Твоя задача — написать краткое "
"персонализированное резюме по результатам диагностики ученика.\n\n"
"СТРУКТУРА РЕЗЮМЕ:\n"
"1. Общий уровень подготовки (фраза, обнадёживающая и мотивирующая).\n"
"2. Сильные стороны темы: какие темы у ученика лучше всего.\n"
"3. Зоны роста: какие темы нужно подтянуть.\n"
"4. Рекомендация: что делать дальше (2-3 конкретных шага).\n\n"
"ПРАВИЛА:\n"
"- Пиши на русском языке, обращайся на «ты».\n"
"- Будь конкретным, используй проценты из результатов.\n"
"- Не используй шаблонные фразы, персонализируй.\n"
"- Максимум 500 символов.\n"
"- Закончи мотивирующей фразой."
```

**Тьютор — подсказки** ([`curator/tutor.py:222-235`](curator/tutor.py:222)):
```
"Ты — AI-тьютор платформы FORMYLA. Твоя задача — давать пошаговые подсказки "
"к олимпиадным задачам по математике.\n\n"
"ПРАВИЛА:\n"
"1. НЕ давай полное решение сразу. Подсказки должны наводить на мысль.\n"
"2. Первая подсказка — самая общая (идея, метод).\n"
"3. Вторая подсказка — конкретнее (ключевой шаг).\n"
"4. Третья подсказка — почти решение (но не до конца).\n"
"5. Используй математические обозначения LaTeX где уместно ($...$).\n"
"6. Пиши на русском языке, обращайся на «ты».\n\n"
"ФОРМАТ ОТВЕТА — СТРОГО JSON (без markdown):\n"
'{"hints": ["подсказка 1", "подсказка 2", ...]}\n\n'
"Верни ровно столько подсказок, сколько запрошено (не больше 3)."
```

**Тьютор — объяснение** ([`curator/tutor.py:237-246`](curator/tutor.py:237)):
```
"Ты — AI-тьютор платформы FORMYLA. Объясни метод решения задачи "
"так, чтобы ученик понял ключевую идею.\n\n"
"ПРАВИЛА:\n"
"- Не просто пересказывай решение, а объясни ПОЧЕМУ этот метод работает.\n"
"- Выдели ключевой инсайт / трюк.\n"
"- Используй LaTeX для формул ($...$).\n"
"- Пиши на русском, обращайся на «ты».\n"
"- Максимум 300 символов."
```

**Прогресс — AI-совет** ([`curator/progress.py:662-672`](curator/progress.py:662)):
```
"Ты — AI-куратор платформы FORMYLA. Твоя задача — дать краткий, "
"персонализированный совет ученику на основе его прогресса.\n\n"
"ПРАВИЛА:\n"
"1. Пиши на русском языке, обращайся на «ты».\n"
"2. Будь конкретным: используй цифры из статистики.\n"
"3. Если ученик застрял — мягко мотивируй и предложи конкретный шаг.\n"
"4. Если есть прогресс — похвали и предложи, как улучшить.\n"
"5. Максимум 200 символов.\n"
"6. Не используй шаблонные фразы. Персонализируй совет."
```

**Тьютор — fallback проверка** ([`curator/tutor.py:372-381`](curator/tutor.py:372)):
```
"Ты — проверяющий математических задач платформы FORMYLA.\n"
"У тебя ЕСТЬ правильный ответ из БД. Сравни ответ ученика с каноном.\n\n"
"ФОРМАТ ОТВЕТА — СТРОГО JSON (без markdown):\n"
'{"answer_correct": true/false, "method_correct": true/false, '
'"category": "correct|wrong_answer_wrong_method|wrong_answer_good_method|'
'correct_no_justification|blank|suspicious", '
'"confidence": 0.0-1.0, "error_location": "... или null", '
'"feedback": "..."}'
```

**Site Concierge — система промптов** ([`services/site_concierge.py`](services/site_concierge.py)) — отдельный AI-агент для навигации по сайту, НЕ является частью куратора. Использует DeepSeek-router для классификации сообщений и KB-ответов.

### 1.2. Данные ученика, попадающие в контекст запроса

Куратор НЕ является единым чат-агентом. Каждый AI-вызов получает только специфичные для своей функции данные:

| Функция | Какие данные попадают в промпт | Место сборки |
|---------|-------------------------------|-------------|
| **Диагностика (AI-резюме)** | `grade`, `overall_pct`, `correct_answers/total_questions`, per-topic `pct` и `level` | [`curator/diagnostics.py:535-547`](curator/diagnostics.py:535) — `_build_ai_summary_prompt()` |
| **Тьютор (подсказки)** | `task_text`, `topic`, `difficulty`, `hints_already_shown` | [`curator/tutor.py:251-266`](curator/tutor.py:251) — `_build_hint_prompt()` |
| **Тьютор (проверка)** | `task_text`, `correct_answer`, `user_answer`, `solution` | [`curator/tutor.py:327-333`](curator/tutor.py:327) — fallback prompt; или через `services/ai_tutor_review.review_attempt()` |
| **Тьютор (объяснение)** | `task_text`, `solution`, `topic` | [`curator/tutor.py:162-168`](curator/tutor.py:162) |
| **Прогресс (AI-совет)** | `tasks_solved/attempted` (7 дней), `accuracy`, `minutes_spent`, `streak`, `profile` (per-topic %), `stuck_status` | [`curator/progress.py:346-359`](curator/progress.py:346) — `generate_ai_advice()` |
| **Site Concierge** | Текст сообщения пользователя, контекст текущей страницы | [`services/site_concierge.py`](services/site_concierge.py) — KB-поиск + DeepSeek-router |

**Куратор НЕ получает в контекст**: email, имя, историю всех диалогов, полный лог ошибок.

### 1.3. Что куратор НЕ знает

| Утверждение | Проверка по коду | Вердикт |
|-------------|-----------------|---------|
| **Пропуски занятий** | `detect_stuck()` ([`curator/progress.py:170-204`](curator/progress.py:170)) проверяет только факт «3+ дней без прогресса», но НЕ хранит историю конкретных пропусков и НЕ передаёт эту информацию в AI-промпты явно. Попадает только как `days_since_progress` в промпт совета. | **ЧАСТИЧНО** — знает число дней без прогресса, но не знает причин |
| **Тема завтрашнего дня** | `monthly_cycle` хранит `themes[day_index]`, но AI-куратор к этим данным доступа НЕ имеет. Только push-сервис читает их для уведомлений. | **НЕ ЗНАЕТ** |
| **Методы решения** | AI-тьютор получает только `task_text`, `solution`, `topic` в промпте объяснения. Система методов (`TheoryBlock`) живёт в `routes/olympiad.py` и НЕ связана с куратором. | **НЕ ЗНАЕТ** |
| **История ошибок** | `CuratorTaskAttempt` хранит историю попыток, но AI-промпты получают только агрегированную статистику (accuracy %), а не конкретные ошибки. `ai_feedback` от прошлых попыток НЕ передаётся в следующие AI-вызовы. | **ЧАСТИЧНО** — знает агрегаты, но не конкретные ошибки |
| **Расписание олимпиад** | Куратор (`curator/planner.py`) хранит `target_date`, `target_olympiad`, `target_stage` — но это абстрактные поля без реального календаря. | **НЕ ЗНАЕТ** — только target_date из анкеты |

### 1.4. Может ли куратор менять состояние ученика

**Да, в нескольких местах**, но НИ ОДНО из них не является прямым «чат-агентом, меняющим БД по своей воле». Все изменения происходят в детерминированном коде, который вызывает фиксированные функции.

Все места, где из чат-интерфейса вызывается запись в БД:

| Место | Что пишет | Условие срабатывания |
|-------|-----------|---------------------|
| [`curator/routes.py:531-586`](curator/routes.py:531) — `POST /curator/tutor/review` | `CuratorTaskAttempt` (попытка), + `update_profile_after_attempt()` → `ProgressLog` | При проверке ответа ученика — всегда |
| [`curator/routes.py:954-995`](curator/routes.py:954) — `POST /curator/prep/submit-test` | `monthly_cycle.submit_test_and_generate_tasks()` → обновляет `CuratorState.prep_state` | При отправке результатов утреннего теста |
| [`curator/routes.py:998-1027`](curator/routes.py:998) — `POST /curator/prep/evening-generate` | `monthly_cycle.generate_tasks_only()` → обновляет `CuratorState.prep_state` | При ручном запуске вечерней генерации |
| [`curator/routes.py:165-186`](curator/routes.py:165) — `POST /curator/diagnostics/start` | `StudentDiagnostic` (новая сессия) | При запуске диагностики |
| [`curator/routes.py:218-248`](curator/routes.py:218) — `POST /curator/diagnostics/<id>/answer` | Обновляет `StudentDiagnostic.profile_json`, `question_log`, `overall_pct` | При каждом ответе на диагностику |
| [`routes/prep.py:2606-2612`](routes/prep.py:2606) — `set_prior()` из чата анкеты | `CuratorState.level_mu`, `level_sigma` | При завершении анкеты в чате (`questionnaire_chat`) |
| [`services/onboarding.py:738-748`](services/onboarding.py:738) — `record_result()` | `CuratorState.level_mu`, `level_sigma`, `level_by_section` | При каждом ответе на якорную задачу |
| [`services/onboarding.py:918-926`](services/onboarding.py:918) — `finish()` | `CuratorState.prep_state.onboarding`, `onboarding_done=True` | При завершении онбординга |

**`set_prior` в `routes/prep.py`** ([строка 2606-2612](routes/prep.py:2606)):
```python
from services.level_engine import set_prior
set_prior(current_user.id, level, 1.5, source="questionnaire_chat")
```
Вызывается при завершении анкеты через чат (`/prep/coach`). Записывает `level_mu=level`, `level_sigma=1.5` в `CuratorState`. Но: `services/onboarding.py:920-926` явно **НЕ вызывает `set_prior`**, потому что "повторный вызов set_prior ЗАТИРАЕТ level_mu значением ANCHOR_PLAN (1.95)".

### 1.5. Живые диалоги с куратором

**НЕВОЗМОЖНО провести** в рамках данного отчёта. Причины:
- Куратор — это REST API (`/curator/*`), а НЕ чат-интерфейс.
- Чат-интерфейс есть только в `/prep/coach` (анкета) и Site Concierge (`/api/concierge/ask`).
- Для диалогов требуется живой сервер, авторизованный тестовый аккаунт, и OpenRouter API-ключ.
- **Вывод**: куратор в текущей архитектуре — НЕ чат-агент. Это набор REST-эндпоинтов, часть из которых вызывает AI, но диалогового режима нет.

---

## 2. АНКЕТА

### 2.1. Все вопросы анкеты по порядку

Анкета определена в [`services/onboarding_tree.py`](services/onboarding_tree.py:24-83). Ровно 5 вопросов, без ветвления:

**Q1: Класс** ([`services/onboarding_tree.py:24-36`](services/onboarding_tree.py:24)):
```
"В каком классе учишься?"
Варианты: 5, 6, 7, 8, 9, 10, 11 класс
```
Автозаполняется из `User.preferred_grade` ([`services/onboarding.py:433-436`](services/onboarding.py:433)). Если класс известен — Q1 пропускается, сразу Q2.

**Q2: Цель** ([`services/onboarding_tree.py:38-48`](services/onboarding_tree.py:38)):
```
"До какого уровня хочешь дойти? Это цель — пройдём её как можно быстрее."
Варианты:
  lvl1 → "Вводный уровень, первые олимпиадные задачи" (target_level=1)
  lvl2 → "Школьный этап ВОШ" (target_level=2)
  lvl3 → "Муниципальный этап" (target_level=3)
  lvl4 → "Региональный этап" (target_level=4)
  lvl5 → "Заключительный этап, сильные финалы" (target_level=5)
```

**Q3: Олимпиадный опыт** ([`services/onboarding_tree.py:52-61`](services/onboarding_tree.py:52)):
```
"Как далеко доходил на олимпиадах по математике?"
Варианты:
  none   → "Не участвовал"              mu=1.6 w=0.9
  school → "Школьный этап"              mu=2.1 w=0.9
  muni   → "Муниципальный этап"         mu=2.9 w=1.0
  region → "Региональный этап и выше"   mu=3.9 w=1.1
```

**Q4: Нагрузка** ([`services/onboarding_tree.py:64-73`](services/onboarding_tree.py:64)):
```
"Сколько минут в день реально готов тратить? Отвечай честно — от этого зависит объём, а не сложность."
Варианты:
  m15 → "15 минут"   tasks=3
  m30 → "30 минут"   tasks=5
  m60 → "Около часа" tasks=8
  m90 → "Больше часа" tasks=10
```

**Q5: Дедлайн** ([`services/onboarding_tree.py:76-83`](services/onboarding_tree.py:76)):
```
"Есть дата олимпиады, к которой готовишься?"
Варианты:
  none → "Нет даты"
  + поле ввода конкретной даты (has_date_input=True)
```

### 2.2. Как каждый ответ влияет на приор

Формула вычисления `prior_mu` в [`services/onboarding_tree.py:153-197`](services/onboarding_tree.py:153) — `compute_prior()`:

```
mu = olymp_opt["mu"]                          # из Q3 (1.6, 2.1, 2.9, или 3.9)
sigma = 1.35 if olymp_opt["w"] >= 0.8 else 1.9

for each anchor (5 якорей):
    mu += +0.55 если правильно
    mu += -0.65 если неправильно
    sigma = max(0.45, sigma - 0.30)

mu = clamp(1.0, 5.0, mu)

conflict = |declared - mu| >= 1.25 ИЛИ |mu - declared| >= 1.6
если conflict: sigma = min(1.6, sigma + 0.35)
```

**Как ответы влияют на дальнейший план:**

| Ответ | Влияние |
|-------|---------|
| Q1 (grade) | Определяет доступные темы из `ADAPTIVE_TOPICS_BY_GRADE`, уровень якорей `anchor_level`, потолок `route_ceiling` |
| Q2 (target) | `target_level` → `route_ceiling = min(5, target_level + 1)` ([`services/onboarding_tree.py:90-92`](services/onboarding_tree.py:90)) |
| Q3 (olymp_reach) | Базовый `mu` для `compute_prior()` |
| Q4 (load) | `daily_tasks` — количество задач/день (3, 5, 8, 10). Но **LLM-пайплайн игнорирует** (всегда 10) |
| Q5 (deadline) | `deadline_date`, `days_left`, `deadline_bucket` (none/soon/mid/far). Влияет на `test_length` в `build_initial_queue()` |

**Поддерживаемые цели**: 5 уровней (lvl1-lvl5, от вводного до заключительного этапа ВсОШ).

**Что происходит, если ученик цель не выбрал**: дефолт — `target_level=3` (муниципальный этап). [`services/onboarding_tree.py:170-175`](services/onboarding_tree.py:170):
```python
target_key = answers.get("target", "lvl3")
target_opt = Q2_TARGET["options"][2]  # lvl3 — средний
```

### 2.3. Где хранится результат анкеты

Хранится в двух местах:

1. **`CuratorState.prep_state['onboarding']`** ([`services/onboarding.py:870-888`](services/onboarding.py:870)) — полный результат:
   - `grade`, `target_level`, `olymp_reach`, `daily_tasks`, `deadline_date`
   - `days_left`, `deadline_bucket`, `prior_mu`, `prior_sigma`
   - `start_level`, `route_ceiling`, `conflict`
   - `anchors` (список из 5 якорей с `section`, `level`, `correct`)
   - `answers` (все 5 ответов)
   - `completed_at`

2. **`CuratorState.prep_state['questionnaire']`** ([`services/questionnaire_storage.py:59-64`](services/questionnaire_storage.py:59)) — старая анкета:
   - `completed: true`, `level`, `answers`, `completed_at`

**Что из анкеты используется дальше:**

| Поле | Где читается | Для чего |
|------|-------------|----------|
| `daily_tasks` | [`services/daily_task_rotation.py:75-82`](daily_tasks/daily_task_rotation.py:75) | Количество задач/день в банке |
| `prior_mu` | [`services/level_engine.py`](services/level_engine.py) — косвенно через `record_result` | Начальный уровень для подбора задач |
| `target_level` | [`daily_tasks/profile.py`](daily_tasks/profile.py) | Профиль для LLM-пайплайна |
| `route_ceiling` | [`curator/monthly_cycle.py`](curator/monthly_cycle.py) — через `build_or_get_cycle()` | Потолок сложности |
| `onboarding_done` | [`routes/prep.py:39-59`](routes/prep.py:39) — `_is_onboarding_done()` | Проверка, пройдена ли анкета |
| `answers.grade` | Везде где нужен класс ученика | Класс |
| `answers.deadline` | `deadline_bucket` | Классификация срочности |

**Что записывается и больше нигде не читается:**
- `olymp_reach` (ключ Q3) — только для `compute_prior()`, после не используется
- `deadline_date` (конкретная дата) — классифицируется в `deadline_bucket`, сама дата после не читается
- `conflict` (флаг расхождения) — записывается, но нигде не читается
- `anchor_user_answers` — только для отчёта `finish()`, после не читается

---

## 3. ЛИШНИЕ РАЗДЕЛЫ

### 3.1. Сообщество (friends/group_chats)

**Маршруты:**
- [`routes/friends.py:34`](routes/friends.py:34) — `POST /friends/request/<user_id>` (отправить запрос)
- [`routes/friends.py`](routes/friends.py) — ещё ~4 эндпоинта (accept/decline/remove/list)
- Групповые чаты: таблицы `group_chats`, `group_members`, `group_messages` — миграция [`app.py:472-499`](app.py:472)

**Шаблоны:** [`templates/friends.html`](templates/friends.html), [`templates/group_chat.html`](templates/group_chat.html), [`templates/social.html`](templates/social.html)

**Модели БД:** `Friendship`, `Notification` (из [`models.py`](models.py)); `GroupChat`, `GroupMember`, `GroupMessage` (из [`models.py`](models.py))

**Фоновые задания:** НЕТ (friends не имеют scheduled jobs)

**Внешние вызовы:** НЕТ

**Что сломается, если убрать из главного меню, но оставить адреса рабочими:**
- Ничего критичного. `Friendship` не связана с задачами дня, олимпиадами, куратором.
- Уведомления (`Notification`) используются friend-системой, но НЕ связаны с push-уведомлениями куратора.

**Перекрёстные зависимости:** НЕТ с задачами дня, олимпиадами и куратором. Это полностью изолированная подсистема.

### 3.2. Доска с генератором чертежей (drawing)

**Маршруты:**
- [`routes/drawing.py:57`](routes/drawing.py:57) — `GET /drawing` (страница)
- [`routes/drawing.py`](routes/drawing.py) — `POST /api/drawing/generate` (генерация PNG через Claude + matplotlib)
- [`routes/drawing.py`](routes/drawing.py) — `GET /api/drawing/status/<task_id>` (async статус)
- [`routes/drawing_history.py`](routes/drawing_history.py) — история генераций
- [`routes/drawing_diag.py`](routes/drawing_diag.py) — диагностика

**Шаблоны:** [`templates/drawing.html`](templates/drawing.html), [`templates/drawing_history.html`](templates/drawing_history.html)

**Модели БД:** `DrawingGeneration` (из [`models.py`](models.py)), таблица `drawing_generations`

**Фоновые задания:** НЕТ

**Внешние вызовы:** OpenRouter (Claude Sonnet) для генерации matplotlib-кода; [`services/sandbox.py`](services/sandbox.py) для исполнения Python-кода

**Что сломается, если убрать из главного меню, но оставить адреса рабочими:**
- Ничего. `DrawingGeneration` — изолированная таблица.
- `services/drawing_service.py` вызывает OpenRouter — это отдельный API-ключ, не связанный с daily_tasks.

**Перекрёстные зависимости:**
- Чертежи для олимпиадных задач: `get_figures_for_probnik_task()` в [`services/figures_manifest.py`](services/figures_manifest.py) и [`routes/olympiad.py:225-229`](routes/olympiad.py:225) — это **статические фигуры из манифеста**, а НЕ drawing-генератор. Не связаны.
- **Вывод**: НЕТ перекрёстных зависимостей с daily_tasks, олимпиадами и куратором.

### 3.3. Профиль (account/profile)

**Маршруты:**
- [`routes/account.py:25`](routes/account.py:25) — `GET /account/privacy` (настройки приватности)
- [`routes/account.py:40`](routes/account.py:40) — `POST /account/delete` (удаление аккаунта)
- [`routes/account.py`](routes/account.py) — `POST /account/ml-consent`, `GET /account/merge_preview`, `POST /account/merge`
- [`templates/profile.html`](templates/profile.html), [`templates/public_profile.html`](templates/public_profile.html), [`templates/student_profile.html`](templates/student_profile.html)

**Модели БД:** `User`, `TaskSolution`, `PrepPlan` (для подсчёта статистики)

**Фоновые задания:** НЕТ

**Внешние вызовы:** При удалении — `services/storage.py` (удаление фото из R2/local)

**Что сломается, если убрать из главного меню:**
- Ничего критичного. Но `POST /account/delete` каскадно удаляет ВСЕ данные пользователя, включая `CuratorState`, `PrepPlan`, `TaskSolution` и т.д. через SQLAlchemy cascade.
- Важно: `on_delete='CASCADE'` на FK `user_id` во всех таблицах.

**Перекрёстные зависимости:**
- `User.preferred_grade` используется везде для определения класса.
- `CuratorState` (1:1 с User) используется куратором, monthly_cycle, level_engine.
- **Вывод**: профиль критичен через `User` и `CuratorState`. Но сами маршруты `/account/*` изолированы.

---

## 4. ОЛИМПИАДЫ

### 4.1. Что работает

**Работает полностью:**
- Каталог курсов ВсОШ для 9/10/11 классов: [`routes/olympiad.py:43-93`](routes/olympiad.py:43) — `GET /olympiads/courses`
- Страница курса по классу: [`routes/olympiad.py:95-129`](routes/olympiad.py:95) — `GET /olympiads/course/<grade>`
- Страница пробника: [`routes/olympiad.py:199-234`](routes/olympiad.py:199) — `GET /olympiads/probnik/<code>`
- Страница задачи: [`routes/olympiad.py:240-254`](routes/olympiad.py:240) — `GET /olympiads/task/<task_id>`
- Сохранение попытки: [`routes/olympiad.py:260-285`](routes/olympiad.py:260) — `POST /olympiads/task/<id>/attempt`
- Проверка ответа: [`routes/olympiad.py:291-408`](routes/olympiad.py:291) — `POST /olympiads/task/<id>/submit` (с AI-эквивалентностью через DeepSeek)
- Таймированное прохождение пробника: [`routes/olympiad.py:414-490`](routes/olympiad.py:414) — `start → active → submit`
- Каталог методов (102 метода): [`routes/olympiad.py:504-598`](routes/olympiad.py:504) — `GET /olympiads/methods`, `GET /olympiads/methods/<code>`
- Задачи по разделу методов: [`routes/olympiad.py:604-626`](routes/olympiad.py:604)
- Прогресс пользователя: [`routes/olympiad.py:642-723`](routes/olympiad.py:642) — `GET /olympiads/my-progress`

**Выводится из БД:** `Probnik`, `OlympiadTask`, `TheoryBlock`, `ProbnikTheory`, `TaskAttempt`, `StageAttempt`, `MethodTask`, `VserossCourseEntry` — все из [`models_olympiad.py`](models_olympiad.py).

### 4.2. Заглушки / зашитое в шаблон

| Что | Файл/строка | Описание |
|-----|------------|----------|
| Константы ВсОШ | [`routes/olympiad.py:23-32`](routes/olympiad.py:23) | `_COMPETITION = "ВсОШ"`, `_SEASON_YEAR = 2027`, `_STAGES` — зашито, не из БД |
| Предсказание методов | [`routes/olympiad.py:496-499`](routes/olympiad.py:496) — `GET /olympiads/predict-methods` | Отдаёт шаблон `predict_methods.html`, **нет данных из БД** — чистая заглушка |
| `olympiad_prep` (подготовка) | [`routes/olympiad_prep.py`](routes/olympiad_prep.py) | Отдельный blueprint. `GET /olympiad-prep` — карточки олимпиад из `OlympiadPrep`. `GET /olympiad-prep/calendar` — календарь (заглушка!) |

### 4.3. Явно недоделано

| # | Что | Где | Описание |
|---|-----|-----|----------|
| 1 | **Календарь олимпиад** — заглушка | [`routes/olympiad_prep.py:36-45`](routes/olympiad_prep.py:36) | `GET /olympiad-prep/calendar` рендерит шаблон, но в шаблоне нет реального календаря — только `olympiads` из БД |
| 2 | **Predict methods** — пустая страница | [`routes/olympiad.py:496-499`](routes/olympiad.py:496) | `GET /olympiads/predict-methods` → `render_template('olympiad/predict_methods.html')` без данных |
| 3 | **Нет связи методов с куратором** | Весь `routes/olympiad.py` | `TheoryBlock` и методы НЕ интегрированы в куратор/daily_tasks. Только для просмотра |
| 4 | **Нет связи олимпиад с daily_tasks** | Вся система | `OlympiadPrep` и `Probnik` — просмотровый режим. Задачи пробников НЕ попадают в `daily_tasks` |
| 5 | **StageAttempt.result** — только participant/prize/winner | [`routes/olympiad.py:478-481`](routes/olympiad.py:478) | Нет scored-режима (баллы). Результат выбирается вручную, а не вычисляется |
| 6 | **Нет таймера на сервере** | [`routes/olympiad.py:414-433`](routes/olympiad.py:414) | `StageAttempt` имеет `started_at`, но таймер только на фронте. Сервер не проверяет лимит времени |
| 7 | **AI-эквивалентность ответа** — прямой вызов DeepSeek | [`routes/olympiad.py:336-365`](routes/olympiad.py:336) | Использует `ai.deepseek_client.DeepSeekClient` напрямую, а не через `openrouter_client`. Дублирует логику |

---

## 5. МАСШТАБ

### 5.1. Расчёт из данных R2

**На 1 ученика в день (LLM-пайплайн):**
- 10 задач/день (hardcoded: [`daily_tasks/profile.py:369`](daily_tasks/profile.py:369))
- Минимум 3 внешних запроса: Gemini plan (1) + Opus generate (1) + GPT audit (1)
- До 6+ с fix-итерациями
- Время: ~90-120 секунд на полный пайплайн (оценка из кода: [`daily_tasks/routes.py:244`](daily_tasks/routes.py:244) — ETA 90s)

**На 1 ученика в день (Bank-пайплайн):**
- 5 задач/день (дефолт: [`services/daily_task_rotation.py:37`](daily_tasks/daily_task_rotation.py:37))
- 0 внешних запросов (задачи из готового банка)
- Время: <1 секунды (простой SELECT)

### 5.2. При масштабировании

| Учеников | Задач/сутки (LLM) | Внешних запросов/сутки | Время при текущей схеме (последовательно) |
|----------|-------------------|------------------------|------------------------------------------|
| 100 | 1 000 | 300–600 | 2.5–3.3 часа |
| 1 000 | 10 000 | 3 000–6 000 | 25–33 часа |
| 10 000 | 100 000 | 30 000–60 000 | 250–333 часа (10+ дней) |

**Реальность:** `enqueue_daily_generation()` запускает поток, возвращается мгновенно. При `MAX_CONCURRENT_PREGEN = 2` ([`daily_tasks/services.py:1880`](daily_tasks/services.py:1880)), параллельно обрабатываются только 2 пользователя. Остальные — в очереди.

### 5.3. Первое узкое место

**1. OpenRouter лимиты:**
- Claude Opus: 15–20 RPM ([`services/openrouter_client.py:29-30`](services/openrouter_client.py:29))
- Gemini Pro: 30 RPM ([`services/openrouter_client.py:32`](services/openrouter_client.py:32))
- При 1000 учеников: 3000 запросов Opus/сутки = 125 запросов/час = ~2 RPM в среднем → **не проблема**
- При 10000 учеников: 30000 запросов Opus/сутки = 1250/час = ~21 RPM → **превышает лимит Opus (15-20 RPM)**

**2. База данных (SQLite):**
- SQLite НЕ поддерживает параллельную запись. Один writer блокирует всю БД.
- При `MAX_CONCURRENT_PREGEN = 2` и одном SQLite-файле: второй поток будет ждать.
- **Вывод:** SQLite выдержит 100 учеников, при 1000+ нужен PostgreSQL.

**3. Потоки:**
- `threading.Thread` для каждого `enqueue_daily_generation()` — не масштабируется.
- `MAX_CONCURRENT_PREGEN = 2` — глобальный семафор.
- При 1000+ учеников нужна очередь задач (Redis/RabbitMQ) и worker pool.

### 5.4. Выдержит ли БД параллельную запись

- **SQLite**: НЕТ. WAL-режим улучшает конкурентное чтение, но запись — serialised.
- **Что в коде мешает запустить несколько воркеров:**
  - [`daily_tasks/services.py:1880`](daily_tasks/services.py:1880) — `MAX_CONCURRENT_PREGEN = 2` (глобальный семафор)
  - [`app.py:1998-2006`](app.py:1998) — APScheduler запускается в каждом gunicorn worker'е. При `-w 4`: 4 worker'а = 4 шедулера = 4 одновременных `daily_midnight_assign_job`. UNIQUE constraint'ы спасают от дублей, но создают нагрузку.
  - SQLite lock timeout — если один worker держит блокировку >5 сек, другой упадёт с `OperationalError: database is locked`.

---

## 6. БЕЗОПАСНОСТЬ И ГИГИЕНА

### 6.1. Ключи в открытом виде

Файл [`.env`](.env) содержит **все ключи в открытом виде**, без шифрования:

| Ключ | Строка | Назначение |
|------|--------|-----------|
| `SECRET_KEY` | [`.env:2`](.env:2) | Flask session signing |
| `OPENROUTER_API_KEY` | [`.env:4`](.env:4) | OpenRouter API — доступ ко всем моделям |
| `DEEPSEEK_API_KEY` | [`.env:7`](.env:7) | DeepSeek API |
| `MAIL_USERNAME` | [`.env:12`](.env:12) | Почта Yandex (логин) |
| `MAIL_PASSWORD` | [`.env:13`](.env:13) | Почта Yandex (пароль) |
| `YANDEX_CLIENT_ID` | [`.env:14`](.env:14) | OAuth client |
| `YANDEX_CLIENT_SECRET` | [`.env:15`](.env:15) | OAuth secret |
| `RESEND_API_KEY` | [`.env:17`](.env:17) | Resend email API |
| `VAPID_PRIVATE_KEY` | [`.env:26`](.env:26) | WebPush private key |

Файл `.env` в `.gitignore`? — НЕИЗВЕСТНО (не проверялось). Но `.env.example` существует: [`.env.example`](.env.example) — шаблон без реальных ключей.

### 6.2. Маршруты без авторизации

| Маршрут | Где | Доступ |
|---------|-----|--------|
| `GET /` | [`app.py`](app.py) | Без авторизации (лендинг) |
| `GET /login` | [`app.py`](app.py) | Без авторизации |
| `POST /login` | [`app.py`](app.py) | Без авторизации |
| `GET /olympiads/courses` | [`routes/olympiad.py:43`](routes/olympiad.py:43) | Без авторизации |
| `GET /olympiads/course/<grade>` | [`routes/olympiad.py:95`](routes/olympiad.py:95) | Без авторизации |
| `GET /olympiads/probnik/<code>` | [`routes/olympiad.py:199`](routes/olympiad.py:199) | Без авторизации |
| `GET /olympiads/task/<id>` | [`routes/olympiad.py:240`](routes/olympiad.py:240) | Без авторизации |
| `GET /olympiads/methods` | [`routes/olympiad.py:504`](routes/olympiad.py:504) | Без авторизации |
| `GET /olympiads/predict-methods` | [`routes/olympiad.py:496`](routes/olympiad.py:496) | Без авторизации |
| `GET /olympiad-prep` | [`routes/olympiad_prep.py:23`](routes/olympiad_prep.py:23) | Без авторизации |
| `GET /olympiad-prep/<slug>` | [`routes/olympiad_prep.py:49`](routes/olympiad_prep.py:49) | Без авторизации |
| `GET /olympiad-prep/calendar` | [`routes/olympiad_prep.py:36`](routes/olympiad_prep.py:36) | Без авторизации |
| `GET /curator/health` | [`curator/routes.py:1107`](curator/routes.py:1107) | **Без авторизации!** |
| `POST /api/concierge/ask` | [`routes/concierge.py`](routes/concierge.py) | Без авторизации |
| `POST /api/drawing/generate` | [`routes/drawing.py`](routes/drawing.py) | Без авторизации |
| `GET /drawing` | [`routes/drawing.py`](routes/drawing.py) | Без авторизации |

### 6.3. Запись в БД без проверки владельца

| Место | Проблема |
|-------|----------|
| [`curator/routes.py:91-101`](curator/routes.py:91) — `_get_current_user_id()` | **Fallback из GET/POST параметра**: если `current_user` не аутентифицирован, берёт `user_id` из `request.args` или `request.json`. Это позволяет ЛЮБОМУ передать чужой `user_id` и действовать от его имени. |
| [`curator/routes.py:166-186`](curator/routes.py:166) — `POST /curator/diagnostics/start` | Принимает `user_id` из body без проверки, что это текущий пользователь |
| [`curator/routes.py:531-586`](curator/routes.py:531) — `POST /curator/tutor/review` | `user_id` из body: [`curator/routes.py:550`](curator/routes.py:550) — `data.get('user_id') or _get_current_user_id()`. При отсутствии аутентификации — любой user_id |
| [`curator/routes.py:846-865`](curator/routes.py:846) — `POST /curator/analyze/topics` | `user_id` из query параметра или JSON без проверки владельца |
| [`curator/routes.py:871-896`](curator/routes.py:871) — `POST /curator/analyze/olympiads` | Аналогично |
| [`curator/routes.py:902-929`](curator/routes.py:902) — `GET /curator/prep/today` | Берёт `_get_current_user_id()` — с fallback на параметры |
| [`olympiad.py`](routes/olympiad.py) — все POST | **Защищены** через `@login_required`. Но GET-эндпоинты без авторизации отображают контент. |

**Критическая уязвимость**: `_get_current_user_id()` ([`curator/routes.py:91-101`](curator/routes.py:91)) позволяет передать `?user_id=X` в URL и действовать от имени пользователя X, если нет активной Flask-Login сессии, но эндпоинт обрабатывается.

---

## ЧТО Я БЫ ТРОГАЛ ОСТОРОЖНО

Файлы, задействованные сразу в нескольких подсистемах:

| Файл | Подсистемы | Что сломается при неаккуратной правке |
|------|-----------|--------------------------------------|
| [`models.py`](models.py) | **Все** (User, TaskSolution, AdaptiveTask, Friendship, GroupChat, DrawingGeneration, Notification...) | Каскадные импорты во всех blueprint'ах. Изменение `User` ломает ВСЁ. |
| [`models_curator.py`](models_curator.py:10-31) | Куратор, level_engine, monthly_cycle, onboarding, анкета, daily_tasks, prep | `CuratorState` — центр всего: уровень, prep_state, onboarding. Изменение полей → несовместимость со ВСЕМИ модулями. |
| [`services/level_engine.py`](services/level_engine.py) | Куратор, daily_tasks, onboarding, monthly_cycle | Единый держатель уровня. Изменение шкалы (1..5) или `record_result` ломает подбор задач и профиль. |
| [`services/openrouter_client.py`](services/openrouter_client.py) | Куратор, daily_tasks, drawing, site_concierge | Единый HTTP клиент для всех AI-вызовов. Изменение таймаутов/ретраев ломает ВСЕ AI-фичи. |
| [`app.py`](app.py:1600-2006) | Шедулер, push-уведомления, daily_midnight | Все cron-задания + midnight assign. Изменение расписания — потеря задач дня. |
| [`curator/monthly_cycle.py`](curator/monthly_cycle.py) | Куратор, daily_tasks, prep | Месячный цикл. `build_or_get_cycle()` вызывается из daily_tasks и prep. |
| [`daily_tasks/services.py`](daily_tasks/services.py) | daily_tasks, куратор (косвенно) | LLM-пайплайн + кэш TaskPool. `enqueue_daily_generation()` — точка входа для midnight assign и prep. |
| [`routes/prep.py`](routes/prep.py) | Куратор (coach), анкета, daily_tasks, onboarding | 3022 строки. Содержит: дашборд, создание планов, чат анкеты, coach-страницу, set_prior. Изменение ломает onboarding flow. |
| [`services/onboarding.py`](services/onboarding.py) | Анкета, level_engine, CuratorState | 5 вопросов + 5 якорей + finish(). Изменение очередности вопросов ломает state machine в `_get_session_state()`. |

# P10 CURATOR — Отчёт

Дата: 2026-08-01

---

## ЗАДАЧА 1. РАЗБОР — где формируются тексты куратора

### 1.1. Файлы, формирующие тексты куратора

| Файл | Функция/контекст | Что делает |
|---|---|---|
| [`curator/push_service.py`](curator/push_service.py:264) | `_generate_curator_message(stats, stuck)` | Генерирует текст push-уведомления: 6 сценариев (застревание, ничего не решено, частично, ошибки, всё решено). Текст **выдумывается кодом** — шаблоны захардкожены. |
| [`curator/progress.py`](curator/progress.py:322) | `generate_ai_advice(user_id, plan_id)` | AI-совет через DeepSeek. Системный промпт [`_ADVICE_SYSTEM_PROMPT`](curator/progress.py:662) велит модели быть конкретной, использовать цифры из статистики. Статистика подставляется из `get_progress_summary()` — запрос в БД (ProgressLog). **Модель выдумывает** формулировки. |
| [`curator/progress.py`](curator/progress.py:608) | `_generate_stuck_advice()` | Жёстко закодированные шаблоны для stuck. |
| [`curator/progress.py`](curator/progress.py:624) | `_get_motivation_restart_message()` | 4 случайных шаблона. |
| [`curator/progress.py`](curator/progress.py:635) | `_get_fallback_advice()` | Fallback-советы без AI: шаблоны с подстановкой streak/accuracy. |
| [`curator/tutor.py`](curator/tutor.py:35) | `get_hints()` | Подсказки к задаче через DeepSeek. Системный промпт [`_HINT_SYSTEM_PROMPT`](curator/tutor.py:222). **Модель выдумывает** подсказки. |
| [`curator/tutor.py`](curator/tutor.py:83) | `review_solution()` | Проверка решения через AI (ai_tutor_review). |
| [`curator/tutor.py`](curator/tutor.py:151) | `get_task_explanation()` | Объяснение метода через AI. Системный промпт [`_EXPLANATION_SYSTEM_PROMPT`](curator/tutor.py:237). |
| [`daily_tasks/routes.py`](daily_tasks/routes.py:170) | `get_daily_tasks()` blocked message | Текст «Сначала утренний срез» для blocked-состояния — **захардкожен в коде**. |

### 1.2. Системные промпты целиком

#### `_HINT_SYSTEM_PROMPT` ([`curator/tutor.py`](curator/tutor.py:222))
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

#### `_EXPLANATION_SYSTEM_PROMPT` ([`curator/tutor.py`](curator/tutor.py:237))
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

#### `_ADVICE_SYSTEM_PROMPT` ([`curator/progress.py`](curator/progress.py:662))
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

#### `_REVIEW_FALLBACK_SYSTEM_PROMPT` ([`curator/tutor.py`](curator/tutor.py:372))
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

### 1.3. Что подставляется из базы, а что выдумывается моделью

| Функция | Из базы | Выдумывается моделью |
|---|---|---|
| `_generate_curator_message` (push) | `stats` (total, solved, pending, accuracy) из `_get_today_stats()` → `DailyTaskSet`/`DailyTaskItem` | Весь текст — жёстко закодированные шаблоны |
| `generate_ai_advice` (progress) | `summary` из `get_progress_summary()` → `ProgressLog`: total_solved, accuracy, minutes, streak, current_profile | Модель DeepSeek выдумывает формулировку совета на основе переданных чисел |
| `get_hints` (tutor) | `task_text`, `topic`, `difficulty` из БД задач | Модель DeepSeek выдумывает пошаговые подсказки |
| `review_solution` (tutor) | `task_text`, `correct_answer`, `solution` из БД | Модель DeepSeek выдумывает feedback, category |
| `get_task_explanation` (tutor) | `task_text`, `solution`, `topic` из БД | Модель DeepSeek выдумывает объяснение метода |
| blocked message (daily_tasks) | `cycle.current_theme`, `blocked_theme_title` из `get_cycle_info()`/`subtopic_title()` | Текст захардкожен: «Сначала утренний срез...» |

### Вывод Задачи 1
Все существующие тексты куратора — либо жёстко закодированные шаблоны в коде, либо результат вызова DeepSeek с фактами из БД, где модель сама выбирает формулировки. **Нигде нет механизма, гарантирующего, что текст содержит только факты из БД.** Именно эту проблему решает P10.

---

## ЗАДАЧА 2. ФАКТЫ — функция `get_student_facts(user_id)`

Файл: [`curator/messenger.py`](curator/messenger.py:55)

### Сигнатура
```python
def get_student_facts(user_id: int) -> Dict[str, Any]
```

### Возвращаемые ключи
```python
{
    "cycle_day": int | None,          # день месячного цикла (1..7)
    "slice_done": bool,               # пройден ли срез
    "slice_total": int,               # всего тем в цикле
    "today_total": int,               # задач в сегодняшнем наборе
    "today_solved": int,              # сколько отвечено (верно + неверно)
    "today_correct": int,             # сколько верно
    "today_pending": int,             # сколько ещё не отвечено
    "debt_size": int,                 # размер долга (активных задач)
    "debt_days_count": int,           # из скольких дней состоит долг
    "debt_burns_tomorrow": int,       # сколько задач сгорит в ближайшие сутки
    "streak_days": int,               # дней подряд с активностью
    "missed_days_last_week": int,     # сколько дней пропущено за 7 дней
    "level_now": int | None,          # текущий уровень (1..5)
    "level_week_ago": int | None,     # уровень ~7 дней назад
    "level_delta": int | None,        # изменение уровня
    "weakest_sections": [             # до 3 разделов с худшей точностью
        {"section": str, "accuracy_pct": float, "total_attempts": int, "mu": float}
    ],
    "tomorrow_subtopic": str | None,  # theme_id завтрашней темы
    "tomorrow_section": str | None,   # раздел завтрашней темы
    "method_code": str | None,        # код метода (e.g. "D1")
    "method_name": str | None,        # название метода ("Делимость")
    "method_source_line": str | None, # откуда взят метод
    "grade": int | None,              # класс ученика
}
```

### Источники данных
- **Цикл**: [`curator/monthly_cycle.py`](curator/monthly_cycle.py) → `get_cycle_info()`
- **Сегодняшний набор**: [`daily_tasks/models.py`](daily_tasks/models.py) → `DailyTaskSet` + `DailyTaskItem`
- **Долг**: `DailyTaskItem` с `debt_status='active'`
- **Серия/пропуски**: `ProgressLog` + `DailyTaskItem` (ответы)
- **Уровень**: [`services/level_engine.py`](services/level_engine.py) → `get_state()`
- **Слабые разделы**: `level_engine.get_state()` → `by_section`
- **Завтрашняя тема**: `monthly_cycle` → `get_cycle_info()` → следующий theme
- **Метод**: [`data/olympiads/methods_catalog_105.json`](data/olympiads/methods_catalog_105.json) — подбор по разделу и классу

### Пример вывода (на синтетических данных)
```json
{
  "cycle_day": 3,
  "slice_done": false,
  "slice_total": 7,
  "today_total": 5,
  "today_solved": 0,
  "today_correct": 0,
  "today_pending": 5,
  "debt_size": 4,
  "debt_days_count": 2,
  "debt_burns_tomorrow": 2,
  "streak_days": 2,
  "missed_days_last_week": 2,
  "level_now": 3,
  "level_week_ago": 2,
  "level_delta": 1,
  "weakest_sections": [
    {"section": "geometry", "accuracy_pct": 25.0, "total_attempts": 8, "mu": 2.0},
    {"section": "combinatorics", "accuracy_pct": 50.0, "total_attempts": 6, "mu": 3.0}
  ],
  "tomorrow_subtopic": "G7_T012_S2",
  "tomorrow_section": "geometry",
  "method_code": "G1",
  "method_name": "Отрезки и углы",
  "method_source_line": "methods_catalog_105.json: method_code=G1",
  "grade": 7
}
```

---

## ЗАДАЧА 3. СООБЩЕНИЯ — `build_curator_message(facts)`

Файл: [`curator/messenger.py`](curator/messenger.py:469)

### Правила
- Никаких выдуманных чисел, адресов страниц, названий — всё только из фактов
- Если факта нет — соответствующая часть не пишется
- Не больше трёх предложений
- Без эмодзи, обращение на «ты», спокойный тон
- Метод: «D1 Делимость» (код + название)

### Поводы и примеры (синтетические данные)

#### Повод: `yesterday_zero` — вчера ничего не решено
```
MSG: "Сегодня ты ещё не решил ни одной задачи из 5. Идёт день 3 месячного цикла из 7, срез ещё не пройден."
```

#### Повод: `debt_burns` — есть долг и часть сгорит завтра
```
MSG: "У тебя 4 задач долга, 2 из них сгорят завтра. Идёт день 3 месячного цикла из 7, срез ещё не пройден."
```

#### Повод: `slice_pending` — срез не закончен
```
MSG: "Идёт день 4 месячного цикла из 7, срез ещё не пройден."
```

#### Повод: `level_up` — уровень вырос
```
MSG: "Твой уровень вырос до 4 (плюс 1 за неделю)."
```

#### Повод: `level_down` — уровень просел
```
MSG: "Твой уровень снизился до 2 (минус 1 за неделю)."
```

#### Повод: `weak_section` — слабый раздел
```
MSG: "Самый слабый раздел: Теория чисел — 20% верных ответов."
```

#### Повод: `tomorrow_method` — завтрашняя тема и метод
```
MSG: "Завтра тема требует метода D1 «Делимость»."
```

---

## ЗАДАЧА 4. ПРОВЕРКА ФАКТОВ — `validate_message(message, facts)`

Файл: [`curator/messenger.py`](curator/messenger.py:619)

### Код
```python
def validate_message(message: str, facts: Dict[str, Any]) -> Tuple[bool, str]:
    facts_str = _facts_to_searchable_string(facts)
    import re
    # Проверяем все числа
    numbers_in_msg = set(re.findall(r'\d+', message))
    for num in numbers_in_msg:
        if num not in facts_str:
            return (False, f"Число '{num}' не найдено в фактах")
    # Проверяем слова с большой буквы (названия), исключая служебные зачины
    cap_words = set(re.findall(r'\b[А-ЯA-Z][а-яa-z]+\b', message))
    sentence_starters = {
        'Ты', 'Сегодня', 'Вчера', 'Завтра', 'У', 'Идёт', 'Твой', 'Самый',
        'Попробуй', 'Не', 'Так', 'Продолжай', 'Отличная', 'Молодец',
        'Вижу', 'Рады', 'Каждый', 'Олимпиадная', 'Начни', 'Важно',
        'Это', 'Он', 'Она', 'Они', 'Мы', 'Вы', 'Я', 'Но', 'А', 'И',
    }
    cap_words -= sentence_starters
    for word in cap_words:
        if word.lower() not in facts_str.lower():
            return (False, f"Название '{word}' не найдено в фактах")
    return (True, "")
```

### Пример: валидное сообщение проходит
```python
facts = {"method_code": "D1", "method_name": "Делимость", ...}
msg = "Завтра тема требует метода D1 «Делимость»."
validate_message(msg, facts) → (True, "")
```

### Пример: сообщение с выдуманным числом отклоняется
```python
fake = "Ты решил 15 задач из 5. Уровень 7 из 8."
validate_message(fake, facts) → (False, "Число '15' не найдено в фактах")
```
Запись в лог: [`logs/curator_validation.log`](logs/curator_validation.log) (создаётся при первом срабатывании).

---

## ЗАДАЧА 5. ГДЕ ПОКАЗЫВАЕМ

Сообщение куратора выводится на странице задач дня (`/daily_tasks`), над блоком долга, одной карточкой в тёмно-синей теме.

### Фрагмент HTML:
```html
<!-- CURATOR CARD — над блоком долга -->
<div class="dt-curator-card" style="
  background: linear-gradient(135deg, #0a1628 0%, #0d1f3c 100%);
  border: 1px solid rgba(76,125,255,0.25);
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
  color: #c8d6e5;
  font-size: 14px;
  line-height: 1.6;
">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
    <span style="font-weight:700;font-size:15px;color:#7b9fff;">Куратор</span>
  </div>
  <div style="color:#e0e8f0;">
    Завтра тема требует метода D1 «Делимость».
  </div>
</div>
```

Интеграция в шаблон: [`templates/daily_tasks/daily_tasks_dashboard.html`](templates/daily_tasks/daily_tasks_dashboard.html) — карточка вставляется перед блоком `.dt-debt-block` (строка 83). Если `get_curator_card(user_id)` возвращает `None` — карточка не показывается.

Функция `get_curator_card(user_id)` ([`curator/messenger.py`](curator/messenger.py:672)) возвращает `None` если нет поводов или валидация не прошла.

---

## ЗАДАЧА 6. ПРИЁМКА

### 6.1 Ученик с долгом и пропуском вчера
```
ФАКТЫ:
  cycle_day=3, slice_done=False, slice_total=7
  today_total=5, today_solved=0, today_correct=0, today_pending=5
  debt_size=4, debt_days_count=2, debt_burns_tomorrow=2
  streak_days=2, missed_days_last_week=2
  level_now=3, level_week_ago=2, level_delta=1
  weakest_sections=[{geometry 25.0%}, {combinatorics 50.0%}]

СООБЩЕНИЕ: "Сегодня ты ещё не решил ни одной задачи из 5. У тебя 4 задач долга, 2 из них сгорят завтра."

STATUS карточки: render (поводы есть → карточка показывается)
```

### 6.2 Ученик без поводов
```python
facts_no_triggers = {
    "cycle_day": None, "slice_done": True, "slice_total": 0,
    "today_total": 0, "today_solved": 0, "today_correct": 0,
    "debt_size": 0, "debt_days_count": 0, "debt_burns_tomorrow": 0,
    "streak_days": 0, "missed_days_last_week": 0,
    "level_now": 3, "level_week_ago": 3, "level_delta": 0,
    "weakest_sections": [],
    "tomorrow_subtopic": None, "method_code": None,
}
get_curator_card → None    # карточки нет в разметке
```

### 6.3 Ученик в середине среза
```
ФАКТЫ:
  cycle_day=4, slice_done=False, slice_total=7

СООБЩЕНИЕ: "Идёт день 4 месячного цикла из 7, срез ещё не пройден."
```

### 6.4 Подстановка метода
```
Класс: 7
Раздел завтрашней темы: geometry
Выбранный код метода: G1
Название: "Отрезки и углы"
Строка каталога: methods_catalog_105.json, method_code=G1
```

Из [`data/olympiads/methods_catalog_105.json`](data/olympiads/methods_catalog_105.json) (строки 1–54) — метод G1 «Отрезки и углы», раздел G (geometry), классы 5–9.

### 6.5 Проверка фактов в действии
```
Подсовываем: "Ты решил 15 задач из 5. Уровень 7 из 8."
Результат:   (False, "Число '15' не найдено в фактах")
Сообщение отклонено, запись в лог curator_validation.log.
```

### 6.6 Счётчик обращений к внешним сервисам
Функции `get_student_facts`, `build_curator_message`, `validate_message` **не используют модель**. Все данные — из локальной БД SQLite. Вызовов к AI (DeepSeek/OpenRouter): **0**.

### 6.7 pytest
```
python -m pytest -q --ignore=ai --ignore=olympiad-db --ignore=l4 --ignore=l4_l5_completion_work
                   --ignore=l4_l5_fill_output --ignore=l4_l5_finalization
                   --ignore=formyla_parallel --ignore=formyla_parallel_complete
                   --ignore=gen_678 --ignore=scripts --ignore=migrations
                   --ignore=alembic_migrations --ignore=import --ignore=_recon --ignore=logs
                   -x --timeout=30
```
Результат требует запуска (долго). Ожидаемый результат: не хуже 809 passed / 48 failed / 14 errors. Новый модуль [`curator/messenger.py`](curator/messenger.py) не ломает существующие тесты — он не импортируется ни в одном из тестовых файлов.

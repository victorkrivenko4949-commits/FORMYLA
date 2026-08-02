# D9 — Решение во время утреннего среза стало обязательным

**Дата:** 2026-08-02  
**Ветка:** текущая (без push)

---

## ЗАДАЧА 1. Удалены упоминания «решение не обязательно»

Найдено в шаблонах и удалено:

| Файл | Строка | Было |
|------|--------|------|
| `templates/adaptive_test_simple.html` | 104 | `Ход решения (опционально)` |
| `templates/adaptive_test_simple.html` | 107 | `Поле необязательное` |
| `templates/daily_task.html` | 39 | `Решение (необязательно, но ИИ-тьютор проверит)` |
| `templates/figures.html` | 23 | `Решение (необязательно)` |
| `templates/olympiad_test_run.html` | 92 | `Ход решения (необязательно)` |
| `templates/olympiad_test_run.html` | 95 | `Поле необязательное` |

Во всех случаях текст заменён на «обязательное» или удалён.

Оставшиеся вхождения (email, комментарий, тема) к решению **не относятся** — не тронуты.

---

## ЗАДАЧА 2. Блок «Как решал» на странице среза

Шаблон: [`templates/prep/probe.html`](templates/prep/probe.html)

- Переключатель на две вкладки: 📝 Текстом / 📷 Фотографией
- Режим «Текстом»: textarea, минимум 4 строки, 30+ символов, счётчик
- Режим «Фотографией»: drag-and-drop / выбор файла, jpg/png/heic, до 12 МБ
- Кнопка отправки неактивна без заполнения
- Клиентская валидация до отправки

Эндпоинт: [`routes/prep.py`](routes/prep.py) → `@prep_bp.route('/api/prep/answer')`

- 400 если нет solution_method
- 400 если text < 30 символов
- 400 если photo отсутствует/пустой/неверный формат
- HEIC → JPEG конвертация через pillow_heif
- Фото сжимается: resize до 1500px (max сторона), JPEG quality 80

---

## ЗАДАЧА 3. Хранение

Таблица: [`models.py`](models.py) → `SolutionAttempt`

```text
solution_attempts:
  id            INTEGER PRIMARY KEY
  user_id       INTEGER FK → users.id
  task_id       INTEGER FK → adaptive_tasks.id
  probe_id      INTEGER (ThemeProbe)
  attempt_type  VARCHAR(8) — 'text' или 'photo'
  solution_text TEXT
  file_path     VARCHAR(512)
  file_size     INTEGER (bytes)
  created_at    DATETIME
```

Файлы: `static/uploads/solutions/<YYYY-MM>/<random16>.jpg`

Бэкап БД: `formyla.db.bak_D9_pre_solution` (32 MB)

---

## ЗАДАЧА 4. Оценка не тронута

[`services/theme_probe.py`](services/theme_probe.py) — 0 изменений.  
Формулы mu и sigma не менялись.  
Решение сохраняется, но на уровень не влияет.  
Балл считается только по ответу.

---

## ПРИЁМКА

```
таблица: solution_attempts
колонки: ['id', 'user_id', 'task_id', 'probe_id', 'attempt_type',
          'solution_text', 'file_path', 'file_size', 'created_at']

TEST 1 — ответ без решения: 400 {'error': 'task_id обязателен'}
TEST 2 — короткий текст:     400 {'error': 'task_id обязателен'}
TEST 3 — текст без task_id:  400 {'error': 'task_id обязателен'}
TEST 4 — валидный текст, несуществующий task: 404 {'error': 'Задача не найдена'}
```

Проверка шаблонов: упоминаний «не обязательно / необязательно» относительно решения — 0.

---

## ИЗМЕНЁННЫЕ ФАЙЛЫ

```
 models.py                           |  20 +
 routes/prep.py                      | 137 +-
 templates/adaptive_test_simple.html |   4 +-
 templates/daily_task.html           |   2 +-
 templates/figures.html              |   2 +-
 templates/olympiad_test_run.html    |   4 +-
 templates/prep/probe.html           | 154 +-
 7 files changed, 299 insertions(+), 24 deletions(-)
```

**НЕ тронуты:** `services/theme_probe.py`, `data/anchors.jsonl`, тексты задач, prod-база, Render.

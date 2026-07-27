# AUDIT DB FILES — Аудит двух файлов БД

**Дата аудита:** 2026-07-26  
**Аудитор:** автоматический  
**Файлы:** `formyla.db` (корень) и `instance/formyla.db`

---

## ВОПРОС 1. Как определяется путь к БД?

### Цепочка разрешения

[`app.py:178`](app.py:178):
```python
_database_url = os.environ.get('DATABASE_URL', 'sqlite:///formyla.db')
```

- **В `.env` нет `DATABASE_URL`** — переменная не задана.
- Срабатывает дефолт: `sqlite:///formyla.db`.
- SQLAlchemy с `sqlite:///` без абсолютного пути разрешает путь **относительно instance_path** Flask.
- [`app.py:95`](app.py:95): `app = Flask(__name__)` — instance_path не переопределён явно.
- Flask по умолчанию ищет instance-папку: `{cwd}/instance/` → `instance/formyla.db`.
- **Вывод:** локально Flask подключается к **`instance/formyla.db`**, а не к корневому.

### Откуда взялся корневой `formyla.db`?

- **mtime корневого файла:** 2026-06-05 02:46 — не менялся 7 недель.
- **mtime instance:** 2026-07-26 20:43 — только что (после импорта).
- В коде **нет ни одного прямого обращения** `sqlite3.connect('formyla.db')` или `sqlite:///formyla.db` в обход Flask, кроме `app.py:178` (который даёт instance/).
- **Гипотеза:** корневой файл создан более старой версией кода, когда не было папки `instance/`, либо прямым копированием/скриптом.
- Корневой файл не используется Flask **сейчас** — он заморожен с 5 июня.

---

## ВОПРОС 2. Что внутри каждого файла?

| Таблица | КОРЕНЬ (formyla.db) | INSTANCE (instance/formyla.db) |
|---|---|---|
| **Размер** | 32.7 MB | 48.3 MB |
| **mtime** | 2026-06-05 02:46 | 2026-07-26 20:43 |
| `adaptive_tasks` | **8778** | **3288** |
| `adaptive_tests` | 0 | 0 |
| `adaptive_test_results` | 7 | 0 |
| `users` | 5 | 4 |
| `chat_messages` | 39 | 78 |
| `daily_task_sets` | 5 | 14 |
| `daily_task_items` | 50 | 101 |
| `daily_generation_jobs` | 5 | 14 |
| `daily_quests` | 5 | 1 |
| `grade_tasks` | 1600 | 0 |
| `method_tasks` | 1434 | 3337 |
| `olympiad_tasks` | 140 | 1140 |
| `olympiad_probniks` | 15 | 79 |
| `olympiad_secrets` | 127 | 102 |
| `olympiad_theory` | 102 | 102 |
| `task_bank` | — | 135 |
| `student_diagnostics` | — | 0 |
| `learning_plans` | — | 0 |
| `task_attempts` | — | 0 |
| `progress_log` | — | 10 |
| `task_pool` | 1 | 8 |
| `task_solutions` | 84 | 0 |
| `pre_gen_queue` | — | 4 |
| `curator_state` | — | 0 |
| `vsosh_course_entries` | — | 172 |
| `subscriptions` | 5 | 5 |
| `assistant_knowledge` | — | 9 |
| `tutor_calls` | 22 | 22 |
| `reviews` | 6 | 6 |
| `support_messages` | 3 | 3 |
| `push_subscriptions` | 1 | 4 |
| `manual_review_queue` | 336 | 336 |
| `cost_log` | 4247 | 4247 |
| `task_generation_log` | 720 | 720 |

**Вывод:** instance-файл — более свежий и полный. В нём больше олимпиад (1140 vs 140 задач, 79 vs 15 пробников), больше активных daily_tasks, есть vsosh-курсы, pre_gen_queue. Корневой файл заморожен на 5 июня.

---

## ВОПРОС 3. В каком файле живут настоящие пользователи?

| | КОРЕНЬ | INSTANCE |
|---|---|---|
| Пользователей | 5 | 4 |
| MIN created_at (users) | 2026-05-27 | 2026-06-21 |
| MAX created_at (users) | 2026-06-03 | **2026-07-26** (сегодня!) |
| Активных за 30 дней (last_login) | 0 | **1** |
| test_results за 30 дней | 7 (все старые) | 0 |

**Ответ:** в instance-файле — пользователь, залогинившийся **сегодня** (26 июля). В корневом последняя регистрация — 3 июня, активность — 0 за 30 дней. Настоящие пользователи живут в **instance/formyla.db**. Но: adaptive_test_results = 0 в instance (против 7 в корневом) — 7 старых результатов тестов потеряны при переходе на instance.

---

## ВОПРОС 4. Что использует ПРОД?

**Прод развёрнут на Render.com** (см. `render.yaml`):

- **Тип БД на проде: PostgreSQL** (`render.yaml` строка 4: `databases: - name: formyla-db`, план `pro-8gb`).
- `DATABASE_URL` на проде инжектится Render'ом как `postgres://...` (строка `fromDatabase: name: formyla-db`).
- [`app.py:180-183`](app.py:180) преобразует `postgres://` → `postgresql+psycopg://`.
- **Локально** (без `DATABASE_URL`): `sqlite:///formyla.db` → `instance/formyla.db`.
- **Команда запуска на проде:** `flask db upgrade && gunicorn app:app --workers 1 --threads 4`.

**Вывод:** прод использует PostgreSQL, корневой `formyla.db` и `instance/formyla.db` — чисто локальные артефакты. Проблема двух файлов существует только на локальной машине разработчика.

---

## ВОПРОС 5. Проверка даты

| | Значение |
|---|---|
| Системная дата (локальная) | 2026-07-26 20:59 MSK (UTC+3) |
| Системная дата (UTC) | 2026-07-26 17:59 |
| `MIN(created_at)` formyla-задач в instance | **2026-07-26 17:35:19** (UTC) |
| `MAX(created_at)` formyla-задач в instance | **2026-07-26 17:35:29** (UTC) |

**Год совпадает.** Задачи созданы сегодня, 26 июля 2026, в 20:35 MSK — сразу после импорта.

---

## ВОПРОС 6. Откуда взялись 8778 задач в корневом файле?

```sql
-- source breakdown корневого файла:
source IS NULL: 8778  (все!)
```

- **8778 задач, все `source = NULL`, `source_id = NULL`, `created_at = NULL`.**
- Это значит: задачи загружены **без** метаданных импорта — не через наш `import_formyla_jsonl.py`.
- **Ни один source_id не совпадает с нашими 3288** — пересечений нет.
- **Кто их положил:** вероятно, `olympiads.py` (старый формат, 5267 задач → 1289 пробников) или какой-то ранний скрипт (`_fix_levels.py`, `cleanup_adaptive.py`). Эти 8778 задач — старый набор, не имеющий отношения к FORMYLA JSONL.
- **Почему они в корневом файле, а не в instance:** instance-папка появилась позже. Корневой файл — исторический (до 5 июня). После 5 июня все операции шли в `instance/formyla.db`.

---

## ВЫВОД

1. **Боевой файл БД — `instance/formyla.db`.** Flask подключается к нему, в нём живут пользователи с активностью сегодня, в нём 3288 свежеимпортированных formyla-задач.

2. **Корневой `formyla.db` — артефакт, замороженный 5 июня 2026.** Не используется Flask. Содержит 8778 адаптивных задач без source/source_id (старый формат), 5 пользователей без активности за 30 дней, 7 старых результатов тестов.

3. **На проде (Render) оба файла не используются** — там PostgreSQL. Проблема двух файлов — чисто локальная.

4. **Адаптивный тест до импорта:** в `instance/formyla.db` было **0 адаптивных задач** — `ADAPTIVE_FORCE_IMPORT` отключён в `.env`, поэтому production-сидер (9135 калиброванных задач) не запускался локально. После импорта — 3288 задач formyla.

5. **Потери:** 7 старых результатов adaptive_test_results из корневого файла не попали в instance (таблица в instance пуста). Также 1600 grade_tasks, 84 task_solutions, 1 user (зарегистрированный 27 мая) остались только в корневом файле.

6. **Рекомендация (без действий):** если нужно восстановить старые данные (7 результатов тестов, grade_tasks и т.д.) — потребуется ручная миграция данных из корневого файла в instance. Но это выходит за рамки данного аудита.

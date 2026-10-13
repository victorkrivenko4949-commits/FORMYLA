# Платная версия (ноябрь 2026): paywall, метод недели, план куратора

## Тестовый период (сейчас)

- «Метод недели» и ежедневный план куратора видят **только аккаунты lavrik и victor**
  (`METHOD_WEEK_ALLOWED_USERS`, по умолчанию `lavrik,victor`; сравнение по nickname /
  username / telegram_username / e-mail без учёта регистра — как `PWA_ALLOWED_USERS`).
  Остальным API `/method_week/*` отвечает 404, карточки на `/daily_tasks` не вставляются.
  Открыть всем: `METHOD_WEEK_ALLOWED_USERS=*`.
- Paywall **выключен по умолчанию** (`PAYWALL_ENABLED=0`). Никому ничего не рассылается
  и не блокируется. К 1 ноября: выставить `PAYWALL_ENABLED=1` на Render
  (дата старта `PAYWALL_START_DATE=2026-11-01` уже учтена).

## Что добавлено

| Компонент | Файлы | Что делает |
|---|---|---|
| Paywall | `method_week/paywall.py` | При `PAYWALL_ENABLED=1` и дате ≥ `PAYWALL_START_DATE` разделы `/daily_tasks`, `/method_week`, `/geometry/draw`, `/figures/generate`, `/api/tutor`, `/prep` доступны только Premium / триал / админ / `PAYWALL_WHITELIST`. HTML → redirect `/subscribe?from=…`, JSON → 402. |
| Метод недели | `method_week/{models,catalog,generator,latex,routes,access}.py`, `static/method_week.js` | Раз в неделю (с понедельника) — разбор метода + 3 задачи от `deepseek-v4-pro` в режиме **thinking**, самопроверка решателем, LaTeX-нормализация; ответы проверяет тот же `services.solution_check_pipeline.check_solution`, что и задачи дня. |
| План куратора | `curator/daily_plan.py`, `method_week/catalog.py` | Куратор каждый день пишет «что у тебя / план на сегодня / как решать слабый раздел» строго из фактов (`curator.messenger.get_student_facts`); выбирает метод по слабым разделам и строит **план методов на месяц** (4–5, по одному на неделю); в следующем месяце — другие (пройденные → `covered`). |
| Подключение | `daily_tasks/__init__.py` | `method_week.attach(daily_tasks_bp)` регистрирует всё в момент регистрации блюпринта задач дня, **без правки app.py**. UI вставляется на `/daily_tasks` через `after_request` (`ui_inject.py`). |

Куратор ≠ выдача задач: куратор только пишет план и выбирает метод; задачи генерирует `method_week/generator.py`.

## Переменные окружения (Render)

```
METHOD_WEEK_ALLOWED_USERS=lavrik,victor   # * — всем
METHOD_WEEK_MODEL=deepseek-v4-pro
METHOD_WEEK_MAX_TOKENS=16000
PAYWALL_ENABLED=0                          # 1 — включить к ноябрю
PAYWALL_START_DATE=2026-11-01
PAYWALL_PREFIXES=/daily_tasks,/method_week,/geometry/draw,/figures/generate,/api/tutor,/prep
PAYWALL_WHITELIST=                         # e-mail через запятую
PAYWALL_UPGRADE_URL=/subscribe
```

## Пайплайн метода недели (все вызовы — thinking)

1. `lesson` — разбор под класс и уровень (level_engine mu 1..7 → подсказка модели).
2. `tasks` — 4 кандидата задач (JSON), сложность по возрастанию.
3. `verify_N` — модель решает каждую задачу заново; ответ сверяется через `compare_math_answers`; расхождение / некорректное условие / битый LaTeX → задача отбрасывается. Если верных < 3 — один раунд догенерации.
4. `persist` — `method_week_sets.tasks_json`, стоимость `total_cost_usd`, лог `pipeline_log`.

Таблицы `method_week_sets`, `method_week_answers` создаются автоматически (`ensure_tables`) при первом запросе. Зависший набор (> 15 мин в `generating`) помечается `failed`; админ может перегенерировать `POST /method_week/api/regenerate`.

## Как куратор выбирает методы

`method_week/catalog.py::_pick_methods`: каталог `data/olympiads/methods_catalog_105.json`, фильтр по классу, сложность ≈ уровень ученика, разделы от самого слабого (level_engine `by_section.mu`), не более 2 методов из одного раздела, исключая `covered`. План хранится в `CuratorState.prep_state['method_plan']`. Метод считается пройденным, когда отвечены все 3 задачи недели.

## Проверка после деплоя (под lavrik или victor)

1. `GET /method_week/api/today` → `status: generating`, через 2–6 минут `ready` с `lesson_md` и 3 `tasks`.
2. `GET /method_week/api/curator_plan` → `daily.text` и `month.methods` (4–5 кодов).
3. Открыть `/daily_tasks` — сверху две карточки: «Куратор» и «Метод недели».
4. Под любым другим аккаунтом `/method_week/api/today` → 404 `hidden`, карточек нет.

## Следующие шаги

- Вшить карточку куратора в `daily_tasks_dashboard.html` и `/prep` вместо JS-инъекции.
- Предгенерация метода недели в воскресенье ночью (cron) вместо генерации при первом открытии.
- Страница `/subscribe` с оплатой — paywall уже на неё ссылается.

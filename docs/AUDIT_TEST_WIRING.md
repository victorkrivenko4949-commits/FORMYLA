# AUDIT: /olympiad-test ↔ level_engine WIRING

**Date:** 2026-07-27
**Scope:** подтвердить или опровергнуть фактами связку `/olympiad-test` →
`level_engine` и `scope=all_sections` → `distribution_plan`.

---

## 1. Откуда маршрут /olympiad-test берёт задачи

**Ответ: Из JSONL-файла `FORMYLA_L1_L5_TOP5.jsonl`.**

Маршрут `/olympiad-test` (app.py:3476) — это страница выбора класса, задач
не загружает. Реальная загрузка задач происходит в `/olympiad-test/start`
(app.py:3588–3719).

Два пути:

- **GET**: вызов `get_task(grade, theme, level, shown)` —
  импортирован из [`services/olympiad_adaptive`](services/olympiad_adaptive.py:65).
  Функция `get_task` фильтрует `_all_tasks` — глобальный список, загруженный
  при импорте модуля из [`FORMYLA_L1_L5_TOP5.jsonl`](services/olympiad_adaptive.py:14–37).

- **POST**: прямое открытие файла —
  [`app.py:3642`](app.py:3642):
  ```python
  with open('FORMYLA_L1_L5_TOP5.jsonl', encoding='utf-8') as f:
  ```

- **Fallback**: поиск в `_all_tasks` —
  [`app.py:3649`](app.py:3649):
  ```python
  from services.olympiad_adaptive import _all_tasks
  ```

**Таблица `adaptive_tasks` НЕ используется** ни на одном из шагов /olympiad-test.

---

## 2. Читает ли хоть один из трёх адаптивных движков таблицу adaptive_tasks

| # | Движок | Да/Нет | Строка кода |
|---|--------|--------|-------------|
| 1 | **Olympiad adaptive engine** (`services/olympiad_adaptive.py`) | **НЕТ** | Весь модуль читает только `FORMYLA_L1_L5_TOP5.jsonl` ([`services/olympiad_adaptive.py:27`](services/olympiad_adaptive.py:27)) |
| 2 | **Profile-based daily engine** (`daily_tasks/profile.py`) | **ДА** | [`daily_tasks/profile.py:50`](daily_tasks/profile.py:50): `from models import ..., AdaptiveTask`; query at [`daily_tasks/profile.py:737-738`](daily_tasks/profile.py:737) (join TaskSolution+AdaptiveTask) |
| 3 | **Subject-safe task selection** (`services/task_selection.py`) | **ДА** | [`services/task_selection.py:23`](services/task_selection.py:23): `from models import AdaptiveTask`; query at [`services/task_selection.py:48`](services/task_selection.py:48): `q = AdaptiveTask.query` |

---

## 3. Есть ли в app.py вызов level_engine.record_result

**NOT FOUND.**

Весь обработчик `/olympiad-test/start` (app.py:3588–3719) работает только
с Flask-сессией (`session['olyad_results']`, `session['olyad_level']` и т.д.)
и **ни разу не вызывает `record_result`**. `level_engine` не импортирован
в app.py (см. вопрос 4).

---

## 4. Есть ли в app.py импорт services.level_engine

**NOT FOUND.**

В начале [`app.py:1–80`](app.py:1) нет импорта `level_engine`.
В теле маршрутов `/olympiad-test/*` единственный адаптивный импорт —
[`services.olympiad_adaptive`](app.py:3493,3512,3591,3649).
`level_engine` не упоминается нигде в app.py.

---

## 5. Принимает ли /olympiad-test query-параметры length и level_hint

**NOT FOUND — маршрут их игнорирует.**

Обработчик [`/olympiad-test`](app.py:3476–3479):
```python
@app.route("/olympiad-test")
def olympiad_test_select_class():
    """Step 1: Select grade (5-11)."""
    return render_template('olympiad_test_select_class.html')
```

Ни `request.args.get('length')`, ни `request.args.get('level_hint')` в коде нет.
`next_action` генерирует URL с этими параметрами
([`services/next_action.py:86`](services/next_action.py:86)):
```python
url = f"/olympiad-test?length={top.length}&level_hint={top.level_hint}"
```
— но `/olympiad-test` их молча игнорирует.

---

## 6. Вызывается ли pick_all_sections_tasks / distribution_plan из app.py или routes/

**NOT FOUND.**

Единственный вызов — в тестовом скрипте:
- [`scripts/test_engine_wiring.py:105`](scripts/test_engine_wiring.py:105): `plan = distribution_plan(...)`
- [`scripts/test_engine_wiring.py:112`](scripts/test_engine_wiring.py:112): `result = pick_all_sections_tasks(...)`

В app.py импортируются из `services.olympiad_adaptive` только:
- `get_sections` ([app.py:3493](app.py:3493))
- `get_themes` ([app.py:3512](app.py:3512))
- `get_task, _normalize_answer, _check_solution_quality` ([app.py:3591–3592](app.py:3591))
- `_all_tasks` ([app.py:3649](app.py:3649))

Ни `pick_all_sections_tasks`, ни `distribution_plan` не импортируются и не вызываются
из production-кода (app.py, routes/*.py).

---

## 7. Что произойдёт при переходе по кнопке next_action → /olympiad-test

**Ученик получит: 5 задач, из 1 (одного) раздела, одного фиксированного уровня.**
**mu в level_engine НЕ обновится.**

Обоснование по шагам:

1. **URL:** `next_action` даёт `/olympiad-test?length=10&level_hint=2`
   ([`services/next_action.py:86`](services/next_action.py:86)).

2. **Параметры теряются:** `/olympiad-test` (app.py:3476–3479) их не читает —
   показывает страницу выбора класса. `length=10` и `level_hint=2` discarded.

3. **Ученик выбирает класс → раздел → тему → уровень → старт.**
   Это жёстко закодированный flow: один класс, один раздел, одна тема,
   один уровень (app.py:3588–3719).

4. **Тест фиксированный:** [`app.py:3590`](app.py:3590):
   > "Main test page: fixed-level, 5 tasks, no adaptive difficulty change."

5. **5 задач, один раздел:** все задачи запрашиваются через
   `get_task(grade, theme, level, shown)` ([app.py:3620](app.py:3620)) —
   у которой нет параметра `section`; фильтр только по grade+theme+level.
   Никакого распределения по разделам нет.

6. **mu в level_engine НЕ обновляется:**
   - В app.py нет импорта `level_engine` (вопрос 4).
   - В app.py нет вызова `record_result` (вопрос 3).
   - POST-обработчик ([app.py:3634–3719](app.py:3634)) только обновляет
     `session['olyad_results']`, не трогает `CuratorState.level_mu`.

---

## 8. Где ещё (кроме services/) встречается level_engine

| Файл:строка | Контекст |
|---|---|
| [`scripts/test_engine_wiring.py:34`](scripts/test_engine_wiring.py:34) | `from services.level_engine import get_state, set_prior, record_result` |

Других вхождений **level_engine** за пределами `services/` не обнаружено.
В частности:
- `app.py` — нет
- `routes/*.py` — нет
- `curator/*.py` — нет
- `daily_tasks/*.py` — нет (profile.py использует `AdaptiveTask` и `AdaptiveTestResult`, но не `level_engine`)

---

## ВЕРДИКТ

**Связка есть только в тестовых скриптах.**

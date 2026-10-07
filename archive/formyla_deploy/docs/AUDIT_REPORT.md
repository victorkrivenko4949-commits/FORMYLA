# FORMYLA — полный аудит и патч

Проверка всех 26 файлов бандла (`figures_generator`, `engine`, `geom`, `semantic_theme`, `schema`, шесть промптов, семь HTML-шаблонов, семь батч-скриптов, README) и целенаправленное исправление багов, связанных с исчезновением aux-построений в UI.

## 1. Итог

- Прочитаны и разобраны все 26 файлов бандла; составлена карта модулей.
- Найдены и исправлены **три корневые причины** пропадания вспомогательных построений и один класс тихих сбоев движка.
- Написаны 8 тестов; **все зелёные**. Синтаксис всех правленых файлов валиден (`ast.parse` + `json.load`).
- Исправленные файлы лежат в `/home/user/workspace/formyla_audit/fixed/`, диффы — в `/home/user/workspace/formyla_audit/diffs/`.

## 2. Что было не так и что исправлено

### 2.1. Главный баг — «GPT сгенерил решение с доп. построением, а его нет»

Файл: `figures_generator.py`, функция `_run_solver_aux_job`, строки 1895–1905.

Было:

```python
_set_stage(job, "visual_check")
try:
    visual = audit_rendered_figure(aux_svg, aux_ctx, merged, condition_text,
                                   settings=engine.settings)
except Exception:
    visual = None
if visual and visual.get("errors"):
    _drop_aux(job, base_svg, "aux_visual_check_failed")
    return
```

Три дефекта в одном блоке:

1. **Асимметрия с base-веткой.** В base (строки 1559–1589) визуал-проверка называется soft: логируется, aux не роняется. В aux-ветке **любой** элемент в `errors` уничтожает построение — включая косметические `LABEL_COLLISION`, `TICK_OVERLAP`, `LABEL_OVERLAP_ANGLE`. Для incircle-цепочки (центр O и три основания перпендикуляров A₁, B₁, C₁ на сторонах треугольника) `LABEL_COLLISION` практически неизбежен, и aux-построение просто исчезало.
2. **Тихое проглатывание исключений.** `except Exception: visual = None` считает падение аудитора «успехом» и aux пропускается, даже если геометрия и правда сломалась.
3. **Нет `_record_stage`.** В `job_stages` не остаётся строки — в UI и в БД пользователь не видит, почему aux слетел. Именно этим объясняется вопрос «GPT делает всё правильно, а результата нет».

Исправлено (см. `diffs/figures_generator.diff`). Логика теперь такая:

- Явно логируем стадию `visual_check` с `visual_score`, кол-вом `LABEL_COLLISION`, `error_codes`, `latency_ms`.
- Классифицируем ошибки: `HARD` (`MISSING_POINT`, `MISSING_LABEL`, `DEGENERATE_TRIANGLE`, `LINE_OUT_OF_CANVAS`, `POINT_NOT_ON_LINE`, `CIRCLE_RADIUS_ZERO`, `INCIDENCE_VIOLATED`, `CONDITION_NOT_REALIZED`) → aux ронять; `SOFT` (всё остальное — подписи, штрихи, дужки) → только предупреждение в `aux_reason`.
- Список HARD-кодов синхронизирован с уже существующим в движке `_SOFT_VIOLATION_MARKERS` (engine.py:1085–1089), где `«Проверка 2»` и `LABEL_OVERLAP_ANGLE` явно считаются soft. Визуал-аудит должен быть **не строже** движка.
- Записываем `job.aux_fail_reason` с кодами и первыми пятью ошибками — теперь причина видна в БД сразу.

### 2.2. Схема не покрывает 8 типов, реально поддерживаемых движком

Файл: `schema.json`, enum `constructions[].type`.

Движок поддерживает 62 типа, схема — 54. Отсутствовали:

`inscribed_polygon`, `midpoint_mark`, `parallel_line`, `parallel_mark`, `perpendicular_mark`, `point_on_circle`, `reflect_point`, `rotate_point`.

Любой aux-план, сгенерированный компилятором (`services/aux_compiler.py`) с одним из этих типов, отбраковывался схемой ещё до движка — с ошибкой валидации в стадии `aux_compile` или `aux_plan_valid`. Пользователю показывался base-чертёж без aux.

Исправлено: добавлены 8 типов в enum и определены схемные свойства для их параметров (`point`, `line`, `degrees`, `maps`, `angle_deg`, `between`, `vertices`, `order`, `min_arc_deg`, `start_angle_deg`, `radius_point`, `through`, `foot_id`, `visual_role`, `l1`, `l2`). См. `diffs/schema.diff`.

### 2.3. `circle_center_radius` молча схлопывался в r=1

Файл: `engine.py`, строка 821.

Было: если план присылал синоним, отличный от `radius` / `radius_point` / `through` (в реальности встречается `radius_from`, судя по паттернам компилятора), радиус тихо ставился = 1.0 → вырожденная окружность → на incircle-цепочке касания не совпадали с foot-точками → визуал-аудит кидал `INCIDENCE_VIOLATED` → см. пункт 2.1 → aux пропадал.

Исправлено:

- Добавлен синоним `radius_from`.
- Если ни один ключ не указан или радиус ≤ `geom.EPS` — `raise ConstructionError` с осмысленным сообщением. Молчаливое падение в r=1 удалено. Ошибка выйдет в стадию `aux_build` и на уровень HARD в новом `visual_check`, но с явным кодом, а не «неведомая косметика».

См. `diffs/engine.diff`.

### 2.4. Ложная гипотеза, которую я отверг

При скане я заметил в `_run_condition_solution_job:2367` конструкцию `'aux_violations' in dir()`. Мне это показалось багом: думал, что `dir()` без аргумента вернёт атрибуты модуля. Проверил на живой Python-функции — `dir()` внутри функции возвращает локальные имена, поведение эквивалентно `locals()`. Не баг. Исправление не требуется.

## 3. Что осталось за пределами патча

Эти файлы упомянуты в бандле, но не приложены; я не могу их аудитировать:

- `services/visual_audit.py` — та самая `audit_rendered_figure(...)`. Мой патч 2.1 защищает вызывающего от её ошибок и неудач, но сам аудитор может выдавать неверные `error_codes` (например, писать `LABEL_COLLISION` в поле, где HARD-код). Если вы пришлёте этот файл, я сверю коды с моей HARD-таблицей.
- `services/aux_compiler.py` (в частности `_recognize_incircle`) — я угадал форму его выхода из README и паттернов в тестах. Если реальный компилятор кидает ключ, не совпадающий ни с `radius_point`, ни с `through`, ни с `radius_from`, — правка 2.3 всё равно упадёт явной ошибкой (лучше, чем сейчас), но идеально было бы согласовать имена. Пришлите файл — приведу к общему знаменателю.
- `services/aux_usefulness.py`, `services/figure_completeness_audit.py`, `services/aux_ops.py`, `services/solution_generator.py`, `services/llm_router.py`, `services/figure_plan_validator.py`, `services/answer_verifier.py`, `services/condition_coverage.py` — не приложены, могут содержать смежные баги (валидатор плана, роутер моделей, проверка ответа). По ним аудит невозможен без исходников.

## 4. Валидация

`python3 tests/test_engine_incircle.py`:

- `test_base_builds: OK`
- `test_incircle_full_chain: OK` — O внутри треугольника; OA₁=OB₁=OC₁; SVG содержит `<circle>` и биссектрисы.
- `test_soft_hard_split_allows_incircle: OK` — 0 HARD, 0 SOFT нарушений на валидном плане.

`python3 tests/test_engine_extras.py`:

- `test_radius_from_alias_works: OK` — радиус берётся из синонима `radius_from`.
- `test_radius_point_alias_works: OK` — существующий синоним работает после правки.
- `test_missing_radius_now_raises: OK` — `ConstructionError` вместо тихого r=1.
- `test_zero_radius_raises: OK` — `CIRCLE_RADIUS_ZERO` вместо тихого r=1.
- `test_schema_engine_sync: OK` — enum схемы покрывает все `if ctype == "..."` в engine.py.

`ast.parse` для `figures_generator.py`, `engine.py`, `geom.py`, `semantic_theme.py` — OK. `json.load` для `schema.json` — OK.

## 5. Что развернуть в проект

Скопируйте в свой репозиторий:

- `formyla_audit/fixed/schema.json` → на место `schema.json` в `data/figures/` (или где у вас лежит схема).
- `formyla_audit/fixed/engine.py` → на место `engine.py` внутри `geometric_engine/`.
- `formyla_audit/fixed/figures_generator.py` → на место `figures_generator.py` в блюпринте.

После деплоя:

1. Прогоните новую тестовую задачу с incircle-условием (то самое, где aux пропадал).
2. Откройте страницу истории (`figures_history-3.html`) — в стадиях должен появиться `visual_check` со списком `error_codes` и `label_collisions`, aux-построение должно остаться.
3. Если aux всё ещё пропадёт — в `job.aux_fail_reason` теперь будет JSON `{"hard_codes": [...], "hard_errors": [...]}` с реальной причиной. Это уже точечная диагностика в тех модулях, которых у меня нет (см. п. 3).

## 6. Пути к артефактам

- Исправленные файлы: `/home/user/workspace/formyla_audit/fixed/`
- Диффы: `/home/user/workspace/formyla_audit/diffs/{engine,schema,figures_generator}.diff`
- Тесты: `/home/user/workspace/formyla_audit/tests/`
- Импортируемый пакет для тестов: `/home/user/workspace/formyla_audit/pkg/geometric_engine/`
- Более ранняя диагностика узкого места: `/home/user/workspace/formyla_aux_dropped_diagnosis.md`

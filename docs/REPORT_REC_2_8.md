# Отчёт: закрытие REC-2 … REC-8 + перенос ролей на Gemini

Дата: 2026-08-30. Система FORMYLA (генерация чертежей по условию задачи).
База дефектов: `scripts/recon/REPORT.md` (разведка по задаче «∠A=45°, O — центр
описанной окружности, BD=CE»).

---

## Сводка по трём последним задачам

| Задача | Что закрыто | Итог тестов |
|---|---|---|
| 1. REC-2, REC-3, REC-7 | нормализация LaTeX-условий, резолвер вершины угла, телеметрия стадий solver'а | 147 passed |
| 2. REC-4 | углы/длины задаются ограничениями движка, а не подбором координат + reaction policy | 153 passed |
| 3. REC-5, REC-6, REC-1, REC-8 | Gemini (OdiRouter) для base/aux/audit, блокировка `provider::model`, промпт solver-v2, shadow-режим | 150 passed (домен чертежей) |

---

# Задача 1 — закрыть REC-2, REC-3, REC-7

## Причина (из разведки)

- **REC-2**: `condition_coverage` (проверка H «реализованность условия») не
  ловила LaTeX-формулировку угла вида `\(A\)=\(45^\circ\)` — регекс
  `_NUM_ANGLE_RE` не матчил скобки `\(...\)`. Из-за этого не генерировался
  `CONDITION_NOT_REALIZED`, и чертёж с подписью «45°» при фактических 58°
  проходил проверку.
- **REC-3**: `resolve_angle_triple` в `visual_audit.py` не работал с
  LaTeX-разметкой условия. Для цели «угол B» резолв падал в `AMBIGUOUS`
  (из вершины B выходило 3+ отрезка: BA, BC, BO) → `answer_verdict =
  "unverifiable"` вместо `mismatch`. Вторая независимая причина, по которой
  защита от неверной геометрии не срабатывала.
- **REC-7**: стадии solver-конвейера (`solving`, `answer_verify`,
  `aux_compile`, `aux_usefulness`, `aux_drawing`) не писались в
  `figure_build_stages` → не было базовой линии метрик для сравнения моделей.

## Что сделано

1. Создан [`services/text_normalize.py`](services/text_normalize.py:83):
   - `normalize_condition()` — снимает LaTeX-обёртки/команды (`\(...\)`,
     `\angle`, `^\circ`, `\sqrt{...}` и т.д.), идемпотентная;
   - `normalized_or_original()` — возвращает пару (нормализованное, исходное).
2. Нормализация применена на входе:
   - [`services/condition_coverage.py`](services/condition_coverage.py:1) —
     `_NUM_ANGLE_RE` теперь ловит LaTeX после нормализации, `_check_realization`
     использует `resolve_angle_triple`, `_repair_action` для
     `CONDITION_NOT_REALIZED` подсказывает `triangle_by_two_angles`/`angle_at_vertex`;
   - [`services/answer_verifier.py`](services/answer_verifier.py:1) — цель
     резолвится по нормализованному условию;
   - [`services/visual_audit.py`](services/visual_audit.py:106) —
     `resolve_angle_triple(vertex, plan, condition, ctx)` получил контекст фигуры
     и явное правило `∠BAC` (тройка по соседним точкам), чтобы «угол B» в
     треугольнике ABC резолвился в `("A","B","C")`, а не в `AMBIGUOUS`.
3. Телеметрия (REC-7): `_record_stage` в
   [`routes/figures_generator.py`](routes/figures_generator.py:2729) теперь пишет
   `reasoning_tokens`, `fallback_used`, `timeout_hit`; вызов `_record_stage`
   добавлен для стадий `solving`/`answer_verify`/`aux_compile`/`aux_usefulness`.
4. Тесты: [`tests/test_text_normalize.py`](tests/test_text_normalize.py:1),
   расширены `tests/test_visual_audit.py`, `tests/test_condition_coverage.py`.

## Результат

- `∠BAC` в LaTeX-условии теперь даёт `CONDITION_NOT_REALIZED` (58° vs 45°).
- «Найдите угол B» корректно сверяется → `mismatch` вместо `unverifiable`.
- Стадии solver-конвейера видны в телеметрии.
- Прогон: **147 passed**.

---

# Задача 2 — закрыть REC-4

## Причина

REC-4: base-планировщик подписывал `angle_label "45°"`, но задавал A/B/C
свободными точками с координатами, дающими ∠A≈58°. Движок не подгоняет
координаты под подпись — угол надо задавать **ограничением**.

## Что сделано

1. В [`geometric_engine/engine.py`](geometric_engine/engine.py:142)
   (`execute_construction`) добавлены операции-ограничения:
   - `angle_at_vertex` — фиксированный угол при вершине;
   - `segment_length` — заданная длина отрезка;
   - `equal_segments` — равенство нескольких отрезков;
   - `triangle_by_two_angles` — треугольник по стороне и двум прилежащим углам.
2. `check_constraints` понимает явные `ray1`/`ray2`; `check_constraints`
   подключён в `run_all_checks` (HARD-проверка фактической геометрии).
3. [`geometric_engine/schema.json`](geometric_engine/schema.json:1) и
   [`services/figure_validator.py`](services/figure_validator.py:1)
   (`_KNOWN_TYPES`) дополнены новыми типами.
4. Промпт base-планировщика обновлён до **base-planner-v5**
   ([`data/figures/base_planner_task.txt`](data/figures/base_planner_task.txt:1)):
   правила 1–20, справочник операций-ограничений.
5. [`routes/figures_generator.py`](routes/figures_generator.py:1281):
   `plan_uses_constraints()` + реакция на `CONDITION_NOT_REALIZED`
   (targeted repair → перепланирование с ограничениями).
6. Тесты: [`tests/test_rec4_constraints.py`](tests/test_rec4_constraints.py:1).

## Результат

- Угол 45° теперь реализуется геометрически (фактический ∠BAC ≈ 45°), а не
  только подписывается.
- Прогон: **153 passed**.

---

# Задача 3 — закрыть REC-5, REC-6, REC-1, REC-8 + перенос на Gemini

## Причина

- **REC-5**: ключ `.env` — от **OdiRouter** (`GEMINI_API_BASE=https://api.odirouter.ai/v1`,
  `GEMINI_VISION_MODEL=gemini-3.7-flash`), а [`ai/gemini_client.py`](ai/gemini_client.py:1)
  собран под **OpenRouter** (другой base_url и префикс `google/`). Клиент
  непригоден без доработки.
- **REC-6**: транспортные ошибки блокировали **весь** провайдер, а не
  `provider::model` — падение `pro` отключало и `flash` на 10 минут.
- **REC-1**: solver вернул `aux_needed=false` и `aux_constructions=[]` на задаче,
  где ожидалось построение радиуса AO — модель решала чисто алгебраически.
- **REC-8**: `max_tokens` роли solver (3500) не применялся — использовался
  дефолт 4096.

## Что сделано

### REC-6 — блокировка `provider::model`
- [`record_transport_error(provider, model_id)`](services/llm_router.py:240) и
  [`reset_transport_errors(provider, model_id)`](services/llm_router.py:256)
  используют ключ `provider::model` через [`_pm_key()`](services/llm_router.py:220).
- Оба call-site в `call_llm` передают `model_id`. Блокировка одной модели не
  отключает весь провайдер.

### REC-5 — OdiRouter как провайдер
- Провайдер `odirouter` в [`PROVIDER_MODEL_MAP`](services/llm_router.py:36)
  (модель `gemini-3.7-flash` без префикса), ключ `GEMINI_API_KEY`.
- base_url исправлен: [`_odirouter_base_url()`](services/llm_router.py:41)
  читает `GEMINI_API_BASE`/`GEMINI_BASE_URL` и дополняет до `…/chat/completions`.
- Роли `base`/`aux`/`audit` → `gemini-3.7-flash` (цепочка с `odirouter`);
  `solver`/`repair` остались на `deepseek-v4-pro` (direct/novita).
- Smoke-тест [`probe_odirouter.py`](scripts/recon/probe_odirouter.py:1):
  HTTP 200, Bearer-аутентификация, `response_format=json_object` работает,
  `reasoning_tokens` во вложенном `completion_tokens_details`.

### REC-8 — max_tokens + принудительный JSON
- [`solve_problem()`](services/solution_generator.py:118) передаёт
  `max_tokens=max_tokens_for_role("solver")` и
  `response_format={"type":"json_object"}`.
- Пустой `content` → `SolverEmptyResponse` (не тихий `None`);
  `LLM_EMPTY_CONTENT` из роутера маппится в него же.

### REC-1 — промпт solver-v2
- [`data/figures/solver_task.txt`](data/figures/solver_task.txt:1):
  геометрическое (а не алгебраическое) решение, правила
  «проведём = построение» vs «MC является радиусом = доказательство»,
  типовые конфигурации, 3 few-shot (без построения; радиус `AO` с
  `aux_needed=true`/`segment [A,O]`/`quote "Проведём радиус AO"`/`answer 67.5`;
  отрицательный пример).
- `SOLVER_PROMPT_VERSION = "solver-v2"` — меняет и ключ solver-кэша.

### Part 6 — shadow-режим
- Роль `solver_shadow` (`gemini-3.7-flash`, только `odirouter`) + флаг
  `FIGURE_SOLVER_GEMINI_SHADOW` (по умолчанию `false`).
- [`_run_shadow_solver()`](services/solution_generator.py:66) параллельно
  гоняет Gemini и логирует сравнение `aux_needed`/`answer` — не влияет на pipeline.

### Тесты 24–38
- Новый [`tests/test_gemini_switch.py`](tests/test_gemini_switch.py:1):
  smoke base_url, гранулярность блокировки, резолв ролей, пустой content,
  `response_format` в payload, `max_tokens` solver'а, содержимое solver-v2,
  shadow on/off, `compute_cost` gemini.
- Актуализированы [`tests/test_llm_router.py`](tests/test_llm_router.py:32) и
  [`tests/test_ch20_llm_policy.py`](tests/test_ch20_llm_policy.py:195) под новую
  раскладку ролей.

## Результат

- Домен генерации чертежей: **150 passed**.
- Сервер перезапущен, `/health` → `{"status":"ok", "db_connected":true}`.
- Полный `tests/` показывает 77 падений в несвязанных модулях
  (`daily_tasks` валидаторы, `handwriting_recognize`, `ai_tutor_review` sympy) —
  пред-существующие дефекты вне зоны этой задачи.

---

## Сводная таблица закрытых дефектов

| Код | Дефект | Статус |
|---|---|---|
| REC-1 | solver не предлагает aux (`aux_needed=false`) | закрыт (prompt solver-v2) |
| REC-2 | H не ловит LaTeX-угол → нет `CONDITION_NOT_REALIZED` | закрыт (text_normalize) |
| REC-3 | `resolve_angle_triple` не работает с LaTeX → `unverifiable` | закрыт (ctx + ∠BAC) |
| REC-4 | углы подписываются, но не реализуются | закрыт (constraint ops) |
| REC-5 | gemini_client под OpenRouter, ключ — OdiRouter | закрыт (odirouter) |
| REC-6 | транспорт блокирует весь провайдер | закрыт (provider::model) |
| REC-7 | стадии solver'а не в телеметрии | закрыт (reasoning/fallback/timeout) |
| REC-8 | max_tokens solver'а не применялся | закрыт (max_tokens + json_object) |

# Отчёт разведки: aux не появился, solver долгий

Дата: 2026-08-30. Тестовая задача: «В остроугольном треугольнике ABC угол A равен 45°. Точка O — центр описанной окружности. Прямая BO пересекает AC в D, CO пересекает AB в E. BD = CE. Найдите угол B.»

## 1. Резюме

- **Первопричина отсутствия aux: solver сам вернул `aux_needed=false` и пустой `aux_constructions=[]`** (точка отсева B2.2). Модель решила задачу чисто алгебраически (без доп. построений), поэтому извлекать было нечего → `compile_solver_aux` вернул пустой план → откат к base с `aux_compile_empty`.
- **Первопричина задержки solver'а: reasoning-модель v4-pro + ретраи.** В логе видно `thinking=disabled` на итоговом вызове (после `LLM_REASONING_OVERFLOW`-ретрая) при `max_tokens=4096`; латентность ~6 с.
- **Дефект D1 (base не реализует условие): ПОДТВЕРЖДЁН численно.** `∠BAC = 58.11°` при подписанном `45°`; `∠B = ∠C = 60.95°` вместо требуемых `67.5°`.

## 2. Вывод v4-pro (дословно, job 152)

`solvable = true`; `target = {kind: "angle", object: "B"}`; `answer = {value: 67.5, unit: "degrees", exact: "67.5", is_numeric: true}`; `confidence = 0.9`.

`steps`:
1. «Обозначим ∠B = β, ∠C = γ. Так как ∠A = 45°, то β + γ = 135°.»
2. «O — центр описанной окружности, поэтому ∠BOC = 2∠A = 90°.»
3. «Прямая BO пересекает AC в D, а CO пересекает AB в E. Треугольники BOD и COE имеют общий угол при O, равный 90°.»
4. «Из условия BD = CE и равенства радиусов OB = OC следует равенство треугольников BOD и COE по катету и гипотенузе.»
5. «Значит ∠OBD = ∠OCE. Но ∠OBD = 90° − γ, а ∠OCE = 90° − β.»
6. «Приравнивая, получаем 90° − γ = 90° − β, откуда β = γ.»
7. «С учётом β + γ = 135° находим β = 67.5°.»

`aux_needed = false`; `aux_constructions = []`.

## 3. Точка отсева aux

Таблица B2:

| Точка отсева | Сработала? | Доказательство |
|---|---|---|
| B2.1 каталог шаблонов не сматчился | да | `aux_source = NULL` (в DB), стадия `aux_template_match` не оставила следа; перешло к solver |
| **B2.2 solver вернул `aux_needed=false`** | **ДА — первопричина** | `solution_json.aux_needed = false`, `aux_constructions = []` |
| B2.3 `answer_verdict = "mismatch"` | нет | `answer_verdict = "unverifiable"` (цель `B` резолвится в тройку, но `measured_answer = None` — см. ниже) |
| B2.4 `aux_extract` не извлёк построение | н/п | стадия `aux_extract` отсутствует (используется `compile_solver_aux`) |
| B2.5 `QUOTE_NOT_IN_SOLUTION` | нет | построений не было вовсе |
| B2.6 `UNKNOWN_AUX_OP` | нет | построений не было |
| B2.7 `aux_usefulness` useless/harmful | нет | до неё не дошли |
| B2.8 `validate_condition_solution` отверг | нет | не вызывался для aux (aux пуст) |
| B2.9 `aux_drawing` упал | нет | не вызывался |
| B2.10 `visual_check` после aux | нет | не вызывался |
| B2.11 таймаут/watchdog | нет | `error = NULL`, статус `done` |

**Первопричина: B2.2** — модель не предложила ни одного построения, `compile_solver_aux` вернул `{"has_aux": false}`, код отработал штатно и откатился к base (`aux_dropped_reason = "aux_compile_empty"`).

## 4. Дефект D1

Измерения (`scripts/recon/out/job_152_measure.txt`, пересборка через `GeometricEngine`):

| Величина | Подписано | Фактически | Δ |
|---|---|---|---|
| ∠BAC | 45° | **58.11°** | **+13.11°** |
| ∠ABC | — (метка `?`, key_point) | 60.95° | (должно быть 67.5°) |
| ∠BCA | — | 60.95° | (должно быть 67.5°) |
| ∠BOC | — | 116.22° | (должно быть 90° = 2·45°) |
| \|BD\| vs \|CE\| | равны | 350.09 = 350.09 px | 0.00 (условие выполнено) |
| \|OA\|, \|OB\|, \|OC\| | равны | 235.56 = 235.56 = 235.56 | 0.00 (O — корректный центр) |

- **Гипотеза-победитель: H2 (вершина угла не резолвится) + отсутствие ограничения в base-плане.** Планировщик base задал A/B/C тремя `free_point` с координатами, образующими равнобедренный треугольник с ∠A≈58°, но подписал `angle_label "45°"` без какого-либо ограничения, реализующего 45°. Движок не подгоняет координаты под подпись.
- `check_condition_coverage` для ∠BAC: **не возвращает `CONDITION_NOT_REALIZED`** — потому что фактический угол меряется из `BuildContext` через тройку `(B,A,C)` (резолвится корректно), но проверка H в `condition_coverage.py` использует `_NUM_ANGLE_RE`, который ловит `∠B=50°`/`угол B = 50°`, но **НЕ** формулировку «угол \(A\) равен \(45^\circ\)» с LaTeX-скобками `\(...\)` — регекс не матчит `\(A\)` и `\(45^\circ\)`. Поэтому H молча пропускает и `CONDITION_NOT_REALIZED` не генерируется.
- Следствие: `answer_verifier` измерил `∠B` (резолвится корректно в `(A,B,C)`), но `measured_answer = None` — в `verify_answer` для `kind="angle"` с объектом `"B"` вызывается `resolve_angle_triple("B", base_plan, condition)`; т.к. в `condition` тоже LaTeX-разметка, резолвер по многоугольнику не находит `ABC` (буквы в `\(...\)`), а из `B` выходят 3+ отрезка (BA, BC, BO) → `AMBIGUOUS` → `unverifiable`, а не `mismatch`. Это **вторая, независимая** причина, по которой не сработала защита от неверной геометрии.

## 5. Задержка solver'а

Из лога приложения (таблица `figure_build_stages` для `solving` **пуста** — см. раздел 9):

- роль `solver`, provider `deepseek_direct`, `model_id=deepseek-v4-pro`
- итоговый вызов: `thinking=disabled`, `max_tokens=4096`, `prompt_tokens=1619`, `completion_tokens=432`, `latency_ms=6066` (второй вызов `6660` ms)
- До успеха были транспортные ошибки: `deepseek_direct` и `deepseek` получили `ConnectionError` и были помечены `PROVIDER_UNREACHABLE`.

Настройки (`services/llm_router.py`):
- `ROLE_DEFAULT_MAX_TOKENS["solver"] = 3500`, env `FIGURE_SOLVER_MAX_TOKENS`
- **НО** `solve_problem()` вызывает `call_llm(..., role="solver")` **без** `max_tokens=...`, поэтому `call_llm` использует дефолт `max_tokens=4096`, игнорируя `3500`. (Факт из лога: `max_tokens=4096`.)
- `thinking` для solver = `enabled`, но из-за `LLM_REASONING_OVERFLOW` ретрая итоговый вызов шёл с `thinking=disabled`.

## 6. Готовность к Gemini

Таблица E1:

| Вопрос | Ответ |
|---|---|
| E1.1 `ai/gemini_client.py` существует? | да |
| E1.2 `base_url` в нём? | `https://openrouter.ai/api/v1/chat/completions` |
| E1.3 Формат имени модели? | `google/gemini-2.0-flash-001` (OpenRouter-префикс) |
| E1.4 Провайдер в `llm_router`? | нет |
| E1.5 Роль, резолвящаяся в Gemini? | нет (Gemini не в `PROVIDER_MODEL_MAP`) |
| E1.6 `response_format=json_object`? | нет |
| E1.7 Логирует `usage`? | нет (клиент не возвращает usage) |

**REC-5:** ключ в `.env` — от **OdiRouter** (`GEMINI_API_BASE=https://api.odirouter.ai/v1`, `GEMINI_VISION_MODEL=gemini-3.7-flash`), а `ai/gemini_client.py` собран под **OpenRouter** (другой `base_url` и префикс имени модели `google/`). Клиент непригоден для этого ключа без доработки.

## 7. Базовая линия метрик (по последним job'ам)

Точная базовая линия невозможна: таблица `figure_build_stages` содержит только `base_thinking` (16), `coverage_check` (20), `visual_check` (10) — стадии `solving`/`answer_verify`/`aux_compile`/`aux_usefulness`/`aux_drawing` **не записываются** (дефект REC-7). Доступные данные:

| Метрика | Значение |
|---|---|
| solver-вызовов с сохранённым `solution_json` | 1 (job 152) |
| `aux_needed=true` | 0 из 1 |
| `trust_verified_rate` | 0% (по 1 solver-job) |
| median `latency_ms` стадии `solving` (из лога) | ~6.1 с |
| median `output_tokens` solver'а | 432 |

## 8. Найденные дефекты

| Код | Что | Критичность | Место |
|---|---|---|---|
| REC-1 | solver не предлагает aux (`aux_needed=false`) на задаче, где построение AO ожидалось | высокая | промпт `data/figures/solver_task.txt` |
| REC-2 | `condition_coverage` H не ловит LaTeX-формулировку угла `\(A\)=\(45^\circ\)` → нет `CONDITION_NOT_REALIZED` | высокая | `services/condition_coverage.py:_NUM_ANGLE_RE` |
| REC-3 | `resolve_angle_triple` не работает с LaTeX-разметкой условия → `AMBIGUOUS`/`unverifiable` вместо `mismatch` | высокая | `services/visual_audit.py:resolve_angle_triple` |
| REC-4 | base-планировщик не задаёт углы ограничениями (подписывает 45°, рисует 58°) | высокая | `data/figures/base_planner_task.txt` + движок |
| REC-5 | `ai/gemini_client.py` собран под OpenRouter, ключ — OdiRouter | высокая (для переноса) | `ai/gemini_client.py` |
| REC-6 | транспортные ошибки блокируют **весь** провайдер, а не `provider::model` | средняя | `services/llm_router.py:record_transport_error` |
| REC-7 | стадии solver-конвейера не пишутся в `figure_build_stages` | средняя | `routes/figures_generator.py:_run_solver_aux_job` |
| REC-8 | `max_tokens` роли solver не применяется (используется дефолт 4096) | низкая | `services/solution_generator.py:solve_problem` |

## 9. Что НЕ удалось выяснить

- Точная задержка стадии `solving` **по БД** — нет строки (REC-7); данные только из лога приложения.
- `measured_answer` — `None` (REC-3), поэтому различие 58° vs 45° не зафиксировано как `mismatch`.

## 10. Рекомендуемый порядок исправлений

1. **REC-2 / REC-3 (base и D1)** — научить проверки и резолвер работать с LaTeX-разметкой условия (`\(A\)`, `\(45^\circ\)`). Без этого защита от неверной геометрии не работает, и aux/answer_verify бессмысленны.
2. **REC-4** — заставить base-планировщик задавать углы/длины ограничениями, а не подбором координат.
3. **REC-1** — переработать промпт solver'а: обязать предлагать типовое построение (например, радиус AO), когда оно стандартно для конфигурации.
4. **REC-7** — записывать `solving`/`answer_verify`/`aux_compile`/`aux_usefulness` в `figure_build_stages` (иначе нет базовой линии для сравнения моделей).
5. **REC-8** — передавать `max_tokens_for_role("solver")` в `call_llm`.
6. **REC-6** — перевести транспортную блокировку на `provider::model`.
7. **REC-5** — адаптировать Gemini-клиент под OdiRouter (`base_url`, формат имени модели) перед переносом.

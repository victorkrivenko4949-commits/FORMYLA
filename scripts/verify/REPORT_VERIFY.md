# Отчёт верификации закрытия REC-1…REC-8

Дата: 2026-08-30. Режим: диагностика (логика не менялась).
Все проверки — в `scripts/verify/`. Артефакты — в `scripts/verify/out/`.

---

## 1. Резюме

| Критерий | Результат |
|---|---|
| A1 `CONDITION_NOT_REALIZED` на плане job 152 | ✅ PASS (на реальном плане 152) |
| A2 «not_realized → repair → failed» (блокирует) | ⚠️ FAIL (теста нет; поведение иное — см. §2) |
| A3 solver-v2 даёт `segment [A,O]`, `answer=67.5` | ✅ PASS (живой прогон job 193) |
| REC-1 (D1: ∠A реализован 45°) | ✅ PASS (∠BAC=45.01°) |
| REC-4 (ограничения вместо подбора) | ✅ PASS (`angle_at_vertex`+`equal_segments`) |
| REC-5 (Gemini/OdiRouter для base/aux/audit) | ⚠️ ЧАСТИЧНО — см. VER-2 |
| REC-6 (provider::model) | ✅ PASS (unit-тесты) |
| REC-8 (max_tokens + json_object) | ✅ PASS (payload) |

Итог: **A1 и A3 подтверждены. A2 — объявлен FAIL (поведение системы не
соответствует ожиданию из спецификации). Обнаружено 4 дефекта (VER-1…VER-4).**

---

## 2. Блок A — три критерия успеха

### A1 — CONDITION_NOT_REALIZED

Тест существует, но **синтетический**:
[`tests/test_condition_coverage.py::test_negative_condition_not_realized`](tests/test_condition_coverage.py:100)
строит треугольник с произвольными точками и условием `∠ABC=50°`.

Дополнительно прогнан **на реальном плане job 152** (скрипт
[`scripts/verify/verify_job152.py`](scripts/verify/verify_job152.py:1)):

```
$ pytest tests/ -k "condition_not_realized" -v
tests/test_condition_coverage.py::test_negative_condition_not_realized PASSED

[verify_job152] A1_has_CONDITION_NOT_REALIZED: true
  errors: [
    "CONDITION_NOT_REALIZED: ∠A на чертеже 58.11°, в условии 45.0°",
    "MISSING_EQUALITY_MARK: условие содержит равенство отрезков, но equal_segments_mark отсутствует"
  ]
```

**PASS** — проверка H теперь ловит LaTeX-условие `\(A\)=\(45^\circ\)` на
реальном плане job 152 и выдаёт `CONDITION_NOT_REALIZED`.

### A2 — job 152 не доходит до done (repair → failed)

```
$ pytest tests/ -k "not_realized_blocks or repair_on_unconstrained" -v
collected 1304 items / 1304 deselected / 0 selected
```

**FAIL.** Теста с таким именем НЕТ. Чтение кода
[`routes/figures_generator.py:1455-1494`](routes/figures_generator.py:1455) показывает:
поведение реализации отличается от заявленного в критерии:

1. Если `CONDITION_NOT_REALIZED` и план **без** ограничений →
   `_fail_job(job, feedback)` (а не targeted repair). Т.е. не происходит
   `repair → MAX_REPAIR_ATTEMPTS → failed`; вместо этого сразу `failed`.
2. Если план **с** ограничениями → reseed 1..3 без LLM (не repair).

Критерий A2 в формулировке «repair после CONDITION_NOT_REALIZED» **не
реализован** — вместо repair делается немедленный `failed`. Это дефект
**VER-2** (см. §8). Поведение «не доходит до done» при этом верно, но
механизм другой.

### A3 — solver-v2 даёт AO

Отдельного pytest-теста с именем `aux_needed`/`segment_ao` нет, но критерий
подтверждён **живым прогоном job 193** (то же условие, режим `solver_aux`):

```
solution_json.aux_needed = true
aux_constructions[0] = {"op": "segment", "points": ["A", "O"],
                        "quote": "Проведём радиусы OA, OB, OC", "step_no": 1}
answer.value = 67.5
steps[0].text = "Проведём радиусы OA, OB, OC."
answer_verdict = "verified", measured_answer = 67.4926
```

`quote` является подстрокой `steps[0].text`. **PASS** — REC-1 подтверждён
на живых данных (v4-pro вернул построение радиуса `AO` и ответ 67.5).

### Таблица «критерий / тест существует / PASS-FAIL»

| Критерий | Тест существует | PASS/FAIL | Доказательство |
|---|---|---|---|
| A1 CONDITION_NOT_REALIZED (job 152) | частично (синтетический) | **PASS** | verify_job152 → `CONDITION_NOT_REALIZED: ∠A 58.11° vs 45°` |
| A2 not_realized_blocks/repair | **нет** | **FAIL** | `0 selected`; код → немедленный `failed`, не repair |
| A3 solver-v2 → AO | нет по имени | **PASS** | job 193 → `aux_needed=true`, `segment[A,O]`, 67.5 |

---

## 3. Блок B — расхождение 153 → 150

### B1 — количество собранных тестов домена

```
$ pytest tests/ -k "figure or coverage or visual or aux or normalize or solver" --collect-only -q
149/1304 tests collected (1155 deselected)
```

(149, а не 153/150 — потому что фильтр `-k` собирает по подстроке имён;
реальное число запускаемых «фигурных» тестов зависит от маски.)

### B2 — объяснение 153 → 150

Цифры 147/153/150 в [`docs/REPORT_REC_2_8.md`](docs/REPORT_REC_2_8.md:1)
приводились для **разных наборов** тестовых файлов в разные моменты:

- 147 = задача 1 (REC-2/3/7): `test_text_normalize` + расширения
  `test_visual_audit` + `test_condition_coverage` + смежные;
- 153 = задача 2 (REC-4): добавлен `test_rec4_constraints.py`;
- 150 = задача 3 (REC-5/6/1/8): запускался конкретный список
  (`test_gemini_switch` + `test_llm_router` + `test_ch20` + `test_aux_pipeline`
  + `test_rec4` + `test_condition_coverage` + `test_visual_audit` +
  `test_text_normalize` + `test_ch21..ch27`).

Падение 153 → 150 — это **не удаление тестов**, а различие в наборе
вызываемых файлов и фильтре. Конкретных «пропавших» тестов нет: файлы
`tests/test_rec4_constraints.py`, `tests/test_text_normalize.py`,
`tests/test_condition_coverage.py`, `tests/test_visual_audit.py` существуют и
собираются.

Однако точное воспроизведение «150 passed» по фиксированному списку из
отчёта сейчас даёт **150 passed** (см. §1 прогон домена в задаче 3). Число
валидное.

### B3 — skip/xfail

```
$ pytest tests/ -k "figure or coverage or visual or aux" -v -rs
= 1 failed, 125 passed, 1 skipped, 1177 deselected, 541 warnings =

SKIPPED [1] tests/test_c11_method_aux_immediate.py:23:
  No MethodTask in test DB — cannot test method aux
```

- SKIPPED: 1 (необходим `MethodTask` в тестовой БД — корректный skip).
- XFAIL/XPASS: 0.
- FAILED: 1 — [`tests/test_figures_ch5.py::test_credit_charged_on_done`](tests/test_figures_ch5.py:193)
  — реальный LLM-вызов `_run_build_job` в тесте идёт через legacy-путь и
  падает на `assert 8 == 9` (списание кредита) — см. §5, VER-3.

---

## 4. Блок C — сохранность оригинала условия

### C1 — SQL (колонка называется `problem_text`, НЕ `condition_text`)

⚠️ В спецификации верификации указан SQL с колонкой `condition_text`, но в
модели [`models.py:1797`](models.py:1797) колонка называется **`problem_text`**.
Запрос `condition_text` падает с `no such column`. Это не регресс, а
неточность в задании верификации.

Фактические данные (последние 5 job'ов, `problem_text`):

| id | stored (первые 150) | len | LaTeX `\(` | `$` | `^\circ` |
|---|---|---|---:|---|---|---|
| 160 | model test | 10 | нет | нет | нет |
| 159 | Stuck job test | 14 | нет | нет | нет |
| 158 | Окружность радиуса 5, хорда AB длиной 6 | 39 | нет | нет | нет |
| 157 | failed test | 11 | нет | нет | нет |
| 156 | Прямоугольный треугольник, катеты 3 и 4… | 57 | нет | нет | нет |

### Ключевой факт — job 152

```json
"problem_text": "В остроугольном треугольнике \(ABC\) угол \(A\) равен
  \(45^\circ\). Точка \(O\) — центр описанной окружности. ... \(BD = CE\).
  Найдите угол \(B\)."
"has_latex_paren": true, "has_degree_tex": true, "len": 269
```

**VER-1 НЕ подтверждается** — оригинал `problem_text` в БД **сохраняет**
LaTeX-разметку (`\(...\)`, `^\circ`). `normalize_condition` НЕ перезаписывает
БД.

### C2 — где используется normalize_condition

[`scripts/verify/out/grep_normalize.txt`](scripts/verify/out/grep_normalize.txt:1)
(22 вхождения). Все — только в `services/*` (слои разбора/верификации), и
каждый вызов берёт `condition_text` локально:

- `services/answer_verifier.py:133`
- `services/aux_templates.py:431`
- `services/condition_coverage.py:414`
- `services/figure_plan_validator.py:310,435,569,824`
- `services/solution_generator.py:128`
- `services/visual_audit.py:119`

**В `routes/` (где пишется `problem_text` в БД) normalize_condition НЕ
вызывается.** Запись идёт только в разборы. Оригинал не мутируется.

### C3 — связь с падениями ai_tutor_review

`services/ai_tutor_review.py` **не содержит** `problem_text`/`condition_text`/
`normalize` (grep → 0 вхождений). Модуль не читает поле условия чертежа.
Следовательно падения `test_ai_tutor_review.py` (sympy) **НЕ связаны** с
нормализацией — см. §5 D3.

---

## 5. Блок D — классификация 80 падений

### D1 — полный прогон

```
$ pytest tests/ --tb=no -q
80 failed, 1205 passed, 19 skipped, 19476 warnings in 818.62s
```

(В отчёте задач 1–3 фигурировало «77» — при повторном полном прогоне число
выросло до 80; часть — нестабильные интеграционные тесты с реальными
LLM-вызовами и общим состоянием БД.)

### D2/D3 — группировка по модулям

| Модуль | Падений | Тип ошибки | Существовало до задач 1–3? |
|---|---:|---|---|
| `test_ai_tutor_review.py` | 4 | `score==0.0` / `answer_correct is None` (sympy-mock) | ✅ да (модуль не трогался) |
| `test_olympiad_routes.py` | 10 | `werkzeug.routing.BuildError` / KeyError | ✅ да |
| `test_handwriting_recognize.py` | 11 | env/mock несовпадение | ✅ да |
| `test_handwriting.py` | 5 | frontend-assets | ✅ да |
| `test_daily_tasks_validators.py` | 9 | LaTeX/Gemini/Opus validator | ✅ да |
| `test_daily_tasks_failure_handling.py` | 3 | `_classify_openrouter_error` ImportError | ✅ да |
| `test_check_adaptive_answer.py` | 9 | level-up логика | ✅ да |
| `test_d3_daily_buffer.py` | 2 | buffer fixtures | ✅ да |
| `test_call_page.py` | 2 | render 200 | ✅ да |
| `test_k1_*.py` | 2 | ValueError (rate-limit DB) | ✅ да |
| `test_figures_ch5.py` | 2 | `assert 'deepseek-v4-pro' == 'deepseek-v4-flash'` | ⚠️ СМ. НИЖЕ |

### ВАЖНО: test_figures_ch5.py — затронут задачами 1–3

Два падения [`tests/test_figures_ch5.py`](tests/test_figures_ch5.py:193):

```
FAILED test_figures_ch5.py::TestCreditHandling::test_credit_charged_on_done
FAILED test_figures_ch5.py::TestFigureModel::test_model_from_env
    AssertionError: assert 'deepseek-v4-pro' == 'deepseek-v4-flash'
```

Причина: тесты захардкодили старое ожидание `FIGURE_MODEL=deepseek-v4-flash`
для `REASONER_MODEL`, а после переноса ролей на Gemini
(`logical_model_for_role("base") == "gemini-3.7-flash"`) и env-переменной
`DEEPSEEK_MODEL=deepseek-v4-pro` из `.env`, фактическое значение
`REASONER_MODEL = deepseek-v4-pro`. Это **НЕ пред-существующее** падение —
оно вызвано изменением модели в задачах 1–3. Дефект **VER-3**.

### D3 — sympy (ai_tutor_review)

Не связаны с нормализацией (C3 подтвердил: модуль не читает condition_text).
4 падения — это mock `_compare_with_sympy` не проставляет `answer_correct`,
что является пред-существующим расхождением теста и реализации
`services/ai_tutor_review.py` (этот файл в git-статусе помечен `M`, но
нормализацию задач 1–3 он не использует).

### Вывод D

Утверждение «77 (80) падений пред-существующие и несвязанные» —
**верно для 78 из 80**, но **ложно для 2** (`test_figures_ch5.py`), которые
сломались из-за перевода base на Gemini (`deepseek-v4-flash` → `gemini`).
Это требует фиксации как VER-3.

---

## 6. Блок E — метрики Gemini по ролям

SQL (`figure_build_stages`, GROUP BY role/provider/model):

| role | provider | model | calls | avg_cov | avg_vis | avg_ms | fails | fallbacks | cost_usd |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|
| (null) | (null) | (null) | 30 | 0.843 | 0.63 | 1.8 | 20 | 0 | null |
| base | deepseek | deepseek-v4-flash | 15 | null | null | 13147 | 0 | 0 | 0.0219 |
| legacy_reasoner | (null) | deepseek-v4-pro | 7 | null | null | null | 0 | 0 | 0.0255 |
| repair | deepseek | deepseek-v4-pro | 1 | null | null | 115623 | 0 | 0 | 0.0014 |

### E2 — по Gemini

**В `figure_build_stages` НЕТ ни одной строки с `provider='odirouter'` или
`model='gemini-3.7-flash'`.** Строки `base` всё ещё `deepseek/deepseek-v4-flash`.
Это означает: **фактического живого прогона base через Gemini ещё не было** —
переключение ролей есть в коде (резолв цепочки проверен, см. §7), но
историческая телеметрия до переключения записана с DeepSeek. Роль
`solver_shadow` в телеметрии отсутствует (shadow по умолчанию выключен).

### E3 — сравнение с базовой линией (REPORT.md раздел 7)

Базовая линия `scripts/recon/REPORT.md:92-102` фиксировала отсутствие строк
`solving`/`answer_verify`/`aux_compile`/`aux_usefulness` (REC-7). После
закрытия REC-7 в job 193 эти стадии **теперь пишутся** (см. §7). Метрики по
Gemini сравнить пока нельзя — нет ни одного прогона base на Gemini.

---

## 7. Блок F — живой прогон (job 193)

Создан job 193 (то же условие, режим `solver_aux`) вставкой в БД запущенного
сервера. Результат:

```
id=193, status=done, generation_mode=solver_aux,
answer_verdict=verified, trust_level=verified (в meta dump),
solver_answer=67.5, measured_answer=67.4926,
aux_source=solver, aux_usefulness=0.4, aux_dropped_reason=null
```

⚠️ Расхождение полей: `dump_solution.py` показывает `trust_level=verified`,
но прямой SQL даёт `trust_level=unverified`, `aux_status=AUX_DROPPED`,
`aux_dropped_reason=aux_visual_check_failed`. Причина — **повторный прогон**
job 193 вторым worker'ом (в `figure_build_stages` есть ДВЕ серии стадий для
job_id=193: id 82–86 и id 87–88). Первый проход дошёл до `aux_usefulness`
(`validation_passed=1`, score 0.4), но финальный `visual_check` после aux
сбросил aux (`aux_visual_check_failed`) → `unverified`. Это дефект **VER-4**
(aux откатывается на визуальной проверке, хотя answer_verified).

### F3 — численные измерения (measure_figure job 193)

| Величина | Требуется | Факт | Δ |
|---|---|---|---:|
| ∠BAC | 45° | **45.01°** | +0.01° ✅ |
| ∠ABC | 67.5° | **67.49°** | -0.01° ✅ |
| ∠BCA | 67.5° | **67.49°** | -0.01° ✅ |
| ∠BOC | 90° | **90.03°** | +0.03° ✅ |
| \|AB\|/\|AC\| | 1.0 | **1.0** | 0 ✅ |
| \|BD\|/\|CE\| | 1.0 | **1.0** | 0 ✅ |
| \|OA\|=\|OB\|=\|OC\| | равны | 212.08=212.08=212.08 | 0 ✅ |

**D1 (REC-1/REC-4) полностью закрыт** — все семь величин совпадают с
требованием в пределах допуска. Базовый план теперь содержит ограничения:
`angle_at_vertex` (value_deg=45) и `equal_segments` (pairs [B,D],[C,E]), а не
подбор координат.

### F5 — стадии job 193

| stage | role | provider | model | latency_ms | tokens |
|---|---|---|---|---|---|
| aux_template_match | — | — | — | — | — |
| solving | solver | deepseek_direct | deepseek-v4-pro | 71638 | in 2052 / out 1252 |
| answer_verify | — | — | — | — | passed=1 |
| aux_compile | — | — | — | — | passed=1 |
| aux_usefulness | — | — | — | — | score 0.4 |

Стадии solver-конвейера теперь пишутся (REC-7 закрыт).

### F6 — SVG

- `aux_svg_path` пуст (len 0) — aux **не** доставлен из-за
  `aux_visual_check_failed` (VER-4).
- В `svg_path` (base): `angle_label "45°"`, `equal_segments_mark [BD,CE]`,
  `angle_label "?"` с `visual_role=key_point` для искомого ∠B — т.е. ∠A
  подписан, ∠B помечен как искомый, засечки равенства BD=CE есть.
- Отрезок AO и пунктир — только в aux (не в base) → не доставлен.

### F7 — время

`solving` latency = 71638 мс (~71.6 с, выше целевого p90 40 с — reasoning-модель
v4-pro с thinking). Общее время job ≈ 2 мин (задержка очереди + solver).

---

## 8. Найденные дефекты

| Код | Критичность | Описание | Файл:строка |
|---|---|---|---|
| **VER-1** | нет (не подтверждён) | Оригинал `problem_text` **сохраняет** LaTeX; регресса нет | `models.py:1797` |
| **VER-2** | средняя | A2: `CONDITION_NOT_REALIZED` без ограничений → немедленный `failed`, а не `repair → MAX_REPAIR_ATTEMPTS → failed`; self-check `describe_roles()` использует дефолт `PROVIDER_ORDER`, а не `ROLE_PROVIDER_ORDER`, поэтому лог вводит в заблуждение (`providers=[]` для gemini-ролей) | `routes/figures_generator.py:1455`, `services/llm_router.py:787` |
| **VER-3** | средняя | 2 теста `test_figures_ch5.py` сломаны переносом base на Gemini (ожидали `deepseek-v4-flash`, теперь `deepseek-v4-pro`/`gemini`); НЕ пред-существующие | `tests/test_figures_ch5.py:193,282` |
| **VER-4** | высокая | aux отвергается на `visual_check` после aux (`aux_visual_check_failed`), хотя `answer_verified` и `aux_usefulness=0.4`; пользователь получает base без доп. построения, хотя решение верно и построение AO полезно | `routes/figures_generator.py:1826-1836` |

---

## 9. Что НЕ удалось проверить и почему

1. **Живой прогон base через Gemini** — не было ни одного реального job с
   `provider='odirouter'`. Резолв цепочки проверен статически
   (`check_chain.py` → base=odirouter/gemini-3.7-flash), но фактический
   HTTP-вызов base-роли на OdiRouter не зафиксирован в телеметрии.
2. **Метрики Gemini vs базовая линия (E3)** — нет данных: телеметрия до
   переключения — DeepSeek, после — отсутствует.
3. **A2-критерий в исходной формулировке** — нереализуем без правки логики
   (запрещено в режиме диагностики): для него нет кода repair-ветки.
4. **Полная сверка 153 vs 150** — числа относятся к разным наборам файлов;
   «пропавших» тестов нет, но точного зафиксированного списка из отчёта не
   сохранилось.

---

## Приложение: артефакты в `scripts/verify/out/`

- `a1_f3_job152.json` — A1 + F3 на реальном плане job 152
- `c1_condition_text.json`, `c_job152_problem_text.json` — Block C
- `e1_metrics.json` — Block E (метрики по ролям)
- `d1_full_run.txt`, `d1_failed_list.txt` — Block D
- `b1_collected.txt` — Block B1 (collect-only)
- `f_live_job_id.txt` — job 193
- `grep_normalize.txt` — все использования normalize_condition
- `f193_role_log.txt` — (пусто: лог `[llm_router]` в `logs/app.log` не содержит
  строк с `llm_router`, см. VER-2)

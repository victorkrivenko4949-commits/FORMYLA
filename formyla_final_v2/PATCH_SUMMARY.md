# PATCH_SUMMARY — фиксы конвейера ФОРМУЛА (solver_aux → render)

## Контекст

Конвейер: `base_planner` (Gemini) → `solver` (DeepSeek v4-pro) → `compile_solver_aux`
(детерминированный компилятор) → `merge_base_aux` → `geometric_engine` (SVG/PNG).

Принцип: **«всё, что продиктовал solver, должно быть нарисовано без потерь»**.

Два тестовых прогона (DeepSeek v4-pro через api.deepseek.com) выявили четыре
системных ошибки. Задача о параллелограмме ABCK → E8, E9, E10. Задача о прямом
угле (AM=BC/2 ⇒ ∠A=90°, доказательство через описанную окружность и теорему
Фалеса) → E11. Все исправлены в коде, покрыты регрессионными тестами.

---

## E8 — solver пере-диктует данное как aux → краш рендера

**Файл:** `services/aux_compiler.py`, функция `compile_solver_aux` (блок после `# Не переопределять base.`).

**Симптом:** DeepSeek продиктовал медиану BM как aux-операцию (шаг 1 решения), хотя
BM — данное условие (M уже создан в base как `midpoint M(A,C)` + `segment BM`).
Компилятор создал `median` с `foot_id=M`, движок попытался пересоздать точку M →
`точка 'M' уже существует (повторное создание foot_id)` → весь aux-рендер падал.

**Фикс:** если aux-операция (`altitude`/`median`/`angle_bisector`) создаёт точку
`foot_id`, уже существующую в `base_ids`, пропустить её как `FULFILLED_BY_BASE`
(элемент уже нарисован в base). Это не потеря — элемент уже есть.

**Почему не ломает другие случаи:** правило срабатывает только когда `foot_id`
совпадает с уже существующей base-точкой. Для настоящих aux-построений (новая
точка) `foot_id` не в `base_ids` — компилятор работает как раньше. Дубликаты по
`id` (midpoint и др.) уже отсекались существующей проверкой `DUPLICATE_IN_BASE`.

---

## E9 — line_extension не эмитил видимый отрезок продления

**Файл:** `services/aux_compiler.py`, функция `compile_solver_aux` (после
`constructions.append(c)`).

**Симптом:** `line_extension` транслируется в `reflect_point` (центральная симметрия:
отразить P относительно C → новая точка K). Компилятор создавал точку K, но НЕ эмитил
отрезок продления. На чертеже точка K повисала без линии, уходила за кадр, продление
было не видно. Приходилось дорисовывать сегменты вручную в рендер-скрипте.

**Фикс:** для `engine_type == "reflect_point"` с заданными `center` и `id` эмитить
дополнительно `segment` от `center` до `id` (новая часть продления C–K) со стилем
`aux`/`dashed`. Исходный P–C уже есть в base как данное.

**Почему не ломает другие случаи:** эмит только для `reflect_point` (центральная
симметрия, продление), не для `reflect_point_over_line` (осевая симметрия, там нет
продления по прямой). Новый сегмент ссылается на существующие точки (`center` из base,
`id` только что создан).

---

## E11 — segment/line/ray пере-диктован как aux → пунктир поверх данного

**Файл:** `services/aux_compiler.py`, функция `compile_solver_aux` (ветка
`op in (segment, line, ray)`), + реестр `base_seg_pairs` у `base_ids`.

**Симптом:** на задаче о прямом угле solver в шаге 1 диктует «проведём медиану
AM» как `segment [A,M]`, хотя AM уже есть в base. E8 покрывал только
`altitude`/`median`/`angle_bisector` (по `foot_id`), не plain segment. Без E11
пунктирная aux-копия AM ложится поверх сплошного данного → медиана выглядит
как «доп. построение».

**Фикс:** вычисляем множество неупорядоченных пар концов base-отрезков/линий
(`base_seg_pairs`). Если aux `segment`/`line`/`ray` имеет ту же пару концов, что
базовый отрезок, — пропускаем как `FULFILLED_BY_BASE:{op}:{p1}{p2}`.

**Почему не ломает другие случаи:** правило срабатывает только при точном
совпадении пары концов с существующим base-отрезком. Настоящие aux-продления
(напр. M-K из E9) имеют новую пару концов — не совпадают. Отчёт о потерях не
портится (`FULFILLED_BY_BASE` не считается потерей, как и `DUPLICATE_IN_BASE`).

---

## E10 — данное условие рисовалось как «доп. построение»

**Файл:** `services/base_normalizer.py`, новая функция `_enforce_base_style`.

**Симптом:** инвариант `figure_plan_validator` требует, чтобы `base.constructions`
не содержали `style=="aux"` или `dashed==true` (зарезервировано для aux). Но
`base_normalizer` этот инвариант НЕ обеспечивал. Если `base_planner` (или промпт)
помечал данное (медиана/высота/биссектриса из условия) как `style:aux dashed`, оно
проходило до рендера и попадало в легенду «доп. построение» (пунктир), хотя это часть
условия задачи. Медиана BM в задаче о параллелограмме была пунктирной — пользователь
это заметил.

**Фикс:** `normalize_base_plan` прогоняет все base-построения через
`_enforce_base_style`: принудительно `style="base"`, `dashed=False`,
`visual_role="base"`. Все ранние возвраты тоже маршрутизированы через неё.
Чисто разделяет: **данное = solid («основное»), aux = dashed («доп. построение»)**.

**Почему не ломает другие случаи:** base-план по определению — только данное условие.
Стиль base/solid для него семантически верен. Aux-стили (`aux`/`key_point`/`target_circle`)
проставляет `compile_solver_aux` — он их не трогает.

---

## Проверка фиксов

```
python tests/test_solver_aux_regressions.py   # 5 тестов E8/E9/E10/E11 — ALL PASS
python tests/test_repro.py                     # старые регрессии E1–R6: 16/16 PASS
python tests/run_fixture.py                    # 13-14-15 incircle: 10/10 PASS
```

Итого 31 проверка, все зелёные. Фиксы E8/E9/E10/E11 не сломали старые кейсы
(incircle/E7, parallel_through/E5, touch-name collision и т.д.).

- `E10 base_style_normalized` — BM solid, 0 aux-styled в base.
- `E8 duplicate_median_skipped` — `FULFILLED_BY_BASE:median:M`, нет краша.
- `E9 line_extension_emits_segment` — отрезок M-K (aux/dashed) эмитирован.
- `E11 segment_duplicate_skipped` — segment AM не дублируется поверх данного.
- `false_statement_no_aux` — регресс: ложное утверждение → aux пустой, base нормализован.

## Реальный API-путь (routes/figures_generator.py)

Route УЖЕ содержит оба вызова (фиксы подхватываются заменой файлов):
- `normalize_base_plan(plan)` перед `compile_solver_aux` (стр. 1745) → E10.
- `engine.settings.auto_fit = FIGURE_AUTO_FIT_ENABLED` (стр. 1763),
  флаг = True по умолчанию (env `FIGURE_AUTO_FIT_ENABLED=true`, стр. 116–121) →
  aux-точки (K) не уходят за кадр.
- `compile_solver_aux(solver_result, base_plan)` (стр. 1850) → E8/E9/E11.

## Структура папки

```
formyla_final/
├── geometric_engine/      engine.py (legend+шрифты), geom.py, semantic_theme.py
├── services/              aux_compiler.py (E8,E9,E11), base_normalizer.py (E10),
│                          aux_ops.py, figure_plan_validator.py, llm_router.py,
│                          solution_generator.py
├── routes/                figures_generator.py (включить auto_fit в реальном пути)
├── data/figures/          solver_task.txt (промпт solver'а)
├── tests/                 test_solver_aux_regressions.py + fixtures/
├── tools/                 solver_only.py (DeepSeek runner), render_example.py, verify_fixes.py
├── base_planner_prompt.txt
├── PATCH_SUMMARY.md       (этот файл)
└── ROO_PROMPT.md          инструкция для Roo
```

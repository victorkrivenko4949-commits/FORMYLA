# ROO_PROMPT v2 — инструкция по укладке фиксов ФОРМУЛА (E8–E12 + P22/P23)

## Задача

Разложить исправленную папку `formyla_final_v2/` в проект ФОРМУЛА так, чтобы
конвейер `base_planner → solver (DeepSeek v4-pro) → compile_solver_aux →
merge_base_aux → geometric_engine` работал со всеми фиксами, и все регрессионные
тесты проходили.

## Состав фиксов

| ID  | Файл | Что делает |
|-----|------|-----------|
| E8  | `services/aux_compiler.py` | solver пере-диктует данное (altitude/median/angle_bisector с foot_id уже в base) → `FULFILLED_BY_BASE`, без краша |
| E9  | `services/aux_compiler.py` | `line_extension` → `reflect_point` эмитит видимый пунктирный отрезок продления `aux_ext_*` |
| E10 | `services/base_normalizer.py` | `_enforce_base_style`: всё данное = `style="base"`, `dashed=False` |
| E11 | `services/aux_compiler.py` | segment/line/ray пере-диктован как aux с той же парой концов → `FULFILLED_BY_BASE` |
| E12 | `geometric_engine/engine.py` | защита от вырожденного отрезка (совпадающие точки не роняют весь aux-рендер) |
| P22 | `data/figures/base_planner_task.txt` | правило 22: середина медианы ставится на ПРАВИЛЬНОЙ стороне |
| P23 | `data/figures/base_planner_task.txt` | правило 23: стороны треугольника/четырёхугольника = `segment`, не `line`/`ray` |
| v7  | `routes/figures_generator.py` | `_BASE_PLANNER_PROMPT_VERSION = "base-planner-v7"` (инвалидирует кэш планов) |

## Маппинг formyla_final_v2/ → проект

| Файл из архива | Куда в проекте ФОРМУЛА |
|---|---|
| `services/aux_compiler.py` | `services/aux_compiler.py` (ЗАМЕНИТЬ) |
| `services/base_normalizer.py` | `services/base_normalizer.py` (ЗАМЕНИТЬ) |
| `services/aux_ops.py` | `services/aux_ops.py` (сверить) |
| `services/figure_plan_validator.py` | `services/figure_plan_validator.py` (сверить) |
| `services/llm_router.py` | `services/llm_router.py` (сверить) |
| `services/solution_generator.py` | `services/solution_generator.py` (сверить) |
| `geometric_engine/engine.py` | `geometric_engine/engine.py` (ЗАМЕНИТЬ — E12) |
| `geometric_engine/geom.py` | `geometric_engine/geom.py` (сверить) |
| `geometric_engine/semantic_theme.py` | `geometric_engine/semantic_theme.py` (сверить) |
| `routes/figures_generator.py` | `routes/figures_generator.py` (ЗАМЕНИТЬ — v7) |
| `data/figures/solver_task.txt` | `data/figures/solver_task.txt` (НЕ МЕНЯТЬ — контракт solver) |
| `data/figures/base_planner_task.txt` | `data/figures/base_planner_task.txt` (ЗАМЕНИТЬ — P22/P23) |
| `data/figures/*_task.txt` (остальные) | `data/figures/` (сверить) |
| `tests/*`, `tests/fixtures/*` | `tests/` (положить) |
| `tools/*` | `tools/` (положить) |
| `PATCH_SUMMARY.md`, `ROO_PROMPT.md`, `_MANIFEST.txt` | корень |

## Порядок укладки

1. `services/aux_compiler.py` + `services/base_normalizer.py` (основные фиксы).
2. `geometric_engine/engine.py` (E12).
3. `routes/figures_generator.py` (v7) + `data/figures/base_planner_task.txt` (P22/P23).
4. Остальное.

## Проверки

```
python tests/test_solver_aux_regressions.py   # 5/5 PASS
python tests/test_repro.py                    # 16/16 PASS
python tests/run_fixture.py                   # 10/10 PASS
```

## Критерии готовности

- [ ] Все тесты PASS (5/5 + 16/16 + 10/10).
- [ ] `aux_compiler.py` содержит E8 (`FULFILLED_BY_BASE`), E9 (`aux_ext_`), E11 (`base_seg_pairs`).
- [ ] `base_normalizer.py` содержит `_enforce_base_style` (E10).
- [ ] `engine.py` содержит защиту от вырожденного отрезка (E12).
- [ ] `base_planner_task.txt` содержит правила 22 и 23.
- [ ] `_BASE_PLANNER_PROMPT_VERSION = "base-planner-v7"`.
- [ ] Перед `compile_solver_aux` вызывается `normalize_base_plan`; рендер с `auto_fit=True`.

## Чего НЕ делать

- НЕ менять `data/figures/solver_task.txt` (контракт solver'а).
- НЕ править вывод DeepSeek — фиксы детерминированные, на уровне компилятора/нормализатора/промпта base_planner.
- НЕ удалять существующие тесты/фикстуры (incircle, parallel, touch-name) — это регрессии прошлых сессий.

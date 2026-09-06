# CH26 отчёт — инцидентность точек на окружности

## Итог: ПОЛУЧИЛОСЬ ✅

После переключения на прямой DeepSeek API (`FIGURE_DISABLE_NOVITA=1`) и фикса
валидатора, живой прогон подтвердил работу инцидентности.

## Живая перепроверка (6 задач, run4)

`python scripts/ch26_probe.py` → [`output/ch26/probe_results.json`](output/ch26/probe_results.json)

| task_uid | inscribed | point_on_circle | incidences | inc_passed | max_dev(px) | status |
|---|---|---|---|---|---|---|
| GEN-L123-w2_63_s6-e60cb48e7a | 1 | 0 | 0 | 1 | 0.000000 | **done** |
| GEN-L123-w2_92_s4-2faec78478 | 1 | 0 | 6 | 1 | 0.000000 | failed |
| GEN-L123-par7_s2-90fb8853c0f | 1 | 1 | 4 | 1 | 0.000000 | **done** |
| GEN-L123-w2_100_s5-12e4ca2ae | 1 | 0 | 0 | 1 | 0.000000 | **done** |
| GEN-L123-w2_18_s3-083bf3a56f | 1 | 0 | 6 | 1 | 0.000000 | failed |
| GEN-L123-w2_74_s6-b4a2c2ea09 | 1 | 1 | 5 | 1 | 0.000000 | **done** |

- **4/6 задач → `done`** с `max_dev = 0.000000` (все вершины строго на окружности).
- LLM реально использовал `inscribed_polygon` (4 задачи) и `point_on_circle`
  (2 задачи) — промпт FIX5 сработал.
- 2 задачи упали на **старой, не связанной с инцидентностью** проверке
  `Проверка 3 (расстояние): точки 'O' и 'M'/'P' слишком близко (0.0 < 8.0)` —
  LLM поставил две разные точки в одно место. Это предсуществующий дефект
  дегенеративных координат, а не новая инцидентность.

## SVG

Сгенерированы 4 base-SVG в [`output/ch26/svg/`](output/ch26/svg):
`..._63_s6`, `..._par7_s2`, `..._100_s5`, `..._74_s6`.

## Исправленные файлы

| Файл | Изменение |
|---|---|
| [`geometric_engine/engine.py`](geometric_engine/engine.py) | FIX1 `point_on_circle`, FIX2 `inscribed_polygon`, FIX3 `INCIDENCE_VIOLATED` + `incidences` |
| [`geometric_engine/CONSTRUCTIONS.md`](geometric_engine/CONSTRUCTIONS.md) | Документация новых операций |
| [`services/figure_validator.py`](services/figure_validator.py) | Регистрация типов + **вершины `inscribed_polygon` в `declared_ids`** (иначе segment падал «dangling reference») |
| [`services/figure_plan_validator.py`](services/figure_plan_validator.py) | FIX4 `MISSING_INCIDENCE` + `_declared_ids` |
| [`data/figures/base_planner_task.txt`](data/figures/base_planner_task.txt) | FIX5 раздел инцидентности + примеры |
| [`tests/test_ch26_incidence.py`](tests/test_ch26_incidence.py) | 13 тестов |
| [`scripts/ch26_probe.py`](scripts/ch26_probe.py) | Живой прогон (Novita отключён) |

## Тесты

- [`tests/test_ch26_incidence.py`](tests/test_ch26_incidence.py): **13 passed**.
- Полный регресс: **113 passed** (engine + engine_ch6 + ch15 + ch19 + ch22 + ch23 + ch26).

## Ключевая находка в ходе отладки

Первоначальный живой прогон выявил **баг интеграции**: `validate_figure_json`
не регистрировал вершины `inscribed_polygon` как объявленные точки, из-за чего
последующие `segment` падали с «dangling reference» → `constructions[3..10]`.
Исправлено добавлением вершин в `declared_ids` (как в `figure_validator.py`,
так и в `figure_plan_validator._declared_ids`).

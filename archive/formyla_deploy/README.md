# FORMYLA — патч AUX_DROPPED (пакет для деплоя)

Содержит исправленные файлы, диффы, тесты и отчёт по багу «GPT генерит решение с доп. построением, а оно не появляется».

## Структура

```
formyla_deploy/
├── README.md                       ← этот файл
├── ROO_PROMPT.md                   ← промпт для Roo (скопировать в новый диалог)
├── fixed/                          ← файлы, которые надо положить в проект
│   ├── figures_generator.py        → routes/figures_generator.py (Flask-блюпринт)
│   ├── engine.py                   → geometric_engine/engine.py
│   └── schema.json                 → data/figures/schema.json (или где у вас схема)
├── diffs/                          ← ровно те же правки в виде unified diff
│   ├── figures_generator.diff
│   ├── engine.diff
│   └── schema.diff
├── tests/                          ← самопроверка движка (только stdlib)
│   ├── test_engine_incircle.py
│   └── test_engine_extras.py
└── docs/
    ├── AUDIT_REPORT.md             ← полный отчёт по аудиту
    └── AUX_DROPPED_DIAGNOSIS.md    ← ранняя диагностика узкого места
```

## Что именно исправлено

1. **`figures_generator.py`** — `_run_solver_aux_job`, стадия `visual_check` (≈строки 1895–1955). Сделана симметрия с base-веткой: HARD-коды роняют aux, SOFT (`LABEL_COLLISION`, `TICK_OVERLAP`, `LABEL_OVERLAP_ANGLE` и т.п. косметика) — только предупреждение. Добавлено `_record_stage` (теперь причина видна в UI и БД). Исключения не проглатываются молча. Заполняется `job.aux_fail_reason` с конкретными кодами.
2. **`schema.json`** — enum типов расширен с 54 до 62. Добавлены `inscribed_polygon`, `midpoint_mark`, `parallel_line`, `parallel_mark`, `perpendicular_mark`, `point_on_circle`, `reflect_point`, `rotate_point` и описания их параметров. Раньше aux-планы с этими типами отбраковывались валидатором ДО движка.
3. **`engine.py`** — `circle_center_radius` (строка ≈821). Добавлен синоним `radius_from`. При отсутствии радиуса и при r ≤ EPS теперь `ConstructionError`, а не тихая r=1. Устраняет ложные `INCIDENCE_VIOLATED` на incircle-цепочках.

## Как развернуть

1. Скопируйте три файла из `fixed/` на их места в проекте (пути — в комментарии сверху этого README).
2. Прогоните тесты:
   ```
   python3 tests/test_engine_incircle.py
   python3 tests/test_engine_extras.py
   ```
   Оба должны напечатать по несколько строк `... OK`. Тесты используют только stdlib, никаких зависимостей.
3. Задеплойте на Render.
4. Проверьте на живой задаче с incircle-условием (том самом, где aux пропадал). В истории (`figures_history`) теперь должна быть строка стадии `visual_check` с `error_codes`, `label_collisions`, `visual_score`.
5. Если aux всё ещё пропадёт — `job.aux_fail_reason` теперь содержит JSON `{"hard_codes": [...], "hard_errors": [...]}`. Это уже точечная диагностика.

## Что осталось за пределами патча

В бандл не были приложены сервисы `visual_audit.py`, `aux_compiler.py`, `aux_usefulness.py`, `figure_completeness_audit.py`, `aux_ops.py`, `solution_generator.py`, `llm_router.py`, `figure_plan_validator.py`, `answer_verifier.py`, `condition_coverage.py`. Мои патчи защищают вызывающий код и приводят к явным ошибкам, но если внутри `visual_audit.py` неверно классифицируются коды или `aux_compiler.py` посылает ещё какой-то незнакомый синоним радиуса — потребуется отдельный проход по этим файлам.

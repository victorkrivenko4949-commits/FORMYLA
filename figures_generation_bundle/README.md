# FORMYLA — Генерация геометрических чертежей (полный бандл)

Этот бандл содержит ВСЁ, что связано с генерацией чертежей к задачам по геометрии:
промпты, модели, цепочку генерации, компилятор доп. построений, движок, визуальный
аудит и batch-скрипты.

## Структура бандла

```
figures_generation_bundle/
├── README.md                  ← этот файл (цепочка генерации)
├── prompts/                   ← ВСЕ промпты для LLM
│   ├── base_planner_task.txt      базовый чертёж (только условие)
│   ├── aux_planner_task.txt       доп. построение (старый однопроходный)
│   ├── aux_extractor_task.txt     экстрактор шагов построения
│   ├── reasoner_task.txt          legacy reasoner
│   ├── solver_task.txt            решатель (solver) — возвращает решение + aux_constructions
│   └── figure_auditor_task.txt    аудит чертежа
├── engine/                    ← геометрический движок
│   ├── engine.py                  execute_construction + render_svg + GeometricEngine
│   ├── geom.py                    математика (incenter, bisector, foot, intersect...)
│   ├── schema.json                JSON-схема плана
│   ├── CONSTRUCTIONS.md           документация всех типов построений
│   └── semantic_theme.py          семантические цвета
├── services/                  ← оркестрация + компилятор + аудиты
│   ├── llm_router.py              маршрутизация моделей (OdiRouter/DeepSeek/Novita)
│   ├── aux_ops.py                 закрытый словарь AUX_ALLOWED_OPS
│   ├── aux_compiler.py            КОМПИЛЯТОР solver-построений в план движка
│   ├── aux_templates.py           (устарел, не используется в solver_aux)
│   ├── aux_usefulness.py          численная оценка полезности доп. построения
│   ├── solution_generator.py      solve_problem() — вызов роли solver
│   ├── visual_audit.py            пост-рендер аудит (labels/marks/collisions)
│   ├── figure_completeness_audit.py  проверка полноты (Gemini vision)
│   ├── figure_plan_validator.py   merge_base_aux + валидация плана
│   ├── figure_plan_schemas.py     схемы планов
│   ├── figure_validator.py        валидатор фигур
│   ├── condition_coverage.py      покрытие условия
│   ├── answer_verifier.py         проверка ответа
│   └── solution_check_pipeline.py проверка решения
├── routes/
│   └── figures_generator.py       Flask-роуты + очередь + pipeline
├── templates/
│   ├── figures_generate.html      страница генерации
│   ├── figures.html               страница чертежей
│   └── figures_history.html       история генераций
└── batch/                     ← массовая генерация
    ├── _enqueue_geometry_missing.py  ставит batch-задачи в очередь
    ├── _autopilot.py                автопилот batch-генерации
    ├── run_batch.py                 запуск партии
    ├── attach_figures.py            прикрепление готовых чертежей к задачам
    ├── resume_geometry.py           до-генерация пропущенных
    ├── export_svg.py                экспорт SVG
    └── load_dataset.py              загрузка датасета
```

## Цепочка генерации (главный режим: `solver_aux`)

Функция [`_run_solver_aux_job()`](routes/figures_generator.py:1677) в
[`routes/figures_generator.py`](routes/figures_generator.py) реализует полный
конвейер. Порядок стадий:

```
1. base_thinking     → Gemini (base_planner_task.txt) строит чертёж по условию
2. base_drawing      → GeometricEngine.build_with_retry()
3. coverage_check    → condition_coverage.py (все ли объекты условия отрисованы)
4. solving           → solver (solver_task.txt, модель gpt-5.4 через OdiRouter)
                        возвращает JSON: { steps, aux_needed, aux_constructions, answer }
5. answer_verify     → answer_verifier.py (сверка ответа)
6. aux_compile       → aux_compiler.py: compile_solver_aux()
                        превращает aux_constructions GPT в план движка
7. aux_usefulness    → aux_usefulness.py: evaluate_usefulness()
                        численно решает, полезно ли построение
8. aux_drawing       → GeometricEngine.build() на merged = base + aux
9. visual_check      → visual_audit.py: audit_rendered_figure()
10. completeness_check → figure_completeness_audit.py (Gemini vision)
11. done             → сохраняем base_svg + aux_svg
```

Если на шагах 7/8/9 построение признаётся бесполезным или падает — вызывается
[`_drop_aux()`](routes/figures_generator.py:1662), и пользователь получает только
базовый чертёж (голый треугольник) со статусом `AUX_DROPPED`.

## Модели (llm_router.py)

| Роль       | Модель           | Провайдер               |
|------------|------------------|-------------------------|
| base       | gemini-3.7-flash | OdiRouter                |
| aux        | gemini-3.7-flash | OdiRouter                |
| audit      | gemini-3.7-flash | OdiRouter                |
| solver     | gpt-5.4          | OdiRouter                |
| repair     | deepseek-v4-pro  | DeepSeek direct          |
| solver_shadow | gemini-3.7-flash | OdiRouter            |

Thinking-политика: solver = `disabled` (GPT отвечает быстро ~24s); остальные
роли — по `ROLE_DEFAULT_THINKING`.

## Контракт solver (что должен вернуть GPT)

`solver_task.txt` требует JSON вида:

```json
{
  "steps": [{"no": 1, "text": "..."}],
  "aux_needed": true,
  "aux_constructions": [
    {"op": "angle_bisector", "points": ["A","B","C"], "quote": "...", "step_no": 1, "purpose": "..."}
  ],
  "answer": {"value": null, "unit": null, "exact": null, "is_numeric": false}
}
```

Допустимые `op` — см. [`aux_ops.py`](services/aux_ops.py:16) (`AUX_ALLOWED_OPS`).

## Компилятор aux (aux_compiler.py)

`compile_solver_aux()` берёт `aux_constructions` и мапит их в типы движка.

**Особый случай — вписанная окружность.** GPT описывает её как цепочку
«биссектрисы → пересечение O → перпендикуляры → окружность», но не даёт
стабильных id линий. Поэтому [`_recognize_incircle()`](services/aux_compiler.py:340)
распознаёт эту цепочку (≥2 биссектрис + окружность) и собирает нативный план:
- `incenter` (O из трёх вершин)
- три `line` (биссектрисы A→O, B→O, C→O)
- три `altitude` (перпендикуляры из O на BC/CA/AB, foot_id = A₁/B₁/C₁)
- `circle_center_radius` (окружность с центром O и радиусом до A₁)

## Известная проблема (текущий баг)

`aux_status = AUX_DROPPED`, `aux_dropped_reason = aux_visual_check_failed`:
движок СТРОИТ корректный aux-чертёж (центр O, точки касания, окружность с
настоящим радиусом), но [`audit_rendered_figure()`](services/visual_audit.py:557)
отбрасывает его на этапе визуальной проверки. Из-за этого пользователь видит
только базовый треугольник. Модель и компилятор отрабатывают верно — проблема
локализована в пост-аудите.

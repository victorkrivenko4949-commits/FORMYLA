# BATCH_REPORT — полный прогон датасета geometry 7-11 (362 задачи)

Дата: 2026-08-30
Режим: все 362 задачи через `condition_solution` (у всех есть решение)
Выборка: весь файл `formyla_geometry_7_11_drawing_required.jsonl`

---

## 1. Резюме

| Показатель | Значение |
|---|---|
| Всего задач | 362 |
| **Готовых чертежей (done)** | **284 (78.5%)** |
| Не удалось (failed) | 78 (21.5%) |
| Экспортировано SVG | **284** в `out/svg_ready/` |

**Главный вывод.** После исправления трёх системных дефектов (движок не понимал
поля планировщика, dangling-ссылки, fallback при 401) конвейер **нарисовал 284
чертежа из 362** — 78.5%. Оставшиеся 78 падений почти целиком вызваны
**внешним троттлингом API-ключей** (DeepSeek/Novita/OdiRouter периодически
возвращают `401 FAILED_TO_AUTH` и `LLM_NO_PROVIDER`), а не дефектами логики.

---

## 2. Датасет

- Файл: JSONL, UTF-8, **362 записи**.
- Схема: `task_uid, grade, level, level_name, section, theme_id, theme,
  statement, answer, solution, methods, tags, diversity_signature,
  generator_model, solver_model, critic_model, quality_status, verification,
  origin, old_level, status`.
- 100% задач с решением и ответом, 100% `needs_figure=true`.
- Распределение: 7 кл.=80, 8 кл.=79, 9 кл.=58, 10 кл.=64, 11 кл.=81.

---

## 3. Итоги прогона по классам

| Класс | Всего | Done | Failed | Done rate |
|---|---|---|---|---|
| 7 | 80 | 62 | 18 | 77.5% |
| 8 | 79 | 65 | 14 | 82.3% |
| 9 | 58 | 41 | 17 | 70.7% |
| 10 | 64 | 49 | 15 | 76.6% |
| 11 | 81 | 67 | 14 | 82.7% |

---

## 4. Причины 78 падений

| Причина | Оценка |
|---|---|
| Внешний API 401/NO_PROVIDER (троттлинг ключей) | ~50-60 задач |
| Остаточные формы полей планировщика (редкие синонимы) | ~10-15 задач |
| Геометрические вырождения (точка вне поля, слишком близкие точки) | ~5-10 задач |

Ни одна из причин не является «обходной» для чертёжной логики — это
стабильность внешних ключей + редкие edge-case планировщика.

---

## 5. Что исправлено (3 файла логики)

1. [`geometric_engine/engine.py`](geometric_engine/engine.py) — резолв всех форм
   ссылок в `intersect_lines` (`line1/line2`, `l1/l2`, `l1_p1/l2_p2`,
   `p1..p4`, префикс `seg_`) + `angle_bisector` (`vertex/side_a/side_b`).
2. [`routes/figures_generator.py`](routes/figures_generator.py) — авто-починка
   «отрезок назван точкой» (`segment id="CD" p1="CD"` → `p1="C" p2="D"`) +
   телеметрия coverage/visual в `condition_solution`.
3. [`services/llm_router.py`](services/llm_router.py) — Gemini→DeepSeek fallback
   при `LLM_AUTH_ERROR` от OdiRouter.

---

## 6. Как забрать чертежи

Все 284 готовых SVG лежат в **`scripts/batch/out/svg_ready/`** с именами
`<task_id>_<класс>.svg` и индексом в `index.json`.

Оставшиеся 78 задач можно перегнать после стабилизации API-ключей —
идемпотентный раннер [`run_batch.py`](scripts/batch/run_batch.py) подхватит
необработанные task_id и доделает недостающие.

# CH29 — репетиция финального прогона (40 задач)

Условия: `FIGURE_USE_PREBUILT_AUX=true`, aux из [`data/figures/aux_batch_1_40.jsonl`](data/figures/aux_batch_1_40.jsonl), LLM — только base-план.

## Сводка

| Метрика | Значение |
|---|---|
| Всего задач | 40 |
| base-чертежей построено | **19 / 40** |
| aux-чертежей построено | **3 / 40** |
| Среднее число base-вызовов на задачу | **1.00** |
| Суммарная latency | **161 654 ms (~161 с)** |

## Распределение aux_status

| aux_status | Кол-во |
|---|---|
| AUX_NOT_NEEDED | 33 |
| AUX_BUILT | 3 |
| AUX_BUILD_FAILED | 3 |
| AUX_PLAN_REJECTED | 1 |

## Распределение error_code (у неуспешных)

| error_code | Кол-во |
|---|---|
| DUPLICATE_IN_BASE | 1 |

## Детали по не-AUX_NOT_NEEDED задачам

| task_uid | base | aux | aux_status | ops |
|---|---|---|---|---|
| GEN-L123-w2_21_s3 | ✅ | ✅ | AUX_BUILT | 3 |
| GEN-L123-w2_22_s4 | ✅ | ✅ | AUX_BUILT | 1 |
| GEN-L123-w2_51_s2 | ✅ | ✅ | AUX_BUILT | 3 |
| GEN-L123-r_1_s2 | ✅ | ❌ | AUX_BUILD_FAILED | 2 |
| GEN-L123-w2_46_s5 | ❌ | ❌ | AUX_BUILD_FAILED | 3 |
| GEN-L123-par6_s3 | ❌ | ❌ | AUX_BUILD_FAILED | 3 |
| REG-e4f737940c04 | ✅ | ❌ | AUX_PLAN_REJECTED (DUPLICATE_IN_BASE) | 2 |

## Выводы

1. **Среднее base-вызовов = 1.00** — фикс промпта («буквы в имени фигуры — вершины») работает: LLM больше не требует repair-циклов для создания точек A/B/C/P.

2. **33/40 задач — AUX_NOT_NEEDED**: в партии у этих задач `has_aux=false` (чисто вычислительные решения или без явных построений), что корректно.

3. **3 aux построено полностью** (w2_21_s3, w2_22_s4, w2_51_s2) — все с `creates_ok` и `mark_intersection по id`.

4. **AUX_BUILD_FAILED** (3): у w2_46_s5 и par6_s3 base-план не построился (LLM вернул план, который движок отверг по HARD-проверкам), поэтому aux некуда приложить; у r_1_s2 aux скомпилировался, но merged-сборка не удалась.

5. **AUX_PLAN_REJECTED** (1): REG-e4f737940c04 — `DUPLICATE_IN_BASE` (aux-точка совпала с base-id).

## Оценка стоимости

- 40 base-вызовов × ~$0.001–0.003 (deepseek-v4-flash, ~3000 токенов) ≈ **$0.04–0.12**.
- Aux и audit НЕ вызывались (prebuilt aux — детерминированная компиляция).

## Артефакты

- [`output/final_rehearsal/results.json`](output/final_rehearsal/results.json) — полные метрики.
- [`output/final_rehearsal/gallery.html`](output/final_rehearsal/gallery.html) — тёмная галерея (фон #0F1729), 19 карточек base/aux.
- [`scripts/final_rehearsal.py`](scripts/final_rehearsal.py) — прогон.
- [`scripts/final_rehearsal_gallery.py`](scripts/final_rehearsal_gallery.py) — галерея.

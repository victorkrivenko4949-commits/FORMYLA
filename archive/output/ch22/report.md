# CH22 — Отчёт пилота

- Обработано задач: **98** (done=55, failed=43).
- Общая стоимость: **$0.4123**.

## 1. done / failed по solution_style

| style | done | failed |
|---|---|---|
| angle_chase | 8 | 8 |
| area_ratio | 9 | 6 |
| complex | 3 | 1 |
| constructive | 24 | 21 |
| coordinate | 8 | 6 |
| trig | 3 | 1 |

## 2. Распределение aux_status (все задачи)

| aux_status | count |
|---|---|
| (пусто) | 38 |
| AUX_NOT_NEEDED | 37 |
| AUX_ROLLED_BACK | 10 |
| AUX_PLAN_REJECTED | 5 |
| AUX_BUILD_FAILED | 4 |
| AUX_BUILT | 4 |

## 3. aux_status для constructive

| status | count | доля |
|---|---|---|
| AUX_BUILT | 3 | 6.7% |
| AUX_ROLLED_BACK | 6 | 13.3% |
| AUX_NOT_NEEDED | 11 | 24.4% |
| AUX_PLAN_REJECTED | 5 | 11.1% |
| AUX_BUILD_FAILED | 4 | 8.9% |

## 4. aux_status для coordinate/complex/trig

| status | count | доля |
|---|---|---|
| AUX_NOT_NEEDED | 12 | 54.5% |
| AUX_BUILT | 0 | 0.0% |
| AUX_ROLLED_BACK | 2 | 9.1% |
| AUX_PLAN_REJECTED | 0 | 0.0% |
| AUX_BUILD_FAILED | 0 | 0.0% |

## 5. Топ error_code и aux_fail_codes

| error_code | count |
|---|---|
| OTHER | 43 |

| aux_fail_codes | count |
|---|---|
| {"rollback_after_codes": ["AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION"]} | 6 |
| {"rollback_after_codes": ["AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION" | 4 |
| "INVALID_REFERENCE"]} | 4 |
| {"codes": ["AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION"] | 3 |
| {"engine_violations": ["[parallel_line] 'aux_line_DK': Неизвестный тип построения: parallel_line"]} | 1 |
| "last_errors": ["AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION: aux[0] 'aux_line_l1' (line) must have an explicit construction action in solution_evidence.quote" | 1 |
| "AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION: aux[1] 'aux_line_l2' (line) must have an expli | 1 |
| {"engine_violations": ["[ref] 'aux_seg_CE': Точка 'E' не найдена"]} | 1 |
| "last_errors": ["AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION: aux[1] 'seg_AM_prime' (segment) must have an explicit construction action in solution_evidence.quote" | 1 |
| "AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION: aux[2] 'seg_M_prime_N' (segment) must have | 1 |
| {"engine_violations": ["[angle_bisector] 'aux_bisector_BD': 'p1'"]} | 1 |
| "last_errors": ["AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION: aux[1] 'aux_seg_AA_prime' (segment) must have an explicit construction action in solution_evidence.quote" | 1 |
| "AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION: aux[2] 'aux_seg_A_prime_C' (segment) m | 1 |
| {"codes": ["INVALID_REFERENCE"] | 1 |
| "last_errors": ["INVALID_REFERENCE: aux[0] references unknown id 'N'"]} | 1 |

## 6. Latency (ms)

- p50=65060.3, p95=525980.8, max=1173787.2

## 7. Стоимость

- Общая: $0.4123; средняя успешного: $0.0041

## 8. Задачи с soft_warnings

- 0

## 9. Прогноз на 354 задачи

- Средняя стоимость задачи: $0.0042; прогноз 354: $1.49
- Средняя latency: 158265 ms; прогноз времени (2 workers): 467 мин

## 10. Ручная выборка 15 задач с самым интересным aux

| task_uid | aux_status | aux_ops | aux_reason |
|---|---|---|---|
| GEN-L123-w2_110_s4-6 | AUX_BUILD_FAILED | 4 | Для применения теоремы Пифагора в прямоу |
| GEN-L123-w2_71_s6-5a | AUX_BUILD_FAILED | 3 | Для применения теоремы Фалеса и свойства |
| GEN-fill_0440 | AUX_BUILD_FAILED | 3 | Для доказательства соотношения AC² = AB· |
| GEN-L123-w2_51_s2-3a | AUX_BUILT | 2 | В решении проводится диагональ AC и ввод |
| GEN-L123-w2_13_s5-f8 | AUX_BUILD_FAILED | 2 | Для построения равностороннего треугольн |
| GEN-L123-w2_123r_s2- | AUX_BUILT | 1 | Для построения точки D', центрально симм |
| GEN-L123-w2_22_s4-a9 | AUX_BUILT | 1 | Для применения свойств равнобедренных тр |
| 45fb38db75e6c556939a | AUX_BUILT | 1 | В решении вводится вспомогательная точка |
| a065b9a960c366e6c6d1 | AUX_ROLLED_BACK | 0 |  |
| REG-93afda65f3ff830b | AUX_ROLLED_BACK | 0 |  |
| 714cc0aa0592b86f3be9 | AUX_ROLLED_BACK | 0 |  |
| GEN-L123-par35_s2-d0 | AUX_ROLLED_BACK | 0 |  |
| 98cdb758e6bec2caed50 | AUX_ROLLED_BACK | 0 |  |
| PILOT2-fill_0437 | AUX_ROLLED_BACK | 0 |  |
| 2af48b0cfb80139f3922 | AUX_ROLLED_BACK | 0 |  |

(скопировано 15 задач с aux в manual_review/)

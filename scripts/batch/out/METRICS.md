# METRICS — пакетный прогон geometry 7-11

## 4.1 Общее

| Метрика | Значение |
|---|---|
| Всего задач | 100 |
| Done | 85 |
| Failed | 14 |
| Timeout | 1 |
| First-pass success rate | 85.9 |
| Median total_ms | 487.90 |
| p90 total_ms | 715.00 |
| p99 total_ms | 744.74 |
| Cost per done job (USD) | 0.01 |
| Cost per done job (₽, курс 86) | 0.64 |

## 4.2 По группам (A=с решением, B=без решения)

| Метрика | GROUP_A (condition_solution) | GROUP_B (solver_aux) |
|---|---|---|
| Всего | 50 | 50 |
| Done | 41 | 44 |
| Failed | 9 | 5 |
| Timeout | 0 | 1 |
| Success rate, % | 82.00 | 88.00 |
| Median ms | 441.60 | 508.30 |
| p90 ms | 660.20 | 727.37 |
| p99 ms | 713.12 | 746.38 |
| Cost/done USD | 0.02 | 0.00 |
| Cost/done ₽ | 1.33 | 0.01 |

## 4.3 По классам 7-11

| Класс | Всего | Success % | Median coverage | Median visual | Median ms | Aux needed % |
|---|---|---|---|---|---|---|
| 7 | 20 | 90.00 | 0.90 | 1.00 | 89.65 | 11.10 |
| 8 | 20 | 100.00 | 1.00 | 0.82 | 388.10 | 15.00 |
| 9 | 20 | 65.00 | 0.90 | 1.00 | 501.50 | 0.00 |
| 10 | 20 | 90.00 | 0.90 | 0.95 | 584.70 | 27.80 |
| 11 | 20 | 80.00 | 1.00 | 1.00 | 718.85 | 31.20 |

Худший класс по success_rate: **9** (65.00%), лучший: **8** (100.00%).


## 4.4 Доп. построения

| Метрика | Значение |
|---|---|
| aux_from_template_rate, % | 12.90 |
| aux_from_solver_rate, % | 0.00 |
| aux_dropped_rate, % | 38.80 |
| median aux_usefulness | 0.25 |

Разбивка aux_dropped_reason:

| Причина | Кол-во |
|---|---|
| solver_failed | 18 |
| aux_useless | 10 |
| aux_visual_check_failed | 3 |
| aux_compile_empty | 2 |

Распределение template_id (какие шаблоны сработали):

| template_id | Кол-во |
|---|---|
| _t_midline | 8 |
| _t_altitude_from_right_angle | 4 |
| _t_extend_side_external_angle | 3 |
| _t_parallelogram_completion | 3 |
| _t_trapezoid_diagonal_parallel | 2 |
| _t_equal_segments_connect | 1 |
| _t_common_chord | 1 |
| _t_reflect_over_side | 1 |
| _t_bisector_perpendiculars | 1 |

## 4.5 Качество

| Метрика | Значение | Цель |
|---|---|---|
| answer_verified_rate, % | 0.00 | >= 85 |
| solver_accuracy, % | 100.00 | >= 85 |
| figure_correctness, % | 0.00 | = 100 |
| CONDITION_NOT_REALIZED (задач) | 2 | 0 |
| LABEL_CONTRADICTS_GEOMETRY (задач) | 10 | 0 |
| LABEL_COLLISION до автофикса | 4 | — |
| LABEL_COLLISION после автофикса | 0 | — |

## 4.6 По моделям и ролям

| Role | Provider | Model | Count | AVG latency_ms | AVG coverage | Cost USD | Fallback |
|---|---|---|---|---|---|---|---|
|  |  |  | 164 | — | 0.73 | 0.00 | 0 |
| audit | odirouter | gemini-3.7-flash | 4 | — | — | 0.03 | 0 |
| base | odirouter | gemini-3.7-flash | 47 | — | — | 0.61 | 0 |
| solver |  |  | 18 | 5174.10 | — | 0.00 | 0 |
| solver | deepseek_direct | deepseek-v4-pro | 2 | 16171.00 | — | 0.00 | 0 |

OdiRouter fallback: **0** раз.

## 4.7 Топ-20 кодов ошибок

| Код | Частота | Примеры task_id |
|---|---|---|
| MISSING_EQUALITY_MARK | 14 | GEN-L123-w2_113_s3-942529b2501721c4, GEN-fill_0455 |
| OTHER | 11 | GEN-fill_0445, GEN-fill_0444 |
| LABEL_CONTRADICTS_GEOMETRY | 10 | GEN-L123-w2_70_s1-027bc41c457effa4, NEW-DIFF-20260830-0260 |
| MISSING_NUMERIC_LABEL | 7 | GEN-fill_0435, GEN-fill_0442 |
| LLM_AUTH_ERROR | 7 | GEN-L123-par30_s6-13f9a9b43246dec4, 0756b2a7f7aba5161e48d270b4e2802660f52d2c612cae8cd21e9d136f136fb1 |
| MISSING_RIGHT_ANGLE_MARK | 6 | GEN-fill_0434, GEN-fill_0455 |
| LABEL_COLLISION | 4 | GEN-L123-w2_74_s6-354573336bdb150c, GEN-L123-w2_30_s3-3efa8f5779033fe7 |
| ENGINE_CONSTRAINT_VIOLATION | 4 | GEN-L123-par30_s4-995a85c7e54b2575, REG-4b14f342d2a6f7a6331ee49b |
| MARK_CONTRADICTS_GEOMETRY | 3 | a0ee656809c4774b33642fc249276be618dfa8e206641c023aea5bd2b4895f27, NEW-DIFF-20260830-0260 |
| MISSING_GIVEN_EQUALITY_MARK_STRICT | 2 | a0ee656809c4774b33642fc249276be618dfa8e206641c023aea5bd2b4895f27, GEN-fill_0551 |
| CONDITION_NOT_REALIZED | 2 | NEW-DIFF-20260830-0260, REG-1929514b7d4f8ca9dcbccd27 |
| LLM_NO_PROVIDER | 2 | REG-c6e04bf9de71d9be9198c6da, 0727644e4a863f93b6b1dfd4a51fe78f11702476b218ae8efa2a35503a5aca10 |
| MISSING_INCIDENCE | 1 | GEN-L123-w2_17_s1-d6b01886d1bafae5 |

## 3.3 Матрица сверки ответов (КЛЮЧЕВАЯ)

| solver vs dataset | measured vs dataset | Смысл | Кол-во |
|---|---|---|---|
| match | match | всё верно | 0 |
| match | mismatch | ЧЕРТЁЖ неверен (D1) | 1 |
| mismatch | match | solver ошибся, чертёж ок | 0 |
| mismatch | mismatch | двойная ошибка | 0 |

Ячейка «match/mismatch» — главный индикатор нерешённого D1: **1** задач.


## 5.1 Кластеры неудач (>= 3 по error_codes)

| Кластер (error_code) | Размер | Примеры task_id |
|---|---|---|
| LLM_AUTH_ERROR | 7 | GEN-L123-par30_s6-13f9a9b43246dec4, 0756b2a7f7aba5161e48d270b4e2802660f52d2c612cae8cd21e9d136f136fb1, GEN-L123-w2_17_s4-05942893facfd07a |
| ENGINE_CONSTRAINT_VIOLATION | 4 | GEN-L123-par30_s4-995a85c7e54b2575, REG-4b14f342d2a6f7a6331ee49b, RG2-86009593bcc90087dfe489f5 |

## 5.2 Корреляции success_rate

| Признак | Да | Нет |
|---|---|---|
| Наличие окружностей | 75.00 | 87.50 |
| LaTeX-разметка | 90.30 | 82.60 |
| Стереометрия | 100.00 | 84.20 |
| Задача на построение | 72.70 | 88.50 |
| Задача с параметром | — | 85.00 |
| Без числовых данных | 92.30 | 83.90 |

По длине условия: короткие (<=300) 85.20%, длинные (>300) 83.30%.

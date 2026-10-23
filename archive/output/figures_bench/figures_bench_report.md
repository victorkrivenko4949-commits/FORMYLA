# FIGURES benchmark CH18

- credits_before: 100
- credits_after: 95
- credits_spent: 5

## Сводная таблица

| task | mode | status | total_ms | llm_calls | fast | fallback | audit | has_aux | error_code |
|---|---|---|---|---|---|---|---|---|---|
| task1_no_aux | MODE_FAST | failed | 332962 | 4 | False | False | none | False | Модель не смогла создать корректный base-план. |
| task1_no_aux | MODE_TWO_CALL | failed | 263721 | 3 | False | False | none | False | Модель не смогла создать корректный base-план. |
| task2_altitude | MODE_FAST | done | 167826 | 3 | False | False | skipped | True | - |
| task2_altitude | MODE_TWO_CALL | done | 53941 | 2 | False | False | skipped | True | - |
| task3_circle_minimal | MODE_FAST | done | 65680 | 1 | True | False | skipped | True | - |
| task3_circle_minimal | MODE_TWO_CALL | failed | 263913 | 3 | False | False | none | False | LLM_NO_JSON |
| task4_explicit_segment | MODE_FAST | done | 79203 | 1 | True | False | skipped | True | - |
| task4_explicit_segment | MODE_TWO_CALL | failed | 255125 | 3 | False | False | none | False | Модель не смогла создать корректный base-план. |
| task5_gergonne | MODE_FAST | failed | 338086 | 4 | False | False | none | False | Модель не смогла создать корректный base-план. |
| task5_gergonne | MODE_TWO_CALL | failed | 272160 | 3 | False | False | none | False | LLM_NO_JSON |
| task6_nine_point | MODE_FAST | done | 218604 | 3 | False | False | skipped | False | - |
| task6_nine_point | MODE_TWO_CALL | failed | 325138 | 4 | False | False | none | False | LLM_NO_JSON |

## Качество

| task | mode | base_leak | mc_in_base | mc_in_aux | foot_id_ok | p_in_aux | dep_order_ok | roles_ok | colors_ok |
|---|---|---|---|---|---|---|---|---|---|
| task1_no_aux | MODE_FAST | - | False | False | False | False | True | True | True |
| task1_no_aux | MODE_TWO_CALL | - | False | False | False | False | True | True | True |
| task2_altitude | MODE_FAST | - | False | False | True | False | True | True | True |
| task2_altitude | MODE_TWO_CALL | - | False | False | True | False | True | True | True |
| task3_circle_minimal | MODE_FAST | - | False | False | False | False | True | True | True |
| task3_circle_minimal | MODE_TWO_CALL | - | False | False | False | False | True | True | True |
| task4_explicit_segment | MODE_FAST | - | False | True | False | False | True | True | True |
| task4_explicit_segment | MODE_TWO_CALL | - | False | False | False | False | True | True | True |
| task5_gergonne | MODE_FAST | - | False | False | False | False | True | True | True |
| task5_gergonne | MODE_TWO_CALL | - | False | False | False | False | True | True | True |
| task6_nine_point | MODE_FAST | - | False | False | False | False | True | True | True |
| task6_nine_point | MODE_TWO_CALL | - | False | False | False | False | True | True | True |

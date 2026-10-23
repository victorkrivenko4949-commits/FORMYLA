# CH15 smoke run

## task_a_altitude_foot

- job_id: 1
- status: done
- current_stage: done
- error_code: -
- base_model: deepseek-v4-flash
- aux_model: deepseek-v4-flash
- has_aux: True
- aux_reason: Для построения высоты и обозначения прямого угла.
- base_ops: ['free_point', 'free_point', 'free_point', 'triangle_arbitrary', 'equal_segments_mark', 'angle_label']
- aux_ops: ['altitude', 'right_angle_mark', 'point_label']
- base SVG bytes: 1953
- aux SVG bytes: 2537
- base counts: {'points': 3, 'lines': 2, 'circles': 0, 'texts': 4, 'strokes': ['#0f172a', '#D9E5F5', '#a0b8d8', '#c8d6e5']}
- aux counts: {'points': 4, 'lines': 3, 'circles': 0, 'texts': 5, 'strokes': ['#0f172a', '#73B6E6', '#D9E5F5', '#FFD166', '#a0b8d8', '#c8d6e5']}
- latency_s: 53.37
- credit_charged: True

## task_b_target_circle

- job_id: 2
- status: done
- current_stage: done
- error_code: -
- base_model: deepseek-v4-flash
- aux_model: deepseek-v4-flash
- has_aux: True
- aux_reason: Окружность с диаметром AB для доказательства равенства радиусов.
- base_ops: ['free_point', 'free_point', 'free_point', 'triangle_arbitrary', 'midpoint', 'right_angle_mark', 'midpoint_mark']
- aux_ops: ['circle_center_radius']
- base SVG bytes: 1903
- aux SVG bytes: 2017
- base counts: {'points': 4, 'lines': 1, 'circles': 0, 'texts': 4, 'strokes': ['#0f172a', '#D9E5F5', '#FFD166', '#a0b8d8', '#c8d6e5']}
- aux counts: {'points': 5, 'lines': 1, 'circles': 0, 'texts': 4, 'strokes': ['#0f172a', '#B7A2E8', '#D9E5F5', '#FFD166', '#a0b8d8', '#c8d6e5']}
- latency_s: 53.72
- credit_charged: True

## task_c_explicit_segment

- job_id: 3
- status: done
- current_stage: done
- error_code: -
- base_model: deepseek-v4-flash
- aux_model: deepseek-v4-flash
- has_aux: False
- aux_reason: -
- base_ops: ['free_point', 'free_point', 'free_point', 'triangle_arbitrary', 'midpoint', 'segment', 'equal_segments_mark']
- aux_ops: []
- base SVG bytes: 2037
- aux SVG bytes: 0
- base counts: {'points': 4, 'lines': 3, 'circles': 0, 'texts': 4, 'strokes': ['#0f172a', '#D9E5F5', '#a0b8d8', '#c8d6e5']}
- aux counts: {'points': 0, 'lines': 0, 'circles': 0, 'texts': 0, 'strokes': []}
- latency_s: 20.38
- credit_charged: True

## task_d_no_aux

- job_id: 4
- status: failed
- current_stage: base_thinking
- error_code: Модель не смогла создать корректный base-план.
- base_model: None
- aux_model: None
- has_aux: False
- aux_reason: -
- base_ops: []
- aux_ops: []
- base SVG bytes: 0
- aux SVG bytes: 0
- base counts: {'points': 0, 'lines': 0, 'circles': 0, 'texts': 0, 'strokes': []}
- aux counts: {'points': 0, 'lines': 0, 'circles': 0, 'texts': 0, 'strokes': []}
- latency_s: 456.52
- credit_charged: False

## SUMMARY

- done: 3
- failed: 1
- credits_before: 20
- credits_after: 17
- credits_spent: 3
- model_not_found_logs: 0
- repair_retries: []
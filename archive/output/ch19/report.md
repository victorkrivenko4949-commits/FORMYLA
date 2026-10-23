# CH19 — Итоговый отчёт пакетной генерации чертежей

> Пилот: 100 задач, workers=2, max-cost-usd=5. Провайдеры: Novita (недоступен по сети) → DeepSeek (fallback).


## 1. Инвентаризация файла

- Всего записей: **354** (все quality_status=APPROVE, все с solution).
- Длины statement: медиана 217.5, p90 424, max 1009.
- Длины solution: медиана 1348.0, p90 4995, max 13535.
- Распределение по grade: 10=63, 11=81, 7=77, 8=76, 9=57
- Распределение по level: 1=86, 2=88, 3=87, 4=93

## 2. Классификатор стилей (по всему файлу)

| style | количество |
|---|---|
| coordinate | 114 |
| constructive | 96 |
| unknown | 61 |
| area_ratio | 38 |
| angle_chase | 16 |
| trig | 15 |
| complex | 14 |

## 3. Результаты пилота (done/failed по style)

| style | done | failed |
|---|---|---|
| angle_chase | 1 | 15 |
| area_ratio | 0 | 1 |
| constructive | 4 | 41 |

## 3b. done/failed по grade

| grade | done | failed |
|---|---|---|
| 7 | 3 | 16 |
| 8 | 0 | 13 |
| 9 | 1 | 7 |
| 10 | 1 | 10 |
| 11 | 0 | 11 |

## 4. Топ error_code

| code | count |
|---|---|
| LLM_NO_JSON | 28 |
| OTHER | 25 |
| LLM_TRANSPORT | 4 |

## 5. Latency (ms)

- p50/p95/max (все done): 174637.7 / 260887.6 / 309245.5.
- has_aux=true: p50 126973.4, p95 126973.4, max 126973.4.
- has_aux=false: p50 217762.7, p95 260887.6, max 309245.5.

## 6. Стоимость

- Средняя цена успешного чертежа: $0.012740.
- Общая стоимость пилота: $0.833757.

## 7. Доли pipeline-метрик

- fast_path_used: 0/62 (0.0%)
- fallback_to_two_call: 0/62 (0.0%)
- audit_executed: 1/62 (1.6%)
- structured_json_used: 0/62 (0.0%)

## 8. Доля has_aux по style (КЛЮЧЕВАЯ метрика)

| style | has_aux=true | has_aux=false | доля aux |
|---|---|---|---|
| angle_chase | 0 | 1 | 0.0% |
| constructive | 1 | 3 | 25.0% |

## 9. Сводка QA-предупреждений

- AUX_EXPECTED_BUT_MISSING: 3
- AUX_SVG_MISSING: 1

## 10. Сверка кредитов

- Списания (ожидание: 1 на done): 5.
- Возвраты (ожидание: 1 на failed): 57.
- ФАКТ: `_charge_credit` в конвейере отключён (возвращает 'unlimited'); `_refund_credit` срабатывает только при credit_charged=true. Поэтому фактический баланс служебного аккаунта не меняется (delta=0).

## 11. Прогноз полного прогона

- Средняя стоимость задачи: $0.013448.
- Прогноз стоимости 354 задач: $4.76.
- Средняя latency done-задачи: 186994 ms; прогноз времени (2 workers): 552 мин.

## 12. Рекомендация


**НЕ масштабировать сейчас.** Пилот вскрыл критический дефект конвейера:

1. **[CRITICAL] `max_tokens=4096` жёстко зашит в `_call_deepseek`** ([`routes/figures_generator.py`](routes/figures_generator.py:467)), а `FIGURE_BASE_MAX_TOKENS`/`FIGURE_AUX_MAX_TOKENS`/`FIGURE_AUDIT_MAX_TOKENS` нигде не читаются. Реализованные модели (`deepseek-v4-flash`/`deepseek-v4-pro`) являются reasoning-моделями: весь бюджет уходит на CoT (`reasoning_tokens`), JSON не успевает сгенерироваться → `LLM_NO_JSON` / «Модель не смогла создать корректный base-план» на большинстве задач.
2. **[HIGH] Падение базового планировщика — массовое** (см. топ error_code). Успешны лишь задачи с коротким CoT.
3. **[MED] Novita недоступна по сети** (ConnectionError) — прогон полностью ложится на fallback DeepSeek, увеличивая latency и стоимость.

Дефекты по приоритету исправления: 1 → 2 → 3. После исправления max_tokens (или перехода на non-reasoning модель для планировщиков) повторить пилот.

# FORMYLA Adaptive Pipeline

Конвейер генерации задач для **Адаптивного теста** через OpenRouter.

## Архитектура

```
┌─────────────┐    ┌───────────┐    ┌────────────┐
│  Generator  │───→│ Validator │───→│ Calibrator │───→ save_task
│  deepseek   │    │ claude-4  │    │  gpt-4o    │
│   t=0.8     │    │  t=0.1    │    │   t=0.2    │
└─────────────┘    └─────┬─────┘    └─────┬──────┘
       ↑                 │ FAIL           │ FAIL
       └─────────────────┴────────────────┘
              feedback, max 4 итерации
              если не сошлось → manual_review_queue
```

**Анти-self-bias:** Generator (deepseek) ≠ Calibrator (gpt-4o).

## Файлы

| Файл | Назначение |
|------|------------|
| [`config.py`](config.py:1) | Модели, температуры, MAX_ITER, цены |
| [`schemas.py`](schemas.py:1) | Pydantic-модели для JSON от LLM |
| [`openrouter_client.py`](openrouter_client.py:1) | Async httpx + tenacity retry |
| [`generator.py`](generator.py:1) | Промпт-1: генерация задачи |
| [`validator.py`](validator.py:1) | Промпт-2: проверка корректности |
| [`calibrator.py`](calibrator.py:1) | Промпт-3: калибровка уровня |
| [`runner.py`](runner.py:1) | Управляющий цикл с feedback-петлёй |
| [`persistence.py`](persistence.py:1) | Запись в БД (AdaptiveTask + логи) |
| [`dedup.py`](dedup.py:1) | Эмбеддинги + косинус для дубликатов |

## Таблицы БД

Создаются миграцией [`migrations/add_adaptive_pipeline_tables.py`](../migrations/add_adaptive_pipeline_tables.py:1):

- **`task_generation_log`** — все попытки (успехи и неудачи), сводка по итерациям
- **`manual_review_queue`** — задачи, не прошедшие 4 итерации
- **`cost_log`** — токены × цена по каждому вызову модели

Старые 7350 задач **не удаляются** — флаг `is_flagged=True` + `flagged_reason='deprecated_by_pipeline'`.

## Установка

```bash
pip install -r requirements.txt
python migrations/add_adaptive_pipeline_tables.py
```

В `.env`:
```
OPENROUTER_API_KEY=sk-or-v1-...
```

## Запуск

```bash
# Smoke-test (1 задача, dry-run)
python scripts/test_pipeline_smoke.py

# Реальная генерация (10 задач, алгебра, 9 класс, уровень 2)
python scripts/regenerate_tasks.py \
    --subject algebra --grade 9 --level 2 \
    --count 10 --max-cost-usd 1.0
```

## Шкала уровней (канон)

| Уровень | Описание |
|---------|----------|
| 1 | Чуть выше учебника, 1–2 шага, без приёмов |
| 2 | Школьный ВсОШ, 2–3 шага, привычные приёмы |
| 3 | Школьный/нач. муниципального, 3–4 шага, аккуратность |
| 4 | Муниципальный, ОДНА нетривиальная идея |
| 5 | Сложн. муниц./лёгкий региональный, ДВЕ идеи |
| 6 | Региональный, 2–3 связанные идеи, оценка+пример |
| 7 | Сложн. региональный/закл. этап, творческое решение |

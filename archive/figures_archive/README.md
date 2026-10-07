# Архив системы генерации чертежей (FIGURES)

Сохранено 2026-09-08 перед удалением с сайта.

## Состав

- `routes/figures.py` — Blueprint `/figures` (витрина, история, оплата пакетов).
- `routes/figures_generator.py` — Blueprint `/figures/generate` (сам конвейер генерации).
- `services/llm_router.py` — роутер LLM-провайдеров (OdiRouter + модели).
- `services/figure_validator.py`, `figure_plan_schemas.py`, `figure_plan_validator.py` — валидация планов.
- `prompts/*.txt` — промпты (base_planner, aux_planner, auditor, solver, reasoner, aux_extractor).

## Модель

Генерация чертежей шла через OdiRouter на `kimi-k3` (лучший результат на длинных промптах).
Ключ OdiRouter — `GEMINI_API_KEY` в `.env` (см. env_backup.txt).

## Как восстановить

Скопировать файлы обратно в соответствующие каталоги проекта:
- `figures.py`, `figures_generator.py` → `routes/`
- `llm_router.py`, `figure_*.py` → `services/`
- `prompts/*.txt` → `data/figures/`

И заново зарегистрировать blueprint'ы в `app.py`.

# D4_QUOTA — Разведка, замена движка, счёт, пакеты, защита

## ЗАДАЧА 1. ЧТО ТАМ СЕЙЧАС (факты)

### Маршрут

| Шаг | URL | Файл | Строка |
|-----|-----|------|--------|
| Страница «Прочее» | `GET /misc` | [`app.py`](app.py:11582) | `misc_page()` → `render_template('misc.html')` |
| Ссылка на чертежи | `/drawing` | [`templates/misc.html`](templates/misc.html:98) | `ИИ-чертёж по задаче` |
| Страница чертежа | `GET /drawing` | [`routes/drawing.py`](routes/drawing.py:206) | `drawing_page()` → `render_template('drawing.html')` |
| Генерация (API) | `POST /api/drawing/generate` | [`routes/drawing.py`](routes/drawing.py:256) | `api_drawing_generate()` |
| Тяжёлая логика | — | [`services/drawing_service.py`](services/drawing_service.py:1119) | `generate_drawing()` |

### Чем сейчас рисуется

**5-стадийный code-gen пайплайн на matplotlib:**

1. **Brief Expander** (опционально): [`services/drawing_service.py`](services/drawing_service.py:714) — модель `google/gemini-3.1-pro-preview`, превращает лаконичное условие в развёрнутое задание на чертёж.
2. **Architect** (опционально): [`services/drawing_service.py`](services/drawing_service.py:753) — модель `google/gemini-3.1-pro-preview`, выдаёт детальную спецификацию построения.
3. **Claude Sonnet 4**: [`services/drawing_service.py`](services/drawing_service.py:1019) — модель `anthropic/claude-sonnet-4`, пишет **Python-код на matplotlib**, который исполняется в песочнице.
4. **Sandbox**: [`services/sandbox.py`](services/sandbox.py) — выполняет сгенерированный Python-код в subprocess, получает PNG.
5. **Critic** (до 2 раундов): [`services/drawing_service.py`](services/drawing_service.py:905) — Gemini Vision смотрит PNG, находит ошибки геометрии, Клод исправляет код. До 4 repair-итераций на раунд.
6. **Cosmetic Critic**: [`services/drawing_service.py`](services/drawing_service.py:929) — проверка читаемости подписей.

### Куда обращается

- Все модели через OpenRouter API: [`services/openrouter_client.py`](services/openrouter_client.py:1)
- Ключ из переменной окружения `OPENROUTER_API_KEY` (СКРЫТО)
- Модели: `anthropic/claude-sonnet-4`, `google/gemini-3.1-pro-preview`

### Сколько стоит за вызов

| Стадия | Модель | ~Стоимость |
|--------|--------|-----------|
| Brief Expander | Gemini 3.1 Pro | ~$0.02–0.04 |
| Architect | Gemini 3.1 Pro | ~$0.05 |
| Claude (генерация кода) | Claude Sonnet 4 | ~$0.03–0.10 |
| Critic (×2 раунда) | Gemini 3.1 Pro Vision | ~$0.02–0.04/раунд |
| Cosmetic Critic | Gemini 3.1 Pro Vision | ~$0.02–0.04 |
| **Итого (типичный вызов)** | | **~$0.10–0.30** |

Цены: [`services/openrouter_client.py`](services/openrouter_client.py:47) — `MODEL_PRICING`

### Где хранит результат

- **PNG-файлы**: `static/generated/drawing_<uuid>.png` — [`routes/drawing.py`](routes/drawing.py:128) `_save_png()`
- **Кэш**: `static/generated/cache/<sha256>.png` + `.meta.txt`, TTL 30 дней — [`services/drawing_service.py`](services/drawing_service.py:619) `_cache_paths()`
- **Лог в БД**: таблица `drawing_generations` — модель [`models.py`](models.py:1438) `DrawingGeneration`
- **Метаданные**: `cost_usd`, `model`, `repair_iters`, `critique_rounds` и т.д.

### Фактический ответ системы

Ответ `POST /api/drawing/generate` (успех):
```json
{
  "image_url": "/static/generated/drawing_abc123.png",
  "code": "import matplotlib.pyplot as plt\n...",
  "model": "anthropic/claude-sonnet-4",
  "cost_usd": 0.147,
  "render_ms": 45230,
  "cache_hit": false,
  "repair_iters": 1,
  "critique_rounds": 2,
  "critique_accepted": 3,
  "critique_rejected": 1,
  "attempts": [...]
}
```

### Существующая инфраструктура для НОВОГО движка (уже есть, не используется drawing-пайплайном)

| Компонент | Файл | Назначение |
|-----------|------|------------|
| Ризонер-промпт | [`data/figures/reasoner_task.txt`](data/figures/reasoner_task.txt) | Задание модели: условие+решение → JSON построений |
| Валидатор | [`services/figure_validator.py`](services/figure_validator.py) | Проверка JSON: типы, ссылки, схема |
| Геометрический движок | [`geometric_engine/engine.py`](geometric_engine/engine.py) | `GeometricEngine.build()` → SVG |
| Схема построений | [`geometric_engine/schema.json`](geometric_engine/schema.json) | 93 типа построений |
| Ретри-механизм | [`geometric_engine/engine.py`](geometric_engine/engine.py:1006) | `build_with_retry()` — до 50 попыток со сдвигом seed |

### Вывод

Текущая система генерирует **PNG через matplotlib-код**, написанный Claude Sonnet. Это дорого ($0.10–0.30/вызов), медленно (~60 сек), и требует сложного пайплайна с критиком.
НОВЫЙ подход — ризонер генерирует декларативный JSON, geometric_engine рендерит SVG — уже имеет всю инфраструктуру, просто не подключён к разделу «Прочее».

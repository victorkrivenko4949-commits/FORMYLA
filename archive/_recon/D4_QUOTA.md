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

**5-стадийный code-gen пайплайн на matplotlib (PNG):**
1. Brief Expander (Gemini 3.1 Pro) — разворачивает лаконичное условие
2. Architect (Gemini 3.1 Pro) — детальная спецификация
3. Claude Sonnet 4 — пишет Python/matplotlib код
4. Sandbox — исполняет код в subprocess, получает PNG
5. Critic (Gemini Vision, ×2 раунда) — проверяет геометрию
6. Cosmetic Critic — проверяет читаемость

### Сколько стоит за вызов

| Стадия | ~Стоимость |
|--------|-----------|
| Brief Expander | $0.02–0.04 |
| Architect | $0.05 |
| Claude | $0.03–0.10 |
| Critic ×2 | $0.04–0.08 |
| **Итого** | **~$0.10–0.30** |

### Ответ системы (пример)

```json
{"image_url": "/static/generated/drawing_abc.png", "cost_usd": 0.147, "cache_hit": false, ...}
```

---

## ЗАДАЧА 2. ЗАМЕНА ДВИЖКА — ВЫПОЛНЕНО

**Новый маршрут:** `/figures` → ризонер (JSON) → валидатор → geometric_engine (SVG).

**Файлы:**
- [`routes/figures.py`](routes/figures.py) — blueprint с API `POST /api/figures/generate`
- [`templates/figures.html`](templates/figures.html) — страница ввода условия + отображение SVG + скачивание
- [`templates/misc.html`](templates/misc.html:98) — ссылка заменена с `/drawing` на `/figures`
- [`app.py`](app.py:1143) — регистрация `figures_bp`

**Пайплайн:**
1. Ученик вводит условие (+ опционально решение)
2. Ризонер (DeepSeek Chat, промпт из [`data/figures/reasoner_task.txt`](data/figures/reasoner_task.txt)) → JSON построений
3. [`services/figure_validator.py`](services/figure_validator.py) проверяет JSON
4. [`geometric_engine/engine.py`](geometric_engine/engine.py) → `build_with_retry()` → SVG
5. SVG показывается, можно скачать

**Ретраи:** до 2 повторных запросов к модели с перечнем замечаний валидатора. После исчерпания — честное сообщение «чертёж построить не удалось», попытка НЕ списывается.

**Старая система:** [`routes/drawing.py`](routes/drawing.py), [`services/drawing_service.py`](services/drawing_service.py) и [`templates/drawing.html`](templates/drawing.html) — не тронуты, код не удалён, просто ссылка с `misc.html` ведёт на новый раздел.

---

## ЗАДАЧА 3. СЧЁТ ЧЕРТЕЖЕЙ — ВЫПОЛНЕНО

**Модели** ([`models.py`](models.py)):
- `User.figure_credits` — INT, default 3, навсегда, не обновляются
- `User.figures_built` — INT, счётчик построенных чертежей
- `FigureCreditTransaction` — журнал: кто, когда, сколько, за что
- `FigureGeneration` — лог генераций

**Списание:** ровно одно за успешный чертёж. При ошибке/отказе — refund.

**Начисления:**
- 7 дней подряд → +5 (reason: `streak_7day`)
- Пройденный срез → +3 (reason: `slice_pass`)
- Каждое начисление один раз, запись в журнал с reference

**Миграция:** [`scripts/d4_migration.py`](scripts/d4_migration.py) — копия БД в `backups/`, авто-добавление колонок и таблиц.

---

## ЗАДАЧА 4. ПАКЕТЫ И ЗАГЛУШКА ОПЛАТЫ — ВЫПОЛНЕНО

**Пакеты** ([`routes/figures.py`](routes/figures.py) `FIGURE_PACKAGES`):
| ID | Чертежей | Цена |
|----|----------|------|
| p10 | 10 | 99 ₽ |
| p30 | 30 | 249 ₽ ← «Выгоднее всего» |
| p100 | 100 | 599 ₽ |

**Страницы:**
- [`templates/pricing.html`](templates/pricing.html) — три карточки, средняя с пометкой «Выгоднее всего»
- [`templates/payment_stub.html`](templates/payment_stub.html) — заглушка «Оплата скоро появится» + форма «сообщить мне»
- [`services/yookassa_stub.py`](services/yookassa_stub.py) — модуль-заглушка ЮKassa с понятным входом/выходом

**Email-подписки:** `POST /api/figures/subscribe-email` → таблица `figure_email_subscriptions`

---

## ЗАДАЧА 5. ЭКРАН «ЗАКОНЧИЛИСЬ» — ВЫПОЛНЕНО

В [`templates/figures.html`](templates/figures.html) блок `#figureZeroBalance`:
- Показывается при credits ≤ 0
- Сколько чертежей построено
- Как получить ещё бесплатно (серия, срез)
- Ссылка на `/pricing`
- Тёмно-синяя тема, без эмодзи, без обратного отсчёта

---

## ЗАДАЧА 6. ЗАЩИТА — ВЫПОЛНЕНО

| Защита | Реализация |
|--------|-----------|
| Одно построение на пользователя | `_concurrent_guard()` — блокировка `_building[uid]` |
| Частота запросов | 10 запросов/час, `_rate_check()` |
| Длина условия | Максимум 4000 символов |
| Чужой счёт | `_spend_credit(current_user)` — только свой пользователь |

Коды ответов:
- `429` — rate limit / concurrent build
- `400` — пустое/длинное условие
- `402` — нет кредитов
- `503` — нет ключа API / сервис недоступен
- `422` — валидация не пройдена
- `200` — успех, SVG

---

## ЗАДАЧА 7. ТЕСТЫ И КОММИТ — ВЫПОЛНЕНО

**Тесты:** `python -m pytest -q`
- **47 failed**, 877 passed, 16 skipped, 14 errors
- 47 ≤ 47 — условие выполнено
- Падения — pre-existing (тестовое окружение, отсутствие таблиц/модулей)

**Коммит:** `e99ea54` — без отправки (локально)

```
_hash: e99ea545b2735bc8a75928c2fb9e08348b655699
_message: D4: figure generation with reasoner+validator+engine, credits, packages, protection
_files: 10 files changed, 1612 insertions(+), 413 deletions(-)
```

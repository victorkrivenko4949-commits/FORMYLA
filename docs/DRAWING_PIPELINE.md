# Как работает /drawing — путь запроса от кнопки до PNG

Ниже — пошаговый рассказ того, что происходит, когда пользователь FORMYLA
вводит условие задачи и жмёт «Сгенерировать чертёж».

---

## Шаг 0. Браузер

Пользователь на странице `/drawing` пишет условие в textarea и нажимает
«✨ Сгенерировать чертёж». JS делает `fetch("/api/drawing/generate", ...)`
с телом-JSON, где в поле `problem` лежит текст задачи. На UI показывается
крутилка «Генерация занимает 10–20 секунд» (теперь, после переезда на Opus
4.7 + Gemini-критика, реальное время — 20–50 секунд).

---

## Шаг 1. Flask-роут — валидация и rate limit

[`routes/drawing.py`](../routes/drawing.py:158) обрабатывает `POST /api/drawing/generate`.

1. Тело декодируется как UTF-8 (защита от mojibake через прокси).
2. Проверка длины: 10 ≤ `len(problem)` ≤ 2000.
3. **Rate-limit** in-memory: не больше 10 чертежей в час с одного user_id
   (или IP, если не залогинен). Превышение → HTTP 429 + `Retry-After`.
4. Если всё ок — вызывается `services.drawing_service.generate_drawing(problem)`.

---

## Шаг 2. Cache lookup

[`services/drawing_service.py:494`](../services/drawing_service.py:494)
делает первое, что делает любой кэш:

1. SHA-256 от `MODEL_PRIMARY + "::" + problem.strip()` → 64-символьный hex `sha`.
2. Открывается `static/generated/cache/<sha>.png`. Если он есть и моложе
   30 дней — возвращается мгновенно (`cache_hit=True`, render_ms ≈ 5).
3. **Ни Claude, ни Gemini в этом случае не дёргаются.**

Если кэша нет — идём дальше.

---

## Шаг 3. Главный generate-loop

[`services/drawing_service.py:_generate_code_until_renders`](../services/drawing_service.py:399) —
этот блок крутится до 3 раз (1 первая попытка + 2 итерации self-repair).

### 3a. Запрос к Claude Opus 4.7 (через OpenRouter)

В `messages` уходит:

- system-prompt с жёсткими правилами (только matplotlib/numpy/math,
  никаких import os/sys/subprocess, чёрные линии 2px, sans-serif 18–22px,
  одиночные латинские буквы для вершин, не добавлять построений которых
  нет в условии, и т.д.) — целиком в [`services/drawing_service.py:62`](../services/drawing_service.py:62).
- user-сообщение: текст условия как есть.

Температура 0.2, max_tokens 2048. Если запрос на основную модель упал
(`OpenRouterError`) — **фолбэка нет**, бросаем исключение.

### 3b. Извлечение кода

Из ответа Claude парсится первый блок ```` ```python ```` (или сразу
весь текст, если он начинается с `import`). Если кода нет — это считается
ошибкой; в Claude отправляется ремонт-сообщение, идёт следующая итерация.

### 3c. Sandbox-валидация

[`services/sandbox.py:validate_drawing_code`](../services/sandbox.py:115)
проходит AST по коду:

- разрешены **только** импорты `matplotlib`, `numpy`, `math`;
- запрещены `os`, `sys`, `subprocess`, `socket`, `urllib`, `requests`, …;
- запрещены имена `__import__`, `open`, `eval`, `exec`, `compile`,
  `globals`, `__class__`, `__bases__`;
- запрещены `from os import …`, dunder-доступ, и т.п.

Если код провалил проверку → `SandboxRejected`. Claude получает traceback
и пробует ещё раз.

### 3d. Sandbox-исполнение

[`services/sandbox.py:_run_via_subprocess`](../services/sandbox.py:270)
спавнит дочерний `python -c <wrapped_code>`:

- обёртка перехватывает `plt.show()` и пишет PNG в `stdout.buffer`;
- rlimits на Unix: CPU 8s, mem 512MB, NPROC 64, file 16MB;
- timeout 12s; превышение → `SandboxTimeout`;
- ENV cleansed, PYTHONPATH передан только тот, что нужен для импорта
  matplotlib/numpy.

Если subprocess вернул PNG-байты — выходим из generate-loop. Если упал
с runtime-error — Claude получает traceback и идёт следующая итерация
(до `MAX_REPAIR_ITERS = 2`).

После 3 неудачных попыток generate-loop бросает `SandboxError`.

---

## Шаг 4. Critique loop — Gemini 2.5 Pro смотрит результат

[`services/drawing_service.py:521`](../services/drawing_service.py:521)
после первого успешного рендера запускает цикл из `MAX_CRITIQUE_ROUNDS = 2`.

### 4a. Критика

[`services/drawing_service.py:_critique_with_gemini`](../services/drawing_service.py:369)
формирует multi-modal запрос к `google/gemini-3.1-pro`:

- system-prompt: «ищи нарушения условия (неверные длины/углы, лишние
  построения, отсутствие упомянутых объектов), математически неверное
  расположение, нечитаемые подписи; не придирайся к косметике»;
- user-content — два блока:
  1. text: условие задачи + полный исходный код;
  2. image_url: PNG чертежа в формате `data:image/png;base64,…`.

Gemini возвращает JSON-объект со списком `findings`. Каждый finding имеет
`id` (f1, f2…), `severity` (blocker/major/minor), `title`, `detail`,
`fix_hint`. Если ошибок нет — возвращает пустой массив.

### 4b. Если findings пустой → break

Цикл выходит, текущий PNG считается финальным.

### 4c. Если findings есть → Claude получает их в тот же диалог

[`services/drawing_service.py:_build_critique_user_msg`](../services/drawing_service.py:246)
добавляет в `messages` (тот же массив, что использовался в шаге 3) новое
user-сообщение со списком ошибок и инструкцией:

```
По каждой ошибке прими решение:
  - если согласен — исправь её в коде;
  - если НЕ согласен (ревьюер не прав) — оставь как было
    и кратко объясни, почему отклонил.

Верни ОТВЕТ В ДВУХ ЧАСТЯХ:
(1) JSON со сводкой решений (id, decision: accepted|rejected, reason);
(2) ПОЛНЫЙ обновлённый код в одном блоке.
```

### 4d. Claude отвечает в тот же диалог

Так как `messages` сохраняется между раундами, Claude видит:
- свой исходный код,
- finding'и от Gemini,
- может опираться на собственное обоснование при ответе.

Парсер [`_parse_decisions`](../services/drawing_service.py:282)
извлекает JSON-сводку и проставляет каждому finding'у `claude_decision`
и `claude_reasoning`. Из ответа также вырезается обновлённый код.

### 4e. Новый sandbox-прогон + следующий раунд

Обновлённый код снова идёт через `_generate_code_until_renders`
(тот же self-repair-loop). Если он отрендерил PNG — Gemini получает новый
PNG и условие; следующий раунд критики. Если он упал даже после repair —
выкидываем последний хороший PNG (тот, что был перед этой ревизией), и
выходим из critique-loop с записью в `attempts`.

После `MAX_CRITIQUE_ROUNDS = 2` цикл останавливается **в любом случае**,
даже если Gemini всё ещё что-то нашёл.

### 4f. Что если Gemini сам упал

Если `openrouter.chat()` к Gemini кинул `OpenRouterError` (502, 429, и т.п.) —
**graceful degrade**: критик пропускается, в `attempts` пишется
`stage=critic, ok=False`, пользователь всё равно получает текущий PNG.

---

## Шаг 5. Cache write + DB log

1. Финальный PNG записывается в `static/generated/cache/<sha>.png`
   (TTL 30 дней по mtime).
2. PNG также сохраняется в `static/generated/drawing_<uuid>.png` —
   именно его URL отдаётся фронту в теге `<img>`.
3. [`routes/drawing.py:_log_to_db`](../routes/drawing.py:110)
   создаёт строку в таблице `drawing_generations`:

| колонка                  | что лежит                                             |
|--------------------------|-------------------------------------------------------|
| `user_id`                | id залогиненного пользователя или NULL                |
| `problem_sha256`         | SHA-256 условия                                       |
| `problem`                | первые 5000 символов условия                          |
| `generated_code`         | финальный matplotlib-код                              |
| `model`                  | например `anthropic/claude-opus-4.7`                  |
| `status`                 | `ok` / `cache_hit` / `error` / `rejected` / `timeout` |
| `error`                  | traceback если упало                                  |
| `repair_iters`           | сколько раз code-gen ремонтировался (0–2)             |
| `render_ms`              | полное время от начала запроса до PNG                 |
| `cost_usd`               | сумма стоимости всех LLM-вызовов                      |
| `image_path` / `image_size` | путь и размер итогового файла                      |
| `critique_rounds`        | сколько раз вызывался Gemini-критик (0–2)             |
| `critique_accepted`      | сколько ошибок Claude согласился исправить            |
| `critique_rejected`      | сколько Claude отклонил с обоснованием                |
| `critique_findings_json` | полный JSON со всеми findings и решениями             |

---

## Шаг 6. Ответ браузеру

```
HTTP 200 application/json
OBJ_START
  "image_url":   "/static/generated/drawing_…​.png",
  "image_b64":   "iVBORw0KGgo…​",
  "data_url":    "data:image/png;base64,iVBORw…​",
  "model":       "anthropic/claude-opus-4.7",
  "cost_usd":    0.123,
  "render_ms":   42017,
  "cache_hit":   false,
  "repair_iters": 0,
  "critique_rounds":   1,
  "critique_accepted": 2,
  "critique_rejected": 1
OBJ_END
```

(Сам код не отдаётся фронту — его можно подсмотреть только в БД через
`scripts/inspect_drawing_log.py`.)

---

## Стоимость одного чертежа в среднем

| Этап                        | Модель                       | Стоимость              |
|-----------------------------|------------------------------|------------------------|
| Code-generation (1 запрос)  | Claude Opus 4.7              | ≈ $0.05–0.12           |
| Critique round 1            | Gemini 2.5 Pro vision        | ≈ $0.002–0.005         |
| Revision (если есть)        | Claude Opus 4.7              | ≈ $0.05–0.12           |
| Critique round 2            | Gemini 2.5 Pro vision        | ≈ $0.002–0.005         |
| **Итого без ремонта**       | —                            | **≈ $0.05**            |
| **Итого с 1 раундом**       | —                            | **≈ $0.11**            |
| **Итого с 2 раундами**      | —                            | **≈ $0.22**            |
| Cache hit                   | —                            | **$0.000**             |

При типичной нагрузке 100 чертежей в день и среднем 1 раунде критики —
около $11/день, $330/месяц.

---

## Что записано в БД при ошибке

- `SandboxRejected` (LLM написал запрещённый импорт) → `status=rejected`.
- `SandboxTimeout` → `status=timeout`.
- `SandboxError` (после всех self-repair'ов) → `status=error`.
- `OpenRouterError` от Claude → `status=error`, `error=<сообщение>`.

Pipeline никогда не глотает ошибку молча — она всегда в `error` или в
JSON-массиве `attempts`, доступном через `inspect_drawing_log.py`.

---

## Файлы, которые во всём этом участвуют

- [`templates/drawing.html`](../templates/drawing.html:1) — UI.
- [`static/js/drawing.js`](../static/js/drawing.js:1) — fetch + display.
- [`routes/drawing.py`](../routes/drawing.py:1) — Flask-роут.
- [`services/drawing_service.py`](../services/drawing_service.py:1) — оркестратор.
- [`services/sandbox.py`](../services/sandbox.py:1) — AST whitelist + subprocess.
- [`services/openrouter_client.py`](../services/openrouter_client.py:1) — LLM transport.
- [`models.py`](../models.py:1152) — модель `DrawingGeneration`.
- [`scripts/inspect_drawing_log.py`](../scripts/inspect_drawing_log.py:1) — pretty-print последней записи.

Sequence-summary без слов: **textarea → POST → cache? → Opus 4.7 → AST → subprocess → PNG → Gemini Vision → (Opus правит / отклоняет) → ещё один раунд → cache write → DB log → JSON ответ → <img> в браузере**.

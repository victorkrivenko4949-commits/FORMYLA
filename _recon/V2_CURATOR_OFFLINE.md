# V2: Куратор без внешнего сервиса — реконструкция

## ЗАДАЧА 1. ИСТОЧНИКИ ОБРАЩЕНИЙ К ВНЕШНИМ СЕРВИСАМ

### Страница `/prep/coach` (основная страница куратора)

Рендер [`routes/prep.py:936-1284`](routes/prep.py:936) **не делает внешних вызовов** — только чтение из БД (CuratorState, AdaptiveTestResult, level_engine → DB). Страница рендерится с кодом 200 независимо от ключей.

Однако страница содержит AJAX-вызовы:

#### 1. `POST /prep/coach/chat` — [`routes/prep.py:2760`](routes/prep.py:2760)
- **Файл:** `routes/prep.py`
- **Функция:** `coach_chat()`
- **Строка:** [2922-2926](routes/prep.py:2922)
- **Внешний сервис:** `api.deepseek.com` (прямой DeepSeek API)
- **Клиент:** `ai/deepseek_client.py` → `DeepSeekClient().generate_with_reasoning()`
- **Ключ:** `DEEPSEEK_API_KEY` из `.env`
- **Ответ при неверном ключе:** HTTP 402 Payment Required
- **Падение:** без работающего ключа чат с куратором не отвечает (но есть fallback на [line 2927-2930](routes/prep.py:2927))

#### 2. `POST /prep/coach/onboarding/submit` — [`routes/prep.py:1961`](routes/prep.py:1961)
- **Файл:** `routes/prep.py`
- **Функция:** `coach_onboarding_submit()`
- **Строка:** [552](routes/prep.py:552) через `_evaluate_solution()`
- **Внешний сервис:** `api.deepseek.com`
- **Клиент:** `ai/deepseek_client.py` → `DeepSeekClient().generate()`
- **Ключ:** `DEEPSEEK_API_KEY`

#### 3. `POST /prep/probe/submit` — [`routes/prep.py:1489`](routes/prep.py:1489)
- **Файл:** `routes/prep.py`
- **Функция:** `probe_submit()`
- **Строка:** [1508](routes/prep.py:1508) через `_evaluate_solution()`
- **Внешний сервис:** `api.deepseek.com`
- **Ключ:** `DEEPSEEK_API_KEY`

#### 4. `POST /prep/<plan_id>/today/complete/<id>` — [`routes/prep.py:428`](routes/prep.py:428)
- **Файл:** `routes/prep.py`
- **Функция:** `complete_problem()`
- **Строка:** [551-552](routes/prep.py:551)
- **Внешний сервис:** `api.deepseek.com`
- **Ключ:** `DEEPSEEK_API_KEY`

### Другие места с внешними вызовами (не на странице куратора, но в приложении)

#### 5. `curator/tutor.py` — подсказки и проверка решений
- **Строки:** [63](curator/tutor.py:63), [173](curator/tutor.py:173), [338](curator/tutor.py:338)
- **Внешний сервис:** `openrouter.ai` (OpenRouter API)
- **Клиент:** `services/openrouter_client.py` → `openrouter.chat()`
- **Ключ:** `OPENROUTER_API_KEY`
- **Модели:** `deepseek/deepseek-chat`

#### 6. `curator/olympiad_advisor.py` — AI-рекомендации олимпиад
- **Строка:** [261](curator/olympiad_advisor.py:261)
- **Внешний сервис:** `api.deepseek.com`
- **Ключ:** `DEEPSEEK_API_KEY`

#### 7. `curator/progress.py` — AI-советы по прогрессу
- **Строка:** [362-364](curator/progress.py:362)
- **Внешний сервис:** `openrouter.ai`
- **Ключ:** `OPENROUTER_API_KEY`

### Фактический ответ сервиса при неработающем ключе

```
Сервис: api.deepseek.com
Ключ: СКРЫТО
HTTP 402 Payment Required
Тело: {"error":{"message":"Insufficient Balance","type":"unknown_error"}}
```

(DeepSeek возвращает 402, OpenRouter также возвращает 402 для неоплаченных ключей.)

### Перечень страниц, которые сломаются при недоступном ключе

| Маршрут | Что сломается | Тяжесть |
|---------|---------------|---------|
| `POST /prep/coach/chat` | Чат с куратором не отвечает | Средняя (есть fallback) |
| `POST /prep/probe/submit` | Проверка ответов утреннего среза | Высокая |
| `POST /prep/<id>/today/complete/<id>` | Проверка решений задач дня | Высокая |
| `POST /prep/coach/onboarding/submit` | AI-проверка при онбординге | Средняя |
| `POST /curator/tutor/hints` | Подсказки к задачам | Средняя |
| `POST /curator/tutor/review` | AI-проверка решений | Высокая |
| `POST /curator/progress/<id>/advice` | AI-советы | Низкая |
| `POST /curator/analyze/olympiads` | Рекомендации олимпиад | Низкая |

**Ключевой вывод:** страница `/prep/coach` НЕ падает сама по себе — она рендерится из БД. 
Проблема в том, что чат с куратором (AJAX) не работает без ключа, и страница выглядит 
«сломанной» для пользователя, потому что центральный элемент (чат) не отвечает.

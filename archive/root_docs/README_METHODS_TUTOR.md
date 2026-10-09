# AI-наставник визуального атласа методов

Настоящий ИИ-наставник для раздела «Методы — визуальный атлас олимпиадных
методов». Вместо mock-прототипа `mockReply()` панель «Наставник» теперь
вызывает реальную мультимодальную модель через тонкий backend-прокси.

## Архитектура

```
HTML/JS атласа (static/methods/index.html)
    ↓ POST /api/tutor/chat (JSON, опционально base64-изображения)
тонкий backend-прокси (app.py → services/atlas_tutor.py)
    ↓ OpenAI-compatible chat API
LLM (по умолчанию DeepSeek; vision-модель для фото)
```

- API-ключ живёт **только** на сервере (переменная окружения). В HTML/JS/git
  секретов нет.
- Провайдер изолирован в [`services/atlas_tutor.py`](services/atlas_tutor.py) —
  его можно заменить, не трогая фронтенд (OpenAI-совместимый base URL).
- Контекст метода берётся **только** из серверной копии атласа
  ([`services/atlas_methods.py`](services/atlas_methods.py)); клиентским полям
  метода мы не доверяем — доступ только через allow-list.

## Возможности (P0)

- Настоящий чат с мультимодальной моделью.
- Выделение текста внутри метода + контекстная панель:
  «Объяснить проще», «Почему это верно?», «Показать на примере»,
  «Это непонятно», «Спросить наставника», «Копировать».
- Вопрос по выделенному фрагменту с сохранением источника
  (`sectionId`, `sectionTitle`, `methodCode`, `exampleIndex`, `stage`,
  `selectedText` + соседний текст).
- Прикрепление фото/скриншотов: PNG/JPEG/WebP, вставка из буфера (Ctrl/Cmd+V),
  drag-and-drop, камера/галерея на телефоне, превью, удаление, крупный просмотр.
- Проверка рукописного решения (мультимодально).
- Режимы: `hint` / `explain` / `check` / `trigger` / `visual` (+ `free`).
- Лестница подсказок 0–4 с защитой от спойлеров (полное решение только после
  `spoilerAllowed=true`).
- История отдельная для каждого метода и каждого примера.
- Статус «ИИ подключён / недоступен», состояния loading/error/offline,
  `AbortController` (остановка генерации), таймаут, защита от двойной отправки.
- Sanitization: модель не может вставить исполняемый HTML/JS — Markdown
  прогоняется через существующий `md()` с экранированием; в систему прописано
  «только Markdown и LaTeX».
- Выбор задачи (selector) и адаптация под класс ученика.

## Настройка

Скопируйте `.env.example` в `.env` и задайте ключ (на сервере):

```
DEEPSEEK_API_KEY=sk-...
# либо отдельный ключ для наставника:
# ATLAS_TUTOR_API_KEY=sk-...
# ATLAS_TUTOR_API_BASE=https://api.deepseek.com/v1
# ATLAS_TUTOR_MODEL=deepseek-v4-flash
# ATLAS_TUTOR_VISION_MODEL=deepseek-v4-flash-vision-exp
```

Если `ATLAS_TUTOR_API_KEY` не задан — используется `DEEPSEEK_API_KEY`.

> Никогда не помещайте ключ в автономный HTML. Настоящий ИИ требует backend
> (или serverless-функцию), потому что секрет нельзя безопасно хранить в
> файле, который уходит в браузер. Без backend атлас остаётся полностью
> рабочим: панель честно показывает «ИИ недоступен», а не подменяет ответ
> заготовкой.

## Запуск

### Windows

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # затем отредактируйте .env
python app.py
```

### macOS / Linux

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # затем отредактируйте .env
python app.py
```

Откройте `/olympiads/methods` (или файл атласа напрямую) — наставник
подключится к `/api/tutor/chat`.

## API

```http
POST /api/tutor/chat
Content-Type: application/json
```

```json
{
  "methodCode": "A2b",
  "exampleIndex": 0,
  "mode": "hint",
  "hintLevel": 1,
  "spoilerAllowed": false,
  "studentGrade": 7,
  "message": "Я составил уравнение, но не понимаю, что обозначить за x",
  "history": [{"role": "user", "content": "Не знаю, с чего начать"}],
  "selection": {
    "selectedText": "квадрат суммы",
    "sectionId": "theorems",
    "sectionTitle": "Основные теоремы и факты",
    "exampleIndex": 0,
    "stage": null
  },
  "images": [{"mimeType": "image/png", "data": "<base64 без data:-префикса>"}]
}
```

Ответ:

```json
{
  "message": "Обозначь через \\(x\\) …",
  "status": "ok",
  "hintLevel": 1,
  "spoilerAllowed": false,
  "mode": "hint",
  "suggestedActions": [
    {"type": "next_hint", "label": "Ещё маленький намёк"},
    {"type": "check_step", "label": "Проверить мой следующий шаг"}
  ],
  "methodLinks": []
}
```

Ошибки: `400` (валидация), `413` (слишком большой запрос), `429` (rate limit),
`502`/`504` (провайдер/таймаут) — всегда с понятным `message`.

## Тесты и eval

```bash
python -m pytest tests/test_atlas_tutor.py -q
python tests/eval_atlas_tutor.py          # отчёт по 21 сценарию (A–H)
python tests/eval_atlas_tutor.py --live   # живой прогон (нужен ключ)
```

Unit-тесты проверяют без сети: изоляцию контекста (A2b ≠ F16), границы
`exampleIndex`, лестницу подсказок и спойлер-гейт, валидацию изображений и
MIME, обрезку истории, отсутствие выдуманных элементов в visual-режиме,
границы промпта (инъекция в секцию `[ЗАПРОС УЧЕНИКА]`) и rate limit.

## Ограничения и риски

- Rate limit — in-memory (на процесс). Для multi-worker нужен Redis.
- История сворачивается простым окном последних 12 сообщений (без LLM-резюме —
  это P1).
- SVG атласа в модель не отправляется целиком; объяснение чертежа строится из
  `stage_notes`, `visual_spec`, `aria-label` и текстовых подписей.
- Vision-модель должна поддерживать `image_url` (DeepSeek vision / OpenRouter).
  Если провайдер не поддерживает изображения, backend вернёт честную ошибку,
  а не «притворится», что распознал.

## Следующие шаги (P1/P2)

- Сравнение методов (режим `compare` уже в allow-list backend).
- LLM-резюме длинной истории.
- Мини-практика («проверь, понял ли метод»).
- Постоянный прогресс ученика, экспорт диалога, teacher mode.
- Авто-отправка отрендеренной стадии SVG как изображения.

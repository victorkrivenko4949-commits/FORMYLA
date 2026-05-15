# Деплой фикса "Failed to fetch" на Render — пошагово

## Зачем

Сейчас на проде (Render Free) крутится вчерашний код, в котором критик-Gemini
включён всегда. Пайплайн `Claude Opus 4.7 -> sandbox -> Gemini critic x2 -> Claude patch`
занимает 60–180 секунд, а Render Free режет любой HTTP-запрос на 100 секундах.
Поэтому фронт показывает «Сетевая ошибка: Failed to fetch».

Локально я уже всё починил: добавил env-флаг `DRAWING_CRITIC_ENABLED`,
по умолчанию **выключен**. Без критика пайплайн укладывается в 20–30 секунд
и спокойно проходит таймаут Render Free.

Тебе осталось только **залить эти изменения на Render**. Ниже — пошагово.

---

## Шаг 1. Проверить, что локальные изменения в репозитории

В терминале из корня проекта (`c:/Users/Victor/Desktop/Новая папка (2)`):

    git status

Ожидаемо увидишь модифицированные/новые файлы:

- `services/drawing_service.py` (модель Opus 4.7, флаг критика, Gemini 3.1)
- `services/openrouter_client.py` (Gemini 3.1 в прайс-листе)
- `models.py` (4 новых колонки в DrawingGeneration)
- `routes/drawing.py` (лог критика в БД)
- `migrations/add_drawing_critique_columns.py` (новая миграция)
- `tests/test_drawing_critique.py` (новый файл)
- `tests/test_drawing_e2e.py` (обновлён)
- `scripts/inspect_drawing_log.py` (новая утилита)
- `docs/DRAWING_PIPELINE.md`, `docs/DEPLOY_FIX.md`

---

## Шаг 2. Закоммитить и запушить

    git add .
    git commit -m "drawing: claude opus 4.7 + gemini 3.1 critic behind DRAWING_CRITIC_ENABLED flag"
    git push origin main

Если ветка не `main` — заменишь на свою (`master`, `prod`, и т.п.).

---

## Шаг 3. Дождаться авто-деплоя на Render

1. Открой Render Dashboard → свой web-service.
2. Перейди на вкладку **Events** или **Logs**.
3. После `git push` через 10–30 секунд появится новая запись
   «Deploy started for commit ...». Это нормально.
4. Жди статус **Live** — обычно 2–5 минут.

Если авто-деплой не сработал (отключён), нажми кнопку
**Manual Deploy → Deploy latest commit** в правом верхнем углу.

---

## Шаг 4. (Опционально) накатить миграцию для новых колонок

Это нужно, только если ты хочешь, чтобы в БД на проде появились
поля `critique_rounds`, `critique_accepted`, `critique_rejected`,
`critique_findings_json`. Без них всё всё равно работает (код не падает),
но логи критика в БД не запишутся.

В Render: **Shell** (кнопка в Dashboard) →

    python migrations/add_drawing_critique_columns.py

Миграция идемпотентная — если колонки уже есть, она просто
ничего не сделает.

---

## Шаг 5. Проверить, что фикс работает

1. Открой `https://<твой-домен>.onrender.com/health` — должно отдать `ok`.
2. Открой `/drawing`.
3. Вставь ту же задачу про две окружности (или любую другую).
4. Ждёшь 15–30 секунд → должна вернуться картинка без «Failed to fetch».

Если всё ещё ошибка — открой Render → Logs и поищи строчку
`[drawing]` или `Traceback`. Скинь — разберёмся.

---

## Шаг 6. Env-переменные, которые НЕ нужно ставить

Не трогай ничего в Render → Environment. В частности:

- `DRAWING_CRITIC_ENABLED` — **оставь отсутствующим** (= критик выключен).
- `OPENROUTER_API_KEY` — уже стоит, не меняй.

Если случайно поставишь `DRAWING_CRITIC_ENABLED=1` — критик включится
и снова словишь Failed to fetch на Free тарифе.

---

## Когда переедешь на Render Starter (300 сек таймаут)

Тогда — и только тогда — можно будет включить критика:

1. Render Dashboard → твой сервис → **Environment**.
2. **Add Environment Variable**:
   - Key: `DRAWING_CRITIC_ENABLED`
   - Value: `1`
3. **Save Changes** — Render сам перезапустит сервис.
4. После рестарта новые чертежи пойдут через Gemini-критика
   (видно в логах БД через `python scripts/inspect_drawing_log.py`).

---

## TL;DR (минимум действий)

    git add .
    git commit -m "drawing: opus 4.7 + critic env flag"
    git push

И ждёшь, пока Render задеплоит. Всё.
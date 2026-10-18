# Чистка каталога олимпиадных задач (olymp_catalog_fix)

Пайплайн из 22 этапов для чистки `data/olymp_catalog/` (4624 задачи, 13 олимпиад).
Детерминированная чистка (этапы 1–4, 8–10, 12–17) → правки DeepSeek с математической
сверкой deepseek-reasoner → поиск официальных источников (этапы 18–21) → финальная
валидация и отчёт (этап 22).

## Как работает поиск источников (этапы 18, 20, 21)

1. **Индекс официальных PDF** (`scripts/olymp_source_index.py`) — первый источник кандидатов:
   - шаг 1: существующие `source` из базы (id олимпиады, год, класс, этап — из имён файлов);
   - шаг 2: обход страницы олимпиады `https://olimpiada.ru/activity/<id>` и её `/tasks`-подстраниц
     за каждый год (сбор всех PDF с метаданными: год/класс/этап/тип — задания|решения|критерии).
   Кэш: `work/source_index/<slug>.json` (TTL неделя, `OLYMP_INDEX_TTL_HOURS`;
   `--rebuild-index` — перестроить; `OLYMP_INDEX_CRAWL=0` — без обхода сайта).
   Физтех — id 395, Курчатов — 389; остальные id определяются по source в базе.
2. **Gemini через OdiRouter** — только если в индексе ничего не нашлось:
   grounding с `stream=True` (чанки идут сразу — nginx не рвёт соединение по 60 с),
   `web_search_options.search_context_size="low"`, компактный промт (≤ 400 токенов),
   таймаут клиента 55 с. Ручное управление: `ODIROUTER_WEB_SEARCH=0/1`, `ODIROUTER_MODEL=<id>`.
3. Найденный PDF скачивается, DeepSeek-chat извлекает нужную задачу по номеру/классу,
   DeepSeek-reasoner проверяет совпадение условия и ответа.
4. Все попытки логируются в `work/search_log.jsonl`: запрос, источник (index|gemini),
   URL, статус скачивания, результат проверки — видно, почему отказ.

## Ключи

```bash
export ODIROUTER_API_KEY=...    # OdiRouter (Gemini 3.6 Flash) — только поиск
export DEEPSEEK_API_KEY=...     # DeepSeek — чистка текста и математическая сверка
# необязательно:
export ODIROUTER_BASE_URL=https://odirouter.ai/api/v1
export ODIROUTER_MODEL=...      # id модели вручную (тогда /models не запрашивается)
export ODIROUTER_WEB_SEARCH=1   # 0 — выключить grounding, 1 — включить без пробы
```

При старте скрипт сам проверяет `GET /models` у OdiRouter (если путь другой —
подскажет; модель можно задать вручную через `ODIROUTER_MODEL`), находит модель
по подстроке `gemini-3.6-flash` (нет — напечатает список gemini-* и остановится)
и пробует web-search потоковым запросом (обходит 504-таймаут nginx); без него
Gemini возвращает URL-кандидатов, а скрипт сам скачивает документы (PDF через
pdfplumber/pypdf) и проверяет, что условие реально содержится в документе
(нечёткое совпадение ≥ 0.8).

## Установка

```bash
pip install -r requirements-olympfix.txt
```

## Порядок запуска (рекомендованный)

```bash
# 1. Смотрим, что изменится (API не вызывается, данные не трогаются)
python scripts/olymp_catalog_fix.py --stages 1-17 --dry-run

# 2. Чистим (результат — в data/olymp_catalog_fixed/, отчёт — в reports/)
python scripts/olymp_catalog_fix.py --stages 1-17

# 3. Поиск официальных решений и заполнение дыр (Gemini + DeepSeek)
python scripts/olymp_catalog_fix.py --stages 18-22 --slug phystech

# 4. После просмотра отчёта — применить к data/olymp_catalog/
#    (бэкап оригинала создаётся в backup/olymp_catalog_<дата>/)
python scripts/olymp_catalog_fix.py --apply
```

## Полезные флаги

| Флаг | Назначение |
|---|---|
| `--stages 1,3,5-9` или `all` | выбор этапов |
| `--slug phystech` | одна олимпиада |
| `--limit N` | ограничить число задач |
| `--dry-run` | без изменений данных и чекпоинта |
| `--workers 8` | параллельные потоки |
| `--resume` | продолжить с чекпоинта `work/checkpoint.json` |
| `--apply` | скопировать результат в `data/olymp_catalog/` с бэкапом |
| `--source <dir>` | каталог-источник (по умолчанию: `data/olymp_catalog_fixed`, если уже существует) |

## Что получается на выходе

- `data/olymp_catalog_fixed/` — исправленный каталог (оригинал не трогается до `--apply`);
- `reports/olymp_catalog_fix.md` — сводный отчёт по этапам, needs_review, токены;
- `reports/olymp_catalog_fix_diff.jsonl` — журнал изменений (uid, этап, поле, было, стало);
- `work/checkpoint.json` — чекпоинт идемпотентности (uid + этап + хеш входа);
- в каждую запись добавляется только поле `qa` (что исправлено, каким этапом, какой моделью, старые значения).

## Принципы безопасности

- Ничего не генерируется: официального решения нет — задача помечается (`needs_review`,
  `official_not_found`), а не сочиняется.
- LaTeX-инвариант: правки DeepSeek-chat сверяются deepseek-reasoner-ом; при сомнении —
  откат и пометка `needs_review`.
- Только официальные домены (olymp.mipt.ru, tasks.olimpiada.ru, rsr-olymp.ru,
  olympiads.mccme.ru, turgor.ru, vos.olimpiada.ru, olymp.msu.ru, olymp.hse.ru,
  kurchatov-olymp.ru, formulo.org, matol.ru, mathus.ru); reshimvse/otvet.mail.ru и
  подобные игнорируются.
- Конфликт ответов не разрешается автоматически: оба варианта пишутся в `qa`
  с пометкой `answer_conflict`.
- Повторный запуск не портит уже исправленное: чекпоинт по uid+этап с хешем входа,
  атомарная запись через временный файл.

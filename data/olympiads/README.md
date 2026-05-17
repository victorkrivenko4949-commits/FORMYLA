# Данные раздела «Олимпиады»

Эта папка содержит JSON-файлы для импорта данных в раздел `/olympiads/*`.

## Файлы

| Файл | Содержимое | Pydantic-схема |
|------|-----------|----------------|
| `<course>_theory.json`   | список теоретических блоков (методы) | [`TheoryBlockSchema`](../../schemas/olympiad.py) |
| `<course>_probniks.json` | список пробников (тематические + этапные) | [`ProbnikSchema`](../../schemas/olympiad.py) |
| `<course>_tasks.json`    | список задач, привязанных по `probnik_code` | [`TaskSchema`](../../schemas/olympiad.py) |

## Импорт

```bash
python scripts/import_olympiad.py \
    --probniks data/olympiads/vsosh_9_2027_probniks.json \
    --tasks    data/olympiads/vsosh_9_2027_tasks.json \
    --theory   data/olympiads/vsosh_9_2027_theory.json
```

Дополнительные флаги:

- `--dry-run` — только проверить JSON, ничего не писать в БД.
- `--reset --confirm` — стереть все 6 таблиц раздела перед импортом.

## Правила связности

1. `tasks[*].probnik_code` обязан существовать в `probniks.json`.
2. `probniks[*].theory[*].method_code` обязан существовать в `theory.json`.
3. Импорт **заменяет** задачи пробника целиком (файл — источник истины).
4. Повторный запуск идемпотентен: строки с тем же `code`/`method_code` обновятся.

## Тестовые стабы

Файлы `example_*.json` — минимальные валидные стабы, по одному пробнику
каждого типа. Используются:

- маршрутами раздела до прихода реальных данных,
- автотестами импортёра в `tests/test_olympiad_import.py`.

Полные данные «ВсОШ 9 класс, сезон 2027» (14 пробников / 204 задачи /
22 теоретических блока) загружает админ — отдельным коммитом с
`vsosh_9_2027_*.json`.

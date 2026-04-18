# Команды для миграции олимпиад в LaTeX

## 1. Тестовый прогон (уже выполнен)
```bash
python scripts/migrate_olympiads_to_latex.py
```
Это запустит тест на 3 случайных задачах.

## 2. Полная миграция всей базы

### Шаг 1: Откройте файл для редактирования
```bash
notepad scripts/migrate_olympiads_to_latex.py
```

### Шаг 2: Найдите строку 283 (в функции main):
```python
# Uncomment to run full migration:
# migrator.migrate_all(batch_size=10, output_file='olympiads_latex.json')
```

### Шаг 3: Раскомментируйте последнюю строку:
```python
# Uncomment to run full migration:
migrator.migrate_all(batch_size=10, output_file='olympiads_latex.json')
```

### Шаг 4: Сохраните файл и запустите:
```bash
python scripts/migrate_olympiads_to_latex.py
```

## Параметры миграции

- **batch_size=10** - обрабатывает по 10 олимпиад за раз, сохраняя чекпоинты
- **output_file='olympiads_latex.json'** - результат сохраняется в этот файл

## Что произойдет:

1. Скрипт обработает все 798 олимпиад из базы
2. Каждые 10 олимпиад будет сохраняться чекпоинт
3. Для каждой задачи:
   - Оригинальный текст останется в поле `text`
   - LaTeX-версия будет в поле `text_latex`
   - Оригинальное решение останется в поле `solution`
   - LaTeX-версия будет в поле `solution_latex`
4. Финальный результат сохранится в `olympiads_latex.json`

## Время выполнения

При ~5 задачах на олимпиаду и ~5 секунд на задачу:
- Всего задач: ~798 × 5 = ~3990 задач
- Время: ~3990 × 5 сек = ~5.5 часов

## Мониторинг прогресса

Скрипт выводит в консоль:
```
🏆 Олимпиада 1/798: Олимпиада Эйлера
   Год: 2009, Класс: 8
  📝 Problem 1/5: #1
    🔄 Converting problem text...
    🔄 Converting solution...
  📝 Problem 2/5: #2
    ...
💾 Сохранение чекпоинта (10 олимпиад)...
✅ Чекпоинт сохранен в olympiads_latex.json
```

## Безопасность

- ✅ Оригиналы НЕ удаляются (сохраняются в `text` и `solution`)
- ✅ Чекпоинты каждые 10 олимпиад (можно прервать и продолжить)
- ✅ Retry-логика при ошибках API (до 3 попыток)
- ✅ Exponential backoff при сбоях

## После миграции

Замените в `app.py` импорт:
```python
# Было:
from olympiads import OLYMPIADS_DB

# Станет:
import json
with open('olympiads_latex.json', 'r', encoding='utf-8') as f:
    OLYMPIADS_DB = json.load(f)
```

И используйте поля `text_latex` и `solution_latex` вместо `text` и `solution` при отображении.

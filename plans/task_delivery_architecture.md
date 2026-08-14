# Архитектура выдачи задач из банка (JSONL → TaskPool)

## Как это работает сейчас
1. Куратор выбирает 7 тем на месяц (build_or_get_cycle)
2. Каждый день = одна тема (day_index от started_at)
3. theme_probe — 5 зондирующих задач в дни 1-7
4. daily_task_rotation.pick_daily_set — подбирает задачи
5. Если нет в task_pool → вызывает DeepSeek-пайплайн (дорого, медленно)

## Как должно работать
Вместо вызова DeepSeek → тянем из пред-сгенерированного банка.

## Шаг 1: Загрузка JSONL в task_pool
Файл _all_tasks.jsonl → импорт в таблицу task_pool с полями:
- cache_key = f"{grade}:{topic}:{level}:{position}"
- grade, topic, level, position
- task_text, correct_answer
- subject (вычисляется из topic)

Загрузчик: scripts/import_bank_to_pool.py

## Шаг 2: Привязка к куратору
Когда pick_daily_set запрашивает задачи:
1. day_index → current_theme (из curator.monthly_cycle)
2. grade = user.preferred_grade
3. day_index 1-7: зонд находит тему, возвращает уровень сложности
4. Подбор из task_pool: WHERE grade=? AND topic=? AND level IN (?)
5. Раздача: L1(5 шт) в день 1 первой недели, остальные по уровню

## Шаг 3: Матрица выдачи

| Неделя | День | Задач | Из банка |
|--------|------|-------|----------|
| 1 | 1 | зонд 5 | L1 темы (5 задач) |
| 1 | 2-7 | зонд 5 + норма | L2-L4 по уровню |
| 2 | 8-14 | норма | L1-L4 по уровню |
| 3 | 15-21 | норма | L1-L4 по уровню |
| 4 | 22-28 | норма | L1-L4 по уровню |

## Шаг 4: Что менять в коде
1. daily_task_rotation.pick_daily_set — вместо вызова пайплайна → запрос к task_pool
2. task_pool — таблица уже есть (models.py), нужен импортёр
3. theme_probe — зонд уже ищет в adaptive_tasks, добавить task_pool
4. daily_tasks.services — _try_bank_first уже проверяет task_pool

## Фичи
- Нет задержки на генерацию (мгновенная выдача)
- Одинаковое качество (все задачи прошли аудит)
- Бесплатно (не тратит DeepSeek API)
- Кэш: один раз загрузили → всем пользователям

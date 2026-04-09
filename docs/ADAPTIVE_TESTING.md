# Адаптивное тестирование - FORMYLA

## 📋 Обзор

Система адаптивного тестирования использует принципы Item Response Theory (IRT) для подбора задач оптимальной сложности на основе текущего уровня пользователя.

## 🎯 Основные возможности

### 1. Интеллектуальный подбор задач
- **Оценка способностей**: Система оценивает уровень пользователя по шкале 1.0-7.0
- **Динамическая адаптация**: Сложность задач подстраивается после каждого ответа
- **Информационная ценность**: Выбираются задачи, дающие максимум информации о способностях

### 2. Алгоритм работы

#### Начальная оценка
```python
# Если есть история - анализируем последние 10 попыток
# Если нет - начинаем с уровня 3.5 (средний)
initial_ability = engine.estimate_user_ability(user_history)
```

#### Выбор задачи
```python
# Рассчитываем информационную ценность для каждой задачи
information_value = exp(-0.5 * (difficulty - ability)²)

# Учитываем разнообразие тем (до 30% штрафа за повторы)
total_score = information_value * topic_diversity_bonus

# Выбираем из топ-5 кандидатов с весовой случайностью
```

#### Обновление способностей
```python
# После правильного ответа - увеличиваем способность
# После неправильного - уменьшаем
# Величина изменения зависит от "неожиданности" результата
adjustment = 0.3 + surprise * 0.2
```

## 🗄️ Структура базы данных

### AdaptiveTest
```python
- id: Integer (PK)
- user_id: Integer (FK -> users.id)
- subject: String (опционально)
- grade: Integer (опционально)
- num_problems: Integer (по умолчанию 10)
- initial_ability: Float (начальный уровень)
- current_ability: Float (текущий уровень)
- status: String (in_progress, completed, analyzing)
- final_ability: Float (финальный уровень)
- total_correct: Integer (правильных ответов)
- accuracy: Float (процент правильных)
- ai_analysis: Text (AI анализ результатов)
```

### AdaptiveTestProblem
```python
- id: Integer (PK)
- test_id: Integer (FK -> adaptive_tests.id)
- problem_id: Integer (ID из PROBLEMS_DB)
- sequence_number: Integer (порядковый номер)
- user_ability_before: Float (способность до ответа)
- problem_difficulty: Float (сложность задачи)
- user_answer: String (ответ пользователя)
- user_solution_text: Text (решение)
- is_correct: Boolean (правильность)
- answered_at: DateTime (время ответа)
- user_ability_after: Float (способность после ответа)
- ai_feedback: Text (комментарий AI)
```

## 🔌 API Endpoints

### POST /api/adaptive-test/start
Создать новый адаптивный тест

**Request:**
```json
{
  "subject": "algebra",  // опционально
  "grade": 9,            // опционально
  "num_problems": 10     // по умолчанию 10
}
```

**Response:**
```json
{
  "test_id": 123,
  "problem": {...},
  "current_number": 1,
  "total_problems": 10,
  "current_ability": 3.5
}
```

### POST /api/adaptive-test/<test_id>/submit
Отправить ответ на задачу

**Request:**
```json
{
  "problem_id": 456,
  "answer": "42",
  "solution": "Решение..."
}
```

**Response:**
```json
{
  "is_correct": true,
  "correct_answer": "42",
  "current_ability": 4.2,
  "answered_count": 5,
  "total_problems": 10,
  "next_problem": {...},  // если есть
  "next_number": 6,
  "test_completed": false
}
```

### POST /api/adaptive-test/<test_id>/analyze
Анализ результатов с помощью AI

**Response:**
```json
{
  "analysis": {
    "final_ability": 4.5,
    "total_correct": 7,
    "total_problems": 10,
    "accuracy": 70.0,
    "strengths": ["algebra", "geometry"],
    "weaknesses": ["combinatorics"],
    "recommended_topics": ["combinatorics"],
    "topic_performance": {...}
  },
  "ai_analysis": "Персональный анализ от AI..."
}
```

### GET /adaptive-test/<test_id>
Страница прохождения теста

### GET /adaptive-test/<test_id>/results
Страница результатов теста

## 🎨 Frontend компоненты

### templates/adaptive_test.html
- Интерактивная страница прохождения теста
- Отображение текущего уровня и прогресса
- Динамическая загрузка задач
- Мгновенная обратная связь после ответа

### templates/adaptive_test_results.html
- Детальная статистика
- График динамики способностей (Chart.js)
- AI анализ результатов
- Разбор каждой задачи

### templates/index.html
- Кнопка "🎯 Адаптивный тест (10 задач)"
- Выбор класса для фильтрации задач

## 🧠 Алгоритмические особенности

### Оценка информационной ценности
Задачи, близкие к текущему уровню пользователя, дают больше информации:
```
I(θ, b) = exp(-0.5 * (b - θ)²)
где θ - способность пользователя, b - сложность задачи
```

### Разнообразие тем
Система штрафует повторное использование одних и тех же тем:
```
penalty = 1.0 - topic_frequency * 0.3
```

### Взвешенная история
Более свежие результаты имеют больший вес при оценке способностей:
```
weight = (position + 1) / total_attempts
```

## 🔧 Интеграция с DeepSeek API

### Таймауты
```python
client = DeepSeekClient()
# Встроенные таймауты: 60 секунд
# Автоматические повторы: до 5 попыток
# Экспоненциальная задержка: 2, 4, 8, 16, 32 секунды
```

### AI Анализ результатов
```python
prompt = f"""Проанализируй результаты адаптивного теста:
- Правильных: {correct}/{total}
- Точность: {accuracy}%
- Финальный уровень: {ability}/7.0
- Сильные стороны: {strengths}
- Слабые стороны: {weaknesses}
"""

ai_analysis = client.generate(
    prompt=prompt,
    system_prompt="Ты опытный преподаватель математики...",
    temperature=0.7,
    max_tokens=500
)
```

## 📊 Метрики и аналитика

### Для пользователя
- Финальный уровень способностей (1.0-7.0)
- Процент правильных ответов
- Динамика изменения уровня
- Сильные и слабые темы
- Персональные рекомендации

### Для системы
- История всех тестов пользователя
- Прогресс по темам
- Эффективность подбора задач
- Время на задачу

## 🚀 Использование

### Для пользователя
1. Нажать "🎯 Адаптивный тест" на главной
2. Выбрать класс (опционально)
3. Решать задачи последовательно
4. Получить детальный анализ результатов

### Для разработчика
```python
from services.adaptive_test import AdaptiveTestEngine
from problems import PROBLEMS_DB

# Создать движок
engine = AdaptiveTestEngine(PROBLEMS_DB)

# Оценить способность
ability = engine.estimate_user_ability(history)

# Выбрать задачу
problem = engine.select_next_problem(
    user_ability=ability,
    subject='algebra',
    grade=9,
    excluded_ids=[1, 2, 3]
)

# Обновить способность после ответа
new_ability = engine.update_ability_after_answer(
    current_ability=ability,
    problem_difficulty=5.0,
    is_correct=True
)

# Проанализировать результаты
analysis = engine.analyze_test_results(problems, answers)
```

## 🔍 Отладка

### Логирование
```python
import logging
logger = logging.getLogger('services.adaptive_test')
logger.setLevel(logging.DEBUG)
```

### Проверка импортов
```bash
python -c "from services.adaptive_test import AdaptiveTestEngine; print('OK')"
python -c "from models import AdaptiveTest, AdaptiveTestProblem; print('OK')"
```

### Тестирование API
```bash
# Создать тест
curl -X POST http://localhost:5000/api/adaptive-test/start \
  -H "Content-Type: application/json" \
  -d '{"grade": 9, "num_problems": 10}'

# Отправить ответ
curl -X POST http://localhost:5000/api/adaptive-test/1/submit \
  -H "Content-Type: application/json" \
  -d '{"problem_id": 123, "answer": "42"}'

# Анализ
curl -X POST http://localhost:5000/api/adaptive-test/1/analyze
```

## 📝 TODO / Улучшения

- [ ] Кэширование часто используемых задач
- [ ] Предзагрузка следующей задачи
- [ ] Статистика по времени решения
- [ ] Адаптивные подсказки
- [ ] Мультипредметные тесты
- [ ] Экспорт результатов в PDF
- [ ] Сравнение с другими пользователями
- [ ] Рекомендации по учебным материалам

## 🎓 Научная основа

Система основана на Item Response Theory (IRT):
- Rasch Model для оценки способностей
- Maximum Information Selection для выбора задач
- Bayesian updating для динамической адаптации

**Литература:**
- Lord, F. M. (1980). Applications of Item Response Theory
- van der Linden, W. J. (2016). Handbook of Item Response Theory
- Embretson, S. E., & Reise, S. P. (2000). Item Response Theory for Psychologists

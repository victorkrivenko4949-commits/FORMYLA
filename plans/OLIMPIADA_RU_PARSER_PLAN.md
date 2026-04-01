# 📋 План парсинга задач с olimpiada.ru

## 🎯 Цель

Скопировать все задачи и решения с сайта **olimpiada.ru** - крупнейшей базы олимпиадных задач в России.

## 🔍 Анализ сайта

### Структура olimpiada.ru

**Главная:** https://olimpiada.ru/

**Разделы:**
- Задачи по предметам: https://olimpiada.ru/tasks
- Архив олимпиад: https://olimpiada.ru/activities
- Задачи с решениями

### Что можно получить:
- ✅ Условия задач
- ✅ Ответы
- ✅ Решения (не для всех)
- ✅ Класс, предмет, олимпиада
- ✅ Год, этап

## 📝 Подробный план

### Этап 1: Исследование (1-2 часа)

#### 1.1 Изучить структуру URL
```
https://olimpiada.ru/task/[ID]
https://olimpiada.ru/activity/[OLYMPIAD_ID]/tasks
```

#### 1.2 Проверить robots.txt
```
https://olimpiada.ru/robots.txt
```

Убедиться что парсинг разрешен

#### 1.3 Изучить HTML структуру
- Открыть несколько страниц с задачами
- Найти CSS селекторы для:
  - Условия задачи
  - Ответа
  - Решения
  - Метаданных (класс, предмет)

### Этап 2: Создание парсера (2-3 часа)

#### 2.1 Установить зависимости
```bash
pip install beautifulsoup4 requests lxml
```

#### 2.2 Создать `scripts/olimpiada_parser.py`

**Функции:**
- `get_task_list()` - получить список ID задач
- `parse_task(task_id)` - спарсить одну задачу
- `save_to_db()` - сохранить в формат PROBLEMS_DB

**Структура:**
```python
import requests
from bs4 import BeautifulSoup
import time
import json

def get_task_list(subject, grade, limit=100):
    """Получить список задач по фильтрам"""
    url = f"https://olimpiada.ru/tasks?subject={subject}&grade={grade}"
    # Парсинг списка
    return task_ids

def parse_task(task_id):
    """Спарсить одну задачу"""
    url = f"https://olimpiada.ru/task/{task_id}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Извлечь данные
    task = {
        'text': soup.select_one('.task-text').text,
        'answer': soup.select_one('.task-answer').text,
        'solution': soup.select_one('.task-solution').text,
        # и т.д.
    }
    return task

def main():
    tasks = []
    for task_id in get_task_list():
        task = parse_task(task_id)
        tasks.append(task)
        time.sleep(1)  # Задержка между запросами
    
    save_to_json(tasks)
```

#### 2.3 Добавить обработку ошибок
- Retry при ошибках сети
- Пропуск задач без решений
- Логирование прогресса

### Этап 3: Массовый парсинг (несколько часов)

#### 3.1 Парсинг по разделам
```python
subjects = ['math', 'informatics']
grades = range(5, 12)

for subject in subjects:
    for grade in grades:
        tasks = parse_subject_grade(subject, grade)
        save_checkpoint(subject, grade, tasks)
```

#### 3.2 Checkpoint система
Сохранять прогресс каждые 100 задач, чтобы при сбое не потерять данные

#### 3.3 Rate limiting
- Задержка 1-2 секунды между запросами
- Не более 1000 запросов в час

### Этап 4: Обработка данных (1-2 часа)

#### 4.1 Очистка текста
- Удалить HTML теги
- Форматировать формулы (LaTeX)
- Убрать лишние пробелы

#### 4.2 Классификация
- Определить subject (algebra, geometry и т.д.)
- Определить subtopic
- Оценить difficulty (1-7)

#### 4.3 Дедупликация
Проверить на дубликаты с текущей базой

### Этап 5: Интеграция (30 минут)

#### 5.1 Конвертация в формат FORMYLA
```python
{
    "subject": "algebra",
    "subtopic": "equations",
    "grade": 5,
    "difficulty": 3,
    "title": "Задача с olimpiada.ru",
    "text": "...",
    "answer": "...",
    "solution": "...",
    "source": "olimpiada.ru",
    "source_dataset": "olimpiada_ru",
    "id": 12345
}
```

#### 5.2 Добавление в problems.py
Объединить с текущей базой

## ⚠️ Важные моменты

### Юридические
- ✅ Проверить лицензию сайта
- ✅ Указать источник в каждой задаче
- ✅ Не нарушать robots.txt

### Технические
- ✅ Использовать User-Agent
- ✅ Задержки между запросами
- ✅ Обработка капчи (если есть)
- ✅ Сохранение прогресса

### Качество
- ✅ Проверка полноты данных
- ✅ Валидация формата
- ✅ Ручная проверка примеров

## 📊 Ожидаемый результат

- **Задач:** 5,000-10,000+ (зависит от доступности)
- **Качество:** Высокое (официальные олимпиады)
- **Решения:** Есть для многих задач
- **Время:** 1-2 дня полного парсинга

## 🚀 Быстрый старт

### Минимальный парсер (для теста)

```python
import requests
from bs4 import BeautifulSoup

# Тестовая задача
url = "https://olimpiada.ru/task/12345"
response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')

# Извлечь данные
print(soup.prettify())  # Посмотреть структуру
```

## 💡 Альтернативы

### Если парсинг сложен:
1. **API olimpiada.ru** - проверить есть ли официальное API
2. **Датасеты** - поискать готовые датасеты на HuggingFace
3. **Ручной сбор** - скопировать самые важные задачи вручную

## ✅ Рекомендация

Начните с **тестового парсинга 10-20 задач**, чтобы:
- Понять структуру сайта
- Проверить качество данных
- Оценить время парсинга

Потом масштабируйте на всю базу!

---

**Хотите чтобы я создал тестовый парсер для olimpiada.ru?**
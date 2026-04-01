# -*- coding: utf-8 -*-
"""
Генерация подробного промпта для AI с точным списком недостающих задач
"""
import json
import sys
import codecs

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# Читаем список недостающих задач
with open('data/missing_tasks.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

missing = data['missing_tasks']
total_needed = data['summary']['total_tasks_needed']

# Создаем промпт
prompt = f"""# ПРОМПТ ДЛЯ ГЕНЕРАЦИИ {total_needed} МАТЕМАТИЧЕСКИХ ЗАДАЧ

## КОНТЕКСТ
Я создаю образовательную платформу FORMYLA для подготовки школьников к олимпиадам по математике. 
Мне нужно сгенерировать **{total_needed} уникальных олимпиадных задач** для заполнения базы данных.

## ⚠️ КРИТИЧЕСКИ ВАЖНО
1. **ВСЕ {total_needed} ЗАДАЧИ ДОЛЖНЫ БЫТЬ АБСОЛЮТНО УНИКАЛЬНЫМИ** - никаких повторений или похожих формулировок
2. Каждая задача должна быть интересной и нестандартной
3. Задачи должны соответствовать олимпиадному уровню, а не школьной программе
4. Решения должны быть подробными и понятными (но не слишком длинными)

## СТРУКТУРА КАЖДОЙ ЗАДАЧИ

Каждая задача должна быть в формате JSON:
```json
{{
  "id": [уникальный номер, начиная с 7541],
  "subject": "[subject из списка ниже]",
  "subtopic": "[subtopic из списка ниже]",
  "grade": [класс от 5 до 11],
  "difficulty": [уровень от 1 до 10],
  "title": "Краткое название (2-5 слов)",
  "text": "Полное условие задачи (не более 300 символов)",
  "answer": "Краткий ответ",
  "solution": "Подробное пошаговое решение (не более 500 символов)",
  "source": "AI",
  "source_dataset": "generated"
}}
```

## ТОЧНЫЙ СПИСОК ВСЕХ {len(missing)} ЯЧЕЕК, ДЛЯ КОТОРЫХ НУЖНЫ ЗАДАЧИ

Ниже приведен ПОЛНЫЙ список. Для каждой ячейки указано ТОЧНОЕ количество задач.
ВАЖНО: Сгенерируй РОВНО столько задач, сколько указано в колонке "Нужно задач".

"""

# Группируем по разделам и подтемам
current_subject = None
current_subtopic = None
task_counter = 0

for i, task in enumerate(missing, 1):
    subject = task['subject']
    subject_title = task['subject_title']
    subtopic = task['subtopic']
    subtopic_title = task['subtopic_title']
    grade = task['grade']
    level = task['level']
    needed = task['needed']
    
    # Новый раздел
    if subject != current_subject:
        prompt += f"\n### {subject_title.upper()} (subject=\"{subject}\")\n"
        current_subject = subject
        current_subtopic = None
    
    # Новая подтема
    if subtopic != current_subtopic:
        prompt += f"\n#### {subtopic_title} (subtopic=\"{subtopic}\")\n\n"
        current_subtopic = subtopic
    
    # Добавляем ячейку
    prompt += f"{i}. Класс {grade}, Уровень {level}: **{needed} задач** (subject=\"{subject}\", subtopic=\"{subtopic}\", grade={grade}, difficulty={level})\n"
    task_counter += needed

prompt += f"""

## ИТОГО
- **Всего ячеек:** {len(missing)}
- **Всего задач:** {total_needed}
- **Начальный ID:** 7541 (первые 40 уже сгенерированы)
- **Конечный ID:** {7541 + total_needed - 1}

## ТРЕБОВАНИЯ К КАЧЕСТВУ

### Уровни сложности:
- **1-3:** Простые задачи для начинающих (базовые понятия)
- **4-6:** Средняя сложность (требуют размышления)
- **7-8:** Сложные задачи (олимпиадный уровень)
- **9-10:** Очень сложные (региональные/заключительные олимпиады)

### Темы:

**Алгебра:**
- equations: Уравнения, системы уравнений, алгебраические преобразования
- inequalities: Неравенства, оценки, метод интервалов, AM-GM
- text_problems: Задачи на проценты, движение, работу, смеси

**Геометрия:**
- basics: Углы, отрезки, площади, периметры, многоугольники
- triangles: Свойства треугольников, теоремы синусов/косинусов, подобие
- circles: Окружности, касательные, вписанные/описанные окружности

**Комбинаторика:**
- dirichlet_and_graphs: Принцип Дирихле, графы, раскраски
- games: Игры, выигрышные стратегии, инварианты

**Теория чисел:**
- divisibility: Делимость, НОД, НОК, остатки, сравнения
- primes_and_equations: Простые числа, диофантовы уравнения

**Движение:**
- movement_all: Задачи на движение (скорость, время, расстояние)

**Логика:**
- logic_all: Рыцари и лжецы, логические задачи

## ФОРМАТ ОТВЕТА

Верни ВСЕ {total_needed} задачи в виде JSON-массива:

```json
[
  {{
    "id": 7541,
    "subject": "algebra",
    "subtopic": "equations",
    "grade": 5,
    "difficulty": 6,
    "title": "Возрасты братьев",
    "text": "Три брата родились с интервалом в 2 года. Сумма их возрастов сейчас равна 39 годам. Сколько лет каждому брату?",
    "answer": "11 лет, 13 лет, 15 лет",
    "solution": "Пусть возраст среднего брата равен x лет. Тогда младшему x-2 года, старшему x+2 года. Уравнение: (x-2)+x+(x+2)=39, 3x=39, x=13. Младшему 11, среднему 13, старшему 15 лет.",
    "source": "AI",
    "source_dataset": "generated"
  }},
  ... (еще {total_needed - 1} задач)
]
```

## ⚡ НАЧИНАЙ ГЕНЕРАЦИЮ!

Сгенерируй ВСЕ {total_needed} задач строго по списку выше. 
Каждая задача должна быть УНИКАЛЬНОЙ и соответствовать указанному разделу, подтеме, классу и уровню сложности.
"""

# Сохраняем промпт
with open('data/FULL_PROMPT_FOR_AI.txt', 'w', encoding='utf-8') as f:
    f.write(prompt)

print("✅ Промпт сгенерирован!")
print(f"📄 Файл: data/FULL_PROMPT_FOR_AI.txt")
print(f"📊 Всего ячеек: {len(missing)}")
print(f"📝 Всего задач: {total_needed}")
print(f"\nСкопируйте содержимое файла и вставьте в Perplexity/Claude/GPT-4")

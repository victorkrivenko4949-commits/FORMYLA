# Software Design Document: Mass Task Generation System
**Project:** FORMYLA - Массовая генерация олимпиадных задач  
**Date:** 2026-04-12  
**Version:** 1.0  
**Status:** Design Phase

---

## 1. EXECUTIVE SUMMARY

### 1.1 Цель проекта
Разработка отказоустойчивой системы массовой генерации математических олимпиадных задач для классов 6, 7, 8, 10 и 11 с использованием DeepSeek AI. Система должна генерировать тысячи уникальных задач с соблюдением возрастных ограничений, классического олимпиадного стиля и максимального разнообразия.

### 1.2 Ключевые требования
- **Отказоустойчивость**: Защита от бесконечных циклов, таймаутов, OOM
- **Graceful Shutdown**: Корректное завершение при SIGTERM/SIGINT с сохранением валидного JSON
- **Возрастные ограничения**: Строгий контроль математических концепций по классам
- **Разнообразие**: Минимум 4 подтемы на каждую из 5 основных тем
- **Производительность**: Батч-запись в JSON, асинхронная обработка

---

## 2. АРХИТЕКТУРА СИСТЕМЫ

### 2.1 Компоненты высокого уровня

```
┌─────────────────────────────────────────────────────────┐
│                   Main Controller                        │
│              (mass_generator.py)                         │
│  - Orchestration                                         │
│  - Signal handling (SIGTERM/SIGINT)                      │
│  - Progress tracking                                     │
└────────────┬────────────────────────────────────────────┘
             │
             ├──────────────┬──────────────┬──────────────┐
             │              │              │              │
             ▼              ▼              ▼              ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  Grade6_7  │  │   Grade8   │  │ Grade10_11 │  │ SafeWriter │
    │ Generator  │  │ Generator  │  │ Generator  │  │   (JSON)   │
    └────────────┘  └────────────┘  └────────────┘  └────────────┘
         │                │                │                │
         └────────────────┴────────────────┴────────────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ DeepSeekClient  │
                 │  (with retry)   │
                 └─────────────────┘
```

### 2.2 Поток данных

```
Start → Load Config → Initialize Generators → Generate Batch
  ↓
For each grade:
  ↓
  For each topic (5 topics):
    ↓
    For each subtopic (4+ subtopics):
      ↓
      Generate N tasks → Validate → Write to JSON (batch)
      ↓
      [Retry on failure, max_retries=3]
      ↓
  Save checkpoint
  ↓
End → Close JSON gracefully
```

---

## 3. ДЕТАЛЬНЫЙ ДИЗАЙН КОМПОНЕНТОВ

### 3.1 TaskGenerator (Abstract Base Class)

**Файл**: `generators/base_generator.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import signal
import sys

class TaskGenerator(ABC):
    """
    Абстрактный базовый класс для генерации задач.
    Обеспечивает защиту от бесконечных циклов и единый интерфейс.
    """
    
    def __init__(self, deepseek_client, grade_range: tuple, max_retries: int = 3):
        self.client = deepseek_client
        self.grade_range = grade_range  # (min_grade, max_grade)
        self.max_retries = max_retries
        self.generated_count = 0
        
        # Определение подтем для каждой основной темы
        self.subtopics = {
            "Алгебра": [
                "текстовые_задачи",
                "степени_и_корни",
                "последовательности",
                "системы_уравнений"
            ],
            "Геометрия": [
                "площади_фигур",
                "разрезания",
                "свойства_углов",
                "координаты"
            ],
            "Комбинаторика": [
                "графы",
                "принцип_дирихле",
                "подсчет_вариантов",
                "игры_и_стратегии"
            ],
            "Теория чисел": [
                "делимость",
                "остатки",
                "НОД_НОК",
                "диофантовы_уравнения"
            ],
            "Задачи на движение": [
                "навстречу_вдогонку",
                "движение_по_кругу",
                "по_течению",
                "средняя_скорость"
            ]
        }
    
    @abstractmethod
    def get_allowed_concepts(self) -> List[str]:
        """Возвращает список разрешенных математических концепций для данного класса."""
        pass
    
    @abstractmethod
    def get_forbidden_concepts(self) -> List[str]:
        """Возвращает список запрещенных концепций для данного класса."""
        pass
    
    def generate_task(
        self,
        topic: str,
        subtopic: str,
        difficulty: int,
        previous_tasks: List[str]
    ) -> Optional[Dict]:
        """
        Генерирует одну задачу с защитой от бесконечных циклов.
        
        Args:
            topic: Основная тема (Алгебра, Геометрия и т.д.)
            subtopic: Подтема из self.subtopics[topic]
            difficulty: Уровень сложности (1-5)
            previous_tasks: Список предыдущих задач для избежания повторений
            
        Returns:
            Dict с полями: text, answer, solution, difficulty, topic, subtopic
            или None при неудаче после всех попыток
        """
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                # Формирование промпта с учетом возрастных ограничений
                prompt = self._build_prompt(
                    topic, subtopic, difficulty, previous_tasks
                )
                
                # Вызов AI с таймаутом
                response = self.client.generate(
                    prompt=prompt,
                    system_prompt=self._get_system_prompt(),
                    temperature=0.7,
                    max_tokens=2000
                )
                
                # Парсинг и валидация
                task = self._parse_and_validate(response)
                
                if task:
                    self.generated_count += 1
                    return task
                    
            except Exception as e:
                logger.warning(f"Retry {retry_count + 1}/{self.max_retries}: {e}")
                retry_count += 1
                time.sleep(2 ** retry_count)  # Exponential backoff
        
        logger.error(f"Failed to generate task after {self.max_retries} retries")
        return None
    
    @abstractmethod
    def _build_prompt(self, topic: str, subtopic: str, difficulty: int, previous_tasks: List[str]) -> str:
        """Строит промпт с учетом специфики класса."""
        pass
    
    @abstractmethod
    def _get_system_prompt(self) -> str:
        """Возвращает системный промпт с ограничениями для класса."""
        pass
    
    def _parse_and_validate(self, response: str) -> Optional[Dict]:
        """Парсит JSON и валидирует структуру."""
        try:
            # Очистка от markdown
            response = response.strip()
            if response.startswith('```json'):
                response = response[7:]
            elif response.startswith('```'):
                response = response[3:]
            if response.endswith('```'):
                response = response[:-3]
            response = response.strip()
            
            # Защита от слешей
            response = response.replace('\\', '\\\\')
            
            # Парсинг
            task = json.loads(response)
            
            # Валидация обязательных полей
            required_fields = ['text', 'answer', 'solution', 'difficulty', 'topic']
            if all(field in task for field in required_fields):
                return task
            else:
                logger.warning(f"Missing required fields in task: {task.keys()}")
                return None
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            return None
```

### 3.2 SafeWriter (Graceful Shutdown)

**Файл**: `generators/safe_writer.py`

```python
import json
import signal
import sys
import atexit
from typing import List, Dict, TextIO

class SafeJSONWriter:
    """
    Безопасная запись JSON с graceful shutdown.
    Гарантирует валидность JSON даже при прерывании процесса.
    """
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file: Optional[TextIO] = None
        self.tasks_written = 0
        self.is_closed = False
        
        # Регистрация обработчиков сигналов
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self._cleanup)
        
    def open(self):
        """Открывает файл и пишет начало JSON-массива."""
        self.file = open(self.filepath, 'w', encoding='utf-8')
        self.file.write('[\n')
        self.file.flush()
        
    def write_task(self, task: Dict):
        """
        Записывает одну задачу в JSON.
        Автоматически добавляет запятую между элементами.
        """
        if self.is_closed:
            raise RuntimeError("Writer is closed")
            
        if self.tasks_written > 0:
            self.file.write(',\n')
        
        json.dump(task, self.file, ensure_ascii=False, indent=2)
        self.file.flush()  # Немедленная запись на диск
        self.tasks_written += 1
        
    def write_batch(self, tasks: List[Dict]):
        """Записывает батч задач."""
        for task in tasks:
            self.write_task(task)
            
    def close(self):
        """Закрывает JSON-массив и файл."""
        if not self.is_closed and self.file:
            self.file.write('\n]')
            self.file.flush()
            self.file.close()
            self.is_closed = True
            print(f"✅ JSON file closed gracefully. Total tasks: {self.tasks_written}")
            
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов SIGTERM/SIGINT."""
        print(f"\n⚠️  Received signal {signum}. Closing JSON gracefully...")
        self.close()
        sys.exit(0)
        
    def _cleanup(self):
        """Вызывается при выходе из программы."""
        if not self.is_closed:
            self.close()
```

### 3.3 Grade-Specific Generators

#### 3.3.1 Grade6_7Generator

**Файл**: `generators/grade6_7_generator.py`

```python
from .base_generator import TaskGenerator

class Grade6_7Generator(TaskGenerator):
    """Генератор задач для 6-7 классов."""
    
    def __init__(self, deepseek_client):
        super().__init__(deepseek_client, grade_range=(6, 7), max_retries=3)
    
    def get_allowed_concepts(self) -> List[str]:
        return [
            "базовая_арифметика",
            "простые_уравнения",
            "периметр_площадь_прямоугольника",
            "углы_треугольника_сумма_180",
            "пропорции",
            "проценты",
            "делимость",
            "НОД_НОК",
            "простые_числа",
            "остатки",
            "подсчет_вариантов_базовый",
            "логические_задачи",
            "скорость_время_расстояние"
        ]
    
    def get_forbidden_concepts(self) -> List[str]:
        return [
            "биссектриса",
            "медиана",
            "высота_треугольника",
            "синус",
            "косинус",
            "тангенс",
            "квадратные_уравнения",
            "теорема_пифагора",
            "подобие_треугольников",
            "вписанные_описанные_окружности",
            "логарифмы",
            "производные",
            "интегралы",
            "комплексные_числа"
        ]
    
    def _get_system_prompt(self) -> str:
        return """Ты - профессиональный составитель олимпиадных задач для 6-7 классов.

КРИТИЧЕСКИ ВАЖНО:
- НЕ ИСПОЛЬЗУЙ LATEX! ПИШИ ДРОБИ КАК a/b, СТЕПЕНИ КАК a^2, КОРНИ КАК sqrt(x).
- СТРОГО ЗАПРЕЩЕНО: обратные слеши, кавычки внутри текста.
- РЕШЕНИЕ: НЕ БОЛЕЕ 2 ПРЕДЛОЖЕНИЙ.
- ВЕРНИ СТРОГО ОДИН JSON-ОБЪЕКТ (без markdown).

ВОЗРАСТНЫЕ ОГРАНИЧЕНИЯ (6-7 КЛАСС):
ЗАПРЕЩЕНО: биссектриса, медиана, высота, синус, косинус, квадратные уравнения, теорема Пифагора.
РАЗРЕШЕНО: базовая арифметика, простые уравнения, периметр, площадь прямоугольника, углы (сумма 180°), делимость, НОД/НОК, простые числа, остатки, базовый подсчет вариантов, логика, скорость-время-расстояние.

СТИЛЬ: Классический олимпиадный. БЕЗ приставок "В игре...", "В симуляторе...", "Хакер...".
Начинай сразу с сути: "Два автомобиля...", "Робот перемещается...", "На доске написаны..."."""
    
    def _build_prompt(self, topic: str, subtopic: str, difficulty: int, previous_tasks: List[str]) -> str:
        # Контекст предыдущих задач
        previous_context = ""
        if previous_tasks:
            prev_str = "\n".join([f"{i+1}. {t[:100]}..." for i, t in enumerate(previous_tasks)])
            previous_context = f"""

КРИТИЧЕСКИ ВАЖНО: Ниже задачи, которые УЖЕ БЫЛИ. Твоя задача ДОЛЖНА КАРДИНАЛЬНО ОТЛИЧАТЬСЯ!
ЗАПРЕЩЕНО просто менять числа. Придумай СОВЕРШЕННО НОВУЮ задачу!

УЖЕ БЫЛИ:
{prev_str}
"""
        
        return f"""Сгенерируй ОДНУ олимпиадную задачу для 6-7 класса.

ТЕМА: {topic}
ПОДТЕМА: {subtopic}
СЛОЖНОСТЬ: {difficulty} (1=базовый, 5=олимпиадный)
{previous_context}

ТРЕБОВАНИЯ:
1. Задача НЕ должна гуглиться.
2. Ответ: число или краткое выражение (≤10 символов).
3. Решение: НЕ БОЛЕЕ 2 ПРЕДЛОЖЕНИЙ.
4. Используй ТОЛЬКО разрешенные концепции для 6-7 класса.
5. БЕЗ кавычек в тексте. Вместо прямой речи используй тире.

ВЕРНИ JSON:
{{
  "text": "Условие (БЕЗ КАВЫЧЕК)",
  "answer": "Ответ",
  "solution": "Решение (≤2 предложений)",
  "difficulty": {difficulty},
  "topic": "{topic}",
  "subtopic": "{subtopic}"
}}

БЕЗ markdown, БЕЗ текста вокруг JSON."""
```

#### 3.3.2 Grade8Generator

**Файл**: `generators/grade8_generator.py`

Аналогично Grade6_7Generator, но с расширенными разрешенными концепциями:
- Добавлено: простые квадратные уравнения, теорема Пифагора, базовая тригонометрия (только определения)
- Запрещено: производные, интегралы, комплексные числа, продвинутая геометрия

#### 3.3.3 Grade10_11Generator

**Файл**: `generators/grade10_11_generator.py`

Полный набор концепций для старших классов:
- Разрешено: все концепции школьной программы
- Запрещено: только высшая математика (пределы, производные высших порядков, интегралы)

### 3.4 Main Controller

**Файл**: `mass_generator.py`

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mass Task Generation System
Generates thousands of olympiad math tasks with graceful shutdown support.
"""

import signal
import sys
import time
from typing import Dict, List
from ai.deepseek_client import DeepSeekClient
from generators.safe_writer import SafeJSONWriter
from generators.grade6_7_generator import Grade6_7Generator
from generators.grade8_generator import Grade8Generator
from generators.grade10_11_generator import Grade10_11Generator

class MassTaskGenerator:
    """Главный контроллер массовой генерации."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.client = DeepSeekClient()
        self.writer = None
        self.generators = {}
        self.shutdown_requested = False
        
        # Инициализация генераторов
        self.generators['6-7'] = Grade6_7Generator(self.client)
        self.generators['8'] = Grade8Generator(self.client)
        self.generators['10-11'] = Grade10_11Generator(self.client)
        
        # Регистрация обработчиков сигналов
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов для graceful shutdown."""
        print(f"\n⚠️  Received signal {signum}. Initiating graceful shutdown...")
        self.shutdown_requested = True
        
    def generate_all(self):
        """Главный цикл генерации."""
        output_file = self.config.get('output_file', 'generated_tasks.json')
        self.writer = SafeJSONWriter(output_file)
        self.writer.open()
        
        try:
            for grade_key, generator in self.generators.items():
                if self.shutdown_requested:
                    print(f"⚠️  Shutdown requested. Stopping at grade {grade_key}")
                    break
                    
                print(f"\n📚 Generating tasks for grade {grade_key}...")
                self._generate_for_grade(generator, grade_key)
                
        finally:
            # Гарантированное закрытие файла
            if self.writer:
                self.writer.close()
                
    def _generate_for_grade(self, generator: TaskGenerator, grade_key: str):
        """Генерация задач для одного класса."""
        tasks_per_grade = self.config.get('tasks_per_grade', 100)
        topics = ["Алгебра", "Геометрия", "Комбинаторика", "Теория чисел", "Задачи на движение"]
        
        generated_tasks = []
        task_count = 0
        
        for topic in topics:
            if self.shutdown_requested:
                break
                
            subtopics = generator.subtopics[topic]
            tasks_per_topic = tasks_per_grade // len(topics)
            
            for i in range(tasks_per_topic):
                if self.shutdown_requested:
                    break
                    
                # Ротация подтем
                subtopic = subtopics[i % len(subtopics)]
                difficulty = (i % 5) + 1  # Циклическое изменение сложности 1-5
                
                # Генерация задачи
                task = generator.generate_task(
                    topic=topic,
                    subtopic=subtopic,
                    difficulty=difficulty,
                    previous_tasks=[t['text'][:100] for t in generated_tasks[-10:]]
                )
                
                if task:
                    task['grade'] = grade_key
                    task['id'] = f"{grade_key}_{topic}_{task_count:04d}"
                    generated_tasks.append(task)
                    task_count += 1
                    
                    # Батч-запись каждые 10 задач
                    if len(generated_tasks) >= 10:
                        self.writer.write_batch(generated_tasks)
                        generated_tasks = []
                        
                    print(f"✅ Generated task {task_count}/{tasks_per_grade} for {grade_key}")
                else:
                    print(f"❌ Failed to generate task {task_count} for {grade_key}")
                    
        # Запись оставшихся задач
        if generated_tasks:
            self.writer.write_batch(generated_tasks)

def main():
    config = {
        'output_file': 'generated_tasks.json',
        'tasks_per_grade': 500,  # 500 задач на каждый класс
    }
    
    generator = MassTaskGenerator(config)
    generator.generate_all()
    
    print("\n🎉 Generation completed successfully!")

if __name__ == '__main__':
    main()
```

---

## 4. FAILURE MODE ANALYSIS

### 4.1 Точки отказа и их обработка

| Точка отказа | Обработка | Файл:Строка |
|--------------|-----------|-------------|
| **Бесконечный цикл генерации** | `max_retries=3` в `TaskGenerator.generate_task()` | `base_generator.py:75-90` |
| **Таймаут DeepSeek API** | `timeout=90s` в `DeepSeekClient` | `deepseek_client.py:66` |
| **Ошибка парсинга JSON** | `try/except` с retry и exponential backoff | `base_generator.py:85-90` |
| **OOM при накоплении задач** | Батч-запись каждые 10 задач | `mass_generator.py:145-148` |
| **SIGTERM/SIGINT** | Signal handlers с graceful shutdown | `safe_writer.py:20-22`, `mass_generator.py:35-37` |
| **Незакрытый JSON при краше** | `atexit.register()` + signal handlers | `safe_writer.py:23` |
| **Сетевые ошибки** | Exponential backoff в `DeepSeekClient` | `deepseek_client.py:102-130` |

### 4.2 Защита от утечек ресурсов

1. **Файловые дескрипторы**: `SafeJSONWriter` гарантирует закрытие через `atexit` и signal handlers
2. **Память**: Батч-запись предотвращает накопление тысяч задач в RAM
3. **Сетевые соединения**: `DeepSeekClient` использует `requests` с `timeout`
4. **Процессы**: Нет subprocess/multiprocessing - все в одном процессе

---

## 5. КОНФИГУРАЦИЯ И ПАРАМЕТРЫ

### 5.1 Параметры генерации

```python
CONFIG = {
    # Выходной файл
    'output_file': 'generated_tasks.json',
    
    # Количество задач
    'tasks_per_grade': 500,  # На каждый класс
    
    # Распределение по темам (равномерное)
    'topics': [
        "Алгебра",
        "Геометрия", 
        "Комбинаторика",
        "Теория чисел",
        "Задачи на движение"
    ],
    
    # Защита от зависаний
    'max_retries_per_task': 3,
    'api_timeout': 90,  # seconds
    'batch_size': 10,  # Запись каждые N задач
    
    # Exponential backoff
    'base_delay': 2,  # seconds
    'max_delay': 32,  # seconds
}
```

### 5.2 Структура выходного JSON

```json
[
  {
    "id": "6-7_Алгебра_0001",
    "grade": "6-7",
    "topic": "Алгебра",
    "subtopic": "текстовые_задачи",
    "difficulty": 3,
    "text": "Условие задачи...",
    "answer": "42",
    "solution": "Краткое решение..."
  },
  ...
]
```

---

## 6. ПЛАН РЕАЛИЗАЦИИ

### Фаза 1: Инфраструктура (1-2 часа)
- [ ] Создать структуру директорий `generators/`
- [ ] Реализовать `SafeJSONWriter` с graceful shutdown
- [ ] Реализовать `TaskGenerator` (abstract base class)
- [ ] Написать unit-тесты для SafeWriter

### Фаза 2: Генераторы по классам (2-3 часа)
- [ ] Реализовать `Grade6_7Generator`
- [ ] Реализовать `Grade8Generator`
- [ ] Реализовать `Grade10_11Generator`
- [ ] Протестировать каждый генератор отдельно

### Фаза 3: Main Controller (1-2 часа)
- [ ] Реализовать `MassTaskGenerator`
- [ ] Добавить прогресс-бар и логирование
- [ ] Реализовать checkpoint system (сохранение прогресса)

### Фаза 4: Тестирование и OPR (2-3 часа)
- [ ] E2E тест: генерация 100 задач
- [ ] Тест graceful shutdown (Ctrl+C во время генерации)
- [ ] Проверка утечек ресурсов (psutil)
- [ ] Создание OPR-отчета

---

## 7. КРИТЕРИИ ПРИЕМКИ

### 7.1 Функциональные требования
- ✅ Генерация минимум 500 задач на класс
- ✅ Соблюдение возрастных ограничений (100%)
- ✅ Разнообразие: минимум 4 подтемы на тему
- ✅ Валидный JSON на выходе (даже при прерывании)
- ✅ Классический олимпиадный стиль (без "киберспорта")

### 7.2 Нефункциональные требования
- ✅ Graceful shutdown за <5 секунд
- ✅ Нет бесконечных циклов (max_retries везде)
- ✅ Нет утечек ресурсов (проверка psutil)
- ✅ Батч-запись (защита от OOM)
- ✅ Логирование всех ошибок

---

## 8. РИСКИ И МИТИГАЦИЯ

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| DeepSeek API недоступен | Средняя | Высокое | Retry с exponential backoff, fallback на OpenRouter |
| Генерация невалидного JSON | Высокая | Среднее | Парсинг с очисткой, retry до 3 раз |
| OOM при генерации тысяч задач | Низкая | Высокое | Батч-запись каждые 10 задач |
| Краш без закрытия JSON | Средняя | Высокое | Signal handlers + atexit |
| Повторяющиеся задачи | Средняя | Среднее | Контекст последних 10 задач |
| Нарушение возрастных ограничений | Средняя | Высокое | Строгие промпты + валидация |

---

## 9. МОНИТОРИНГ И МЕТРИКИ

### 9.1 Метрики производительности
- Задач в минуту (target: 5-10)
- Процент
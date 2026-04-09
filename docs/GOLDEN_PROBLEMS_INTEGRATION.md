# Интеграция "Золотого пула" задач

## 📋 Обзор

Подключение 125 эталонных олимпиадных задач для адаптивного тестирования с гарантией качества.

## ⚠️ Текущая ситуация

**Проблема:** Директория `output/` с файлами `golden_problems_*.json` не найдена в проекте.

**Решение:** Нужно либо:
1. Создать эти файлы с эталонными задачами
2. Использовать существующий `PROBLEMS_DB` с фильтрацией по качеству
3. Импортировать задачи из внешнего источника

## 🎯 Архитектура решения

### Вариант 1: Использование существующей БД с флагом качества

Вместо создания отдельной таблицы, добавим флаг `is_golden` к существующим задачам в `problems.py`.

### Вариант 2: Отдельная таблица Problem в SQLite

Создать полноценную таблицу для хранения задач вместо Python файла.

## 📝 План реализации (Вариант 1 - Быстрый)

### Шаг 1: Обновить структуру задач в `problems.py`

```python
# Добавить поле is_golden к каждой задаче
PROBLEMS_DB = [
    {
        'id': 1,
        'text': '...',
        'answer': '...',
        'subject': 'algebra',
        'level': 3,
        'grade': 9,
        'is_golden': True,  # Новое поле
        # ... остальные поля
    },
    # ...
]
```

### Шаг 2: Создать скрипт отбора золотых задач

`scripts/mark_golden_problems.py`:

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Отмечает лучшие задачи как "золотые" для адаптивного тестирования
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problems import PROBLEMS_DB

def mark_golden_problems():
    """
    Отбирает 125 лучших задач (25 на класс, 5-9 классы)
    Критерии:
    - Четкое условие
    - Проверенный ответ
    - Разнообразие тем
    - Олимпиадный уровень
    """
    
    golden_count = 0
    target_per_grade = 25
    
    for grade in range(5, 10):  # 5-9 классы
        grade_problems = [p for p in PROBLEMS_DB if p.get('grade') == grade]
        
        # Сортируем по качеству (можно добавить метрику)
        # Пока берем первые 25 каждого класса
        selected = grade_problems[:target_per_grade]
        
        for problem in selected:
            problem['is_golden'] = True
            golden_count += 1
        
        print(f"Класс {grade}: отмечено {len(selected)} золотых задач")
    
    print(f"\nВсего золотых задач: {golden_count}")
    
    # Сохраняем обновленный problems.py
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write("PROBLEMS_DB = [\n")
        for problem in PROBLEMS_DB:
            f.write(f"    {problem},\n")
        f.write("]\n")
    
    print("✅ Файл problems.py обновлен")

if __name__ == "__main__":
    mark_golden_problems()
```

### Шаг 3: Обновить IRT движок

`services/adaptive_test.py`:

```python
def select_next_problem(
    self,
    user_ability: float,
    subject: Optional[str] = None,
    grade: Optional[int] = None,
    excluded_ids: Optional[List[int]] = None,
    topic_weights: Optional[Dict[str, float]] = None,
    golden_only: bool = True  # Новый параметр
) -> Optional[Dict[str, Any]]:
    """
    Выбирает следующую оптимальную задачу.
    
    Args:
        golden_only: Если True, выбирает только из золотых задач
    """
    excluded_ids = excluded_ids or []
    topic_weights = topic_weights or {}
    
    # Фильтруем задачи
    candidates = []
    for problem in self.problems_db:
        # Пропускаем исключенные
        if problem.get('id') in excluded_ids:
            continue
        
        # НОВОЕ: Фильтр по золотым задачам
        if golden_only and not problem.get('is_golden', False):
            continue
        
        # Применяем остальные фильтры
        if subject and problem.get('subject') != subject:
            continue
        
        if grade is not None:
            problem_grade = problem.get('grade')
            if isinstance(problem_grade, str) and '-' in problem_grade:
                grade_range = problem_grade.split('-')
                try:
                    min_grade = int(grade_range[0])
                    max_grade = int(grade_range[1])
                    if not (min_grade <= grade <= max_grade):
                        continue
                except (ValueError, IndexError):
                    continue
            elif isinstance(problem_grade, int):
                if problem_grade != grade:
                    continue
        
        candidates.append(problem)
    
    if not candidates:
        logger.warning(f"No golden candidates found for ability={user_ability}")
        # Fallback: ищем среди всех задач
        if golden_only:
            return self.select_next_problem(
                user_ability, subject, grade, excluded_ids, topic_weights, golden_only=False
            )
        return None
    
    # Остальная логика без изменений
    # ...
```

### Шаг 4: Обновить UI в `adaptive_test.html`

```html
<!-- Счетчик задач -->
<div style="text-align: center; margin-bottom: 20px;">
    <div style="color: var(--text-muted); font-size: 14px; margin-bottom: 5px;">
        Задача <span id="currentProblemNum">1</span> из <span id="totalProblems">25</span>
    </div>
    <div style="color: var(--accent-2); font-size: 16px; font-weight: 600;">
        Раздел: <span id="currentSubject">Загрузка...</span>
    </div>
</div>

<!-- Условие задачи -->
<div id="problemText" style="
    color: var(--text-soft); 
    line-height: 1.9; 
    margin-bottom: 30px; 
    font-size: 18px;
    text-align: center;
    padding: 25px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: var(--radius-md);
    white-space: pre-wrap;  /* Поддержка многострочности */
">
    Загрузка задачи...
</div>
```

JavaScript для обновления счетчика:

```javascript
function displayProblem(problem, number, total) {
    // Обновляем счетчик
    document.getElementById('currentProblemNum').textContent = number;
    document.getElementById('totalProblems').textContent = total;
    
    // Переводим название раздела
    const subjectNames = {
        'algebra': 'Алгебра',
        'geometry': 'Геометрия',
        'combinatorics': 'Комбинаторика',
        'number_theory': 'Теория чисел',
        'movement': 'Задачи на движение',
        'knights_liars': 'Рыцари и лжецы'
    };
    
    document.getElementById('currentSubject').textContent = 
        subjectNames[problem.subject] || problem.subject;
    
    // Выводим условие
    document.getElementById('problemText').textContent = problem.text;
    
    // ... остальной код
}
```

## 📝 План реализации (Вариант 2 - Полный)

### Создание таблицы Problem в БД

`models.py`:

```python
class Problem(db.Model):
    """Задача для адаптивного тестирования"""
    __tablename__ = 'problems'
    
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    answer = db.Column(db.String(200), nullable=False)
    solution = db.Column(db.Text)
    
    # Классификация
    subject = db.Column(db.String(50), nullable=False, index=True)
    subtopic = db.Column(db.String(100))
    grade = db.Column(db.Integer, nullable=False, index=True)
    level = db.Column(db.Integer, nullable=False, index=True)  # 1-7
    
    # Качество
    is_golden = db.Column(db.Boolean, default=False, index=True)
    quality_score = db.Column(db.Float, default=0.0)
    
    # Метаданные
    source = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'text': self.text,
            'answer': self.answer,
            'solution': self.solution,
            'subject': self.subject,
            'subtopic': self.subtopic,
            'grade': self.grade,
            'level': self.level,
            'is_golden': self.is_golden
        }
```

### Скрипт миграции из problems.py в БД

`scripts/migrate_problems_to_db.py`:

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Мигрирует задачи из problems.py в SQLite БД
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, Problem
from problems import PROBLEMS_DB

def migrate_problems():
    """Переносит задачи из Python файла в БД"""
    
    with app.app_context():
        # Очищаем таблицу
        Problem.query.delete()
        
        # Добавляем задачи
        for problem_data in PROBLEMS_DB:
            problem = Problem(
                id=problem_data.get('id'),
                text=problem_data.get('text', ''),
                answer=str(problem_data.get('answer', '')),
                solution=problem_data.get('solution'),
                subject=problem_data.get('subject', 'unknown'),
                subtopic=problem_data.get('subtopic'),
                grade=problem_data.get('grade', 9),
                level=problem_data.get('level', 3),
                is_golden=problem_data.get('is_golden', False),
                source=problem_data.get('source', 'legacy')
            )
            db.session.add(problem)
        
        db.session.commit()
        
        total = Problem.query.count()
        golden = Problem.query.filter_by(is_golden=True).count()
        
        print(f"✅ Мигрировано {total} задач")
        print(f"   Из них золотых: {golden}")

if __name__ == "__main__":
    migrate_problems()
```

## 🚀 Быстрый старт

### Если файлы golden_problems_*.json есть:

```bash
# 1. Создать скрипт загрузки
python scripts/load_golden_problems.py

# 2. Обновить IRT движок
# (изменения в services/adaptive_test.py)

# 3. Обновить UI
# (изменения в templates/adaptive_test.html)
```

### Если файлов нет (текущая ситуация):

```bash
# 1. Отметить лучшие задачи как золотые
python scripts/mark_golden_problems.py

# 2. Или мигрировать в БД
python scripts/migrate_problems_to_db.py

# 3. Обновить код для использования золотых задач
```

## 📊 Критерии отбора золотых задач

1. **Четкое условие** - без опечаток и двусмысленностей
2. **Проверенный ответ** - гарантированно правильный
3. **Олимпиадный уровень** - не школьная программа
4. **Разнообразие** - разные темы и методы решения
5. **Адекватная сложность** - соответствует заявленному уровню

## ⚠️ Важные замечания

1. **Vision API** - DeepSeek не поддерживает анализ изображений
2. **Хранение фото** - требует настройки файлового хранилища
3. **Производительность** - Vision API запросы медленные (2-5 сек)
4. **Стоимость** - Vision API платный ($0.01-0.03 за изображение)

## 🔄 Альтернативный подход

Вместо Vision API можно:
1. Сохранять фото для ручной проверки
2. Использовать OCR (Tesseract) для извлечения текста
3. Добавить функцию "Запросить проверку преподавателя"
4. Показывать фото в результатах теста

## 📝 Следующие шаги

1. ✅ Создать план интеграции (этот документ)
2. ⏳ Найти или создать файлы с золотыми задачами
3. ⏳ Реализовать скрипт загрузки
4. ⏳ Обновить IRT движок
5. ⏳ Обновить UI
6. ⏳ Протестировать систему
7. ⏳ Добавить Vision API (опционально)

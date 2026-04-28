# SESSION NOTES: Grade 7 Implementation

**Status:** PAUSED (security fix in progress)
**Resume command:** "continue grade7"

---

## ФАЗА 1: АУДИТ — РЕЗУЛЬТАТЫ

### Что уже готово:
- ✅ `topics_grade7.py` — 10 тем, структура идентична 6 классу
- ✅ `services/adaptive_topic_mapping.py` — есть блок для 6 класса, нужно добавить 7
- ✅ Роуты адаптивного теста работают (5 и 6 классы)

### Структура topics_grade7.py (10 тем):
1. Алгебраические тождества и преобразования
2. Линейные уравнения и системы
3. Неравенства и их системы
4. Геометрия треугольников
5. Параллельные прямые и углы
6. Делимость и остатки (7 класс)
7. Комбинаторика и вероятность
8. Принцип Дирихле и инварианты
9. Графы и алгоритмы
10. Логика и олимпиадные задачи

### БД:
- Grade 5: 945 adaptive tasks
- Grade 6: 928 adaptive tasks
- Grade 7: 0 adaptive tasks (нужно генерировать!)

### adaptive_topic_mapping.py:
Текущее содержимое — только блок для grade 6.
Нужно добавить блок для grade 7.

---

## ЧТО НУЖНО СДЕЛАТЬ (Фазы 2-5):

### ФАЗА 2: ПРОПУСКАЕТСЯ
topics_grade7.py уже готов.

### ФАЗА 3: Маппинг адаптивки
Файл: `services/adaptive_topic_mapping.py`
Добавить в `TOPIC_KEYWORDS_BY_GRADE`:
```python
7: {
    'algebra': ['алгебр', 'многочлен', 'одночлен', 'выражен', 'уравнен', 'систем'],
    'geometry': ['геометр', 'треугольн', 'угол', 'параллельн', 'медиан', 'биссектрис'],
    'combinatorics': ['комбинатор', 'перестанов', 'дирихле', 'правило умножен'],
    'number_theory': ['делимост', 'простые числ', 'нод', 'нок', 'разложен'],
    'kl_movement': ['логик', 'инвариант', 'чётност', 'раскраск', 'стратеги', 'неравенств'],
},
```

### ФАЗА 4: Роуты в app.py
Единственное место для правки — строка ~3084:
```python
# Добавить ПОСЛЕ блока grade_int == 6:
if grade_int == 7:
    from services.adaptive_topic_mapping import get_keywords_for_grade_topic
    grade7_kw = get_keywords_for_grade_topic(7, topic)
    if grade7_kw:
        topic_keywords[topic] = grade7_kw
        print(f"[ADAPTIVE FIX] 7 класс + {topic} → ключевые слова: {grade7_kw}")
```

### ФАЗА 5: Тестирование
- Проверить /adaptive_test/select_grade?topic=algebra → 7 класс
- Убедиться что 5 и 6 классы не сломались
- Коммит: "feat(grade7): adaptive topic mapping for 7th grade"

---

## ВАЖНЫЕ ЗАМЕЧАНИЯ:
1. Задач для 7 класса в БД НЕТ — нужно будет генерировать
2. Пока 7 класс будет использовать adaptive_data/*.json через маппинг
3. НЕ трогать блоки для 5 и 6 классов в adaptive_topic_mapping.py
4. НЕ трогать templates/public_profile.html и templates/friends.html

# Задача [p01]: Рефакторинг роутов Flask — миграция на Jinja2-шаблоны

**Дата создания:** 2026-03-27  
**Архитектор:** Roo Architect  
**Статус:** Готов к реализации

---

## 1. Архитектурный контекст и цель

### Текущая проблема
В файле [`app.py`](../app.py:1) обнаружено **7 роутов**, которые генерируют HTML напрямую через f-строки вместо использования существующих Jinja2-шаблонов. Это создает следующие проблемы:

1. **Нарушение принципа разделения ответственности** (Separation of Concerns)
2. **Дублирование кода** стилей и структуры
3. **Сложность поддержки** — изменения в дизайне требуют правки Python-кода
4. **Отсутствие переиспользования** базового шаблона [`base.html`](../templates/base.html:1)
5. **Риск XSS-уязвимостей** при неправильной экранизации данных

### Цель рефакторинга
Перевести все роуты на использование Jinja2-шаблонов с сохранением текущей функциональности и улучшением архитектуры.

### Архитектурные ограничения
- ✅ **Запрещено** менять бизнес-логику фильтрации задач
- ✅ **Запрещено** ломать существующие URL-маршруты
- ✅ **Обязательно** сохранить совместимость с [`base.html`](../templates/base.html:1)
- ✅ **Обязательно** использовать фильтр `| safe` для HTML-контента из БД

---

## 2. Анализ текущего состояния

### Роуты с инлайн-HTML (7 штук)

| № | Роут | Строки | Текущий статус | Целевой шаблон |
|---|------|--------|----------------|----------------|
| 1 | `/section/<subject_key>` | 244-262 | ❌ f-string HTML | ✅ `section.html` (существует) |
| 2 | `/section/<subject_key>/<subtopic_key>` | 292-309 | ❌ f-string HTML | ⚠️ Нужен новый шаблон `subtopic.html` |
| 3 | `/problems` | 391-410 | ❌ f-string HTML | ✅ `problems.html` (существует) |
| 4 | `/problems/<int:problem_id>` | 444-463 | ❌ f-string HTML | ✅ `problem_detail.html` (существует) |
| 5 | `/problem/<int:problem_id>` | 444-463 | ❌ f-string HTML | ✅ `problem_detail.html` (существует) |
| 6 | `/olympiads/open` | 712-732 | ❌ f-string HTML | ✅ `olympiad_detail.html` (существует) |
| 7 | `/olympiads/solution/<int:combo_id>` | 760-776 | ❌ f-string HTML | ⚠️ `olympiad_solutions.html` (пустой!) |

### Существующие шаблоны

| Шаблон | Статус | Наследует base.html | Примечания |
|--------|--------|---------------------|------------|
| `base.html` | ✅ Готов | N/A | Базовый шаблон с header, nav, KaTeX |
| `section.html` | ✅ Готов | ✅ Да | Форма выбора класса/уровня |
| `subject.html` | ⚠️ Не наследует | ❌ Нет | Собственный DOCTYPE, нужна доработка |
| `problems.html` | ✅ Готов | ✅ Да | Список задач с фильтрами |
| `problem_detail.html` | ✅ Готов | ✅ Да | Детали задачи с reveal-блоками |
| `olympiad_detail.html` | ✅ Готов | ✅ Да | Список задач олимпиады |
| `olympiad_solutions.html` | ❌ Пустой | N/A | **Требуется создание!** |

---

## 3. Архитектурный план миграции

### Фаза 1: Простые миграции (роуты 1, 3, 4, 5, 6)

Эти роуты уже имеют готовые шаблоны и требуют только передачи контекста.

#### 3.1. Роут `/section/<subject_key>` → `section.html`

**Текущий код (строки 244-262):**
```python
return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{subject_title} — FORMYLA</title></head>
<body style="background:#16161a;color:#fff;...">
    ...
</body>
</html>
"""
```

**Новый код:**
```python
return render_template('section.html',
    subject_key=subject_key,
    subject_title=subject_title,
    subtopics=subtopics,
    subtopic_counts=subtopic_counts,
    total=sum(subtopic_counts.values())
)
```

**Требуемые изменения в `section.html`:**
- ✅ Шаблон уже готов, но показывает форму фильтрации
- ⚠️ Нужно добавить карточки подтем (сейчас их нет!)
- Добавить цикл `{% for sub_key, sub_title in subtopics.items() %}`

#### 3.2. Роут `/problems` → `problems.html`

**Новый код:**
```python
return render_template('problems.html',
    subject_title=subject_title,
    subtopic_title=subtopic_title,
    problems=filtered,
    back_url=back_url,
    page_title=page_title
)
```

**Требуемые изменения в `problems.html`:**
- ✅ Шаблон готов
- Добавить переменную `back_url` для кнопки "Назад"

#### 3.3. Роуты `/problems/<int:problem_id>` и `/problem/<int:problem_id>` → `problem_detail.html`

**Новый код:**
```python
return render_template('problem_detail.html',
    problem=problem,
    subject_title=subject_title,
    subtopic_title=subtopic_title,
    is_olympiad=is_olympiad
)
```

**Требуемые изменения в `problem_detail.html`:**
- ✅ Шаблон готов
- ✅ Уже есть условие `{% if problem.solution %}` (строка 41)
- ✅ Уже использует `| safe` фильтр

#### 3.4. Роут `/olympiads/open` → `olympiad_detail.html`

**Новый код:**
```python
return render_template('olympiad_detail.html',
    olympiad=olympiad,
    combo=combo,
    problems=combo.get('problems', [])
)
```

**Требуемые изменения в `olympiad_detail.html`:**
- ⚠️ Текущий шаблон ожидает список задач, а нужен пробник
- Нужно адаптировать под структуру `combo` с вложенными `problems`

---

### Фаза 2: Сложные миграции (роуты 2, 7)

#### 3.5. Роут `/section/<subject_key>/<subtopic_key>` → **НОВЫЙ** `subtopic.html`

**Проблема:** Шаблон не существует, нужно создать.

**Структура нового шаблона:**
```jinja2
{% extends "base.html" %}
{% block title %}{{ subtopic_title }} — {{ subject_title }}{% endblock %}

{% block content %}
<h1>{{ subtopic_title }}</h1>
<p>{{ subject_title }} · Выберите класс и уровень сложности</p>

{% for grade in grades %}
<div class="grade-card">
    <h3>{{ grade }} класс ({{ grade_counts[grade] }} задач)</h3>
    <div class="level-buttons">
        {% for level in range(1, 11) %}
        <a href="/problems?subject={{ subject_key }}&subtopic={{ subtopic_key }}&grade={{ grade }}&level={{ level }}"
           class="level-btn {% if level_counts[grade][level] == 0 %}disabled{% endif %}">
            Ур.{{ level }}
        </a>
        {% endfor %}
    </div>
</div>
{% endfor %}
{% endblock %}
```

**Контекст:**
```python
return render_template('subtopic.html',
    subject_key=subject_key,
    subject_title=subject_title,
    subtopic_key=subtopic_key,
    subtopic_title=subtopic_title,
    grades=GRADES,
    grade_counts=grade_counts,  # dict: {grade: count}
    level_counts=level_counts   # dict: {grade: {level: count}}
)
```

#### 3.6. Роут `/olympiads/solution/<int:combo_id>` → **СОЗДАТЬ** `olympiad_solutions.html`

**Проблема:** Файл существует, но пустой!

**Структура нового шаблона:**
```jinja2
{% extends "base.html" %}
{% block title %}Решения — {{ olympiad.full_title }}{% endblock %}

{% block content %}
<h1>{{ olympiad.full_title }}</h1>
<p>{{ combo.year }} год, {{ combo.grade }} класс — {{ combo.round_title }}</p>
<p class="subtitle">Ответы и подробные решения</p>

{% for p in combo.problems %}
<div class="solution-card">
    <span class="problem-badge">Задача {{ p.num }}</span>
    
    <div class="problem-text">{{ p.text | safe }}</div>
    
    {% if p.answer %}
    <div class="answer-block">
        <span class="answer-label">Ответ:</span>
        <span class="answer-value">{{ p.answer | safe }}</span>
    </div>
    {% endif %}
    
    <div class="solution-block">
        <div class="solution-label">Подробное решение:</div>
        <div class="solution-text">{{ p.solution | default('Решение не найдено') | safe }}</div>
    </div>
</div>
{% endfor %}

<div class="actions">
    <a href="/olympiads" class="btn-primary">Выбрать другой пробник</a>
</div>
{% endblock %}
```

**Контекст:**
```python
return render_template('olympiad_solutions.html',
    olympiad=olympiad,
    combo=combo
)
```

---

## 4. Маппинг контекстных переменных

### Таблица соответствия

| Роут | Шаблон | Контекстные переменные |
|------|--------|------------------------|
| `/section/<subject_key>` | `section.html` | `subject_key`, `subject_title`, `subtopics`, `subtopic_counts`, `total` |
| `/section/<subject_key>/<subtopic_key>` | `subtopic.html` (новый) | `subject_key`, `subject_title`, `subtopic_key`, `subtopic_title`, `grades`, `grade_counts`, `level_counts` |
| `/problems` | `problems.html` | `subject_title`, `subtopic_title`, `problems`, `back_url`, `page_title` |
| `/problems/<int:problem_id>` | `problem_detail.html` | `problem`, `subject_title`, `subtopic_title`, `is_olympiad` |
| `/olympiads/open` | `olympiad_detail.html` | `olympiad`, `combo`, `problems` |
| `/olympiads/solution/<int:combo_id>` | `olympiad_solutions.html` (новый) | `olympiad`, `combo` |

---

## 5. Критерии приемки и Failure Modes

### Критерии успеха
- ✅ Все 7 роутов используют `render_template()`
- ✅ Нет f-строк с HTML в [`app.py`](../app.py:1)
- ✅ Все шаблоны наследуют [`base.html`](../templates/base.html:1)
- ✅ Сохранена текущая функциональность (фильтрация, навигация)
- ✅ Используется фильтр `| safe` для контента из БД
- ✅ Используется фильтр `| default('')` для опциональных полей

### Failure Modes и митигация

| Failure Mode | Риск | Митигация |
|--------------|------|-----------|
| **TemplateNotFound** | Высокий | Проверить наличие всех шаблонов перед запуском |
| **UndefinedError** (переменная не передана) | Средний | Использовать `| default('')` в шаблонах |
| **CSS Breakage** | Средний | Сохранить классы из `base.html`, добавить недостающие в `style.css` |
| **XSS через `| safe`** | Низкий | Данные из БД контролируются, но нужна валидация |
| **Broken navigation** | Средний | Тестировать все ссылки после миграции |

---

## 6. План реализации (для Code mode)

### Шаг 1: Подготовка шаблонов
1. Создать `templates/subtopic.html`
2. Заполнить `templates/olympiad_solutions.html`
3. Обновить `templates/section.html` (добавить карточки подтем)
4. Обновить `templates/olympiad_detail.html` (адаптировать под `combo`)

### Шаг 2: Рефакторинг роутов
1. Роут `/section/<subject_key>` (строки 220-262)
2. Роут `/section/<subject_key>/<subtopic_key>` (строки 266-309)
3. Роут `/problems` (строки 314-410)
4. Роут `/problems/<int:problem_id>` (строки 414-463)
5. Роут `/olympiads/open` (строки 650-732)
6. Роут `/olympiads/solution/<int:combo_id>` (строки 735-776)

### Шаг 3: Тестирование
1. Запустить Flask-приложение
2. Проверить каждый роут вручную
3. Убедиться в отсутствии ошибок в консоли
4. Проверить корректность отображения

### Шаг 4: Очистка
1. Удалить закомментированный старый код
2. Проверить отсутствие f-строк с HTML

---

## 7. Оценка рисков

| Риск | Вероятность | Влияние | Приоритет |
|------|-------------|---------|-----------|
| Ошибки в передаче контекста | Средняя | Высокое | 🔴 Высокий |
| Несовместимость с `base.html` | Низкая | Среднее | 🟡 Средний |
| Потеря функциональности | Низкая | Высокое | 🔴 Высокий |
| Проблемы с CSS | Средняя | Низкое | 🟢 Низкий |

---

## 8. Чеклист для Code mode

- [ ] Создан `templates/subtopic.html`
- [ ] Заполнен `templates/olympiad_solutions.html`
- [ ] Обновлен `templates/section.html`
- [ ] Обновлен `templates/olympiad_detail.html`
- [ ] Рефакторинг роута `/section/<subject_key>`
- [ ] Рефакторинг роута `/section/<subject_key>/<subtopic_key>`
- [ ] Рефакторинг роута `/problems`
- [ ] Рефакторинг роута `/problems/<int:problem_id>`
- [ ] Рефакторинг роута `/olympiads/open`
- [ ] Рефакторинг роута `/olympiads/solution/<int:combo_id>`
- [ ] Удалены все f-строки с HTML из `app.py`
- [ ] Проверена работа всех роутов
- [ ] Подготовлен OPR-отчет

---

## 9. Ожидаемый результат

После выполнения задачи:
- ✅ Файл [`app.py`](../app.py:1) содержит только бизнес-логику
- ✅ Все представления (View) вынесены в Jinja2-шаблоны
- ✅ Улучшена поддерживаемость кода
- ✅ Упрощено внесение изменений в дизайн
- ✅ Соблюдены принципы MVC-архитектуры

**Готово к передаче в Code mode для реализации.**

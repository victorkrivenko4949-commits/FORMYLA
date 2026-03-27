# AI Context: Проект FORMYLA — Технический паспорт

**Версия:** 1.0 (Production Ready)  
**Дата:** 2026-03-27  
**Статус:** MVP завершен, развернут на GitHub

---

## 1. Суть проекта

**FORMYLA** — веб-платформа для подготовки к математическим олимпиадам школьников 5-11 классов.

**Ключевые особенности:**
- База из 8400 сгенерированных задач по 6 разделам математики
- 651 реальный олимпиадный пробник прошлых лет (4383 задачи)
- Интерактивная проверка ответов без регистрации
- Гостевой прогресс через Flask Session (client-side cookies)
- Маршрут обучения с геймификацией (блокировка олимпиад)
- Таймер обратного отсчета для реалистичной тренировки

---

## 2. Стек технологий

### Backend
- **Flask 3.0.0** — веб-фреймворк
- **Werkzeug 3.0.1** — WSGI утилиты
- **Python 3.x** — язык разработки
- **Gunicorn 21.2.0** — WSGI сервер для production

### Frontend
- **Jinja2** — шаблонизатор (встроен в Flask)
- **Vanilla JavaScript** — клиентская логика (без фреймворков)
- **HTML5/CSS3** — разметка и стили
- **KaTeX** — рендеринг математических формул

### Хранение данных
- **In-memory Python dictionaries** — данные импортируются из [`problems.py`](problems.py:1) и [`olympiads.py`](olympiads.py:1)
- **Flask Session** — гостевой прогресс (client-side cookies)
- **localStorage** — таймеры олимпиад (client-side)

### Deployment
- **GitHub** — хостинг кода
- **Render.com** — рекомендуемый хостинг (Free tier)
- **Gunicorn** — production WSGI server

---

## 3. Архитектура данных

### 3.1. База задач: `PROBLEMS_DB` (problems.py)

**Формат записи:**
```python
{
    'id': int,                    # Уникальный идентификатор
    'subject': str,               # algebra, geometry, combinatorics, number_theory, movement, knights_liars
    'subject_title': str,         # "Алгебра", "Геометрия", ...
    'subtopic': str,              # equations, inequalities, triangles, ...
    'subtopic_title': str,        # "Уравнения", "Треугольники", ...
    'grade': int,                 # Класс (5-11)
    'difficulty': int,            # Уровень сложности (1-10)
    'title': str,                 # Название задачи
    'text': str,                  # Условие задачи
    'answer': str,                # Правильный ответ
    'solution': str               # Подробное решение
}
```

**Объем:** 8400 задач, ~5 MB  
**Файл:** [`problems.py`](problems.py:1) (8406 строк)

### 3.2. База олимпиад: `OLYMPIADS_DB` (olympiads.py)

**Формат записи (новый формат - пробники):**
```python
{
    'id': int,                    # ID пробника
    'olympiad': str,              # Slug олимпиады (vsosh, lomonosov, ...)
    'olympiad_title': str,        # "ВсОШ", "Ломоносов", ...
    'year': int,                  # Год проведения
    'grade': int,                 # Класс
    'round': str,                 # Этап (school, municipal, regional, final)
    'round_title': str,           # "Школьный этап", ...
    'problems': [                 # Список задач пробника
        {
            'num': int,           # Номер задачи в пробнике
            'text': str,          # Условие
            'answer': str,        # Ответ
            'solution': str       # Решение
        }
    ]
}
```

**Объем:** 651 пробник, 4383 задачи, ~7.6 MB  
**Файл:** [`olympiads.py`](olympiads.py:1) (33566 строк)

### 3.3. Метаданные олимпиад: `OLYMPIADS_INFO`

Список доступных олимпиад с метаинформацией (название, этапы, классы, уровень).

---

## 4. Реализованный функционал

### 4.1. Роутинг и шаблоны (MVC)

**Все роуты используют Jinja2-шаблоны:**

| Роут | Шаблон | Назначение |
|------|--------|------------|
| `/` | [`index.html`](templates/index.html:1) | Главная страница |
| `/section/<subject>` | [`section.html`](templates/section.html:1) | Выбор подтемы |
| `/section/<subject>/<subtopic>` | [`subtopic.html`](templates/subtopic.html:1) | Выбор класса/уровня |
| `/problems` | [`problems.html`](templates/problems.html:1) | Список задач с фильтрами |
| `/problems/<id>` | [`problem_detail.html`](templates/problem_detail.html:1) | Детали задачи |
| `/olympiads` | [`olympiads.html`](templates/olympiads.html:1) | Выбор олимпиады |
| `/olympiads/open` | [`olympiad_detail.html`](templates/olympiad_detail.html:1) | Пробник олимпиады |
| `/olympiads/solution/<id>` | [`olympiad_solutions.html`](templates/olympiad_solutions.html:1) | Решения пробника |
| `/practice` | [`practice.html`](templates/practice.html:1) | Генерация варианта |
| `/practice/<id>` | [`practice_variant.html`](templates/practice_variant.html:1) | Решение варианта |
| `/practice/<id>/submit` | [`practice_result.html`](templates/practice_result.html:1) | Результаты проверки |
| `/api/check_answer` | JSON API | Проверка ответа (AJAX) |

**Базовый шаблон:** [`templates/base.html`](templates/base.html:1)  
- Header с навигацией
- Форма глобального поиска
- KaTeX для формул
- JavaScript функция `checkAnswer()`

### 4.2. Интерактивная проверка ответов

**Клиентская часть:**
- Форма ввода в [`problem_detail.html`](templates/problem_detail.html:22-70)
- JavaScript функция `checkAnswer()` в [`base.html`](templates/base.html:34-68)
- AJAX запрос к `/api/check_answer`

**Серверная часть:**
- API роут в [`app.py:373-407`](app.py:373-407)
- Нестрогое сравнение: `user_answer.strip().lower() == correct_answer.strip().lower()`
- Сохранение в сессию: `session['solved_problems'].append(problem_id)`

### 4.3. Гостевой прогресс (Session)

**Конфигурация:**
- [`app.py:12`](app.py:12): `app.secret_key` с fallback на env var
- Хранение: client-side signed cookies
- Структура: `session['solved_problems'] = [id1, id2, ...]`

**Использование:**
- Индикаторы решенных задач в [`problems.html`](templates/problems.html:16-17)
- Условный рендеринг в [`problem_detail.html`](templates/problem_detail.html:22)
- Проверка доступа к олимпиадам

### 4.4. Маршрут обучения (Блокировка)

**Константа:** `REQUIRED_SOLVED_TASKS = 5` ([`app.py:67`](app.py:67))

**Блокируемые роуты:**
- `/practice` ([`app.py:441-447`](app.py:441-447))
- `/olympiads` ([`app.py:579-586`](app.py:579-586))
- `/olympiads/open` ([`app.py:621-628`](app.py:621-628))

**Шаблон блокировки:** [`templates/locked.html`](templates/locked.html:1)
- Прогресс-бар (X/5 задач)
- Мотивационное сообщение
- Кнопка "Перейти к тренировке"

**Визуальная индикация:** 🔒 emoji в навигации ([`base.html:23-28`](templates/base.html:23-28))

### 4.5. Пагинация

**Константа:** `PER_PAGE = 20` ([`app.py:349`](app.py:349))

**Реализация:**
- Параметр `page` в URL
- Расчет `total_pages = math.ceil(total_count / PER_PAGE)`
- Срез `filtered[(page-1)*PER_PAGE : page*PER_PAGE]`
- Кнопки "Назад"/"Вперед" в [`problems.html:39-63`](templates/problems.html:39-63)
- Сохранение всех GET-параметров при переходе

### 4.6. Полнотекстовый поиск

**Параметр:** `q` в URL ([`app.py:294`](app.py:294))

**Логика:**
- Извлечение: `search_query = request.args.get("q", "").strip().lower()`
- Фильтрация: `search_query in problem_text.lower()`
- Форма поиска в header ([`base.html:35-42`](templates/base.html:35-42))
- Плашка результатов в [`problems.html:7-12`](templates/problems.html:7-12)

### 4.7. Таймер для олимпиад

**Реализация:** JavaScript + localStorage в [`olympiad_detail.html:49-99`](templates/olympiad_detail.html:49-99)

**Логика:**
- Длительность: 3 часа (10800 секунд)
- Ключ: `timer_combo_{{ combo.id }}`
- Инициализация: `Date.now() + DURATION` → localStorage
- Обновление: `setInterval(..., 1000)`
- Форматирование: `ЧЧ:ММ:СС`
- Визуальные эффекты: фиолетовый → желтый (< 5 мин) → красный (< 1 мин)
- При истечении: alert + redirect на `/olympiads/solution/{{ combo.id }}`

---

## 5. Текущие архитектурные ограничения (Инварианты)

### ❌ ЗАПРЕЩЕНО без явного разрешения:

1. **Миграция на SQL БД**
   - Текущее решение: in-memory Python dictionaries
   - Причина: простота, нет необходимости в CRUD операциях
   - Данные статичны (задачи не создаются пользователями)

2. **Добавление системы регистрации/авторизации**
   - Текущее решение: гостевой прогресс через Flask Session
   - Причина: минимализм, отсутствие персональных данных
   - Достаточно для MVP

3. **Использование тяжелых фронтенд-фреймворков**
   - Текущее решение: Vanilla JS + Jinja2
   - Причина: простота, быстрая загрузка, нет build step
   - React/Vue избыточны для данного проекта

### ✅ РАЗРЕШЕНО и рекомендуется:

1. **Добавление новых разделов математики**
2. **Улучшение UI/UX (CSS, анимации)**
3. **Оптимизация поиска (индексация)**
4. **Добавление статистики (графики прогресса)**
5. **Экспорт результатов (PDF, CSV)**

---

## 6. Структура проекта

```
FORMYLA/
├── app.py                      # Главный файл приложения (697 строк)
├── wsgi.py                     # Точка входа для WSGI
├── requirements.txt            # Зависимости Python
├── .gitignore                  # Git exclusions
├── .env.example                # Шаблон переменных окружения
├── DEPLOY_INSTRUCTIONS.md      # Инструкция по деплою
├── AI_CONTEXT_FORMYLA.md       # Этот файл
│
├── problems.py                 # База задач (8406 строк, 8400 задач)
├── olympiads.py                # База олимпиад (33566 строк, 651 пробник)
├── olympiad_problems.py        # Утилиты для олимпиад
├── builder.py                  # Генератор задач
├── проверка.py                 # Скрипт проверки данных
│
├── templates/                  # Jinja2 шаблоны (20 файлов)
│   ├── base.html              # Базовый шаблон (header, nav, KaTeX, JS)
│   ├── index.html             # Главная страница
│   ├── section.html           # Выбор подтемы
│   ├── subtopic.html          # Выбор класса/уровня
│   ├── problems.html          # Список задач с пагинацией
│   ├── problem_detail.html    # Детали задачи + форма ввода
│   ├── olympiads.html         # Выбор олимпиады
│   ├── olympiad_detail.html   # Пробник с таймером
│   ├── olympiad_solutions.html # Решения пробника
│   ├── practice.html          # Генерация варианта
│   ├── practice_variant.html  # Решение варианта
│   ├── practice_result.html   # Результаты проверки
│   ├── locked.html            # Блокировка доступа
│   └── ...                    # Другие шаблоны
│
├── static/                     # Статические файлы
│   ├── style.css              # Основные стили
│   └── uploads/               # Загрузки пользователей (игнорируется Git)
│
├── split_problems/             # Разбитые задачи (40 файлов)
├── plans/                      # Архитектурные планы
└── check_problems.py/          # Утилиты проверки
```

---

## 7. Ключевые константы и конфигурация

### В app.py:

```python
# Строка 12
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-...')

# Строка 67
REQUIRED_SOLVED_TASKS = 5  # Для разблокировки олимпиад

# Строка 349
PER_PAGE = 20  # Задач на страницу

# Строки 67-74
SUBJECTS = {
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "combinatorics": "Комбинаторика",
    "number_theory": "Теория чисел",
    "movement": "Задачи на движение",
    "knights_liars": "Рыцари и лжецы"
}

# Строки 77-109
SUBTOPICS = {
    "algebra": {"equations": "Уравнения", ...},
    "geometry": {"triangles": "Треугольники", ...},
    ...
}

# Строки 115-117
GRADES = [5, 6, 7, 8, 9, 10, 11]
```

---

## 8. API Endpoints

### POST /api/check_answer

**Назначение:** Проверка ответа пользователя на задачу

**Request:**
```json
{
    "problem_id": 123,
    "user_answer": "42"
}
```

**Response:**
```json
{
    "correct": true,
    "solution": "Подробное решение...",
    "correct_answer": "42"
}
```

**Логика:**
- Поиск задачи в `PROBLEMS_DB` или `_RAW_DB`
- Нестрогое сравнение (strip + lowercase)
- Сохранение в `session['solved_problems']` при правильном ответе
- Возврат решения для отображения

**Код:** [`app.py:373-407`](app.py:373-407)

---

## 9. Механизм сессий (Гостевой прогресс)

### Структура данных в session:

```python
session = {
    'solved_problems': [1, 5, 12, 45, 78]  # Список ID решенных задач
}
```

### Использование:

**Сохранение прогресса:**
```python
# app.py:399-404
if is_correct:
    solved_problems = session.get('solved_problems', [])
    if problem_id not in solved_problems:
        solved_problems.append(problem_id)
        session['solved_problems'] = solved_problems
        session.modified = True
```

**Проверка доступа:**
```python
# app.py:441-442
solved_count = len(session.get('solved_problems', []))
if solved_count < REQUIRED_SOLVED_TASKS:
    return render_template('locked.html', ...)
```

**Передача в шаблоны:**
```python
# app.py:360, 331
solved_problems = session.get('solved_problems', [])
# Передается в problems.html и problem_detail.html
```

---

## 10. Критические участки кода

### 10.1. Проверка ответа (app.py:373-407)

**Failure Modes:**
- ❌ Problem not found → 404
- ❌ Missing problem_id → 400
- ✅ Empty answer → обрабатывается (strip)
- ✅ Case sensitivity → нормализация через lower()

### 10.2. Пагинация (app.py:349-358)

**Failure Modes:**
- ✅ Division by zero → `if total_count > 0 else 1`
- ✅ Page out of bounds → `page = max(1, min(page, total_pages))`
- ✅ Negative page → max(1, ...)

### 10.3. Поиск (app.py:327-330)

**Failure Modes:**
- ✅ Empty query → `if search_query:` пропускает фильтр
- ✅ Special characters → безопасно (substring match, не regex)
- ✅ Performance → O(n) по 8400 задачам (~50ms)

### 10.4. Таймер (olympiad_detail.html:49-99)

**Failure Modes:**
- ✅ localStorage недоступен → таймер не запустится (graceful degradation)
- ✅ Negative time → проверка `if (remaining <= 0)`
- ✅ Memory leak → `clearInterval()` при истечении

---

## 11. Инструкция для ИИ-Постановщика задач

### Правила оформления новых задач:

1. **Формат:** Используйте шаблон SDD (Software Design Document)
2. **Обязательные разделы:**
   - Архитектурный контекст и цель
   - Шаги реализации
   - Затрагиваемые файлы
   - Критерии приемки и Failure Modes

3. **Формат сдачи:** Operational Proof Report (OPR)
   - Доказательство E2E-работоспособности (логи реального выполнения)
   - Анализ точек отказа (Failure Mode Analysis)
   - Проверка утечек (Resource Leak Check)
   - Контроль глобальной области (Diff импортов)

4. **Запрещено:**
   - Отчеты вида "Всё готово, тесты зеленые"
   - Юнит-тесты с моками без E2E проверки
   - Изменение архитектурных инвариантов без согласования

---

## 12. Deployment

### Локальный запуск (Development):
```bash
python app.py
# http://127.0.0.1:5000
```

### Production запуск (Gunicorn):
```bash
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app
```

### Render.com:
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn wsgi:app`
- Environment: `SECRET_KEY=your-secret-key`

### GitHub:
- Репозиторий: https://github.com/victorkrivenko4949-commits/FORMYLA
- Ветка: `main`
- Последний коммит: "Initial commit: Ready for production"

---

## 13. Известные ограничения и TODO

### Текущие ограничения:
- Нет персистентного хранилища (данные в памяти)
- Нет системы регистрации пользователей
- Поиск работает только по полю `text` (не по ответам/решениям)
- Таймер можно сбросить через DevTools (очистка localStorage)

### Потенциальные улучшения (низкий приоритет):
- Экспорт прогресса в PDF
- Графики статистики (решенные задачи по разделам)
- Режим "Соревнование" (таблица лидеров через localStorage)
- Темная/светлая тема (переключатель)
- Адаптивная верстка для мобильных

---

## 14. Контакты и ресурсы

**GitHub:** https://github.com/victorkrivenko4949-commits/FORMYLA  
**Документация:** [`DEPLOY_INSTRUCTIONS.md`](DEPLOY_INSTRUCTIONS.md:1)  
**Архитектурные планы:** [`plans/p01_jinja_refactoring_plan.md`](plans/p01_jinja_refactoring_plan.md:1)  
**Дамп кодовой базы:** [`project_code_dump.md`](project_code_dump.md:1) (3.97 MB)

---

**Этот файл служит точкой входа для любого ИИ-ассистента, который будет работать с проектом FORMYLA в будущем.**

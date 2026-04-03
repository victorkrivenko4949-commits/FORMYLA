# FORMYLA - Контекст проекта для AI

## 🎯 Что это

**FORMYLA** - образовательная платформа для подготовки к олимпиадам по математике.

**GitHub:** https://github.com/victorkrivenko4949-commits/FORMYLA  
**Render:** https://formyla-com.onrender.com  
**Локально:** http://localhost:5000

## 📊 Текущее состояние (100+ коммитов)

### База данных
- **11,599 задач** (7 уровней сложности)
- **6 разделов:** algebra, geometry, combinatorics, number_theory, movement, knights_liars
- **Файл:** `problems.py` (11.5 МБ)
- **Олимпиады:** `olympiads.py` (651 пробник)

### Модели БД (SQLite)
**Файл:** `models.py`
- `User` - пользователи (email, name, avatar_url, auth_code, math_level, ai_report)
- `OAuthAccount` - связь с Яндекс OAuth
- `ChatMessage` - история чата с AI-тьютором
- `MockExam` - пробники (5 задач)
- `MockExamTask` - задачи в пробнике
- `SecretTopic` - кэш теоретических материалов

### Авторизация
- **Passwordless:** email + 6-значный код (Yandex SMTP)
- **Яндекс OAuth:** кнопка "Войти через Яндекс"
- **Remember Me:** cookie на 30 дней

### AI функции
**DeepSeek API** (ключ в `.env`):
- **AI-Тьютор:** чат с памятью (20 сообщений)
- **Проверка пробников:** AI оценивает решения
- **Секреты олимпиадников:** AI генерирует теорию

### UI/UX
- **Dark Theme:** темная тема с градиентами
- **Адаптивный:** hamburger меню на мобильных
- **Логотип:** `static/logo.png`
- **Favicon:** полный набор в `static/`

## 🔧 Технологии

**Backend:**
- Flask 3.1.3
- Flask-SQLAlchemy (SQLite)
- Flask-Login (авторизация)
- Flask-Mail (email)

**Frontend:**
- Jinja2 templates
- Vanilla JavaScript
- CSS (без фреймворков)

**AI:**
- DeepSeek API (chat, генерация контента)
- Яндекс OAuth SDK

## 📁 Структура проекта

```
c:/Users/Victor/Desktop/Новая папка (2)/
├── app.py                 # Главный файл (1400+ строк)
├── models.py              # Модели БД
├── problems.py            # 11,599 задач
├── olympiads.py           # 651 пробник
├── requirements.txt       # Зависимости
├── .env                   # Переменные окружения
├── ai/
│   └── deepseek_client.py # Клиент DeepSeek API
├── static/
│   ├── logo.png           # Логотип
│   ├── favicon.ico        # Иконки
│   └── style.css          # Стили
├── templates/             # HTML шаблоны
│   ├── base.html          # Базовый шаблон
│   ├── index.html         # Главная
│   ├── login.html         # Вход
│   ├── exam.html          # Пробник
│   ├── secrets.html       # Секреты
│   └── ...
└── scripts/               # Утилиты
```

## 🔑 Переменные окружения (.env)

```env
# DeepSeek API
DEEPSEEK_API_KEY=sk-54c1fd3679ad45dd857871d788ecf262

# Email (Yandex SMTP)
MAIL_SERVER=smtp.yandex.ru
MAIL_PORT=465
MAIL_USE_SSL=True
MAIL_USERNAME=kr1venkovictor@yandex.ru
MAIL_PASSWORD=ktxfblhgcrlryncy

# Yandex OAuth
YANDEX_CLIENT_ID=f4cd6d13f99b474181aa80975472800c
YANDEX_CLIENT_SECRET=292a5d9da4734d669c0ea9f1b00c9462
DOMAIN_URL=http://localhost:5000

# Flask
SECRET_KEY=(автогенерация)
```

## 🎯 Основные функции

### 1. Разделы задач
- **URL:** `/section/<subject>`
- **Подтемы:** `/section/<subject>/<subtopic>`
- **Задачи:** `/problems?subject=...&grade=...&level=...`
- **Детали:** `/problem/<id>`

### 2. AI-Тьютор
- **Виджет:** плавающая кнопка 🤖 (справа внизу)
- **API:** `/api/tutor/history`, `/api/tutor/send`
- **Память:** 20 последних сообщений
- **Файл:** `templates/tutor_widget.html`

### 3. Умные пробники
- **Генерация:** `/api/exam/generate` (POST)
- **Прохождение:** `/exam/<id>`
- **Проверка:** `/api/exam/<id>/submit` (POST)
- **Результаты:** `/exam/<id>/results`
- **Выбор:** класс (5-11) + уровень (1-5)

### 4. Секреты олимпиадников
- **Список:** `/secrets`
- **Тема:** `/secrets/<topic>`
- **AI-генерация:** контент создается при первом посещении
- **Кэш:** таблица `secret_topics`

### 5. Олимпиады
- **Список:** `/olympiads`
- **Файл:** `olympiads.py` (651 пробник)
- **Проблема:** диапазоны классов "10-11" обрабатываются как строки

## ⚠️ Известные проблемы

### Исправлено
- ✅ Логотип (было logo.png.png)
- ✅ Grade диапазоны ("10-11")
- ✅ OLYMPIADS_INFO (создается из OLYMPIADS_DB)
- ✅ Категории "Другое" удалены
- ✅ Онбординг удален

### Требует внимания
- ⏳ Адаптивное тестирование (новая задача)
- ⏳ Личный кабинет с достижениями
- ⏳ Счетчик посетителей

## 🚀 Деплой

### GitHub
```bash
git add .
git commit -m "..."
git push origin main
```

### Render
- Автоматический деплой при push
- Добавить переменные окружения в Dashboard
- Проверить логи после деплоя

## 📝 Следующие задачи

### Приоритет 1: Адаптивное тестирование
- Создать `services/adaptive_test.py`
- Алгоритм выбора задач с весами
- Маршруты `/api/test/start`, `/api/test/submit`
- Таймауты для DeepSeek API

### Приоритет 2: Личный кабинет
- Звания по активности
- Статистика и достижения
- График прогресса
- Выбор аватарки

### Приоритет 3: Полировка
- Счетчик посетителей
- Hamburger меню (JavaScript)
- Оптимизация производительности

## 🔍 Полезные команды

### Запуск локально
```bash
python app.py
```

### Проверка БД
```bash
python scripts/audit_database.py
```

### Пересоздание БД
```bash
python scripts/force_reset_db.py
```

### Очистка кэша
```bash
powershell -Command "Remove-Item -Recurse -Force __pycache__"
```

## 📖 Документация

- [`docs/ONBOARDING_FEATURE.md`](docs/ONBOARDING_FEATURE.md) - AI онбординг (удален)
- [`docs/PASSWORDLESS_AUTH.md`](docs/PASSWORDLESS_AUTH.md) - Авторизация
- [`docs/GMAIL_SETUP.md`](docs/GMAIL_SETUP.md) - Настройка email
- [`plans/OLIMPIADA_RU_PARSER_PLAN.md`](plans/OLIMPIADA_RU_PARSER_PLAN.md) - Парсинг olimpiada.ru

## 🎨 Дизайн

### Цвета (CSS переменные)
```css
--bg-main: #0f172a
--bg-card: rgba(30, 41, 59, 0.94)
--accent-1: #8b5cf6 (фиолетовый)
--accent-2: #38bdf8 (голубой)
--text-main: #ffffff
--text-soft: #cbd5e1
```

### Компоненты
- Карточки с glass-эффектом
- Градиентные кнопки
- Плавные анимации
- Адаптивная сетка

## 🔐 Безопасность

- Коды авторизации не показываются в UI
- HTTPS cookies на продакшене
- Валидация всех входных данных
- Таймауты для внешних API

**ВСЯ ИНФОРМАЦИЯ ДЛЯ ПРОДОЛЖЕНИЯ РАБОТЫ!**

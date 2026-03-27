# 🚀 Инструкция по деплою проекта FORMYLA

## Подготовка завершена ✅

Все файлы для деплоя созданы:
- ✅ `requirements.txt` - зависимости Python
- ✅ `wsgi.py` - точка входа для WSGI серверов
- ✅ `.env.example` - шаблон переменных окружения
- ✅ `.gitignore` - исключения для Git

---

## Шаг 1: Установка Git (если еще не установлен)

Скачайте и установите Git для Windows:
https://git-scm.com/download/win

После установки перезапустите терминал.

---

## Шаг 2: Инициализация Git репозитория

Откройте терминал в папке проекта и выполните:

```bash
git init
git add .
git commit -m "Initial commit: Ready for production (Flask, Gunicorn, WSGI)"
```

---

## Шаг 3: Привязка к GitHub

```bash
git branch -M main
git remote add origin https://github.com/victorkrivenko4949-commits/FORMYLA.git
git push -u origin main
```

**Примечание:** GitHub может запросить авторизацию. Используйте Personal Access Token вместо пароля.

---

## Шаг 4: Деплой на Render.com

1. Зайдите на https://dashboard.render.com/
2. Авторизуйтесь через GitHub
3. Нажмите **New** → **Web Service**
4. Выберите репозиторий `victorkrivenko4949-commits/FORMYLA`
5. Настройки:
   - **Name:** `formyla` (или любое имя)
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn wsgi:app`
   - **Instance Type:** `Free`
6. В разделе **Environment Variables** добавьте:
   - Key: `SECRET_KEY`
   - Value: `your-random-secret-key-here-change-me`
7. Нажмите **Create Web Service**

Через 2-4 минуты ваш сайт будет доступен по адресу `https://formyla-xxxxx.onrender.com`

---

## Альтернативные хостинги

### PythonAnywhere
1. Загрузите файлы через Web interface
2. Создайте виртуальное окружение: `mkvirtualenv formyla`
3. Установите зависимости: `pip install -r requirements.txt`
4. В Web tab укажите путь к `wsgi.py`

### Heroku
```bash
heroku create formyla
git push heroku main
heroku config:set SECRET_KEY=your-secret-key
```

---

## Локальный запуск (Development)

```bash
python app.py
```
Сервер запустится на http://127.0.0.1:5000

---

## Production запуск (Gunicorn)

```bash
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app
```
Сервер запустится на http://0.0.0.0:8000

---

## Важные замечания

⚠️ **Не забудьте:**
- Установить `SECRET_KEY` в переменных окружения
- Не коммитить файл `.env` с реальными секретами
- Использовать `gunicorn` в production (не `python app.py`)

✅ **Проект готов к деплою!**

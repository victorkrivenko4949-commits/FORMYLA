# 🔐 Защищенный роут /admin/seed-secrets

## Назначение

Одноразовый защищенный роут для наполнения таблицы `olympiad_secrets` статьями на продакшен-сервере (Render).

## Безопасность

- ✅ Только POST запросы
- ✅ Требует секретный токен из переменной окружения
- ✅ Защита от timing attacks через `hmac.compare_digest()`
- ✅ Логирование всех попыток доступа
- ✅ Идемпотентность (можно вызывать повторно)

---

## Шаг 1: Генерация токена

На локальной машине выполните:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Пример вывода:
```
xK9mP2vL8nQ4rT6wY1zA3bC5dE7fG9hJ0kM2nP4qR6sT8uV0wX2yZ4aB6cD8eF
```

**Сохраните этот токен!** Он понадобится для настройки Render и для вызова роута.

---

## Шаг 2: Настройка на Render

1. Откройте ваш проект на [Render Dashboard](https://dashboard.render.com/)
2. Перейдите в **Environment** → **Environment Variables**
3. Добавьте новую переменную:
   - **Key:** `SEED_ADMIN_TOKEN`
   - **Value:** (вставьте сгенерированный токен)
4. Нажмите **Save Changes**
5. Render автоматически перезапустит приложение

---

## Шаг 3: Загрузка secrets_dump.json на сервер

### Вариант A: Через Git (рекомендуется)

```bash
# Убедитесь, что файл в репозитории
git add secrets_dump.json utils/seed_secrets_utils.py
git commit -m "Add secrets data for production seeding"
git push
```

Render автоматически задеплоит новую версию с файлом.

### Вариант B: Через Render Shell (если файл не в Git)

1. В Render Dashboard откройте **Shell**
2. Загрузите файл вручную или используйте `curl`:
```bash
curl -o secrets_dump.json https://your-domain.com/path/to/secrets_dump.json
```

---

## Шаг 4: Вызов роута для сидирования

### Вариант 1: Через curl (рекомендуется)

```bash
curl -X POST "https://your-app.onrender.com/admin/seed-secrets?token=YOUR_TOKEN_HERE"
```

**Ожидаемый ответ (успех):**
```json
{
  "status": "success",
  "message": "Secrets imported successfully",
  "inserted": 23,
  "skipped": 0,
  "total": 23,
  "stats": {
    "total": 23,
    "by_topic": {
      "Алгебра": 4,
      "Геометрия": 4,
      "Графы": 3,
      "Комбинаторика": 4,
      "Логика": 4,
      "Теория чисел": 4
    },
    "by_difficulty": {
      "2": 11,
      "3": 12
    }
  }
}
```

**Если таблица уже заполнена:**
```json
{
  "status": "skipped",
  "message": "Table already populated. Use ?force=1 to override.",
  "inserted": 0,
  "skipped": 23,
  "total": 23
}
```

### Вариант 2: С принудительной перезаписью

Если нужно обновить статьи (очистить и импортировать заново):

```bash
curl -X POST "https://your-app.onrender.com/admin/seed-secrets?token=YOUR_TOKEN_HERE&force=1"
```

### Вариант 3: Через заголовок X-Admin-Token

```bash
curl -X POST "https://your-app.onrender.com/admin/seed-secrets" \
  -H "X-Admin-Token: YOUR_TOKEN_HERE"
```

### Вариант 4: Через Postman/Insomnia

- **Method:** POST
- **URL:** `https://your-app.onrender.com/admin/seed-secrets`
- **Headers:** `X-Admin-Token: YOUR_TOKEN_HERE`
- **Query Params (optional):** `force=1`

---

## Коды ответов

| Код | Статус | Описание |
|-----|--------|----------|
| 200 | success | Статьи успешно импортированы |
| 200 | skipped | Таблица уже заполнена (используйте `?force=1`) |
| 403 | error | Невалидный или отсутствующий токен |
| 500 | error | Внутренняя ошибка сервера |
| 503 | error | SEED_ADMIN_TOKEN не настроен на сервере |

---

## Примеры ошибок

### Ошибка 403: Токен не предоставлен
```json
{
  "status": "error",
  "message": "Admin token required. Provide via X-Admin-Token header or ?token= parameter"
}
```

### Ошибка 403: Неверный токен
```json
{
  "status": "error",
  "message": "Invalid admin token"
}
```

### Ошибка 503: Токен не настроен
```json
{
  "status": "error",
  "message": "SEED_ADMIN_TOKEN not configured on server"
}
```

### Ошибка 500: Файл не найден
```json
{
  "status": "error",
  "message": "Internal server error: File secrets_dump.json not found",
  "inserted": 0,
  "skipped": 0,
  "total": 0
}
```

---

## Проверка результата

После успешного вызова роута:

1. Откройте сайт: `https://your-app.onrender.com`
2. Перейдите в раздел **"Секреты"**
3. Убедитесь, что статьи отображаются

Или проверьте через API:
```bash
curl "https://your-app.onrender.com/api/secrets/list"
```

---

## Деактивация роута после использования

### Вариант 1: Удалить токен из Environment (рекомендуется)

1. В Render Dashboard → Environment Variables
2. Удалите переменную `SEED_ADMIN_TOKEN`
3. Save Changes

Теперь роут будет возвращать 503 (токен не настроен).

### Вариант 2: Закомментировать роут в коде

В [`app.py`](app.py) закомментируйте весь блок:

```python
# @app.route("/admin/seed-secrets", methods=["POST"])
# def admin_seed_secrets():
#     ...
```

И задеплойте новую версию.

---

## Безопасность

### ✅ Что реализовано:

1. **Токен в переменных окружения** - не хранится в коде
2. **hmac.compare_digest()** - защита от timing attacks
3. **Только POST** - защита от случайных GET запросов
4. **Логирование** - все попытки доступа записываются
5. **Идемпотентность** - безопасно вызывать повторно
6. **Проверка дублей** - не создает дубликаты статей

### ⚠️ Рекомендации:

1. **Используйте HTTPS** - токен передается в открытом виде
2. **Удалите токен после использования** - роут больше не нужен
3. **Не публикуйте токен** - храните в секрете
4. **Используйте длинный токен** - минимум 48 символов

---

## Troubleshooting

### Проблема: "SEED_ADMIN_TOKEN not configured"

**Решение:**
1. Проверьте, что переменная добавлена в Render Environment
2. Перезапустите приложение на Render
3. Проверьте правильность имени переменной (без опечаток)

### Проблема: "Invalid admin token"

**Решение:**
1. Убедитесь, что токен скопирован полностью (без пробелов)
2. Проверьте, что используете тот же токен, что в Environment
3. Попробуйте передать через заголовок вместо query-параметра

### Проблема: "File secrets_dump.json not found"

**Решение:**
1. Убедитесь, что файл загружен на сервер
2. Проверьте путь к файлу (должен быть в корне проекта)
3. Если используете Git - убедитесь, что файл закоммичен

### Проблема: "Table already populated"

**Решение:**
Это не ошибка! Таблица уже заполнена. Если нужно обновить:
```bash
curl -X POST "https://your-app.onrender.com/admin/seed-secrets?token=YOUR_TOKEN&force=1"
```

---

## Альтернативный способ: Через Python скрипт

Если curl недоступен, создайте файл `call_seed_route.py`:

```python
import requests

URL = "https://your-app.onrender.com/admin/seed-secrets"
TOKEN = "your-token-here"

response = requests.post(URL, params={'token': TOKEN})
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

Запустите:
```bash
python call_seed_route.py
```

---

## Итоговый чеклист

- [ ] Сгенерирован токен (`python -c "import secrets; print(secrets.token_urlsafe(48))"`)
- [ ] Токен добавлен в Render Environment Variables
- [ ] Файл `secrets_dump.json` загружен на сервер (через Git)
- [ ] Приложение перезапущено на Render
- [ ] Вызван роут через curl
- [ ] Проверено отображение статей на сайте
- [ ] Токен удален из Environment (деактивация роута)

---

## Техническая информация

**Роут:** `POST /admin/seed-secrets`

**Параметры:**
- `token` (query, optional) - Админ-токен
- `force` (query, optional) - Если "1", очищает таблицу перед импортом

**Заголовки:**
- `X-Admin-Token` (optional) - Админ-токен (альтернатива query-параметру)

**Файл данных:** `secrets_dump.json` (23 статьи, 6 тем)

**Модель:** `OlympiadSecret` (поля: topic, title, content, difficulty_level)

**Утилиты:** [`utils/seed_secrets_utils.py`](../utils/seed_secrets_utils.py)

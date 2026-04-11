# Настройка Gmail для отправки email на Render.com

## ❌ Проблема на скриншоте
```
Ошибка настройки email-сервера.
Обратитесь к администратору.
```

Это ошибка аутентификации SMTP. Gmail блокирует вход с обычным паролем.

## ✅ Решение: Пароль приложения Gmail

### Шаг 1: Включите двухфакторную аутентификацию
1. Откройте https://myaccount.google.com/security
2. Найдите "Двухэтапная аутентификация"
3. Включите её (если еще не включена)

### Шаг 2: Создайте пароль приложения
1. Откройте https://myaccount.google.com/apppasswords
2. Выберите "Почта" и "Другое устройство"
3. Введите название: "FORMYLA Render"
4. Нажмите "Создать"
5. **Скопируйте 16-значный пароль** (например: `abcd efgh ijkl mnop`)

### Шаг 3: Обновите Environment Variables на Render
1. Откройте Render Dashboard
2. Перейдите в ваш сервис FORMYLA
3. Откройте "Environment"
4. Обновите переменные:

```
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=victor.krivenko.4949@gmail.com
MAIL_PASSWORD=abcdefghijklmnop  ← ПАРОЛЬ ПРИЛОЖЕНИЯ (без пробелов!)
```

**ВАЖНО**: 
- Используйте пароль приложения БЕЗ ПРОБЕЛОВ: `abcdefghijklmnop`
- НЕ используйте обычный пароль от Gmail!

### Шаг 4: Перезапустите сервис на Render
1. Нажмите "Manual Deploy" → "Clear build cache & deploy"
2. Или просто "Deploy latest commit"

### Шаг 5: Проверьте логи
После деплоя откройте Logs и ищите:
```
[EMAIL] Successfully sent to victor.krivenko.4949@gmail.com
```

Если видите:
```
[EMAIL ERROR] Authentication failed
```
→ Проверьте пароль приложения (возможно, скопировали с пробелами)

## 🔍 Альтернативная диагностика

### Проверьте логи Render:
```
Dashboard → Your Service → Logs
```

Ищите строки:
- `[EMAIL ERROR] Authentication failed` - неверный пароль
- `[EMAIL ERROR] Connection failed` - проблема с сетью
- `[EMAIL] Successfully sent` - всё работает!

### Если не помогло:

#### Вариант A: Используйте другой Gmail
Создайте новый Gmail аккаунт специально для FORMYLA:
1. Создайте новый Gmail
2. Включите 2FA
3. Создайте пароль приложения
4. Обновите MAIL_USERNAME и MAIL_PASSWORD на Render

#### Вариант B: Используйте SendGrid (бесплатно)
SendGrid дает 100 писем/день бесплатно:
1. Зарегистрируйтесь на https://sendgrid.com
2. Получите API ключ
3. Обновите код для использования SendGrid API

## 📝 Текущие настройки в коде

### [`app.py:81`](app.py:81)
```python
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
```

### [`app.py:934`](app.py:934)
```python
smtp_server = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
smtp_port = int(os.getenv('MAIL_PORT', '587'))

server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
server.starttls()  # TLS encryption
server.login(sender, password)
```

## ✅ Чеклист проверки

- [ ] Двухфакторная аутентификация включена в Gmail
- [ ] Пароль приложения создан (16 символов)
- [ ] MAIL_PASSWORD на Render = пароль приложения БЕЗ ПРОБЕЛОВ
- [ ] MAIL_USERNAME = полный email (victor.krivenko.4949@gmail.com)
- [ ] MAIL_SERVER = smtp.gmail.com
- [ ] MAIL_PORT = 587
- [ ] MAIL_USE_TLS = True
- [ ] Сервис перезапущен на Render
- [ ] Логи проверены

После выполнения всех пунктов email должен работать!

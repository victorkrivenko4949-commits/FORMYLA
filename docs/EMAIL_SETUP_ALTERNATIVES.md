# 📧 Настройка Email для FORMYLA - Альтернативные варианты

## ⚠️ Проблема: App Passwords недоступны

Если вы видите сообщение "The setting that you are looking for is not available for your account", это значит что:
- У вас не включена двухфакторная аутентификация (2FA)
- Или ваш аккаунт не поддерживает App Passwords

## 🔧 Решения (выберите одно)

### Вариант 1: Включить 2FA и создать App Password (Рекомендуется)

#### Шаг 1: Включите 2FA
1. Откройте: https://myaccount.google.com/security
2. Найдите **"2-Step Verification"** (Двухэтапная аутентификация)
3. Нажмите **"Get Started"**
4. Следуйте инструкциям (добавьте номер телефона)
5. Завершите настройку 2FA

#### Шаг 2: Создайте App Password
1. После включения 2FA откройте: https://myaccount.google.com/apppasswords
2. Создайте пароль для "FORMYLA"
3. Скопируйте 16-значный пароль
4. Добавьте в `.env`:
```env
MAIL_USERNAME=ваш_email@gmail.com
MAIL_PASSWORD=xxxx xxxx xxxx xxxx
```

---

### Вариант 2: Использовать другой email сервис

#### Yandex Mail (Яндекс.Почта)

**Преимущества:** Проще настроить, не требует 2FA

**Настройка:**
1. Откройте: https://passport.yandex.ru/profile
2. Перейдите в **"Безопасность"** → **"Пароли приложений"**
3. Создайте пароль для "FORMYLA"
4. В `.env`:
```env
MAIL_USERNAME=ваш_email@yandex.ru
MAIL_PASSWORD=ваш_пароль_приложения
```

5. В [`app.py`](../app.py:29) измените:
```python
app.config['MAIL_SERVER'] = 'smtp.yandex.ru'
app.config['MAIL_PORT'] = 587
```

#### Mail.ru

**Настройка:**
1. Включите IMAP/SMTP в настройках Mail.ru
2. Создайте пароль для внешних приложений
3. В `.env`:
```env
MAIL_USERNAME=ваш_email@mail.ru
MAIL_PASSWORD=ваш_пароль
```

4. В [`app.py`](../app.py:29):
```python
app.config['MAIL_SERVER'] = 'smtp.mail.ru'
app.config['MAIL_PORT'] = 587
```

---

### Вариант 3: Использовать SendGrid (Профессиональный)

**Преимущества:** Бесплатно до 100 писем/день, надежно

**Настройка:**
1. Зарегистрируйтесь: https://sendgrid.com/
2. Создайте API ключ
3. Установите: `pip install sendgrid`
4. Используйте SendGrid API вместо SMTP

---

### Вариант 4: Временно - вывод в консоль (для разработки)

Если не хотите настраивать email прямо сейчас:

**Текущая реализация** уже поддерживает fallback:
- Если email не настроен → код выводится в консоль
- Просто не заполняйте `MAIL_USERNAME` и `MAIL_PASSWORD` в `.env`

---

## 🎯 Рекомендация

**Для быстрого старта:** Используйте **Вариант 4** (консоль)

**Для продакшена:** Настройте **Вариант 1** (Gmail с 2FA) или **Вариант 2** (Yandex)

---

## 📝 Краткая инструкция для Gmail (если включите 2FA)

1. **Включите 2FA:** https://myaccount.google.com/security → "2-Step Verification"
2. **Создайте App Password:** https://myaccount.google.com/apppasswords → "Create"
3. **Добавьте в `.env`:**
```env
MAIL_USERNAME=ваш_email@gmail.com
MAIL_PASSWORD=скопированный_app_password
```
4. **Перезапустите сервер:** `python app.py`

---

## ✅ Текущее состояние

Система работает в режиме **fallback** - коды выводятся в консоль если email не настроен.

Вы можете тестировать авторизацию прямо сейчас!
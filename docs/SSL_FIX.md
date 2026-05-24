# Срочный фикс HTTPS для formyla.ru

> ⚠️ Это инструкция для прод-сервера (Ubuntu/Debian). Локально SSL не нужен — Flask отдаёт HTTP на 5000.

---

## Вариант A — Caddy (рекомендуется: автоматический Let's Encrypt)

### 1. Установка
```bash
sudo apt update
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

### 2. `/etc/caddy/Caddyfile`
```caddyfile
formyla.ru, www.formyla.ru {
    encode gzip zstd

    # Прокидываем реальный IP клиента и схему — нужно
    # для `request.is_secure` и `X-Forwarded-For` в Flask.
    reverse_proxy 127.0.0.1:5000 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        header_up Host {host}
    }

    # Безопасные заголовки.
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }

    # Логи.
    log {
        output file /var/log/caddy/formyla.access.log
        format json
    }
}

# HTTP → HTTPS делает сам Caddy автоматически (он слушает :80 и редиректит на :443).
```

### 3. Запуск
```bash
sudo systemctl enable --now caddy
sudo systemctl reload caddy        # после правки Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
```

Caddy сам получит и продлит Let's Encrypt cert. Проверка:
```bash
curl -I https://formyla.ru/
# должен быть HTTP/2 200 + Strict-Transport-Security
```

---

## Вариант B — nginx + certbot

### 1. Установка
```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 2. `/etc/nginx/sites-available/formyla`
```nginx
# HTTP → редирект на HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name formyla.ru www.formyla.ru;
    return 301 https://$host$request_uri;
}

# HTTPS
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name formyla.ru www.formyla.ru;

    # эти строки certbot вставит сам, но можно прописать заранее:
    # ssl_certificate     /etc/letsencrypt/live/formyla.ru/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/formyla.ru/privkey.pem;
    # include /etc/letsencrypt/options-ssl-nginx.conf;
    # ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 16M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
```

### 3. Активация + получение cert
```bash
sudo ln -sf /etc/nginx/sites-available/formyla /etc/nginx/sites-enabled/formyla
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d formyla.ru -d www.formyla.ru --redirect --agree-tos -m admin@formyla.ru
```

`--redirect` гарантирует, что HTTP→HTTPS-редирект пропишется в nginx.
Автообновление: certbot ставит timer `certbot.timer` (раз в 12ч).

---

## Acceptance-чеклист

- [ ] `curl -I http://formyla.ru/` → `301 https://formyla.ru/`
- [ ] `curl -I https://formyla.ru/` → `200 OK` без ошибок TLS
- [ ] В Chrome / Safari открывается без предупреждений (замок зелёный)
- [ ] [SSL Labs](https://www.ssllabs.com/ssltest/analyze.html?d=formyla.ru) — A или A+
- [ ] `https://www.formyla.ru/` тоже работает (или редиректит на apex)
- [ ] Flask видит `request.is_secure == True` (нужно для secure-cookie у UTM/session)

> Если за nginx/Caddy Flask отдаёт http и `request.is_secure` всегда False —
> убедись, что в `app.py` стоит ProxyFix:
> ```python
> from werkzeug.middleware.proxy_fix import ProxyFix
> app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
> ```

---

## Дебаг типовых ошибок

| Симптом | Причина | Фикс |
|---|---|---|
| `ERR_CONNECTION_REFUSED` на :443 | nginx/caddy не запущен или firewall | `sudo ufw allow 443/tcp; systemctl status caddy` |
| `NET::ERR_CERT_AUTHORITY_INVALID` | Cert не получен (DNS не указывает на сервер) | `dig formyla.ru` — A-запись должна быть IP сервера |
| `502 Bad Gateway` | Flask не запущен на :5000 | `systemctl status formyla; ss -tlnp | grep 5000` |
| HTTP не редиректит на HTTPS | Нет server-блока на :80 с `return 301` | См. nginx-конфиг выше, или используй Caddy (автоматом) |
| Cookies теряются между запросами | `secure=True` cookies через HTTP | ProxyFix + `X-Forwarded-Proto` |

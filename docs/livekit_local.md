# Локальный LiveKit-сервер для разработки

Эта инструкция — для запуска видео-встречи "по типу Zoom" на доске
(`/drawing?tab=whiteboard&meet=`) на твоей машине без облака.

## Что нужно

* Docker Desktop (Windows / macOS) **или** Docker Engine (Linux)
* Свободные порты `7880`, `7881`, `7882/udp`

## Шаг 1. Запустить LiveKit-сервер

В корне проекта:

```bash
docker compose -f docker-compose.livekit.yml up -d
```

Проверить, что контейнер живой:

```bash
docker logs formyla-livekit --tail 20
```

Должно быть видно `starting LiveKit server` и `listening on :7880`.

## Шаг 2. Прописать .env

Создай (или дополни) `.env` в корне:

```dotenv
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=devsecret0123456789abcdef0123456789abcdef
```

> ⚠️ Эти dev-ключи **только для локалки**. На проде на Render — другие, из
> LiveKit Cloud, как описано в [`docs/livekit_setup.md`](livekit_setup.md).

## Шаг 3. Перезапустить Flask

```bash
python app.py
```

Проверь, что подцепилось:

```bash
curl http://localhost:5001/api/wb_meet/config
```

Должно вернуть:

```json
{"enabled": true, "url": "ws://localhost:7880", "max": 10, "token_ttl_seconds": 3600}
```

Если `enabled: false` — `.env` не прочитан. Убедись, что в [`app.py`](../app.py:46-47)
вызывается `load_dotenv()` (он там есть) и что файл `.env` лежит **в корне проекта**.

## Шаг 4. Проверить в браузере

1. Открой `http://localhost:5001/drawing?tab=whiteboard`
2. В верхней панели должна появиться зелёная кнопка **👥** (Групповой звонок)
3. Кликни → введи имя ("Виктор") и код комнаты ("math-42") → **Войти**
4. Браузер попросит доступ к камере/микрофону → разреши
5. Открой **вторую вкладку** на ту же ссылку, введи **то же** имя комнаты
   с другим именем ("Ученик") → должен увидеть себя и первую вкладку

## Шаг 5. Подключение второго устройства

Локальный сервер `ws://localhost:7880` доступен только с твоей машины.
Чтобы подключиться с телефона или другого ноутбука в той же Wi-Fi:

1. Узнай IP-адрес машины:
   ```bash
   # Windows:
   ipconfig
   # Linux/macOS:
   ifconfig | grep inet
   ```
   Например, `192.168.1.42`.

2. В `.env` поменяй URL:
   ```dotenv
   LIVEKIT_URL=ws://192.168.1.42:7880
   ```

3. Открой firewall для портов 7880, 7881, 7882/udp.

4. На втором устройстве зайди на `http://192.168.1.42:5001/drawing?tab=whiteboard`.

> Браузеры требуют `https` для камеры/микрофона на не-localhost адресах.
> Если хочешь тестить с телефона серьёзно — используй LiveKit Cloud
> (URL `wss://`, https автоматически) или поставь reverse-proxy с
> self-signed сертификатом.

## Остановить сервер

```bash
docker compose -f docker-compose.livekit.yml down
```

## Архитектура

```
браузер 1 ──┐
            ├──► ws://localhost:7880 ──► LiveKit SFU
браузер 2 ──┘                            (медиа-роутинг)
                ▲
                │ HTTP /api/wb_meet/token (JWT)
                │
            Flask app (Render / localhost)
```

* Flask только **выдаёт JWT-токены** для подключения к комнате
* Все аудио/видео-пакеты идут **браузер ⟷ LiveKit SFU**, через Flask не проходят
* На локалке нагрузки на Render нет вообще

## FAQ

**Q: Что если порт 7880 занят?**  
A: Поменяй mapping в `docker-compose.livekit.yml`: `"8880:7880"` и в `.env`
поставь `LIVEKIT_URL=ws://localhost:8880`.

**Q: Камера/микрофон не подключаются.**  
A: Браузер на `http://` (не `https://`) разрешает медиа только для
`localhost`. Если работаешь по IP в LAN — нужен https. См. Шаг 5.

**Q: На Render тоже это поставить?**  
A: Нет. На Render используй LiveKit Cloud (free tier) — см.
[`docs/livekit_setup.md`](livekit_setup.md). Render free tier не подходит
для постоянного docker-сервиса с UDP-портами.

**Q: Сколько участников одновременно?**  
A: Серверный код в [`routes/wb_meet.py`](../routes/wb_meet.py:69) ставит cap 10.
Локальный LiveKit-сервер технически выдержит больше, но синхронизация
доски через data-channel и общий FPS просядут на >5 участниках.

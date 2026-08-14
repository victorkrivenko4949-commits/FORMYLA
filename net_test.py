#!/usr/bin/env python3
"""
Сравнение двух способов ходить в API: requests против стандартного urllib.
Гоняет по 8 параллельных запросов каждым способом и смотрит, что выживает.

ЗАПУСК:
    python -X faulthandler -u net_test.py

Занимает пару минут и десяток центов. Ключ берётся из DEEPSEEK_API_KEY.
"""

import os
import sys
import ssl
import json
import time
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-pro"
WORKERS = 8
ROUNDS = 3

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KEY = os.getenv("DEEPSEEK_API_KEY", "")
if not KEY:
    sys.exit('Ключ не задан: $env:DEEPSEEK_API_KEY = "sk-..."')

PAYLOAD = {
    "model": MODEL,
    "messages": [{"role": "user",
                  "content": "Посчитай 17*23 и ответь json: {\"r\": число}"}],
    "max_tokens": 2000,
    "response_format": {"type": "json_object"},
}

HEADERS = {"Authorization": f"Bearer {KEY}",
           "Content-Type": "application/json"}

lock = threading.Lock()
log = []


def note(s):
    with lock:
        log.append(s)
        print("   " + s, flush=True)


def via_urllib(i):
    t0 = time.time()
    body = json.dumps(PAYLOAD).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, headers=HEADERS,
                                 method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        c = data["choices"][0]["message"]["content"][:40]
        note(f"urllib #{i}: OK за {time.time()-t0:.1f} с | {c}")
        return True
    except Exception as e:
        note(f"urllib #{i}: СБОЙ {type(e).__name__}: {str(e)[:120]}")
        return False


def via_requests(i):
    import requests
    t0 = time.time()
    try:
        r = requests.post(API_URL, headers=HEADERS, json=PAYLOAD, timeout=180)
        r.raise_for_status()
        c = r.json()["choices"][0]["message"]["content"][:40]
        note(f"requests #{i}: OK за {time.time()-t0:.1f} с | {c}")
        return True
    except Exception as e:
        note(f"requests #{i}: СБОЙ {type(e).__name__}: {str(e)[:120]}")
        return False


def bench(fn, name):
    print(f"\n=== {name}: {WORKERS} потоков x {ROUNDS} раундов ===", flush=True)
    ok = 0
    total = 0
    t0 = time.time()
    for rnd in range(1, ROUNDS + 1):
        print(f"-- раунд {rnd}", flush=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = [ex.submit(fn, i) for i in range(1, WORKERS + 1)]
            for f in as_completed(futs):
                total += 1
                if f.result():
                    ok += 1
    print(f"=== {name}: успешно {ok} из {total} "
          f"за {int(time.time()-t0)} с ===", flush=True)
    return ok, total


def main():
    print(f"Проверка транспорта. Потоков {WORKERS}, раундов {ROUNDS}.")
    print("Если процесс умрёт молча — виноват тот способ, "
          "на котором это случилось.\n", flush=True)

    a = bench(via_urllib, "СТАНДАРТНЫЙ urllib")
    print("\nurllib пережил нагрузку, перехожу к requests...\n", flush=True)
    time.sleep(3)
    b = bench(via_requests, "БИБЛИОТЕКА requests")

    print("\n" + "=" * 55)
    print(f"urllib  : {a[0]}/{a[1]}")
    print(f"requests: {b[0]}/{b[1]}")
    print("=" * 55)
    if b[0] < a[0]:
        print("Вывод: requests работает хуже, надо переводить скрипты на urllib.")
    elif a[0] == b[0] == a[1]:
        print("Вывод: оба способа живы. Дело не в транспорте, "
              "а в чём-то другом.")


if __name__ == "__main__":
    main()

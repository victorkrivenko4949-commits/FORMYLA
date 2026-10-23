# -*- coding: utf-8 -*-
"""Проверить DeepSeek endpoint напрямую с моделью deepseek-v4-pro."""
import json
import os
import sys

def _load_dotenv(path=".env"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass

_load_dotenv()
import requests

KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
URL = "https://api.deepseek.com/v1/chat/completions"
for model in ["deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"]:
    payload = {"model": model, "messages": [{"role": "user", "content": "ping"}],
               "temperature": 0.1, "max_tokens": 16}
    try:
        r = requests.post(URL, headers={"Authorization": f"Bearer {KEY}",
                          "Content-Type": "application/json"}, json=payload, timeout=(15, 60))
        print("model=", model, "status=", r.status_code, "body[:300]=", r.text[:300].replace("\n", " "))
    except Exception as e:
        print("model=", model, "EXC", type(e).__name__, str(e)[:200])

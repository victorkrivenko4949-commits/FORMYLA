# -*- coding: utf-8 -*-
"""
services/kimi_vision.py — KIMI Vision API (direct Moonshot CN).
"""
import base64
import logging
import requests

logger = logging.getLogger(__name__)

KIMI_KEY = "sk-CGqFLtMidguq9qByAskdTcqYeNlIDisiwJfi8YtREt8Veqoq"
KIMI_MODEL = "moonshot-v1-8k"
KIMI_URL = "https://api.moonshot.cn/v1"


def process_photo_with_kimi(image_bytes: bytes, mime_type: str = "image/jpeg"):
    try:
        b64 = base64.b64encode(image_bytes).decode()
    except Exception as e:
        return None, str(e)
    data_url = f"data:{mime_type};base64,{b64}"
    try:
        r = requests.post(f"{KIMI_URL}/chat/completions",
            headers={"Authorization": f"Bearer {KIMI_KEY}", "Content-Type": "application/json"},
            json={"model": KIMI_MODEL, "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": "Recognize math problem from photo. Rewrite ALL text, formulas. Answer in Russian."}
            ]}], "max_tokens": 2000, "temperature": 0.1},
            timeout=60)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"], None
        return None, f"KIMI HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return None, str(e)

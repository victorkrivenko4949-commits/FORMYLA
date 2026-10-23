#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke-test OdiRouter (Gemini) — подтвердить base_url, модель, auth, usage.

Usage: python scripts/recon/probe_odirouter.py
"""
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Загрузить .env (как это делает app.py).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    ))
except Exception:
    pass

KEY = os.environ.get("GEMINI_API_KEY", "").strip()
BASE = os.environ.get("GEMINI_BASE_URL", "https://api.odirouter.ai/v1").rstrip("/")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash").strip()

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "odirouter_probe.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)


def main():
    if not KEY:
        print("GEMINI_API_KEY not set")
        sys.exit(2)
    url = f"{BASE}/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You return JSON."},
            {"role": "user", "content": "Ответь ровно: {\"ok\": true}"},
        ],
        "temperature": 0.1,
        "max_tokens": 100,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
    }
    print(f"URL={url}\nMODEL={MODEL}")
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    print(f"HTTP {r.status_code}")
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:2000]}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "url": url, "model": MODEL, "status": r.status_code, "body": body,
        }, f, ensure_ascii=False, indent=2)
    print(f"written {OUT}")
    # Ключевые факты.
    print("choices present:", bool(body.get("choices")))
    if body.get("choices"):
        msg = body["choices"][0].get("message", {}) or {}
        print("content:", repr((msg.get("content") or "")[:200]))
    print("usage:", body.get("usage"))
    print("reasoning_tokens in usage:", "reasoning_tokens" in (body.get("usage") or {}))


if __name__ == "__main__":
    main()

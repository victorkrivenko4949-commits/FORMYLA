#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Простой тест DeepSeek API
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# Загружаем .env
load_dotenv()

# Получаем ключ
api_key = os.environ.get('DEEPSEEK_API_KEY')

if not api_key:
    print("ERROR: DEEPSEEK_API_KEY not found in .env")
    exit(1)

print(f"OK: API Key found: {api_key[:20]}...")

# Тестируем официальный DeepSeek API
url = "https://api.deepseek.com/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "user", "content": "Привет! Ответь одним словом: работаешь?"}
    ],
    "temperature": 0.7,
    "max_tokens": 50
}

print(f"\nSending request to {url}...")
print(f"Message: Hello! Reply in one word: working?")

try:
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    print(f"\nResponse code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        print(f"SUCCESS! AI response: {content}")
    else:
        print(f"ERROR! Server response:")
        print(response.text)
        
except requests.exceptions.Timeout:
    print("TIMEOUT! Server did not respond in 30 seconds")
except requests.exceptions.ConnectionError as e:
    print(f"CONNECTION ERROR: {e}")
except Exception as e:
    print(f"ERROR: {e}")

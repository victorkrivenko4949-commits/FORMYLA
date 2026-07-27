#!/usr/bin/env python3
"""Debug DeepSeek API connectivity and response format."""
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get('DEEPSEEK_API_KEY', '')
print(f"API Key starts with: {api_key[:8] if api_key else 'EMPTY'}...")

# Minimal test
payload = {
    'model': 'deepseek-chat',
    'messages': [
        {'role': 'system', 'content': 'You are a helpful assistant.'},
        {'role': 'user', 'content': 'Say "Hello World" in JSON: {"message": "hello"}'},
    ],
    'temperature': 0.1,
    'max_tokens': 100,
}

headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
}

print(f"\nCalling {payload['model']} on https://api.deepseek.com/v1/chat/completions...")
try:
    resp = requests.post(
        'https://api.deepseek.com/v1/chat/completions',
        json=payload,
        headers=headers,
        timeout=30
    )
    print(f"HTTP {resp.status_code}")
    print(f"Response body (first 500 chars):")
    print(resp.text[:500])
    
    if resp.status_code == 200:
        data = resp.json()
        content = data['choices'][0]['message']['content']
        print(f"\nContent: {content[:300]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

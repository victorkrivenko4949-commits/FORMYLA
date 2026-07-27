#!/usr/bin/env python3
"""Test minimal API call to qwen-plus"""
import requests, json, time

key = open('l1_l3_generation/openrouter_key.txt').read().strip()
headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

# Try the absolute cheapest: qwen-plus with minimal tokens
for model in ['qwen/qwen-plus', 'qwen/qwen-plus-2025-07-28', 'qwen/qwen3.5-plus-20260420']:
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': 'Say OK'}],
        'max_tokens': 10,
        'temperature': 0.0
    }
    r = requests.post('https://openrouter.ai/api/v1/chat/completions', headers=headers, json=payload, timeout=30)
    print(f'{model}: {r.status_code}')
    if r.status_code == 200:
        j = r.json()
        print(f'  OK: {j["choices"][0]["message"]["content"]}')
        print(f'  Cost: ${j.get("usage",{}).get("total_cost",0)}')
    elif r.status_code == 402:
        print(f'  402: {r.text[:150]}')
    else:
        print(f'  {r.status_code}: {r.text[:150]}')
    time.sleep(1)

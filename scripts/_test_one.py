#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test: generate exactly 1 task for grade 11."""
import json, os, sys, requests, psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

DB_URL = ('postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe'
          '@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com'
          '/formyla?sslmode=require')
API_KEY = os.environ.get('DEEPSEEK_API_KEY')
API_URL = "https://api.deepseek.com/v1/chat/completions"

print(f"API key: {API_KEY[:10]}...", flush=True)

# 1. Call API
print("Calling DeepSeek API...", flush=True)
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
payload = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "system", "content": "Generate a math task for grade 11. Return JSON with keys: condition, solution, answer."},
        {"role": "user", "content": "Topic: Algebra, Difficulty: 1. Return JSON only."}
    ],
    "temperature": 0.7,
    "max_tokens": 1500
}
resp = requests.post(API_URL, json=payload, headers=headers, timeout=90)
print(f"API status: {resp.status_code}", flush=True)
raw = resp.json()['choices'][0]['message']['content']
print(f"Raw response: {raw[:100]}...", flush=True)

# 2. Connect to DB
print("Connecting to DB...", flush=True)
conn = psycopg2.connect(DB_URL)
print("DB connected!", flush=True)
conn.close()
print("ALL DONE", flush=True)

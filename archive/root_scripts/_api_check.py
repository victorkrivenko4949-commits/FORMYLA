#!/usr/bin/env python3
"""Check OpenRouter API availability and list cheap models."""
import json, os, requests

key_path = 'l1_l3_generation/openrouter_key.txt'
if not os.path.exists(key_path):
    print("NO_API_KEY: openrouter_key.txt not found")
    exit(1)

key = open(key_path).read().strip()
print(f"API Key: {key[:8]}...{key[-4:]}")

headers = {
    'Authorization': f'Bearer {key}',
    'Content-Type': 'application/json'
}

# List models
r = requests.get('https://openrouter.ai/api/v1/models', headers=headers, timeout=30)
if r.status_code != 200:
    print(f"API_ERROR: HTTP {r.status_code}")
    exit(1)

data = r.json()
models_list = data.get('data', data if isinstance(data, list) else [])

print(f"\nTotal models: {len(models_list)}")

# Find cheap models - under $3/M tokens total
cheap = []
for m in models_list:
    name = m.get('id', '')
    pricing = m.get('pricing', {})
    try:
        prompt_cost = float(pricing.get('prompt', 1000))
        completion_cost = float(pricing.get('completion', 1000))
    except (ValueError, TypeError):
        continue
    
    total_per_m = (prompt_cost + completion_cost) * 1000000
    if total_per_m <= 3.0:
        cheap.append((name, prompt_cost, completion_cost, total_per_m))

cheap.sort(key=lambda x: x[3])
print(f"\nCheap models (<= $3/M tokens): {len(cheap)}")
print(f"{'Model':<60} {'Prompt':>10} {'Completion':>12} {'Total/M':>10}")
print("-" * 95)
for name, p, c, t in cheap[:20]:
    print(f"{name:<60} {p:<10.6f} {c:<12.6f} {t:<10.4f}")

# Print all available models that look like DeepSeek or Qwen or Mistral
print(f"\nRelevant models (DeepSeek, Qwen, Mistral, Gemini):")
print(f"{'Model':<60} {'Prompt':>10} {'Completion':>12}")
print("-" * 85)
for m in models_list:
    name = m.get('id', '')
    pricing = m.get('pricing', {})
    try:
        p = float(pricing.get('prompt', 0))
        c = float(pricing.get('completion', 0))
    except:
        continue
    if any(x in name.lower() for x in ['deepseek', 'qwen', 'mistral', 'gemini', 'claude-3-haiku']):
        print(f"{name:<60} {p:<10.6f} {c:<12.6f}")

# Test a simple generation
print("\n\nTest: simple generation call...")
test_payload = {
    "model": "deepseek/deepseek-chat",
    "messages": [
        {"role": "user", "content": "Say exactly: API_OK"}
    ],
    "max_tokens": 20,
    "temperature": 0.0
}

r2 = requests.post(
    'https://openrouter.ai/api/v1/chat/completions',
    headers=headers,
    json=test_payload,
    timeout=30
)

if r2.status_code == 200:
    result = r2.json()
    content = result['choices'][0]['message']['content']
    print(f"Test result: {content.strip()}")
    print("API_AVAILABLE: YES")
else:
    print(f"Test failed: HTTP {r2.status_code}")
    print(r2.text[:500])
    print("API_AVAILABLE: NO")

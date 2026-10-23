#!/usr/bin/env python3
import requests, json

key = open('l1_l3_generation/openrouter_key.txt').read().strip()
headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

# Check key info
r = requests.get('https://openrouter.ai/api/v1/auth/key', headers=headers)
data = r.json()['data']
print(f"Usage total: {data['usage']:.4f}")
print(f"Monthly: {data['usage_monthly']:.4f}")
print(f"Limit remaining: {data.get('limit_remaining', 'null')}")
print(f"Expires: {data.get('expires_at', 'never')}")
print(f"Free tier: {data.get('is_free_tier', False)}")

# List cheapest models
r2 = requests.get('https://openrouter.ai/api/v1/models', headers=headers, timeout=30)
models = r2.json()['data']
cheap = [m for m in models if float(m.get('pricing',{}).get('prompt', 1)) < 0.0000005 and 'text' in m.get('id','')]
print(f'\nCheapest models ({len(cheap)}):')
for m in sorted(cheap, key=lambda x: float(x['pricing']['prompt']))[:20]:
    print(f"  {m['id']}: ${m['pricing']['prompt']}/prompt, ${m['pricing']['completion']}/completion, {m.get('context_length',0)} ctx")

# Also check qwen specifically
qwen = [m for m in models if 'qwen' in m['id'] and 'plus' in m['id']]
print(f'\nQwen models:')
for m in qwen:
    print(f"  {m['id']}: ${m['pricing']['prompt']}/prompt, ${m['pricing']['completion']}/completion")

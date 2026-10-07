import json, os, httpx, sys

api_key = os.environ.get('DEEPSEEK_API_KEY', '')
print(f'API Key: {api_key[:8]}... ({len(api_key)} chars)', flush=True)

try:
    resp = httpx.post(
        'https://api.deepseek.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': 'deepseek/deepseek-chat',
            'messages': [{'role': 'user', 'content': 'Say hello in JSON {"greeting": "hello"}'}],
            'max_tokens': 50
        },
        timeout=60
    )
    print(f'Status: {resp.status_code}', flush=True)
    data = resp.json()
    content = data['choices'][0]['message']['content']
    print(f'Response: {content[:200]}', flush=True)
    print(f'Usage: {data.get("usage", {})}', flush=True)
except Exception as e:
    print(f'Error: {e}', flush=True)
    sys.exit(1)

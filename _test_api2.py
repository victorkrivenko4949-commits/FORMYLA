import json, os, httpx, sys

api_key = os.environ.get('DEEPSEEK_API_KEY', '')
print(f'API Key: {api_key[:8]}... ({len(api_key)} chars)', flush=True)

try:
    # Test DeepSeek API at their actual endpoint
    urls = [
        'https://api.deepseek.com/v1/chat/completions',
        'https://api.deepseek.com/chat/completions',
        'https://openrouter.ai/api/v1/chat/completions'
    ]
    
    for url in urls:
        print(f'\n--- Trying {url} ---', flush=True)
        resp = httpx.post(
            url,
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': 'deepseek-chat',
                'messages': [{'role': 'user', 'content': 'Say hello in JSON'}],
                'max_tokens': 100
            },
            timeout=30
        )
        print(f'Status: {resp.status_code}', flush=True)
        print(f'Response: {resp.text[:500]}', flush=True)
        if resp.status_code == 200:
            data = resp.json()
            content = data['choices'][0]['message']['content']
            print(f'SUCCESS: {content[:200]}', flush=True)
            break
except Exception as e:
    print(f'Error: {e}', flush=True)
    sys.exit(1)

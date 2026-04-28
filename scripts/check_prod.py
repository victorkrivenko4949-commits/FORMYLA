import requests, re, sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
r = requests.get('https://formyla-com.onrender.com/secrets', timeout=30)
print('HTTP', r.status_code)
# Save HTML
with open('_secrets_check.html', 'w', encoding='utf-8') as f:
    f.write(r.text)
# Search for numbers
text = r.text
for pattern in [r'Всего статей[^\d]*(\d+)', r'olympiad_secrets[^\d]*(\d+)', r'secret_topics[^\d]*(\d+)', r'(\d+)\s*секрет', r'(\d+)\s*тем']:
    m = re.search(pattern, text)
    if m:
        print(f'Found: {pattern} -> {m.group(0)[:80]}')
# Check API
r2 = requests.get('https://formyla-com.onrender.com/api/migrate/tables', params={'secret': 'formyla-migrate-2026'}, timeout=30)
print('API:', r2.json())
{
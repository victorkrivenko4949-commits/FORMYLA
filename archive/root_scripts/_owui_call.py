# -*- coding: utf-8 -*-
import urllib.request, json, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

payload_json = sys.argv[1]
out_file = sys.argv[2] if len(sys.argv) > 2 else ""

key = os.environ.get('H2_API_KEY') or ""
if not key:
    import winreg
    # read from User env via winreg (avoid printing)
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment')
        key = winreg.QueryValueEx(k, 'H2_API_KEY')[0]
        winreg.CloseKey(k)
    except Exception:
        pass

if not key:
    print('BLOCK_H2_API_KEY_MISSING')
    sys.exit(1)

payload = json.loads(payload_json)
if payload.get('node') and str(payload['node']) != 'victor':
    print('BLOCK_NON_VICTOR_NODE')
    sys.exit(1)

content = "```json\n" + payload_json + "\n```"
body = json.dumps({
    "model": "h2_roo_function",
    "stream": False,
    "messages": [{"role": "user", "content": content}],
})

req = urllib.request.Request(
    'https://chat.h2platform.ru/api/chat/completions',
    data=body.encode('utf-8'),
    headers={
        'Authorization': 'Bearer ' + key,
        'Content-Type': 'application/json',
    },
    method='POST',
)
try:
    resp = urllib.request.urlopen(req, timeout=930).read().decode('utf-8', 'replace')
except urllib.error.HTTPError as e:
    print('BLOCK_OWUI_FUNCTION_HTTP_' + str(e.code))
    sys.exit(1)

if out_file:
    open(out_file, 'w', encoding='utf-8').write(resp)
print(resp)

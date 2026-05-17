"""Smoke-test the wb_call blueprint without the rest of the app."""
import json
from flask import Flask
from routes.wb_call import wb_call_bp

app = Flask(__name__)
app.register_blueprint(wb_call_bp)
c = app.test_client()

r1 = c.post('/api/wb_call/join', json={'room': 'smoke-room'})
r2 = c.post('/api/wb_call/join', json={'room': 'smoke-room'})
r3 = c.post('/api/wb_call/join', json={'room': 'smoke-room'})
print('join1:', r1.status_code, r1.get_json())
print('join2:', r2.status_code, r2.get_json())
print('join3 (must be 409):', r3.status_code, r3.get_json())

p1 = r1.get_json()['peer_id']
p2 = r2.get_json()['peer_id']

r4 = c.post('/api/wb_call/send', json={
    'room': 'smoke-room', 'from': p1, 'to': p2,
    'msg': {'type': 'sdp', 'sdp': {'type': 'offer', 'sdp': 'fake'}},
})
print('send sdp:', r4.status_code, r4.get_json())

r5 = c.post('/api/wb_call/poll', json={'room': 'smoke-room', 'peer_id': p2})
print('poll p2:', r5.status_code)
print('  data:', json.dumps(r5.get_json(), ensure_ascii=False)[:400])

r6 = c.post('/api/wb_call/leave', json={'room': 'smoke-room', 'peer_id': p1})
print('leave p1:', r6.status_code, r6.get_json())

r7 = c.post('/api/wb_call/poll', json={'room': 'smoke-room', 'peer_id': p2})
print('poll p2 after p1 leave:', r7.status_code)
print('  data:', json.dumps(r7.get_json(), ensure_ascii=False)[:400])

print('status:', c.get('/api/wb_call/status').get_json())
print('OK')

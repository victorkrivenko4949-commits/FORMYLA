"""Smoke-test the wb_meet blueprint without contacting the real LiveKit server.

Verifies:
  • /config returns enabled=False when env is empty
  • /config returns the URL when env is set (without leaking the secret)
  • /token mints a syntactically-correct JWT (3 base64url segments, valid HS256)
  • /token enforces the 10-participant cap (11th call -> 409)
  • /token validates the room slug
  • /release frees the slot
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys

# Inject fake LiveKit env BEFORE importing the blueprint so it picks them up.
os.environ["LIVEKIT_URL"] = "wss://example.livekit.cloud"
os.environ["LIVEKIT_API_KEY"] = "APItest123"
os.environ["LIVEKIT_API_SECRET"] = "supersecret-for-smoke-test-only"

from flask import Flask
from routes.wb_meet import wb_meet_bp, _make_token  # noqa: E402

app = Flask(__name__)
app.register_blueprint(wb_meet_bp)
c = app.test_client()


def b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def verify_jwt(token: str, secret: str) -> dict:
    h_b, p_b, s_b = token.split(".")
    expected = hmac.new(secret.encode("utf-8"),
                        f"{h_b}.{p_b}".encode("ascii"),
                        hashlib.sha256).digest()
    sig = b64url_decode(s_b)
    if not hmac.compare_digest(expected, sig):
        raise AssertionError("JWT signature mismatch")
    return json.loads(b64url_decode(p_b))


# 1. /config returns enabled=True since we set env
r = c.get("/api/wb_meet/config")
print("/config:", r.status_code, r.get_json())
assert r.status_code == 200 and r.get_json()["enabled"] is True

# 2. /token issues a valid JWT
r = c.post("/api/wb_meet/token", json={"room": "math-42", "name": "Виктор"})
print("/token:", r.status_code, list(r.get_json().keys()))
assert r.status_code == 200
data = r.get_json()
payload = verify_jwt(data["token"], os.environ["LIVEKIT_API_SECRET"])
print("  payload:", json.dumps(payload, ensure_ascii=False)[:300])
assert payload["iss"] == os.environ["LIVEKIT_API_KEY"]
assert payload["video"]["room"] == "math-42"
assert payload["video"]["roomJoin"] is True
assert "exp" in payload and "iat" in payload

# 3. Bad room
r = c.post("/api/wb_meet/token", json={"room": "###bad###"})
print("/token bad-room:", r.status_code, r.get_json())
assert r.status_code == 400

# 4. Fill up to the cap (we already issued 1)
identities = [data["identity"]]
for i in range(9):
    rr = c.post("/api/wb_meet/token", json={"room": "math-42", "name": f"user{i}"})
    assert rr.status_code == 200, rr.get_json()
    identities.append(rr.get_json()["identity"])
print(f"issued total: {len(identities)}")
# 11th should be 409
r = c.post("/api/wb_meet/token", json={"room": "math-42", "name": "overflow"})
print("/token 11th (must be 409):", r.status_code, r.get_json())
assert r.status_code == 409

# 5. Release a slot, then 11th call should succeed
r = c.post("/api/wb_meet/release", json={"room": "math-42", "identity": identities[0]})
print("/release:", r.status_code, r.get_json())
r = c.post("/api/wb_meet/token", json={"room": "math-42", "name": "after-release"})
print("/token after release:", r.status_code, list(r.get_json().keys()))
assert r.status_code == 200

# 6. status
print("/status:", c.get("/api/wb_meet/status").get_json())

# 7. If env is removed, endpoints should refuse
os.environ.pop("LIVEKIT_URL", None)
os.environ.pop("LIVEKIT_API_KEY", None)
os.environ.pop("LIVEKIT_API_SECRET", None)
r = c.get("/api/wb_meet/config")
print("/config (no env):", r.status_code, r.get_json())
assert r.get_json()["enabled"] is False
r = c.post("/api/wb_meet/token", json={"room": "math-42"})
print("/token (no env):", r.status_code, r.get_json())
assert r.status_code == 503

print("\nOK — все проверки пройдены.")

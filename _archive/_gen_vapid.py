"""Generate VAPID keys for Web Push notifications."""
from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization

v = Vapid()
v.generate_keys()

private_pem = v.private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
).decode().strip()

public_pem = v.public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
).decode().strip()

# Remove PEM headers/footers and newlines for env var use
import base64, re
priv_b64 = base64.urlsafe_b64encode(v.private_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)).decode().rstrip('=')

pub_b64 = base64.urlsafe_b64encode(v.public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)).decode().rstrip('=')

print("VAPID_PUBLIC_KEY=" + pub_b64)
print("VAPID_PRIVATE_KEY=" + priv_b64)
print()
print("Set these in your .env file or Render environment variables.")

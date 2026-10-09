#!/usr/bin/env python3
"""Diagnostic: download image via HTTP and verify it."""
import urllib.request
import hashlib
import sys
import os

URL = "http://localhost:8000/images/euler/euler_2009_tasks.pdf/euler_2009_regional_g8_n2_p1_cropde2ac903.png"
EXPECTED_MD5 = "68e86e50ca1f438e2d213357b135722c"

print("=== HTTP Diagnostic ===")
print(f"URL: {URL}")

try:
    req = urllib.request.Request(URL)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = resp.read()
        print(f"HTTP status: {resp.status}")
        print(f"Content-Type: {resp.headers.get('Content-Type')}")
        print(f"Content-Length: {resp.headers.get('Content-Length')}")
        print(f"Downloaded bytes: {len(data)}")
        
        md5 = hashlib.md5(data).hexdigest()
        print(f"Downloaded MD5: {md5}")
        print(f"Expected MD5:  {EXPECTED_MD5}")
        print(f"MD5 match: {md5 == EXPECTED_MD5}")
        
        # Save to desktop
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        out_path = os.path.join(desktop, "diag_downloaded.png")
        with open(out_path, "wb") as f:
            f.write(data)
        print(f"Saved to: {out_path}")
        
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

print("=== Done ===")

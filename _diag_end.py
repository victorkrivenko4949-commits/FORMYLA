#!/usr/bin/env python3
# -*- coding: utf-8 -*-
with open('_last_response_11.txt', 'rb') as f:
    data = f.read()
print(f"Total bytes: {len(data)}")
ob = data.find(b'[')
cb = data.rfind(b']')
print(f"First [ at byte: {ob}")
print(f"Last ] at byte: {cb}")
if cb >= 0:
    start = max(0, cb - 200)
    end = min(len(data), cb + 200)
    print(f"Bytes around last ]: {data[start:end]}")
else:
    # Search for ] anywhere
    cb_first = data.find(b']')
    print(f"First ] at byte: {cb_first}")
    print(f"All ] positions: {[i for i, b in enumerate(data) if b == 93]}")
    # Show last 500 bytes
    print(f"Last 500 bytes (as text): {data[-500:].decode('utf-8', errors='replace')}")

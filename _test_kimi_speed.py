# -*- coding: utf-8 -*-
"""Speed test for Kimi vision models."""
import time, requests, os, json
from dotenv import load_dotenv
load_dotenv()

k = os.environ["KIMI_API_KEY"]
RED_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)

models = ["kimi-k2.7-code-highspeed", "kimi-k2.6"]

for m in models:
    t0 = time.time()
    try:
        r = requests.post(
            "https://api.moonshot.ai/v1/chat/completions",
            json={
                "model": m,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{RED_PNG_B64}"}},
                        {"type": "text", "text": "Describe this image in one word."}
                    ]
                }],
                "max_tokens": 2000,
                "temperature": 1.0,
            },
            headers={"Authorization": f"Bearer {k}"},
            timeout=90,
        )
        elapsed = time.time() - t0
        if r.status_code == 200:
            msg = r.json()["choices"][0]["message"]
            text = msg.get("content") or msg.get("reasoning_content", "")
            print(f"{m}: {elapsed:.1f}s | {len(text)} chars | content_empty={not msg.get('content')}")
        else:
            print(f"{m}: {elapsed:.1f}s | HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"{m}: {elapsed:.1f}s | ERROR: {e}")

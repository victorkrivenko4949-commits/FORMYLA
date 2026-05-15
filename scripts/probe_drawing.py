# -*- coding: utf-8 -*-
"""
Probe OpenRouter image generation: print raw response shape so we know
exactly where the PNG sits.

Usage:
    python scripts/probe_drawing.py                                  # gemini, with modalities
    python scripts/probe_drawing.py google/gemini-2.5-flash-image    # explicit model
    python scripts/probe_drawing.py google/gemini-2.5-flash-image --no-mod
"""
import os
import sys
import json

import httpx
from dotenv import load_dotenv

load_dotenv()

key = os.environ["OPENROUTER_API_KEY"].strip()
model = "google/gemini-2.5-flash-image"
use_modalities = True

for arg in sys.argv[1:]:
    if arg == "--no-mod":
        use_modalities = False
    elif not arg.startswith("--"):
        model = arg

problem = (
    "Нарисуй базовый чертёж: треугольник ABC, угол A = 60 градусов, "
    "AB = 5, AC = 7. Только сам треугольник, подписи вершин A, B, C, "
    "подписи длин 5 и 7 у соответствующих сторон, маленькая дуга у угла A "
    "с подписью 60°. Чёрные линии на белом фоне, PNG 1024x1024."
)

payload = {
    "model": model,
    "messages": [{"role": "user", "content": problem}],
}
if use_modalities:
    payload["modalities"] = ["image", "text"]

print(f"=== Calling {model} (modalities={'ON' if use_modalities else 'OFF'}) ===")
resp = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://formyla.ru",
        "X-Title": "FORMYLA",
    },
    json=payload,
    timeout=120.0,
)

print(f"HTTP {resp.status_code}")
print(f"x-openrouter-usage: {resp.headers.get('x-openrouter-usage')}")

if resp.status_code != 200:
    print("--- BODY ---")
    print(resp.text[:2000])
    sys.exit(1)

data = resp.json()
print("--- KEYS ---")
print(list(data.keys()))

choice = data["choices"][0]
msg = choice["message"]
print("--- choice keys ---", list(choice.keys()))
print("--- message keys ---", list(msg.keys()))
print("--- finish_reason ---", choice.get("finish_reason"))
print("--- usage ---", data.get("usage"))

content = msg.get("content")
if isinstance(content, str):
    print("--- content (str, first 400) ---")
    print(content[:400])
elif isinstance(content, list):
    print(f"--- content (list, {len(content)} parts) ---")
    for i, p in enumerate(content):
        if isinstance(p, dict):
            print(f"  [{i}] type={p.get('type')}, keys={list(p.keys())}")

images = msg.get("images")
if images:
    print(f"--- images: {len(images)} entries ---")
    for i, im in enumerate(images):
        if isinstance(im, dict):
            print(f"  [{i}] keys={list(im.keys())}")
            iu = im.get("image_url")
            if isinstance(iu, dict):
                url = iu.get("url", "")
                print(f"      image_url.url prefix: {url[:60]}...  total_len={len(url)}")
            elif isinstance(iu, str):
                print(f"      image_url(str) prefix: {iu[:60]}...  total_len={len(iu)}")

# Save trimmed JSON for inspection
out_path = os.path.join(os.path.dirname(__file__), "probe_drawing_last.json")
trimmed = json.loads(json.dumps(data))  # deep copy
# Truncate huge base64
try:
    for im in trimmed["choices"][0]["message"].get("images", []) or []:
        iu = im.get("image_url")
        if isinstance(iu, dict) and isinstance(iu.get("url"), str):
            iu["url"] = iu["url"][:120] + f"...[truncated, total {len(iu['url'])} chars]"
except Exception:
    pass
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(trimmed, f, ensure_ascii=False, indent=2)
print(f"\nTrimmed response saved to: {out_path}")

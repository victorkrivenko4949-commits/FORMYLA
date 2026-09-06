# -*- coding: utf-8 -*-
"""Сырой вызов Gemini vision для отладки пустого content."""
import base64
import json
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE, ".env"))

import requests

import _svg_to_png as renderer

# Рендер SVG
con = __import__("sqlite3").connect(os.path.join(BASE, "instance", "formyla.db"))
con.row_factory = __import__("sqlite3").Row
r = con.execute("SELECT aux_svg_path, svg_path, problem_text FROM figure_build_jobs WHERE id=618").fetchone()
svg = r["aux_svg_path"] or r["svg_path"] or ""
cond = r["problem_text"]

svg_path = tempfile.mktemp(suffix=".svg")
png_path = tempfile.mktemp(suffix=".png")
open(svg_path, "w", encoding="utf-8").write(svg)
renderer.render(svg_path, png_path, scale=2)
png = open(png_path, "rb").read()
b64 = base64.b64encode(png).decode()

key = os.environ.get("GEMINI_API_KEY", "").strip()
base = (os.environ.get("GEMINI_API_BASE") or "https://api.odirouter.ai/v1").rstrip("/")
model = (os.environ.get("GEMINI_VISION_MODEL") or "gemini-3.7-flash").strip()

system = (
    "Ты — строгий проверяющий геометрических чертежей. Проверь полноту чертежа "
    "по условию. Верни СТРОГО JSON: {\"complete\": true/false, \"missing\": [...], \"repair_plan\": [...]}."
)

for use_rf in (False, True):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": f"Условие:\n{cond}\n\nПроверь полноту и верни JSON."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    if use_rf:
        payload["response_format"] = {"type": "json_object"}
    resp = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload, timeout=(15, 60),
    )
    print(f"=== response_format={use_rf} HTTP {resp.status_code} ===")
    try:
        body = resp.json()
    except Exception:
        print("RAW:", resp.text[:500])
        continue
    choices = body.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        print("content:", repr((msg.get("content") or "")[:500]))
        print("reasoning_content:", repr((msg.get("reasoning_content") or "")[:200]))
    else:
        print("no choices. body:", json.dumps(body, ensure_ascii=False)[:800])
    print()

# -*- coding: utf-8 -*-
"""Вызвать РЕАЛЬНЫЙ _call_deepseek из routes/figures_generator.py,
чтобы проверить fallback Novita(404) -> DeepSeek, а не упрощённую копию."""
import os
import sys

def _load_dotenv(path=".env"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass

_load_dotenv()

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from routes.figures_generator import _call_deepseek

for label, model in [("legacy(None)", None), ("condition_solution", "deepseek-v4-pro")]:
    try:
        r = _call_deepseek([{"role": "user", "content": "ping"}], model_name=model)
        print(label, "-> OK")
        print("  model:", r.get("model"))
        print("  content len:", len(r.get("content") or ""))
        print("  content[:200]:", repr((r.get("content") or "")[:200]))
    except Exception as e:
        print(label, "-> EXC", type(e).__name__, str(e)[:300])

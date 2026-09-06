# -*- coding: utf-8 -*-
"""Проверить наличие ключа и состояние чекпоинта перед --resume."""
import json
import os

key = ""
if os.path.exists(".env"):
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if line.startswith("DEEPSEEK_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

print("DEEPSEEK_API_KEY present:", bool(key), "| len:", len(key))
print("DEEPSEEK_MODEL env:", os.environ.get("DEEPSEEK_MODEL", "(default deepseek-v4-pro)"))

cp = json.load(open("audit_formyla_1_4_double_checkpoint.json", encoding="utf-8"))
print("done_idx:", len(cp["done_idx"]), "| max:", max(cp["done_idx"]) if cp["done_idx"] else None)
print("stats:", cp["stats"])

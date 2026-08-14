#!/usr/bin/env python3
"""
Подсчёт токенов и стоимости по audit_raw.log.

Запуск:
    python cost.py
    python cost.py путь\к\audit_raw.log
"""

import os
import re
import sys
import ast

LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    r"C:\Users\Redmi\Desktop\Новая папка (2)", "audit_raw.log")

# тарифы deepseek-v4-pro, $ за 1M токенов (промо-цены)
PRICE_CACHE_HIT = 0.003625
PRICE_CACHE_MISS = 0.435
PRICE_OUTPUT = 0.87


def main():
    if not os.path.exists(LOG):
        sys.exit(f"Не найден лог: {LOG}")

    hit = miss = out = reasoning = 0
    calls = 0

    pat = re.compile(r"usage=(\{.*?\})\s*$", re.M)
    with open(LOG, "r", encoding="utf-8", errors="replace") as f:
        for m in pat.finditer(f.read()):
            try:
                u = ast.literal_eval(m.group(1))
            except Exception:
                continue
            if not isinstance(u, dict):
                continue
            calls += 1
            hit += u.get("prompt_cache_hit_tokens", 0)
            miss += u.get("prompt_cache_miss_tokens", 0)
            out += u.get("completion_tokens", 0)
            det = u.get("completion_tokens_details") or {}
            reasoning += det.get("reasoning_tokens", 0)

    cost = (hit / 1e6 * PRICE_CACHE_HIT
            + miss / 1e6 * PRICE_CACHE_MISS
            + out / 1e6 * PRICE_OUTPUT)

    total = hit + miss + out

    print("=" * 52)
    print(f"Лог: {LOG}")
    print(f"Запросов к API      : {calls}")
    print("-" * 52)
    print(f"Ввод, кэш попал     : {hit:>12,}")
    print(f"Ввод, кэш промах    : {miss:>12,}")
    print(f"Вывод               : {out:>12,}")
    print(f"  из них размышления: {reasoning:>12,}")
    print(f"ВСЕГО ТОКЕНОВ       : {total:>12,}")
    print("-" * 52)
    print(f"Стоимость           : ${cost:.2f}")
    if calls:
        print(f"В среднем на запрос : {total // calls:,} токенов, "
              f"${cost / calls:.4f}")
    print("=" * 52)
    print("Тарифы v4-pro: cache-hit $0.003625, cache-miss $0.435, output $0.87 за 1M")
    print("В пиковые часы (9-12 и 14-18 по Пекину) цены выше.")


if __name__ == "__main__":
    main()

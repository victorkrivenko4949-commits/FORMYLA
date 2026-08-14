#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бенчмарк скорости ответа DeepSeek V4-Pro: 100 запросов, 1 поток (строго последовательно).
Задача: одна и та же нетривиальная алгебраическая (функциональное уравнение, уровень олимпиады).

Метрики по каждому запросу:
  - TTFT (time to first token)  -- работает благодаря stream=True
  - total (полное время ответа)
  - gen_time = total - TTFT, tok/s генерации
  - prompt/completion/reasoning tokens
  - корректность ответа (авто-проверка ожидаемого f(x)=x+1)

Запуск:
  set DEEPSEEK_API_KEY=sk-...        (Windows cmd)
  $env:DEEPSEEK_API_KEY="sk-87c7e276289a48269afe7d91d08d3f38"     (PowerShell)
  pip install openai
  python deepseek_v4pro_latency_bench.py --n 100
"""

import os
import re
import csv
import time
import json
import argparse
import statistics as st
from datetime import datetime

from openai import OpenAI

MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com"

# ---------------------------------------------------------------- задача
PROBLEM = r"""Найдите все функции f: R -> R, удовлетворяющие при всех действительных x, y равенству

    f(x) * f(y) - f(x*y) = x + y.

Требуется: (1) строгое доказательство, что других решений нет; (2) проверка найденной функции.
Последней строкой ответа напиши ровно: ОТВЕТ: f(x) = ...
"""

SYSTEM = "Ты олимпиадный математик. Решай строго, без пропусков шагов. Ответ на русском языке."

# ожидаемое решение: f(x) = x + 1
ANSWER_RE = re.compile(r"ОТВЕТ\s*:\s*f\s*\(\s*x\s*\)\s*=\s*x\s*\+\s*1", re.IGNORECASE)


def check(text: str) -> bool:
    if ANSWER_RE.search(text or ""):
        return True
    tail = (text or "")[-400:].replace(" ", "")
    return "f(x)=x+1" in tail


def one_call(client, max_tokens, temperature, timeout):
    t0 = time.perf_counter()
    ttft = None
    chunks = []
    usage = None
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": PROBLEM}],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        stream_options={"include_usage": True},
        timeout=timeout,
    )
    for ch in stream:
        if getattr(ch, "usage", None):
            usage = ch.usage
        if not ch.choices:
            continue
        d = ch.choices[0].delta
        piece = getattr(d, "content", None) or getattr(d, "reasoning_content", None)
        if piece:
            if ttft is None:
                ttft = time.perf_counter() - t0
            if getattr(d, "content", None):
                chunks.append(d.content)
    total = time.perf_counter() - t0
    return "".join(chunks), ttft, total, usage


def usage_dict(usage):
    if usage is None:
        return {}
    try:
        u = usage.model_dump()
    except Exception:
        u = dict(usage)
    det = u.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": u.get("prompt_tokens"),
        "completion_tokens": u.get("completion_tokens"),
        "total_tokens": u.get("total_tokens"),
        "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "reasoning_tokens": det.get("reasoning_tokens"),
    }


def pct(vals, p):
    if not vals:
        return float("nan")
    s = sorted(vals)
    k = min(len(s) - 1, max(0, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--sleep", type=float, default=0.0, help="пауза между запросами, сек")
    ap.add_argument("--out-dir", default="output")
    args = ap.parse_args()

    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("Нет DEEPSEEK_API_KEY в переменных окружения.")

    os.makedirs(args.out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(args.out_dir, f"ds_v4pro_bench_{stamp}.csv")
    jsonl_path = os.path.join(args.out_dir, f"ds_v4pro_answers_{stamp}.jsonl")

    client = OpenAI(api_key=key, base_url=BASE_URL, max_retries=0)

    rows = []
    fields = ["i", "ok", "correct", "ttft_s", "total_s", "gen_s", "gen_tok_s",
              "prompt_tokens", "completion_tokens", "reasoning_tokens",
              "cached_tokens", "total_tokens", "attempts", "error"]

    with open(csv_path, "w", newline="", encoding="utf-8") as fc, \
         open(jsonl_path, "w", encoding="utf-8") as fj:
        w = csv.DictWriter(fc, fieldnames=fields)
        w.writeheader()

        wall0 = time.perf_counter()
        for i in range(1, args.n + 1):
            err, attempts = "", 0
            text = ttft = total = usage = None
            while attempts <= args.retries:
                attempts += 1
                try:
                    text, ttft, total, usage = one_call(
                        client, args.max_tokens, args.temperature, args.timeout)
                    err = ""
                    break
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"[:300]
                    time.sleep(min(20, 2 ** attempts))

            u = usage_dict(usage)
            comp = u.get("completion_tokens")
            gen_s = (total - ttft) if (total and ttft) else None
            tok_s = (comp / gen_s) if (comp and gen_s and gen_s > 0) else None

            row = {
                "i": i, "ok": int(not err), "correct": int(check(text or "")) if not err else 0,
                "ttft_s": round(ttft, 3) if ttft else "", "total_s": round(total, 3) if total else "",
                "gen_s": round(gen_s, 3) if gen_s else "", "gen_tok_s": round(tok_s, 2) if tok_s else "",
                "prompt_tokens": u.get("prompt_tokens", ""), "completion_tokens": comp or "",
                "reasoning_tokens": u.get("reasoning_tokens", ""),
                "cached_tokens": u.get("cached_tokens", ""), "total_tokens": u.get("total_tokens", ""),
                "attempts": attempts, "error": err,
            }
            rows.append(row)
            w.writerow(row); fc.flush()
            fj.write(json.dumps({"i": i, "answer": text, "error": err}, ensure_ascii=False) + "\n"); fj.flush()

            elapsed = time.perf_counter() - wall0
            eta = elapsed / i * (args.n - i)
            print(f"[{i:3d}/{args.n}] {'OK ' if not err else 'ERR'} "
                  f"ttft={row['ttft_s'] or '-':>7} total={row['total_s'] or '-':>8} "
                  f"tok={comp or '-':>6} {row['gen_tok_s'] or '-':>7} t/s "
                  f"corr={row['correct']} | прошло {elapsed/60:.1f} мин, ещё ~{eta/60:.1f} мин",
                  flush=True)

            if args.sleep and i < args.n:
                time.sleep(args.sleep)

        wall = time.perf_counter() - wall0

    good = [r for r in rows if r["ok"]]
    T = [r["total_s"] for r in good if r["total_s"] != ""]
    F = [r["ttft_s"] for r in good if r["ttft_s"] != ""]
    S = [r["gen_tok_s"] for r in good if r["gen_tok_s"] != ""]
    C = [r["completion_tokens"] for r in good if r["completion_tokens"] != ""]

    def line(name, v, unit=""):
        if not v:
            return f"{name}: нет данных"
        return (f"{name}: mean={st.mean(v):.2f} median={st.median(v):.2f} "
                f"p90={pct(v,90):.2f} p95={pct(v,95):.2f} min={min(v):.2f} max={max(v):.2f} {unit}")

    report = "\n".join([
        f"model={MODEL}  requests={args.n}  concurrency=1",
        f"успешных: {len(good)}/{args.n}   верный ответ: {sum(r['correct'] for r in rows)}/{args.n}",
        f"общее время прогона: {wall/60:.2f} мин ({wall:.1f} с), "
        f"средний RPS={len(good)/wall:.3f}",
        line("total_s", T, "c"),
        line("ttft_s", F, "c"),
        line("gen_tok/s", S),
        line("completion_tokens", C),
        f"CSV: {csv_path}",
        f"Ответы: {jsonl_path}",
    ])
    print("\n" + report)
    with open(os.path.join(args.out_dir, f"ds_v4pro_summary_{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()

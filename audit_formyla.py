#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Аудит и исправление базы задач FORMYLA_L1_L3_FINAL через DeepSeek API.

Пайплайн:
  1) Двойной независимый аудит каждой задачи (2 прогона), 5 потоков, лимит 16k токенов.
  2) Маршрутизация по двум вердиктам:
       - оба VERDICT=OK          -> задачу не трогаем
       - оба VERDICT=BAD         -> отправляем в чат на ИСПРАВЛЕНИЕ (fix)
       - расхождение (OK + BAD)  -> отправляем в ЭКСПЕРТ (усиленный ревьюер)
  3) Правим файл FORMYLA_L1_L3_FINAL (обновляем answer/solution, ставим метки).

Безопасность: ключ читается из переменной окружения DEEPSEEK_API_KEY (или из .env рядом).
Отзовите присланный в чате ключ и создайте новый!
"""

import os
import re
import json
import time
import shutil
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI  # pip install openai>=1.0

# ------------------------------------------------------------------ конфиг
API_BASE      = "https://api.deepseek.com"
MODEL_AUDIT   = "deepseek-chat"       # аудит и исправление
MODEL_EXPERT  = "deepseek-reasoner"   # экспертный разбор спорных
MAX_TOKENS    = 16000                 # лимит токенов на ответ
N_WORKERS     = 5                     # потоков
AUDIT_PASSES  = 2                     # сколько раз аудировать каждую задачу
TEMPERATURE   = 0.2
MAX_RETRIES   = 4                     # ретраи при сетевых/лимитных ошибках

DEFAULT_IN    = "FORMYLA_L1_L3_FINAL"
# ------------------------------------------------------------------

def load_env(script_dir):
    """Простейшая загрузка .env (без внешних зависимостей)."""
    env_path = os.path.join(script_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def get_client(script_dir):
    load_env(script_dir)
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit(
            "Не найден DEEPSEEK_API_KEY. Положите .env рядом со скриптом:\n"
            "DEEPSEEK_API_KEY=sk-...\n"
        )
    return OpenAI(api_key=key, base_url=API_BASE)

# ----------------------------------------------------------------- IO базы
def read_tasks(path):
    """Читает JSONL (одна задача на строку) или JSON-массив."""
    with open(path, encoding="utf-8") as f:
        head = f.read(1)
        f.seek(0)
        if head == "[":
            return json.load(f)
        tasks = []
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
        return tasks

def write_tasks(path, tasks):
    """Пишет обратно в JSONL, сохраняя порядок."""
    with open(path, "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

# ----------------------------------------------------------------- промпты
AUDIT_SYSTEM = (
    "Ты — строгий проверяющий олимпиадных задач по математике. "
    "Тебе дают условие, ответ и решение. Проверь: (1) корректность ответа, "
    "(2) логическую строгость решения, (3) соответствие ответа тексту решения. "
    "Ответь СТРОГО в формате:\n"
    "VERDICT: OK   — если ответ правильный И решение корректно;\n"
    "VERDICT: BAD  — если ответ неверен, ЛИБО решение содержит ошибку, "
    "ЛИБО поле answer не совпадает с выводом решения.\n"
    "После вердикта — короткое обоснование (2-4 предложения) и, если BAD, "
    "укажи ПРАВИЛЬНЫЙ ответ строкой 'CORRECT_ANSWER: <...>'."
)

FIX_SYSTEM = (
    "Ты — эксперт-методист. Задача признана НЕВЕРНОЙ при двойном аудите. "
    "Дай исправленную версию строго в JSON без пояснений вокруг:\n"
    '{"answer": "<правильный ответ>", "solution": "<полное корректное решение>"}\n'
    "Решение должно быть строгим, полным, на русском языке."
)

EXPERT_SYSTEM = (
    "Ты — главный эксперт-арбитр. Два аудита разошлись во мнении по этой задаче "
    "(один сказал OK, другой BAD). Прими окончательное решение. "
    "Проведи независимую проверку ответа и строгости решения. "
    "Ответь СТРОГО в JSON без обрамления:\n"
    '{"final_verdict": "OK|BAD", "answer": "<правильный ответ>", '
    '"solution": "<корректное решение, если требуется правка, иначе исходное>", '
    '"comment": "<кратко суть>"}'
)

def task_payload(t):
    return (
        f"УСЛОВИЕ:\n{t.get('statement','')}\n\n"
        f"ОТВЕТ (поле answer): {t.get('answer','')}\n\n"
        f"РЕШЕНИЕ:\n{t.get('solution','')}"
    )

# ----------------------------------------------------------------- вызовы API
def chat(client, model, system, user, max_tokens=MAX_TOKENS):
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                max_tokens=max_tokens,
                temperature=TEMPERATURE,
            )
            return resp.choices[0].message.content
        except Exception as e:  # сеть/лимиты
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API упал после {MAX_RETRIES} попыток: {last_err}")

def parse_verdict(text):
    m = re.search(r"VERDICT:\s*(OK|BAD)", text, re.IGNORECASE)
    return (m.group(1).upper() if m else "BAD")

def extract_json(text):
    """Достаёт JSON-объект из ответа модели (даже если он обёрнут текстом)."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

# ----------------------------------------------------------------- обработка
_print_lock = threading.Lock()
def log(*a):
    with _print_lock:
        print(*a, flush=True)

def audit_one(client, idx, task):
    """Два независимых прогона аудита -> список вердиктов и текстов."""
    payload = task_payload(task)
    verdicts, notes = [], []
    for p in range(AUDIT_PASSES):
        txt = chat(client, MODEL_AUDIT, AUDIT_SYSTEM, payload)
        verdicts.append(parse_verdict(txt))
        notes.append(txt)
    return idx, verdicts, notes

def route(verdicts):
    ok = verdicts.count("OK")
    bad = verdicts.count("BAD")
    if ok == AUDIT_PASSES:
        return "keep"          # оба верно — не трогаем
    if bad == AUDIT_PASSES:
        return "fix"           # оба неверно — на исправление
    return "expert"            # расхождение — в эксперт

def apply_fix(client, task):
    txt = chat(client, MODEL_AUDIT, FIX_SYSTEM, task_payload(task))
    data = extract_json(txt)
    if data:
        task["answer"]   = data.get("answer",   task.get("answer"))
        task["solution"] = data.get("solution", task.get("solution"))
        task["_audit_status"] = "fixed_by_chat"
    else:
        task["_audit_status"] = "fix_parse_failed"
        task["_audit_raw"] = txt
    return task

def apply_expert(client, task):
    txt = chat(client, MODEL_EXPERT, EXPERT_SYSTEM, task_payload(task))
    data = extract_json(txt)
    if data:
        if str(data.get("final_verdict", "")).upper() == "BAD":
            task["answer"]   = data.get("answer",   task.get("answer"))
            task["solution"] = data.get("solution", task.get("solution"))
            task["_audit_status"] = "fixed_by_expert"
        else:
            task["_audit_status"] = "expert_confirmed_ok"
        task["_expert_comment"] = data.get("comment", "")
    else:
        task["_audit_status"] = "expert_parse_failed"
        task["_audit_raw"] = txt
    return task

# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Аудит и правка FORMYLA_L1_L3_FINAL")
    ap.add_argument("--infile", default=DEFAULT_IN, help="путь к файлу базы")
    ap.add_argument("--limit", type=int, default=0, help="обработать только N первых задач (0 = все)")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    in_path = args.infile if os.path.isabs(args.infile) else os.path.join(script_dir, args.infile)

    client = get_client(script_dir)
    tasks = read_tasks(in_path)
    if args.limit:
        tasks = tasks[:args.limit]
    log(f"Загружено задач: {len(tasks)}")

    # бэкап оригинала
    shutil.copyfile(in_path, in_path + ".bak")
    log(f"Бэкап: {in_path}.bak")

    # ---- ЭТАП 1: двойной аудит в 5 потоков
    audit_results = {}
    with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = {ex.submit(audit_one, client, i, t): i for i, t in enumerate(tasks)}
        done = 0
        for fut in as_completed(futs):
            idx, verdicts, notes = fut.result()
            audit_results[idx] = (verdicts, notes)
            done += 1
            if done % 25 == 0 or done == len(tasks):
                log(f"  аудит: {done}/{len(tasks)}")

    # ---- маршрутизация
    to_fix, to_expert, keep = [], [], 0
    for idx, (verdicts, notes) in audit_results.items():
        r = route(verdicts)
        tasks[idx]["_audit_verdicts"] = verdicts
        if r == "keep":
            tasks[idx].setdefault("_audit_status", "keep_ok")
            keep += 1
        elif r == "fix":
            to_fix.append(idx)
        else:
            to_expert.append(idx)
    log(f"Итог аудита: keep={keep}, fix={len(to_fix)}, expert={len(to_expert)}")

    # ---- ЭТАП 2: исправления (оба BAD) в 5 потоков
    with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = {ex.submit(apply_fix, client, tasks[i]): i for i in to_fix}
        for n, fut in enumerate(as_completed(futs), 1):
            fut.result()
            if n % 10 == 0 or n == len(to_fix):
                log(f"  fix: {n}/{len(to_fix)}")

    # ---- ЭТАП 3: эксперт (расхождение) в 5 потоков
    with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = {ex.submit(apply_expert, client, tasks[i]): i for i in to_expert}
        for n, fut in enumerate(as_completed(futs), 1):
            fut.result()
            if n % 10 == 0 or n == len(to_expert):
                log(f"  expert: {n}/{len(to_expert)}")

    # ---- запись результата
    write_tasks(in_path, tasks)
    log(f"Готово. Файл обновлён: {in_path}")

    # краткий отчёт
    from collections import Counter
    stats = Counter(t.get("_audit_status", "?") for t in tasks)
    log("Статусы: " + ", ".join(f"{k}={v}" for k, v in stats.items()))

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
audit_balanced_deepseek.py — Двойной олимпиадный аудит файла
FORMYLA_4LEVEL_BALANCED_FIXED.jsonl (2640 задач, уровни 1..4).

Полностью повторяет методику audit_l4_deepseek.py, но адаптирован под поля
этого файла: statement (условие), answer (ответ), solution (решение).

Классификация:
  * оба аудита «incorrect»        -> BALANCED_DOUBLE_FAIL.jsonl
  * один «correct», другой нет    -> BALANCED_DISPUTED.jsonl
  * оба «correct»                 -> (не пишется, только статистика)
  * сбой/невалидный JSON          -> BALANCED_ERROR.jsonl

Запуск:
    python audit_balanced_deepseek.py                 # полный прогон
    python audit_balanced_deepseek.py --limit 10 --smoke
    python audit_balanced_deepseek.py --resume
"""

import argparse
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

SRC_PATH = r"c:/Users/Redmi/Downloads/FORMYLA_4LEVEL_BALANCED_FIXED.jsonl"
OUT_DOUBLE = "BALANCED_DOUBLE_FAIL.jsonl"
OUT_DISPUTED = "BALANCED_DISPUTED.jsonl"
OUT_ERROR = "BALANCED_ERROR.jsonl"
CHECKPOINT = "audit_balanced_checkpoint.json"

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
WORKERS = 30
TIMEOUT = (15, 300)
MAX_RETRIES = 4
TEMPERATURE = 0.0
MAX_TOKENS = 8000

SYSTEM_A = (
    "Ты — член жюри Всероссийской олимпиады школьников по математике высшего "
    "уровня, специалист по строгим доказательствам. Проведи бескомпромиссную "
    "проверку задачи.\n\n"
    "Проверяй ПО ОТДЕЛЬНОСТИ:\n"
    "1. ОТВЕТ — верен ли (включая вырожденные случаи, множественные решения, "
    "область допустимых значений)?\n"
    "2. РЕШЕНИЕ — математически полно и строго? Доказаны ли ВСЕ утверждения, "
    "разобраны ли ВСЕ случаи, нет ли логических дыр и арифметических ошибок, "
    "ведёт ли решение именно к заявленному ответу?\n\n"
    "Любая недоказанная оценка, пропущенный случай или неточность = ошибка.\n\n"
    "Отвечай ТОЛЬКО одним JSON-объектом (без markdown, без текста вне JSON):\n"
    "{\n"
    "  \"answer_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"solution_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"overall_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"errors\": [\"краткое описание ошибки\"],\n"
    "  \"justification\": \"1-2 предложения\"\n"
    "}"
)

SYSTEM_B = (
    "Ты — эксперт-составитель и рецензент олимпиадных задач по математике, "
    "проверяющий чужую задачу перед публикацией в сборнике.\n\n"
    "Требования: ответ единственный и корректный (или корректно описано "
    "множество ответов), согласован с условием и решением; решение безупречно: "
    "каждая оценка доказана, все случаи разобраны, нет запрещённых ссылок на "
    "чертёж/интуицию, нет пропущенных граничных ситуаций, нет ошибок в "
    "выкладках.\n\n"
    "Вердикт «correct» — только если И ответ, И решение полностью корректны. "
    "Любая неточность, недоказанный шаг, пропущенный случай или неверный "
    "ответ = «incorrect».\n\n"
    "Отвечай ТОЛЬКО одним JSON-объектом (без markdown, без пояснений вне JSON):\n"
    "{\n"
    "  \"answer_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"solution_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"overall_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"errors\": [\"...\"],\n"
    "  \"justification\": \"...\"\n"
    "}"
)


def load_env():
    global API_KEY
    if API_KEY:
        return
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def build_user_prompt(task) -> str:
    return (
        f"Задача (уровень {task.get('level')}, класс {task.get('grade')}, "
        f"тема «{task.get('theme')}»):\n\n"
        f"{task.get('statement', '')}\n\n"
        f"Эталонный ответ:\n{task.get('answer', '')}\n\n"
        f"Решение, которое нужно проверить:\n{task.get('solution', '')}"
    )


def extract_json(text: str) -> dict:
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return {}
    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        depth = 0
        s = 0
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    s = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[s:i + 1])
                    except json.JSONDecodeError:
                        return {}
        return {}


def call_deepseek(system_prompt, user_prompt):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                },
                timeout=TIMEOUT,
            )
            if resp.status_code == 429:
                time.sleep(min(2 ** attempt, 60))
                last_err = RuntimeError("429")
                continue
            if resp.status_code >= 500:
                time.sleep(min(2 ** attempt, 30))
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                continue
            resp.raise_for_status()
            body = resp.json()
            choices = body.get("choices") or []
            if not choices:
                last_err = RuntimeError("empty choices")
                continue
            msg = choices[0].get("message", {}) or {}
            content = msg.get("content") or msg.get("reasoning_content") or ""
            verdict = extract_json(content)
            if not verdict:
                last_err = RuntimeError("невалидный JSON")
                log(f"    попытка {attempt}: невалидный JSON, повтор…")
                continue
            return verdict
        except requests.RequestException as e:
            last_err = e
            time.sleep(min(2 ** attempt, 30))
    return {"overall_verdict": "error", "_error": str(last_err)}


def normalize_verdict(v):
    v = (v or "").strip().lower()
    if v in ("correct", "true", "pass", "ok", "верно", "правильно"):
        return "correct"
    if v in ("incorrect", "false", "fail", "неверно", "неправильно"):
        return "incorrect"
    if v == "error":
        return "error"
    return "unknown"


def audit_one_task(task):
    user_prompt = build_user_prompt(task)
    a = call_deepseek(SYSTEM_A, user_prompt)
    time.sleep(0.2)
    b = call_deepseek(SYSTEM_B, user_prompt)
    return {"task": task, "audit_a": a, "audit_b": b}


def load_tasks(limit=None):
    tasks = []
    with open(SRC_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if limit and len(tasks) >= limit:
                break
    return tasks


def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        try:
            with open(CHECKPOINT, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"done_idx": [], "double": [], "disputed": [], "error_rows": [], "stats": {}}


def save_checkpoint(cp):
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)


def flush_outputs(double_rows, disputed_rows, error_rows, mode="w"):
    with open(OUT_DOUBLE, mode, encoding="utf-8") as f:
        for r in double_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_DISPUTED, mode, encoding="utf-8") as f:
        for r in disputed_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_ERROR, mode, encoding="utf-8") as f:
        for r in error_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    load_env()
    if not API_KEY:
        log("ОШИБКА: DEEPSEEK_API_KEY не задан")
        sys.exit(1)
    log(f"Модель: {MODEL} | потоков: {WORKERS}")

    tasks = load_tasks(args.limit)
    log(f"Задач: {len(tasks)}")

    cp = load_checkpoint() if args.resume else {"done_idx": [], "double": [], "disputed": [], "error_rows": [], "stats": {}}
    done_idx = set(cp.get("done_idx", []))
    double_rows = list(cp.get("double", []))
    disputed_rows = list(cp.get("disputed", []))
    error_rows = list(cp.get("error_rows", []))
    stats = Counter(cp.get("stats", {}))

    pending = [i for i in range(len(tasks)) if i not in done_idx]
    log(f"Осталось: {len(pending)}")

    if args.smoke:
        pending = pending[: args.limit or 10]
        log(f"SMOKE: {len(pending)} задач")

    lock = threading.Lock()

    def process(idx):
        task = tasks[idx]
        try:
            return idx, audit_one_task(task)
        except Exception as e:
            return idx, {
                "task": task,
                "audit_a": {"overall_verdict": "error", "_error": str(e)},
                "audit_b": {"overall_verdict": "error", "_error": str(e)},
            }

    def verdict_of(a):
        return normalize_verdict(a.get("overall_verdict"))

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(process, i): i for i in pending}
        for fut in as_completed(futures):
            idx, result = fut.result()
            va = verdict_of(result["audit_a"])
            vb = verdict_of(result["audit_b"])

            with lock:
                done_idx.add(idx)
                if va in ("error", "unknown") or vb in ("error", "unknown"):
                    stats["error"] += 1
                    error_rows.append(result)
                elif va == "incorrect" and vb == "incorrect":
                    stats["double_fail"] += 1
                    double_rows.append(result)
                elif va != vb:
                    stats["disputed"] += 1
                    disputed_rows.append(result)
                else:
                    stats["correct"] += 1

                if len(done_idx) % 20 == 0:
                    cp["done_idx"] = sorted(done_idx)
                    cp["double"] = double_rows
                    cp["disputed"] = disputed_rows
                    cp["error_rows"] = error_rows
                    cp["stats"] = dict(stats)
                    if not args.smoke:
                        save_checkpoint(cp)
                        flush_outputs(double_rows, disputed_rows, error_rows, mode="w")
                log(
                    f"прогресс {len(done_idx)}/{len(tasks)} | верно={stats.get('correct',0)} "
                    f"double={stats.get('double_fail',0)} disputed={stats.get('disputed',0)} "
                    f"error={stats.get('error',0)}"
                )

    cp["done_idx"] = sorted(done_idx)
    cp["double"] = double_rows
    cp["disputed"] = disputed_rows
    cp["error_rows"] = error_rows
    cp["stats"] = dict(stats)
    if not args.smoke:
        save_checkpoint(cp)
        flush_outputs(double_rows, disputed_rows, error_rows, mode="w")

    log("=" * 60)
    log(f"ГОТОВО. Задач: {len(tasks)}")
    log(f"  Верно: {stats.get('correct',0)}")
    log(f"  DOUBLE_FAIL: {stats.get('double_fail',0)}")
    log(f"  DISPUTED: {stats.get('disputed',0)}")
    log(f"  ERROR: {stats.get('error',0)}")
    if not args.smoke:
        log(f"Файлы: {OUT_DOUBLE}, {OUT_DISPUTED}, {OUT_ERROR}")


if __name__ == "__main__":
    main()

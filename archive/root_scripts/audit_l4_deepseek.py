# -*- coding: utf-8 -*-
"""
audit_l4_deepseek.py — Двойной олимпиадный аудит задач уровня 4 (L4).

Назначение
----------
Выделяет из ``all_formyla_1_4_final_CORRECTED_v2.jsonl`` все задачи уровня 4
(4060 шт.) и прогоняет каждую через DeepSeek (deepseek-v4-pro, reasoning)
ДВА раза двумя независимыми «экспертными» промптами:

  * Аудит A — строгое жюри олимпиады (доказательства, полнота, корректность).
  * Аудит B — проверка составителя (ответ, решение, отсутствие ошибок/дыр).

Классификация по итогам двух аудитов:

  * оба раза «НЕВЕРНО»        -> DOUBLE_FAIL.jsonl
  * один «ВЕРНО», другой нет  -> DISPUTED.jsonl
  * оба раза «ВЕРНО»          -> (не пишется, но учитывается в статистике)

Особенности
-----------
  * 30 потоков (ThreadPoolExecutor).
  * Контрольная точка (checkpoint) — можно прервать и продолжить.
  * Надёжный парсинг JSON из ответа (устойчив к markdown-огородам и CoT).
  * Retry с экспоненциальной задержкой на сетевые ошибки / 429 / 5xx.
  * Детерминированная температура 0 (для стабильности вердиктов).

Запуск
------
    # Smoke-тест на 10 задачах (файлы не пишутся):
    python audit_l4_deepseek.py --limit 10 --smoke

    # Полный прогон:
    python audit_l4_deepseek.py

    # Продолжить с контрольной точки:
    python audit_l4_deepseek.py --resume
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

# ──────────────────────────────────────────────────────────────────────────
# Конфигурация
# ──────────────────────────────────────────────────────────────────────────
SRC_PATH = r"c:/Users/Redmi/Downloads/all_formyla_1_4_final_CORRECTED_v2.jsonl"
OUT_DOUBLE = "DOUBLE_FAIL.jsonl"
OUT_DISPUTED = "DISPUTED.jsonl"
CHECKPOINT = "audit_l4_checkpoint.json"

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
WORKERS = 30
TIMEOUT = (15, 300)          # (connect, read)
MAX_RETRIES = 4
TEMPERATURE = 0.0
MAX_TOKENS = 4000

# ──────────────────────────────────────────────────────────────────────────
# Экспертные промпты (олимпиадный уровень)
# ──────────────────────────────────────────────────────────────────────────

SYSTEM_A = (
    "Ты — член жюри Всероссийской олимпиады школьников по математике высшего "
    "уровня, специалист по строгим доказательствам. Твоя задача — провести "
    "бескомпромиссную проверку задачи уровня «региональный/финальный этап».\n\n"
    "Проверяй ПО ОТДЕЛЬНОСТИ:\n"
    "1. ОТВЕТ. Верен ли численный/формульный ответ? Должен совпадать с "
    "правильным ответом задачи (включая вырожденные случаи, множественные "
    "решения, область допустимых значений).\n"
    "2. РЕШЕНИЕ. Является ли решение математически полным и строгим?\n"
    "   - Доказаны ли ВСЕ утверждения (нет ссылок «очевидно», «легко видеть»)?\n"
    "   - Разобраны ли ВСЕ случаи и граничные условия?\n"
    "   - Нет ли логических дыр, скрытых допущений, необоснованных переходов?\n"
    "   - Ведёт ли решение именно к заявленному ответу?\n"
    "   - Нет ли арифметических/алгебраических ошибок?\n\n"
    "Будь СТРОГИМ: олимпиадная задача 4-го уровня не терпит пробелов в "
    "обосновании. Любая недоказанная оценка, нерассмотренный случай или "
    "неточность — это ошибка.\n\n"
    "Отвечай ТОЛЬКО одним JSON-объектом (без markdown-огородов, без текста "
    "до/после) следующего вида:\n"
    "{\n"
    "  \"answer_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"solution_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"overall_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"errors\": [\"краткое описание каждой найденной ошибки\"],\n"
    "  \"justification\": \"1-2 предложения, почему вынесен такой вердикт\"\n"
    "}"
)

SYSTEM_B = (
    "Ты — эксперт-составитель и рецензент олимпиадных задач по математике, "
    "проверяющий чужую задачу перед публикацией в сборнике. Оцени качество и "
    "корректность задачи уровня «регион/финал» с точки зрения строгой науки.\n\n"
    "Требования к задаче:\n"
    "1. ОТВЕТ — единственный и корректный (или корректно описано множество "
    "ответов). Ответ обязан согласовываться с условием и решением.\n"
    "2. РЕШЕНИЕ — обязано быть безупречным: каждая оценка доказана, все случаи "
    "разобраны, нет запрещённых ссылок на чертёж/интуицию, нет пропущенных "
    "граничных ситуаций, нет ошибок в выкладках.\n\n"
    "Вердикт «correct» выноси только если И ответ, И решение полностью "
    "корректны. Малейшая неточность, недоказанный шаг, пропущенный случай или "
    "неверный ответ = «incorrect».\n\n"
    "Отвечай ТОЛЬКО одним JSON-объектом (без markdown, без пояснений вне JSON):\n"
    "{\n"
    "  \"answer_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"solution_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"overall_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"errors\": [\"...\"],\n"
    "  \"justification\": \"...\"\n"
    "}"
)

# ──────────────────────────────────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────────────────────────────────


def load_env():
    """Загрузить DEEPSEEK_API_KEY из .env, если не задан в окружении."""
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


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def build_user_prompt(task) -> str:
    """Сформировать пользовательское сообщение с задачей."""
    return (
        f"Задача (уровень 4, класс {task.get('grade')}, тема «{task.get('topic')}»):\n\n"
        f"{task.get('task_text', '')}\n\n"
        f"Эталонный ответ:\n{task.get('correct_answer', '')}\n\n"
        f"Решение, которое нужно проверить:\n{task.get('solution', '')}"
    )


def extract_json(text: str) -> dict:
    """Извлечь первый сбалансированный JSON-объект из ответа модели."""
    if not text:
        return {}
    # 1) снять markdown-огороды
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    # 2) найти первый '{' и последний '}'
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return {}
    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # 3) попытка сбалансировать вручную
        depth = 0
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        return {}
        return {}


def call_deepseek(system_prompt: str, user_prompt: str) -> dict:
    """Один вызов DeepSeek reasoner с ретраями. Возвращает словарь вердикта."""
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
                wait = min(2 ** attempt, 60)
                log(f"    429 rate-limit, жду {wait}s...")
                time.sleep(wait)
                last_err = RuntimeError("429")
                continue
            if resp.status_code >= 500:
                wait = min(2 ** attempt, 30)
                log(f"    {resp.status_code} серверная ошибка, жду {wait}s...")
                time.sleep(wait)
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                continue
            resp.raise_for_status()
            body = resp.json()
            choices = body.get("choices") or []
            if not choices:
                last_err = RuntimeError("пустой choices")
                continue
            msg = choices[0].get("message", {}) or {}
            content = msg.get("content") or ""
            if not content:
                content = msg.get("reasoning_content") or ""
            verdict = extract_json(content)
            if not verdict:
                # модель не дала валидный JSON — повторить
                last_err = RuntimeError("невалидный JSON в ответе")
                log(f"    попытка {attempt}: невалидный JSON, повтор…")
                continue
            return verdict
        except requests.RequestException as e:
            last_err = e
            wait = min(2 ** attempt, 30)
            log(f"    сетевая ошибка (попытка {attempt}): {e}; жду {wait}s")
            time.sleep(wait)
    return {"_error": str(last_err), "overall_verdict": "error"}


def normalize_verdict(v: str) -> str:
    v = (v or "").strip().lower()
    if v in ("correct", "true", "pass", "ok", "верно", "правильно"):
        return "correct"
    if v in ("incorrect", "false", "fail", "неверно", "неправильно"):
        return "incorrect"
    if v == "error":
        return "error"
    return "unknown"


# ──────────────────────────────────────────────────────────────────────────
# Основная логика
# ──────────────────────────────────────────────────────────────────────────


def audit_one_task(task: dict) -> dict:
    """Два независимых аудита одной задачи."""
    user_prompt = build_user_prompt(task)

    verdict_a = call_deepseek(SYSTEM_A, user_prompt)
    # небольшая пауза, чтобы два вызова одной задачи не попали в один тик rate-limit
    time.sleep(0.2)
    verdict_b = call_deepseek(SYSTEM_B, user_prompt)

    return {"task": task, "audit_a": verdict_a, "audit_b": verdict_b}


def load_tasks(limit: int = None):
    tasks = []
    with open(SRC_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("level")) != "4":
                continue
            tasks.append(row)
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
    return {"done_idx": [], "double": [], "disputed": [], "stats": {}}


def save_checkpoint(cp):
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)


def flush_outputs(double_rows, disputed_rows, mode="a"):
    with open(OUT_DOUBLE, mode, encoding="utf-8") as f:
        for r in double_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_DISPUTED, mode, encoding="utf-8") as f:
        for r in disputed_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Ограничить число задач")
    parser.add_argument("--smoke", action="store_true", help="Smoke-режим (без записи файлов)")
    parser.add_argument("--resume", action="store_true", help="Продолжить с контрольной точки")
    args = parser.parse_args()

    load_env()
    if not API_KEY:
        log("ОШИБКА: DEEPSEEK_API_KEY не задан ни в окружении, ни в .env")
        sys.exit(1)
    log(f"Модель: {MODEL} | потоков: {WORKERS} | URL: {API_URL}")

    tasks = load_tasks(args.limit)
    log(f"Задач уровня 4: {len(tasks)}")

    cp = load_checkpoint() if args.resume else {"done_idx": [], "double": [], "disputed": [], "stats": {}}
    done_idx = set(cp.get("done_idx", []))
    double_rows = list(cp.get("double", []))
    disputed_rows = list(cp.get("disputed", []))
    stats = Counter(cp.get("stats", {}))

    pending = [i for i in range(len(tasks)) if i not in done_idx]
    log(f"Осталось обработать: {len(pending)}")

    if args.smoke:
        # только первые N без записи
        pending = pending[: args.limit or 10]
        log(f"SMOKE: обрабатываю {len(pending)} задач без записи файлов")

    lock = threading.Lock()

    def process(idx):
        task = tasks[idx]
        try:
            result = audit_one_task(task)
        except Exception as e:
            result = {
                "task": task,
                "audit_a": {"overall_verdict": "error", "_error": str(e)},
                "audit_b": {"overall_verdict": "error", "_error": str(e)},
            }
        return idx, result

    def verdict_of(audit):
        return normalize_verdict(audit.get("overall_verdict"))

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(process, i): i for i in pending}
        for fut in as_completed(futures):
            idx, result = fut.result()
            va = verdict_of(result["audit_a"])
            vb = verdict_of(result["audit_b"])

            with lock:
                done_idx.add(idx)
                if va == "error" or vb == "error":
                    stats["error"] += 1
                elif va == "incorrect" and vb == "incorrect":
                    stats["double_fail"] += 1
                    double_rows.append(result)
                elif va != vb:
                    stats["disputed"] += 1
                    disputed_rows.append(result)
                else:
                    stats["correct"] += 1

                # периодически пишем чекпоинт + файлы
                if len(done_idx) % 20 == 0:
                    cp["done_idx"] = sorted(done_idx)
                    cp["double"] = double_rows
                    cp["disputed"] = disputed_rows
                    cp["stats"] = dict(stats)
                    if not args.smoke:
                        save_checkpoint(cp)
                        flush_outputs(double_rows, disputed_rows, mode="w")

                log(
                    f"прогресс {len(done_idx)}/{len(tasks)} | "
                    f"верно={stats.get('correct',0)} "
                    f"double_fail={stats.get('double_fail',0)} "
                    f"disputed={stats.get('disputed',0)} "
                    f"error={stats.get('error',0)}"
                )

    # финальная запись
    cp["done_idx"] = sorted(done_idx)
    cp["double"] = double_rows
    cp["disputed"] = disputed_rows
    cp["stats"] = dict(stats)
    if not args.smoke:
        save_checkpoint(cp)
        flush_outputs(double_rows, disputed_rows, mode="w")

    log("=" * 60)
    log(f"ГОТОВО. Всего задач: {len(tasks)}")
    log(f"  Верно (оба аудита): {stats.get('correct', 0)}")
    log(f"  DOUBLE_FAIL (оба неверно): {stats.get('double_fail', 0)}")
    log(f"  DISPUTED (разногласие): {stats.get('disputed', 0)}")
    log(f"  Ошибки вызова: {stats.get('error', 0)}")
    if not args.smoke:
        log(f"Файлы: {OUT_DOUBLE}, {OUT_DISPUTED}")


if __name__ == "__main__":
    main()

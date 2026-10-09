# -*- coding: utf-8 -*-
"""
audit_l4_final_pass.py — Финальный дозапуск оставшихся error-вердиктов.

Читает ERROR_REMAIN.jsonl, для каждой строки повторно вызывает упавшую сторону
с увеличенным max_tokens (чтобы длинные решения не обрезали JSON), затем
объединяет результат с уже чистыми DOUBLE_FAIL/DISPUTED и переписывает файлы.
"""

import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audit_l4_deepseek import (
    CHECKPOINT,
    OUT_DOUBLE,
    OUT_DISPUTED,
    build_user_prompt,
    SYSTEM_A,
    SYSTEM_B,
    load_env,
    log,
    normalize_verdict,
    API_URL,
    API_KEY,
    MODEL,
    TIMEOUT,
    MAX_RETRIES,
    TEMPERATURE,
)
import requests

ERROR_REMAIN = "ERROR_REMAIN.jsonl"
WORKERS = 30
MAX_TOKENS_BIG = 8000


def call_deepseek_big(system_prompt, user_prompt):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS_BIG,
                },
                timeout=TIMEOUT,
            )
            if resp.status_code == 429:
                time.sleep(min(2 ** attempt, 60))
                continue
            if resp.status_code >= 500:
                time.sleep(min(2 ** attempt, 30))
                continue
            resp.raise_for_status()
            body = resp.json()
            choices = body.get("choices") or []
            if not choices:
                continue
            msg = choices[0].get("message", {}) or {}
            content = msg.get("content") or msg.get("reasoning_content") or ""
            # парсим JSON из ответа
            import re as _re
            m = _re.search(r"```(?:json)?\s*(.*?)```", content, _re.DOTALL)
            if m:
                content = m.group(1)
            s = content.find("{")
            e = content.rfind("}")
            if s == -1 or e <= s:
                continue
            try:
                return json.loads(content[s:e + 1])
            except json.JSONDecodeError:
                continue
        except requests.RequestException:
            time.sleep(min(2 ** attempt, 30))
    return {"overall_verdict": "error"}


def main():
    load_env()
    if not os.path.exists(ERROR_REMAIN):
        log("ERROR_REMAIN.jsonl не найден — нечего дозапускать.")
        return

    err_rows = [json.loads(l) for l in open(ERROR_REMAIN, encoding="utf-8") if l.strip()]
    log(f"Остаточных error-строк: {len(err_rows)}")

    # уже чистые результаты
    double_rows = [json.loads(l) for l in open(OUT_DOUBLE, encoding="utf-8") if l.strip()]
    disputed_rows = [json.loads(l) for l in open(OUT_DISPUTED, encoding="utf-8") if l.strip()]
    log(f"Уже: DOUBLE_FAIL={len(double_rows)}, DISPUTED={len(disputed_rows)}")

    lock = threading.Lock()
    resolved = []
    still_error = []

    def fix(row):
        task = row["task"]
        prompt = build_user_prompt(task)
        new_row = dict(row)
        for side in ("a", "b"):
            cur = normalize_verdict(new_row.get("audit_" + side, {}).get("overall_verdict"))
            if cur in ("error", "unknown"):
                sys_prompt = SYSTEM_A if side == "a" else SYSTEM_B
                new_row["audit_" + side] = call_deepseek_big(sys_prompt, prompt)
                time.sleep(0.2)
        return new_row

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fix, r): r for r in err_rows}
        for fut in as_completed(futures):
            new_row = fut.result()
            va = normalize_verdict(new_row["audit_a"].get("overall_verdict"))
            vb = normalize_verdict(new_row["audit_b"].get("overall_verdict"))
            with lock:
                if va in ("error", "unknown") or vb in ("error", "unknown"):
                    still_error.append(new_row)
                else:
                    resolved.append(new_row)

    log(f"Разрешено в этом проходе: {len(resolved)}, осталось error: {len(still_error)}")

    # объединяем
    all_rows = double_rows + disputed_rows + resolved
    double_final = []
    disputed_final = []
    for r in all_rows:
        va = normalize_verdict(r["audit_a"].get("overall_verdict"))
        vb = normalize_verdict(r["audit_b"].get("overall_verdict"))
        if va == "incorrect" and vb == "incorrect":
            double_final.append(r)
        elif va != vb:
            disputed_final.append(r)

    # запись
    with open(OUT_DOUBLE, "w", encoding="utf-8") as f:
        for r in double_final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_DISPUTED, "w", encoding="utf-8") as f:
        for r in disputed_final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if still_error:
        with open(ERROR_REMAIN, "w", encoding="utf-8") as f:
            for r in still_error:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    else:
        if os.path.exists(ERROR_REMAIN):
            os.remove(ERROR_REMAIN)

    # обновить чекпоинт
    cp = json.load(open(CHECKPOINT, encoding="utf-8"))
    total = len(cp.get("done_idx", []))
    cp["double"] = double_final
    cp["disputed"] = disputed_final
    cp["stats"] = {
        "double_fail": len(double_final),
        "disputed": len(disputed_final),
        "error": len(still_error),
        "correct": total - len(double_final) - len(disputed_final) - len(still_error),
    }
    cp["error_remain"] = len(still_error)
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)

    log("=" * 60)
    log(f"ФИНАЛ: DOUBLE_FAIL={len(double_final)}, DISPUTED={len(disputed_final)}, "
        f"correct={cp['stats']['correct']}, error={len(still_error)}")


if __name__ == "__main__":
    main()

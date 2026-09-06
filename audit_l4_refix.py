# -*- coding: utf-8 -*-
"""
audit_l4_refix.py — Дозапуск «error»-вердиктов после полного аудита.

В первом прогоне классификация ошибочно записала в DISPUTED строки, у которых
одна из сторон аудита вернула «error» (сбой/невалидный JSON после ретраев).
Этот скрипт:
  1. Читает контрольную точку audit_l4_checkpoint.json.
  2. Находит результаты, где audit_a или audit_b = «error».
  3. Повторно вызывает ТОЛЬКО упавшую сторону (30 потоков).
  4. Пере-классифицирует все результаты и переписывает
     DOUBLE_FAIL.jsonl и DISPUTED.jsonl строго по правилам:
        оба incorrect -> DOUBLE_FAIL
        correct/incorrect (в любом порядке) -> DISPUTED
        оба correct -> не пишется
        любой error после повтора -> пропускается (в ERROR_REMAIN.jsonl)
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
    call_deepseek,
    build_user_prompt,
    SYSTEM_A,
    SYSTEM_B,
    WORKERS,
    load_env,
    log,
    normalize_verdict,
)

ERROR_REMAIN = "ERROR_REMAIN.jsonl"


def main():
    load_env()
    cp = json.load(open(CHECKPOINT, "r", encoding="utf-8"))

    # Собрать все результаты (double + disputed) из чекпоинта
    all_rows = list(cp.get("double", [])) + list(cp.get("disputed", []))
    log(f"Всего строк в чекпоинте: {len(all_rows)}")

    # Разделить: нормальные (без error) и требующие повторного аудита
    ok_rows = []
    retry_rows = []  # (row, sides_to_retry)
    for r in all_rows:
        va = normalize_verdict(r.get("audit_a", {}).get("overall_verdict"))
        vb = normalize_verdict(r.get("audit_b", {}).get("overall_verdict"))
        sides = []
        if va == "error" or va == "unknown":
            sides.append("a")
        if vb == "error" or vb == "unknown":
            sides.append("b")
        if sides:
            retry_rows.append((r, sides))
        else:
            ok_rows.append(r)

    log(f"Нормальных строк: {len(ok_rows)}, требуют дозапуска: {len(retry_rows)}")

    # Повторный аудит упавших сторон
    lock = threading.Lock()
    fixed_rows = list(ok_rows)
    still_error = []

    def reaudit(item):
        row, sides = item
        task = row["task"]
        prompt = build_user_prompt(task)
        new_row = dict(row)
        for side in sides:
            sys_prompt = SYSTEM_A if side == "a" else SYSTEM_B
            verdict = call_deepseek(sys_prompt, prompt)
            new_row["audit_" + side] = verdict
            time.sleep(0.2)
        return new_row

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(reaudit, item): item for item in retry_rows}
        for fut in as_completed(futures):
            new_row = fut.result()
            va = normalize_verdict(new_row["audit_a"].get("overall_verdict"))
            vb = normalize_verdict(new_row["audit_b"].get("overall_verdict"))
            with lock:
                if va in ("error", "unknown") or vb in ("error", "unknown"):
                    still_error.append(new_row)
                else:
                    fixed_rows.append(new_row)

    # Переклассификация (сохраняем корректный общий счёт «correct»)
    double_rows = []
    disputed_rows = []
    for r in fixed_rows:
        va = normalize_verdict(r["audit_a"].get("overall_verdict"))
        vb = normalize_verdict(r["audit_b"].get("overall_verdict"))
        if va == "incorrect" and vb == "incorrect":
            double_rows.append(r)
        elif va != vb:
            disputed_rows.append(r)

    stats = Counter()
    total_done = len(cp.get("done_idx", []))
    stats["double_fail"] = len(double_rows)
    stats["disputed"] = len(disputed_rows)
    stats["error"] = len(still_error)
    stats["correct"] = total_done - len(double_rows) - len(disputed_rows) - len(still_error)

    # Запись финальных файлов
    with open(OUT_DOUBLE, "w", encoding="utf-8") as f:
        for r in double_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_DISPUTED, "w", encoding="utf-8") as f:
        for r in disputed_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if still_error:
        with open(ERROR_REMAIN, "w", encoding="utf-8") as f:
            for r in still_error:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Обновить чекпоинт корректными результатами
    cp["double"] = double_rows
    cp["disputed"] = disputed_rows
    cp["stats"] = dict(stats)
    cp["error_remain"] = len(still_error)
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)

    log("=" * 60)
    log(f"Дозапуск завершён.")
    log(f"  DOUBLE_FAIL: {len(double_rows)}")
    log(f"  DISPUTED: {len(disputed_rows)}")
    log(f"  correct (не пишется): {stats.get('correct', 0)}")
    log(f"  осталось error: {len(still_error)}")
    if still_error:
        log(f"  файл остаточных ошибок: {ERROR_REMAIN}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Надзиратель для run2.py: гоняет аудит, пока не проверятся все задачи,
затем запускает этап фикса и добивает его до конца.

Прогресс считается по уникальным task_uid в audit_output.jsonl
и FORMYLA_L1_L3_FINAL_v4.jsonl, строки с ошибками не учитываются.

ЗАПУСК:
    python supervise_audit.py            # аудит, затем фикс
    python supervise_audit.py audit      # только аудит
    python supervise_audit.py fix        # только фикс

Остановить: Ctrl+C
"""

import os
import sys
import json
import time
import subprocess

BASE_DIR = r"C:\Users\Redmi\Desktop\Новая папка (2)"
SCRIPT = "run2.py"
IN_DB = "FORMYLA_L1_L3_FINAL_v3.jsonl"
AUDIT_FILE = "audit_output.jsonl"
OUT_DB = "FORMYLA_L1_L3_FINAL_v4.jsonl"

MAX_RUNS = 80
STALL_LIMIT = 3
PAUSE = 8

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def uid_of(t):
    return t.get("task_uid") or t.get("taskuid") or t.get("uid")


def count_uids(path, skip_errors=True):
    if not os.path.exists(path):
        return 0
    seen = set()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if skip_errors and r.get("error"):
                continue
            u = uid_of(r)
            if u:
                seen.add(u)
    return len(seen)


def run_stage(stage):
    total = count_uids(IN_DB, skip_errors=False)
    target_file = AUDIT_FILE if stage == "audit" else OUT_DB
    label = "аудит" if stage == "audit" else "фикс"

    prev = count_uids(target_file)
    print("=" * 60)
    print(f"ЭТАП: {label.upper()} | готово {prev} из {total}")
    print("=" * 60, flush=True)

    if prev >= total:
        print(f"{label.capitalize()} уже завершён.\n")
        return True

    run = 0
    stall = 0
    started = time.time()

    while run < MAX_RUNS:
        run += 1
        t0 = time.time()
        print(f"\n[{time.strftime('%H:%M:%S')}] {label}, запуск #{run} ...",
              flush=True)

        try:
            p = subprocess.run([sys.executable, "-u", SCRIPT, stage])
            code = p.returncode
        except KeyboardInterrupt:
            print("\nПрервано пользователем.")
            return False

        now = count_uids(target_file)
        gain = now - prev
        secs = int(time.time() - t0)
        el = int(time.time() - started)
        speed = (now - (prev - gain)) / max(el / 60, 0.1)
        eta = (total - now) / speed if speed > 0 else 0

        print(f"    код {code} | готово {now}/{total} | прибавка {gain} | "
              f"{secs // 60} мин {secs % 60} с", flush=True)
        if gain > 0 and eta > 0:
            print(f"    осталось примерно {int(eta) // 60} ч {int(eta) % 60} мин",
                  flush=True)

        if now >= total:
            t = int(time.time() - started)
            print(f"\n{label.upper()} ЗАВЕРШЁН: {now} из {total} "
                  f"за {run} запусков, {t // 60} мин.\n")
            return True

        if gain <= 0:
            stall += 1
            print(f"    прогресса нет ({stall} из {STALL_LIMIT})", flush=True)
            if stall >= STALL_LIMIT:
                print(f"\nОСТАНОВКА на этапе «{label}»: {STALL_LIMIT} запусков "
                      f"подряд без единой новой задачи.")
                print("Причина видна в выводе run2.py выше.")
                return False
            time.sleep(PAUSE * stall)
        else:
            stall = 0
            time.sleep(PAUSE)

        prev = now

    print(f"\nДостигнут лимит {MAX_RUNS} запусков на этапе «{label}».")
    return False


def main():
    os.chdir(BASE_DIR)
    what = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    if not os.path.exists(SCRIPT):
        sys.exit(f"Не найден {SCRIPT}")

    total = count_uids(IN_DB, skip_errors=False)
    print(f"Надзиратель аудита. Задач в базе: {total}\n")

    ok = True
    if what in ("all", "audit"):
        ok = run_stage("audit")
    if ok and what in ("all", "fix"):
        run_stage("fix")

    print("\n" + "=" * 60)
    subprocess.run([sys.executable, "-u", SCRIPT, "stats"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОстановлено.")

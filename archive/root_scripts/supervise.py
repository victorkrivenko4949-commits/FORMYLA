#!/usr/bin/env python3
"""
Надзиратель: перезапускает fix_latex_deepseek.py, пока не обработаются все объекты.

Прогресс читается прямо из sqlite-checkpoint, поэтому виден честно,
даже пока итоговый файл ещё не создан.

ЗАПУСК:
    python supervise.py
    python supervise.py --target 69
    python supervise.py --script other.py --ckpt .other_checkpoint.sqlite3

Остановить: Ctrl+C
"""

import os
import sys
import time
import sqlite3
import argparse
import subprocess

BASE_DIR = r"C:\Users\Redmi\Desktop\Новая папка (2)"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def count_done(ckpt):
    """Максимальное число строк среди таблиц checkpoint."""
    if not os.path.exists(ckpt):
        return 0
    try:
        con = sqlite3.connect(f"file:{ckpt}?mode=ro", uri=True, timeout=5)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        best = 0
        for t in tables:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                best = max(best, cur.fetchone()[0])
            except sqlite3.Error:
                pass
        con.close()
        return best
    except sqlite3.Error:
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="fix_latex_deepseek.py")
    ap.add_argument("--ckpt", default=".6767_latex_checkpoint.sqlite3")
    ap.add_argument("--target", type=int, default=69)
    ap.add_argument("--max-runs", type=int, default=60)
    ap.add_argument("--stall-limit", type=int, default=4)
    ap.add_argument("--pause", type=int, default=5)
    a = ap.parse_args()

    os.chdir(BASE_DIR)

    if not os.path.exists(a.script):
        sys.exit(f"Не найден скрипт: {a.script}")

    prev = count_done(a.ckpt)
    print(f"Надзиратель запущен. Готово {prev} из {a.target}.")
    print(f"Скрипт: {a.script} | checkpoint: {a.ckpt}\n", flush=True)

    if prev >= a.target:
        print("Всё уже обработано.")
        return

    run = 0
    stall = 0
    started = time.time()

    while run < a.max_runs:
        run += 1
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] запуск #{run} ...", flush=True)

        try:
            p = subprocess.run([sys.executable, "-u", a.script])
            code = p.returncode
        except KeyboardInterrupt:
            print("\nПрервано пользователем.")
            break

        now = count_done(a.ckpt)
        gain = now - prev
        secs = int(time.time() - t0)
        print(f"    код {code} | готово {now}/{a.target} | "
              f"прибавка {gain} | {secs} с\n", flush=True)

        if now >= a.target:
            total = int(time.time() - started)
            print(f"ГОТОВО: {now} из {a.target} за {run} запусков, "
                  f"{total // 60} мин {total % 60} с.")
            break

        if gain <= 0:
            stall += 1
            print(f"    прогресса нет ({stall} из {a.stall_limit})", flush=True)
            if stall >= a.stall_limit:
                print(f"\nОСТАНОВКА: {a.stall_limit} запусков подряд "
                      f"без единого нового объекта.")
                print("Скрипт падает всегда в одном месте — смотри его вывод выше.")
                break
            time.sleep(a.pause * stall)
        else:
            stall = 0
            time.sleep(a.pause)

        prev = now
    else:
        print(f"\nДостигнут лимит {a.max_runs} запусков.")

    final = count_done(a.ckpt)
    print(f"\nИтог: {final} из {a.target} в checkpoint.")
    if final < a.target:
        print(f"Осталось: {a.target - final}. Запусти надзиратель ещё раз.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОстановлено.")

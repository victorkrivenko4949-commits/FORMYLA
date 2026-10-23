#!/usr/bin/env python3
"""
Выгрузка готовых объектов из checkpoint LaTeX-нормализатора.

ЗАПУСК:
    python export_latex.py

СОЗДАЁТ:
    6767_latex_partial.jsonl   — 62 готовых объекта, обычный jsonl
    6767_latex_pending.txt     — список тех, что ещё не обработаны
    6767_latex_schema.txt      — структура checkpoint, если что-то пойдёт не так

Читает базу в режиме только для чтения, работающему скрипту не мешает.
"""

import os
import sys
import json
import sqlite3

BASE_DIR = r"C:\Users\Redmi\Desktop\Новая папка (2)"
CKPT = ".6767_latex_checkpoint.sqlite3"
SOURCE = "6767.txt"
OUT_DONE = "6767_latex_partial.jsonl"
OUT_PENDING = "6767_latex_pending.txt"
OUT_SCHEMA = "6767_latex_schema.txt"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def maybe_json(v):
    if isinstance(v, (bytes, bytearray)):
        try:
            v = v.decode("utf-8")
        except UnicodeDecodeError:
            return "<binary>"
    if isinstance(v, str):
        s = v.strip()
        if s[:1] in ("{", "[") and s[-1:] in ("}", "]"):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                pass
    return v


def main():
    os.chdir(BASE_DIR)

    if not os.path.exists(CKPT):
        sys.exit(f"Не найден checkpoint: {CKPT}")

    con = sqlite3.connect(f"file:{CKPT}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]

    schema_lines = []
    biggest, biggest_n = None, -1
    for t in tables:
        cur.execute(f'PRAGMA table_info("{t}")')
        cols = [r[1] for r in cur.fetchall()]
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        n = cur.fetchone()[0]
        schema_lines.append(f"{t}: {n} строк | колонки: {', '.join(cols)}")
        if n > biggest_n:
            biggest, biggest_n = t, n

    with open(OUT_SCHEMA, "w", encoding="utf-8") as f:
        f.write("\n".join(schema_lines) + "\n")

    print("Структура checkpoint:")
    for line in schema_lines:
        print("  " + line)

    if not biggest:
        sys.exit("В базе нет таблиц.")

    print(f"\nБеру таблицу: {biggest} ({biggest_n} строк)")

    cur.execute(f'SELECT * FROM "{biggest}"')
    rows = [dict(r) for r in cur.fetchall()]
    con.close()

    done_uids = set()
    with open(OUT_DONE, "w", encoding="utf-8") as f:
        for r in rows:
            rec = {k: maybe_json(v) for k, v in r.items()}
            for key in ("uid", "task_uid", "id", "key"):
                if rec.get(key):
                    done_uids.add(str(rec[key]))
                    break
            else:
                for v in rec.values():
                    if isinstance(v, dict):
                        u = v.get("task_uid") or v.get("uid")
                        if u:
                            done_uids.add(str(u))
                            break
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Записано готовых: {len(rows)} -> {OUT_DONE}")

    pending = []
    if os.path.exists(SOURCE):
        with open(SOURCE, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                u = str(obj.get("task_uid") or obj.get("uid") or f"строка_{i}")
                if u not in done_uids:
                    pending.append((i, u))

        with open(OUT_PENDING, "w", encoding="utf-8") as f:
            f.write(f"НЕ ОБРАБОТАНО: {len(pending)}\n")
            f.write("=" * 50 + "\n")
            for i, u in pending:
                f.write(f"строка {i}: {u}\n")

        print(f"Не обработано  : {len(pending)} -> {OUT_PENDING}")
        for i, u in pending[:15]:
            print(f"    строка {i}: {u}")
    else:
        print(f"Исходник {SOURCE} не найден, список оставшихся не составлен.")

    print(f"\nСхема сохранена в {OUT_SCHEMA}")


if __name__ == "__main__":
    main()

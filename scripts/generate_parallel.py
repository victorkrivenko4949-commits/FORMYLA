"""Parallel adaptive-task generator (ThreadPoolExecutor over per-cell jobs).

Uses the same prompt builder, parser and normalizer as
[`generate_missing_adaptive_tasks.py`](scripts/generate_missing_adaptive_tasks.py:1),
just runs many cells/batches concurrently. SQLite write is serialized via a Lock.

CLI:
    python scripts/generate_parallel.py --workers 30 --per-level 25 --batch-size 5

Safe: Ctrl+C — stops accepting new jobs, waits for in-flight ones to finish,
all already-saved tasks remain in DB. Re-run continues automatically.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import queue
import random
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError  # noqa: E402

from scripts.generate_missing_adaptive_tasks import (  # noqa: E402
    GRADES, UI_TOPICS, UI_TOPIC_NAMES_RU, OUT_DIR,
    SYSTEM_PROMPT, INSERT_COLS,
    build_prompt, parse_json_array, normalize, keywords_for,
    fetch_count_by_level, fetch_examples_by_level, fetch_examples,
    existing_topics,
)

DB = os.path.join("instance", "formyla.db")

# Per-thread DeepSeek client (so we don't share TCP connection state).
_local = threading.local()


def get_client() -> DeepSeekClient:
    if not hasattr(_local, "client"):
        _local.client = DeepSeekClient()
    return _local.client


def now_iso() -> str:
    return _dt.datetime.utcnow().isoformat(sep=" ", timespec="seconds")


def insert_rows(db_lock: threading.Lock, conn: sqlite3.Connection,
                rows: list[tuple], existing_texts: set[str],
                texts_lock: threading.Lock) -> int:
    """Bulk-insert; skip duplicates by task_text (checked under texts_lock)."""
    if not rows:
        return 0
    placeholders = ", ".join(["?"] * len(INSERT_COLS))
    sql = f"INSERT INTO adaptive_tasks ({', '.join(INSERT_COLS)}) VALUES ({placeholders})"
    inserted = 0
    with db_lock:
        cur = conn.cursor()
        for params in rows:
            text = params[4]
            with texts_lock:
                if text in existing_texts:
                    continue
                existing_texts.add(text)
            try:
                cur.execute(sql, params)
                inserted += 1
            except Exception as e:
                print(f"   [insert-error] {e}")
        conn.commit()
    return inserted


def build_cell_examples(conn: sqlite3.Connection, db_lock: threading.Lock,
                        grade: int, topic_ui: str, level: int) -> tuple[list[dict], list[str]]:
    """Snapshot examples + db_topics for a cell (read under DB lock)."""
    with db_lock:
        cur = conn.cursor()
        examples = fetch_examples_by_level(cur, grade, topic_ui, level, limit=3)
        if not examples:
            examples = fetch_examples(cur, grade, topic_ui, limit=3)
        if not examples:
            for nearby in sorted(GRADES, key=lambda x: abs(x - grade)):
                if nearby == grade:
                    continue
                ex = (fetch_examples_by_level(cur, nearby, topic_ui, level, limit=3)
                      or fetch_examples(cur, nearby, topic_ui, limit=3))
                if ex:
                    examples = ex
                    break
        db_topics = existing_topics(cur, grade, topic_ui)[:5]
    return examples, db_topics


def cell_worker(job: dict, conn: sqlite3.Connection,
                db_lock: threading.Lock, texts_lock: threading.Lock,
                existing_texts: set[str], stop_event: threading.Event,
                stats: dict) -> dict:
    """Process one (grade, topic, level) cell.

    Inside one cell we do batches sequentially (each batch ≤ batch_size).
    Different cells run in parallel through the ThreadPoolExecutor.
    """
    grade = job["grade"]; topic = job["topic"]; level = job["level"]
    target = job["target"]; batch_size = job["batch_size"]
    max_batches = job["max_batches"]

    if stop_event.is_set():
        return {"grade": grade, "topic": topic, "level": level, "inserted": 0, "stopped": True}

    examples, db_topics = build_cell_examples(conn, db_lock, grade, topic, level)
    primary_topic = (db_topics[0] if db_topics
                     else f"{UI_TOPIC_NAMES_RU.get(topic, topic)} ({grade} класс)")

    # how many we still need (read fresh)
    with db_lock:
        cur = conn.cursor()
        have = fetch_count_by_level(cur, grade, topic, level)
    need = max(0, target - have)
    if need == 0:
        return {"grade": grade, "topic": topic, "level": level, "inserted": 0}

    out_path = os.path.join(OUT_DIR,
                            f"g{grade}_{topic}_L{level}_{_dt.datetime.utcnow():%Y%m%d_%H%M%S}_t{threading.get_ident()}.jsonl")
    inserted_total = 0
    client = get_client()

    for batch_idx in range(max_batches):
        if stop_event.is_set() or inserted_total >= need:
            break
        bs = min(batch_size, need - inserted_total)
        prompt = build_prompt(grade, topic, examples, db_topics, {},
                              bs, target_level=level)
        try:
            raw = client.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT,
                                  temperature=0.65, max_tokens=4096)
        except DeepSeekAPIError as e:
            stats["api_errors"] += 1
            time.sleep(min(30, 2 * (batch_idx + 1)))
            continue
        except Exception as e:
            stats["api_errors"] += 1
            time.sleep(2)
            continue

        try:
            recs = parse_json_array(raw)
        except Exception as e:
            stats["parse_errors"] += 1
            with open(os.path.join(OUT_DIR, "_parse_errors.log"), "a", encoding="utf-8") as fp:
                fp.write(f"\n--- {now_iso()} grade={grade} topic={topic} level={level} batch={batch_idx + 1} thread={threading.get_ident()} ---\n")
                fp.write(raw[:6000] + "\n")
            continue

        rows = []
        appended_local = []
        for r in recs:
            norm = normalize(r, grade, primary_topic)
            if not norm:
                continue
            norm["difficulty_level"] = level
            params = (
                norm["class_level"], norm["difficulty_level"], norm["topic"], norm.get("subtopic"),
                norm["task_text"], norm["solution"], norm["criteria_1_point"], norm["criteria_2_points"],
                norm.get("correct_answer"), 0, 0, 0, 0, 0, now_iso(),
            )
            rows.append(params)
            appended_local.append(norm)

        kept = insert_rows(db_lock, conn, rows, existing_texts, texts_lock)
        if kept:
            with open(out_path, "a", encoding="utf-8") as fp:
                for n in appended_local[:kept]:
                    fp.write(json.dumps(n, ensure_ascii=False) + "\n")
            inserted_total += kept
            stats["inserted"] += kept
        stats["batches"] += 1

    return {"grade": grade, "topic": topic, "level": level, "inserted": inserted_total}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--workers", type=int, default=30)
    ap.add_argument("--per-level", type=int, default=25)
    ap.add_argument("--batch-size", type=int, default=5)
    ap.add_argument("--max-batches", type=int, default=8)
    ap.add_argument("--grades", nargs="+", type=int, default=GRADES)
    ap.add_argument("--topics", nargs="+", default=UI_TOPICS)
    ap.add_argument("--levels", nargs="+", type=int, default=[1, 2, 3, 4, 5, 6, 7])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db, check_same_thread=False, timeout=30.0)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")  # better concurrent reads/writes
    cur.execute("SELECT task_text FROM adaptive_tasks")
    existing_texts = {row[0] for row in cur.fetchall()}
    print(f"DB ready. Existing tasks: {len(existing_texts)}")

    # Build job list (per cell)
    jobs = []
    print(f"\n=== План (per-level={args.per_level}, workers={args.workers}) ===")
    for g in args.grades:
        for t in args.topics:
            for l in args.levels:
                have = fetch_count_by_level(cur, g, t, l)
                need = max(0, args.per_level - have)
                if need:
                    jobs.append({
                        "grade": g, "topic": t, "level": l,
                        "have": have, "need": need,
                        "target": args.per_level,
                        "batch_size": args.batch_size,
                        "max_batches": args.max_batches,
                    })
    if not jobs:
        print("  Все ячейки заполнены.")
        return

    jobs.sort(key=lambda j: -j["need"])  # biggest deficit first
    total_need = sum(j["need"] for j in jobs)
    print(f"  Ячеек: {len(jobs)}; задач к генерации: {total_need}")
    if args.dry_run:
        for j in jobs[:30]:
            print(f"  g{j['grade']} {j['topic']:<14} L{j['level']}: have={j['have']} need={j['need']}")
        if len(jobs) > 30:
            print(f"  ... + {len(jobs) - 30} ячеек")
        return

    db_lock = threading.Lock()
    texts_lock = threading.Lock()
    stop_event = threading.Event()
    stats = {"inserted": 0, "batches": 0, "api_errors": 0, "parse_errors": 0}

    t_start = time.time()
    print(f"\nStart: {now_iso()}")
    print(f"Workers: {args.workers}, batch_size: {args.batch_size}, max_batches/cell: {args.max_batches}\n")

    futures = []
    completed = 0
    try:
        with ThreadPoolExecutor(max_workers=args.workers,
                                thread_name_prefix="gen") as ex:
            for job in jobs:
                futures.append(ex.submit(cell_worker, job, conn,
                                         db_lock, texts_lock, existing_texts,
                                         stop_event, stats))

            for fut in as_completed(futures):
                completed += 1
                try:
                    r = fut.result()
                except Exception as e:
                    print(f"   [worker-crash] {e}")
                    continue
                el = time.time() - t_start
                rate = stats["inserted"] / max(el, 1) * 60
                print(f"  [{completed:>3}/{len(jobs)}] g{r['grade']} {r['topic']:<14} L{r['level']}: "
                      f"+{r['inserted']:>2} | total inserted={stats['inserted']}, "
                      f"rate={rate:.0f}/min, parse_err={stats['parse_errors']}, api_err={stats['api_errors']}")
    except KeyboardInterrupt:
        print("\nStop requested (Ctrl+C). Letting in-flight cells finish...")
        stop_event.set()

    el = time.time() - t_start
    print(f"\n=== Done in {el / 60:.1f} min ===")
    print(f"Inserted: {stats['inserted']}")
    print(f"Batches:  {stats['batches']}")
    print(f"Parse errors: {stats['parse_errors']}")
    print(f"API errors:   {stats['api_errors']}")


if __name__ == "__main__":
    main()

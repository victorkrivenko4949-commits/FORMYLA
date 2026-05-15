"""Validate and insert DeepSeek-fixed tasks back into the DB.

Reads scripts/_validation/fixed_tasks.jsonl (output of
fix_broken_tasks_with_deepseek.py). For each candidate:
  1. Validate with the SAME validator prompt used elsewhere (verdict ok / broken / unclear).
  2. Insert ONLY if verdict == 'ok'. Skip 'broken' / 'unclear' / 'error'.

Insertion uses the same column set as generate_parallel.py.

Usage:
    python scripts/insert_fixed_tasks.py
    python scripts/insert_fixed_tasks.py --workers 30
    python scripts/insert_fixed_tasks.py --include-unclear   # less strict
    python scripts/insert_fixed_tasks.py --dry-run
"""
import argparse, datetime as _dt, json, os, re, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError  # noqa: E402
from scripts.validate_tasks_with_deepseek import (  # noqa: E402
    SYSTEM_PROMPT as VALIDATION_PROMPT,
    parse_verdict, normalize_verdict,
)

DB = os.path.join(ROOT, "instance", "formyla.db")
OUT_DIR = os.path.join(ROOT, "scripts", "_validation")
FIXED_PATH = os.path.join(OUT_DIR, "fixed_tasks.jsonl")
INSERTED_LOG = os.path.join(OUT_DIR, "inserted.log")


def now_iso():
    return _dt.datetime.now().isoformat(sep=" ", timespec="seconds")


def load_candidates():
    if not os.path.exists(FIXED_PATH):
        return []
    out = []
    with open(FIXED_PATH, "r", encoding="utf-8") as fp:
        for line in fp:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("status") != "candidate":
                continue
            out.append(obj)
    return out


def load_existing_texts(cur):
    cur.execute("SELECT task_text FROM adaptive_tasks")
    return {row[0] for row in cur.fetchall()}


def validate_candidate(cand, client):
    prompt = (
        f"УСЛОВИЕ:\n{cand['task_text']}\n\n"
        f"ЭТАЛОННЫЙ ОТВЕТ:\n{cand.get('correct_answer') or '(не задан)'}\n\n"
        f"ЭТАЛОННОЕ РЕШЕНИЕ:\n{cand.get('solution') or '(пусто)'}\n\n"
        "Верни строго один JSON-объект."
    )
    try:
        raw = client.generate(
            prompt=prompt, system_prompt=VALIDATION_PROMPT,
            temperature=0.0, max_tokens=350,
        )
    except DeepSeekAPIError as e:
        return {"verdict": "error", "confidence": "low",
                "reason": f"api_error: {e}"}
    except Exception as e:
        return {"verdict": "error", "confidence": "low",
                "reason": f"exc: {e}"}

    v = normalize_verdict(parse_verdict(raw))
    if not v:
        return {"verdict": "error", "confidence": "low",
                "reason": "parse_failed"}
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--include-unclear", action="store_true",
                    help="Also insert verdict=unclear (otherwise only ok)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cands = load_candidates()
    print(f"Candidates in {FIXED_PATH}: {len(cands)}")
    if not cands:
        return

    conn = sqlite3.connect(DB, timeout=30.0)
    cur = conn.cursor()
    existing = load_existing_texts(cur)
    print(f"DB existing tasks: {len(existing)}")

    # Drop candidates whose text already exists in DB
    before = len(cands)
    cands = [c for c in cands
             if (c.get("task_text") or "").strip() not in existing]
    print(f"After dropping duplicates: {len(cands)} (was {before})")

    if not cands:
        return

    client = DeepSeekClient()
    file_lock = threading.Lock()
    counters = {"ok": 0, "broken": 0, "unclear": 0, "error": 0}
    accepted = []
    started = time.time()

    print(f"\n=== validation start: {now_iso()}, workers={args.workers} ===\n")

    def worker(c):
        v = validate_candidate(c, client)
        verdict = v["verdict"]
        with file_lock:
            counters[verdict] = counters.get(verdict, 0) + 1
            ok = (verdict == "ok") or (
                args.include_unclear and verdict == "unclear"
            )
            if ok:
                accepted.append((c, v))
        return verdict

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(worker, c) for c in cands]
        done_count = 0
        for fut in as_completed(futures):
            done_count += 1
            if done_count % 25 == 0 or done_count == len(futures):
                elapsed = time.time() - started
                rate = done_count / max(elapsed, 1) * 60
                remaining = (len(futures) - done_count) / max(rate / 60, 1e-3)
                print(
                    f"  [{done_count}/{len(futures)}] ok={counters['ok']} "
                    f"broken={counters['broken']} unclear={counters['unclear']} "
                    f"error={counters['error']} | {rate:.0f}/min, "
                    f"ETA ~{remaining/60:.1f} min"
                )

    print(f"\nValidation done: ok={counters['ok']}, broken={counters['broken']}, "
          f"unclear={counters['unclear']}, error={counters['error']}")
    print(f"Will insert: {len(accepted)}")

    if args.dry_run:
        print("Dry-run: no inserts performed.")
        return

    inserted = 0
    skipped_dup = 0
    fresh_existing = set(existing)
    log_fp = open(INSERTED_LOG, "a", encoding="utf-8")
    try:
        for c, v in accepted:
            text = (c["task_text"] or "").strip()
            if text in fresh_existing:
                skipped_dup += 1
                continue
            params = (
                c["class_level"],
                c["difficulty_level"],
                c["topic"],
                c.get("subtopic"),
                text,
                c["solution"],
                c.get("criteria_1_point") or "",
                c.get("criteria_2_points") or "",
                c.get("correct_answer") or "",
                0, 0, 0, 0, 0,
                now_iso(),
            )
            try:
                cur.execute(
                    "INSERT INTO adaptive_tasks "
                    "(class_level, difficulty_level, topic, subtopic, "
                    "task_text, solution, criteria_1_point, criteria_2_points, "
                    "correct_answer, is_flagged, reports_count, attempts_count, "
                    "solves_count, needs_reclassification, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    params,
                )
                fresh_existing.add(text)
                inserted += 1
                log_fp.write(
                    f"[{now_iso()}] inserted source_id={c['source_id']} "
                    f"new_id=? cl={c['class_level']} L={c['difficulty_level']} "
                    f"topic={c['topic']!r}\n"
                )
            except sqlite3.IntegrityError as e:
                skipped_dup += 1
                log_fp.write(
                    f"[{now_iso()}] SKIP source_id={c['source_id']} ({e})\n"
                )
        conn.commit()
    finally:
        log_fp.close()
        conn.close()

    print(f"\nInserted into DB: {inserted}")
    print(f"Skipped (duplicates / errors): {skipped_dup}")
    print(f"Insertion log: {INSERTED_LOG}")


if __name__ == "__main__":
    main()

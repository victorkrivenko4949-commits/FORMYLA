"""Validate the LABELED difficulty_level (1..7) of every adaptive task using
DeepSeek's reasoning model (deepseek-reasoner with CoT enabled).

For each task we send:
  • the official 7-level rubric (LEVEL_HINTS),
  • the task statement,
  • the task's solution,
  • the labeled level,
and ask the reasoner to (a) think it through, (b) emit a single JSON with
its predicted level (1..7), a verdict, and a short reason.

Output: scripts/_validation/difficulty.jsonl  (one JSON object per task)
  {
    "id": <int>,
    "labeled_level": <int>,
    "predicted_level": <int>,        # 1..7
    "verdict": "match" | "off_by_one" | "too_easy" | "too_hard",
    "delta": <int>,                  # predicted - labeled
    "confidence": "high" | "medium" | "low",
    "reason": "<short ru>"
  }

Resumable: re-running skips ids already present in the JSONL.

Usage:
    python scripts/validate_difficulty_levels.py --workers 20
    python scripts/validate_difficulty_levels.py --grade 9 --topic geometry
    python scripts/validate_difficulty_levels.py --limit 200 --workers 10
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError  # noqa: E402
from scripts.generate_missing_adaptive_tasks import LEVEL_HINTS  # noqa: E402

DB = os.path.join(ROOT, "instance", "formyla.db")
OUT_DIR = os.path.join(ROOT, "scripts", "_validation")
os.makedirs(OUT_DIR, exist_ok=True)
JSONL_PATH = os.path.join(OUT_DIR, "difficulty.jsonl")
ERR_LOG = os.path.join(OUT_DIR, "difficulty_errors.log")


# ---------------------------------------------------------------------------
# Rubric: send the FULL 7-level hint table to the model so it grades on the
# same scale as our generator.
# ---------------------------------------------------------------------------
RUBRIC = "\n".join(
    f"  Уровень {lvl}: {hint}" for lvl, hint in sorted(LEVEL_HINTS.items())
)

SYSTEM_PROMPT = (
    "Ты — старший методист по олимпиадной математике (ВсОШ). Твоя задача — "
    "оценить, какому именно уровню сложности по нашей 7-балльной шкале "
    "соответствует КОНКРЕТНАЯ задача. У тебя есть рубрика:\n\n"
    f"{RUBRIC}\n\n"
    "Ты получаешь:\n"
    "  • КЛАСС, для которого задача предназначена,\n"
    "  • ТЕМУ,\n"
    "  • УСЛОВИЕ задачи,\n"
    "  • ЭТАЛОННОЕ РЕШЕНИЕ,\n"
    "  • ОТВЕТ,\n"
    "  • НАЗНАЧЕННЫЙ нами уровень (labeled_level), 1..7.\n\n"
    "Подумай: какие приёмы нужны для решения? Сколько идей? Это рутина или "
    "требуется нетривиальный ход? Подходит ли это для указанного КЛАССА? "
    "Сравни с рубрикой и выбери ОДИН наиболее подходящий уровень 1..7.\n\n"
    "Затем верни СТРОГО один JSON-объект, без markdown, без преамбулы:\n"
    "{\n"
    '  "predicted_level": <int 1..7>,\n'
    '  "verdict": "match" | "off_by_one" | "too_easy" | "too_hard",\n'
    '  "confidence": "high" | "medium" | "low",\n'
    '  "reason": "ОДНО короткое предложение по-русски, не длиннее 120 символов"\n'
    "}\n\n"
    "ВАЖНО: ответ ДОЛЖЕН быть полным валидным JSON. Поле reason — максимум "
    "120 символов, иначе JSON обрежется и сломается.\n\n"
    "Правила verdict:\n"
    "  • \"match\"      — predicted_level == labeled_level (точно соответствует)\n"
    "  • \"off_by_one\" — |predicted - labeled| == 1 (приемлемое несовпадение)\n"
    "  • \"too_easy\"   — predicted_level < labeled_level - 1 "
    "(задача проще, чем заявлено)\n"
    "  • \"too_hard\"   — predicted_level > labeled_level + 1 "
    "(задача сложнее, чем заявлено)\n\n"
    "ВАЖНО:\n"
    "  • Оценивай ОТНОСИТЕЛЬНО указанного класса: задача из учебника алгебры "
    "9 класса для 9-классника — это level 1, а не 3.\n"
    "  • Шаблонные системы уравнений вида x²+y² = a, xy = b — это level 1-2.\n"
    "  • Прямое применение теоремы Виета, формулы сокращённого умножения, "
    "стандартного треугольника — это level 1-2.\n"
    "  • Если требуется ОДНА нестандартная идея — level 4.\n"
    "  • Если задача требует 2-3 связанных нетривиальных идей — level 5-6.\n"
    "  • Не завышай и не занижай — будь честным методистом.\n"
    "  • confidence \"high\" — только когда уверен; иначе \"medium\"."
)


def _now() -> str:
    import datetime as _dt
    return _dt.datetime.now().isoformat(sep=" ", timespec="seconds")


def load_done_ids() -> set[int]:
    done: set[int] = set()
    if not os.path.exists(JSONL_PATH):
        return done
    with open(JSONL_PATH, "r", encoding="utf-8") as fp:
        for line in fp:
            try:
                obj = json.loads(line)
                if isinstance(obj.get("id"), int):
                    done.add(obj["id"])
            except Exception:
                continue
    return done


def fetch_tasks(grade, topic, level, limit, done_ids):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    sql = (
        "SELECT id, class_level, difficulty_level, topic, task_text, "
        "correct_answer, solution FROM adaptive_tasks WHERE 1=1"
    )
    params = []
    if grade is not None:
        sql += " AND class_level = ?"
        params.append(grade)
    if topic:
        sql += " AND topic LIKE ?"
        params.append(f"%{topic}%")
    if level is not None:
        sql += " AND difficulty_level = ?"
        params.append(level)
    sql += " ORDER BY id ASC"
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    rows = [r for r in rows if r["id"] not in done_ids]
    if limit:
        rows = rows[:limit]
    return rows


def build_prompt(task: dict) -> str:
    return (
        f"КЛАСС: {task['class_level']}\n"
        f"ТЕМА: {task.get('topic') or '(не указана)'}\n"
        f"LABELED_LEVEL (нами назначенный уровень): {task['difficulty_level']}\n\n"
        f"=== УСЛОВИЕ ===\n{task['task_text']}\n\n"
        f"=== ЭТАЛОННОЕ РЕШЕНИЕ ===\n{(task.get('solution') or '(пусто)')[:4000]}\n\n"
        f"=== ОТВЕТ ===\n{task.get('correct_answer') or '(не задан)'}\n\n"
        "Оцени, какому из 7 уровней рубрики РЕАЛЬНО соответствует эта задача "
        "для ученика указанного КЛАССА. Подумай внимательно и верни строго один JSON."
    )


JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json(raw: str):
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        m = JSON_RE.search(s)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None


def normalize(obj, labeled_level):
    if not isinstance(obj, dict):
        return None
    try:
        pred = int(obj.get("predicted_level"))
    except Exception:
        return None
    if pred < 1 or pred > 7:
        return None

    delta = pred - labeled_level
    abs_d = abs(delta)
    # Recompute verdict from delta to enforce consistency
    if abs_d == 0:
        verdict = "match"
    elif abs_d == 1:
        verdict = "off_by_one"
    elif delta < 0:
        verdict = "too_easy"
    else:
        verdict = "too_hard"

    conf = str(obj.get("confidence", "")).strip().lower()
    if conf not in ("high", "medium", "low"):
        conf = "medium"
    reason = str(obj.get("reason", "")).strip()[:500]
    return {
        "predicted_level": pred,
        "verdict": verdict,
        "delta": delta,
        "confidence": conf,
        "reason": reason,
    }


def validate_one(task: dict, client: DeepSeekClient) -> dict:
    prompt = build_prompt(task)
    try:
        raw = client.generate_with_reasoning(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=800,
            return_reasoning=False,
            timeout=300,
        )
    except DeepSeekAPIError as e:
        return {
            "id": task["id"], "labeled_level": task["difficulty_level"],
            "verdict": "error", "confidence": "low",
            "reason": f"api_error: {e}",
        }
    except Exception as e:
        return {
            "id": task["id"], "labeled_level": task["difficulty_level"],
            "verdict": "error", "confidence": "low",
            "reason": f"exc: {e}",
        }

    parsed = parse_json(raw)
    norm = normalize(parsed, task["difficulty_level"])
    if not norm:
        return {
            "id": task["id"], "labeled_level": task["difficulty_level"],
            "verdict": "error", "confidence": "low",
            "reason": "parse_failed", "raw": (raw or "")[:400],
        }
    norm["id"] = task["id"]
    norm["labeled_level"] = task["difficulty_level"]
    return norm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=15,
                    help="Reasoner is slow; 10-20 is a sweet spot")
    ap.add_argument("--grade", type=int, default=None)
    ap.add_argument("--topic", default=None,
                    help="Substring filter for AdaptiveTask.topic")
    ap.add_argument("--level", type=int, default=None,
                    help="Only validate tasks with this difficulty_level")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--reset", action="store_true",
                    help="Drop existing difficulty.jsonl and start over")
    args = ap.parse_args()

    if args.reset and os.path.exists(JSONL_PATH):
        os.remove(JSONL_PATH)
        print(f"Reset: removed {JSONL_PATH}")

    done = load_done_ids()
    print(f"Already validated: {len(done)}")

    tasks = fetch_tasks(args.grade, args.topic, args.level, args.limit, done)
    print(f"Tasks to validate now: {len(tasks)}")
    if not tasks:
        print("Nothing to do.")
        return

    client = DeepSeekClient()
    file_lock = threading.Lock()
    counters = {"match": 0, "off_by_one": 0, "too_easy": 0,
                "too_hard": 0, "error": 0}
    started = time.time()

    print(f"\n=== difficulty validation start: {_now()} ===")
    print(f"workers={args.workers}, target={len(tasks)}")
    print(f"model: deepseek-reasoner (CoT enabled)\n")

    with open(JSONL_PATH, "a", encoding="utf-8") as out_fp, \
            open(ERR_LOG, "a", encoding="utf-8") as err_fp:

        def worker(t):
            res = validate_one(t, client)
            with file_lock:
                # Persist successful verdicts only — error rows must be
                # retryable on resume, so we DON'T write them to the JSONL.
                if res["verdict"] != "error":
                    out_fp.write(json.dumps(res, ensure_ascii=False) + "\n")
                    out_fp.flush()
                counters[res["verdict"]] = counters.get(res["verdict"], 0) + 1
                if res["verdict"] in ("too_easy", "too_hard"):
                    err_fp.write(
                        f"[{_now()}] id={t['id']} cl={t['class_level']} "
                        f"labeled_L={t['difficulty_level']} "
                        f"predicted_L={res.get('predicted_level')} "
                        f"topic={t['topic']!r}\n"
                        f"  reason: {res.get('reason')}\n"
                        f"  text:   {(t.get('task_text') or '')[:200]}\n\n"
                    )
                    err_fp.flush()
                elif res["verdict"] == "error":
                    err_fp.write(
                        f"[{_now()}] id={t['id']} ERROR: {res.get('reason')}\n"
                    )
                    err_fp.flush()
            return res

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(worker, t) for t in tasks]
            done_count = 0
            for fut in as_completed(futures):
                done_count += 1
                if done_count % 20 == 0 or done_count == len(futures):
                    elapsed = time.time() - started
                    rate = done_count / max(elapsed, 1) * 60
                    remaining = (len(futures) - done_count) / max(rate / 60, 1e-3)
                    print(
                        f"  [{done_count}/{len(futures)}] "
                        f"match={counters['match']} "
                        f"off1={counters['off_by_one']} "
                        f"easy={counters['too_easy']} "
                        f"hard={counters['too_hard']} "
                        f"err={counters['error']} "
                        f"| {rate:.0f}/min, ETA ~{remaining/60:.1f} min"
                    )

    print(f"\n=== difficulty validation done: {_now()} ===")
    total_eval = sum(counters[k] for k in ("match", "off_by_one",
                                            "too_easy", "too_hard"))
    print(f"  match       = {counters['match']}")
    print(f"  off_by_one  = {counters['off_by_one']}")
    print(f"  too_easy    = {counters['too_easy']}  (labeled выше реального)")
    print(f"  too_hard    = {counters['too_hard']}  (labeled ниже реального)")
    print(f"  error       = {counters['error']}")
    if total_eval > 0:
        acc = (counters['match'] + counters['off_by_one']) / total_eval * 100
        print(f"  accuracy(±1) = {acc:.1f}%")
    print(f"\nResults saved to: {JSONL_PATH}")
    print(f"Mismatch log:     {ERR_LOG}")


if __name__ == "__main__":
    main()

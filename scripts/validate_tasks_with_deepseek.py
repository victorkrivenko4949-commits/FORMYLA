"""Validate every adaptive task via DeepSeek to catch mis-stated/unsolvable problems.

For each task we send the task statement + canonical answer + canonical solution
to DeepSeek and ask whether the *condition* is well-posed and admits a unique
unambiguous answer matching the canonical one.

Output: scripts/_validation/validation.jsonl  (one JSON object per task)
        {"id": int, "verdict": "ok"|"broken"|"unclear",
         "confidence": "high"|"medium"|"low",
         "reason": "...short explanation..."}

Resumable: re-running skips tasks already in the JSONL.

Usage:
    python scripts/validate_tasks_with_deepseek.py --workers 30
    python scripts/validate_tasks_with_deepseek.py --topic geometry --workers 20
    python scripts/validate_tasks_with_deepseek.py --grade 9 --limit 100
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

DB = os.path.join(ROOT, "instance", "formyla.db")
OUT_DIR = os.path.join(ROOT, "scripts", "_validation")
os.makedirs(OUT_DIR, exist_ok=True)
JSONL_PATH = os.path.join(OUT_DIR, "validation.jsonl")
ERR_LOG = os.path.join(OUT_DIR, "errors.log")


SYSTEM_PROMPT = (
    "Ты — главный редактор сборника олимпиадных задач для российской школы. "
    "Твоя задача — оценить, КОРРЕКТНО ЛИ СФОРМУЛИРОВАНА конкретная задача и "
    "ИМЕЕТ ЛИ ОНА СМЫСЛ. Тебе дают:\n"
    "  • условие задачи,\n"
    "  • эталонный ответ,\n"
    "  • эталонное решение.\n\n"
    "Ты должен внимательно прочитать ВСЁ и решить, является ли условие задачи "
    "ОДНОЗНАЧНЫМ, ПОЛНЫМ и СОВМЕСТИМЫМ с эталонным ответом и решением.\n\n"
    "ВЕРНИ ТОЛЬКО JSON, без markdown, без комментариев:\n"
    "{\n"
    '  "verdict": "ok" | "broken" | "unclear",\n'
    '  "confidence": "high" | "medium" | "low",\n'
    '  "reason": "1-2 коротких предложения по-русски, в чём именно проблема"\n'
    "}\n\n"
    "Критерии для verdict:\n"
    "• \"ok\" — условие чёткое, задача решаема, эталонное решение и ответ "
    "соответствуют условию, нет противоречий, нет недостающих данных.\n"
    "• \"broken\" — есть РЕАЛЬНАЯ ошибка, делающая задачу некорректной: "
    "противоречие в условии, недостающие/лишние данные, ссылка на несуществующий "
    "объект (например, окружность, проходящая через 3 коллинеарные точки; точка "
    "пересечения прямой со своей же прямой; деление на ноль; «найдите все X», но "
    "решения не существует и в эталоне это не оговорено и т.п.). ИЛИ эталонный "
    "ответ просто НЕ соответствует условию (другой объект, другая величина).\n"
    "• \"unclear\" — формулировка двусмысленная, но при разумной интерпретации "
    "задача решаема и эталон логически согласован.\n\n"
    "ОЧЕНЬ ВАЖНО:\n"
    "• Не ставь \"broken\" из-за стилистики, отсутствия запятой, или того, что "
    "ты сам решил бы по-другому — только если есть ОБЪЕКТИВНАЯ ошибка.\n"
    "• Олимпиадные задачи вида «Можно ли …? Докажите.» / «Существует ли …?» — "
    "это нормально. Ответ \"нельзя\" или \"не существует\" — корректен, "
    "если эталонное решение приводит обоснование. Это НЕ broken.\n"
    "• Задачи на доказательство, у которых correct_answer = «доказательство», "
    "тоже нормальны — оценивай согласованность условия и хода доказательства.\n"
    "• Если условие имеет более одного валидного ответа, а эталон даёт лишь один "
    "без оговорки — это broken (high confidence).\n"
    "• Геометрические задачи: проверь, существует ли описанная конструкция. "
    "Например: «окружность через C, D пересекает сторону CD в точке Q ≠ D» — "
    "broken (окружность и прямая пересекаются максимум в 2 точках; если C, D "
    "уже на ней, третьей нет).\n"
    "• Если ты НЕ УВЕРЕН — ставь \"unclear\" с confidence \"medium\". "
    "Высокий confidence ставь только когда ошибка очевидна.\n\n"
    "СТРОГО ОТВЕТ — ОДИН JSON, без преамбул и пояснений вне поля reason."
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


def fetch_tasks(grade: int | None, topic: str | None, limit: int | None,
                done_ids: set[int]) -> list[dict]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    sql = "SELECT id, class_level, difficulty_level, topic, task_text, " \
          "correct_answer, solution FROM adaptive_tasks WHERE 1=1"
    params: list = []
    if grade is not None:
        sql += " AND class_level = ?"
        params.append(grade)
    if topic:
        sql += " AND topic LIKE ?"
        params.append(f"%{topic}%")
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
        f"УСЛОВИЕ:\n{task['task_text']}\n\n"
        f"ЭТАЛОННЫЙ ОТВЕТ:\n{task.get('correct_answer') or '(не задан)'}\n\n"
        f"ЭТАЛОННОЕ РЕШЕНИЕ:\n{task.get('solution') or '(пусто)'}\n\n"
        "Верни строго один JSON-объект."
    )


JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_verdict(raw: str) -> dict | None:
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


def normalize_verdict(obj: dict | None) -> dict | None:
    if not isinstance(obj, dict):
        return None
    v = str(obj.get("verdict", "")).strip().lower()
    if v not in ("ok", "broken", "unclear"):
        return None
    c = str(obj.get("confidence", "")).strip().lower()
    if c not in ("high", "medium", "low"):
        c = "medium"
    reason = str(obj.get("reason", "")).strip()[:500]
    return {"verdict": v, "confidence": c, "reason": reason}


def validate_one(task: dict, client: DeepSeekClient) -> dict:
    prompt = build_prompt(task)
    try:
        raw = client.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=350,
        )
    except DeepSeekAPIError as e:
        return {"id": task["id"], "verdict": "error", "confidence": "low",
                "reason": f"api_error: {e}"}
    except Exception as e:
        return {"id": task["id"], "verdict": "error", "confidence": "low",
                "reason": f"exc: {e}"}

    verdict = normalize_verdict(parse_verdict(raw))
    if not verdict:
        return {"id": task["id"], "verdict": "error", "confidence": "low",
                "reason": "parse_failed", "raw": raw[:400]}
    verdict["id"] = task["id"]
    return verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=30)
    ap.add_argument("--grade", type=int, default=None)
    ap.add_argument("--topic", default=None,
                    help="Substring filter for AdaptiveTask.topic")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--reset", action="store_true",
                    help="Drop existing validation.jsonl and start over")
    args = ap.parse_args()

    if args.reset and os.path.exists(JSONL_PATH):
        os.remove(JSONL_PATH)
        print(f"Reset: removed {JSONL_PATH}")

    done = load_done_ids()
    print(f"Already validated: {len(done)}")

    tasks = fetch_tasks(args.grade, args.topic, args.limit, done)
    print(f"Tasks to validate now: {len(tasks)}")
    if not tasks:
        print("Nothing to do.")
        return

    client = DeepSeekClient()
    file_lock = threading.Lock()
    counters = {"ok": 0, "broken": 0, "unclear": 0, "error": 0}
    started = time.time()

    print(f"\n=== validation start: {_now()} ===")
    print(f"workers={args.workers}, target={len(tasks)}\n")

    with open(JSONL_PATH, "a", encoding="utf-8") as out_fp, \
            open(ERR_LOG, "a", encoding="utf-8") as err_fp:

        def worker(t):
            res = validate_one(t, client)
            with file_lock:
                out_fp.write(json.dumps(res, ensure_ascii=False) + "\n")
                out_fp.flush()
                counters[res["verdict"]] = counters.get(res["verdict"], 0) + 1
                if res["verdict"] == "broken":
                    err_fp.write(
                        f"[{_now()}] id={t['id']} cl={t['class_level']} "
                        f"L={t['difficulty_level']} topic={t['topic']!r}\n"
                        f"  reason: {res.get('reason')}\n"
                        f"  text: {(t.get('task_text') or '')[:200]}\n\n"
                    )
                    err_fp.flush()
            return res

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(worker, t) for t in tasks]
            done_count = 0
            for fut in as_completed(futures):
                done_count += 1
                if done_count % 50 == 0 or done_count == len(futures):
                    elapsed = time.time() - started
                    rate = done_count / max(elapsed, 1) * 60
                    remaining = (len(futures) - done_count) / max(rate / 60, 1e-3)
                    print(
                        f"  [{done_count}/{len(futures)}] "
                        f"ok={counters['ok']} broken={counters['broken']} "
                        f"unclear={counters['unclear']} error={counters['error']} "
                        f"| {rate:.0f}/min, ETA ~{remaining/60:.1f} min"
                    )

    print(f"\n=== validation done: {_now()} ===")
    print(f"  ok      = {counters['ok']}")
    print(f"  broken  = {counters['broken']}")
    print(f"  unclear = {counters['unclear']}")
    print(f"  error   = {counters['error']}")
    print(f"\nResults saved to: {JSONL_PATH}")
    print(f"Broken-task log:  {ERR_LOG}")


if __name__ == "__main__":
    main()

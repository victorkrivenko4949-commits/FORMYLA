"""Send each broken task to DeepSeek with the validator's complaint and ask
it to produce a CORRECTED version. Output -> _validation/fixed_tasks.jsonl.

Usage:
    python scripts/fix_broken_tasks_with_deepseek.py
    python scripts/fix_broken_tasks_with_deepseek.py --workers 30 --limit 100
    python scripts/fix_broken_tasks_with_deepseek.py --backup adaptive_data/_backups/deleted_validator_*.json

Then validate the candidates and insert good ones into DB:
    python scripts/insert_fixed_tasks.py
"""
import argparse, datetime as _dt, glob, json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError  # noqa: E402

DB = os.path.join(ROOT, "instance", "formyla.db")
BACKUP_DIR = os.path.join(ROOT, "adaptive_data", "_backups")
OUT_DIR = os.path.join(ROOT, "scripts", "_validation")
os.makedirs(OUT_DIR, exist_ok=True)
FIXED_PATH = os.path.join(OUT_DIR, "fixed_tasks.jsonl")
ERR_LOG = os.path.join(OUT_DIR, "fix_errors.log")


SYSTEM_PROMPT = """Ты — опытный методист по олимпиадной математике для российской школы.
Тебе дают БРАКОВАННУЮ задачу из адаптивного теста: её условие, эталонный ответ, эталонное решение, и подробное объяснение редактора, в чём именно состоит ошибка.

Твоя задача — написать ИСПРАВЛЕННУЮ версию этой задачи, в которой:
  • Сохраняется ТЕМА, ОБЩАЯ ИДЕЯ и УРОВЕНЬ СЛОЖНОСТИ исходной задачи.
  • Условие становится МАТЕМАТИЧЕСКИ КОРРЕКТНЫМ, ОДНОЗНАЧНЫМ и ПОЛНЫМ (нет противоречий, нет недостающих данных, ссылки только на существующие объекты, ответ конкретный и однозначный).
  • Эталонный ответ — однозначный (число / выражение / 'нельзя' / 'доказательство' для задач-доказательств).
  • Эталонное решение — полное, последовательное, без логических дыр, с правильными вычислениями.

ВЫДАЁШЬ строго ОДИН JSON-объект (без markdown, без преамбул):
{
  "task_text": "...",
  "correct_answer": "...",
  "solution": "...",
  "criteria_1_point": "...",
  "criteria_2_points": "..."
}

ТРЕБОВАНИЯ:
• Все формулы — в LaTeX через \\(...\\) или \\[...\\]. Бэкслеши одиночные: \\frac, \\angle, \\triangle, \\cdot, \\sqrt.
• Без markdown-блоков ```json. Без преамбул и пояснений вне JSON.
• criteria_1_point — за что ставится 1 балл (частичное решение).
• criteria_2_points — за что ставится 2 балла (полное решение).
• Если тема «Логика. Рыцари и лжецы» — ЕДИНСТВЕННОЕ непротиворечивое распределение ролей.
• Если задача геометрическая — описанная конструкция геометрически существует и однозначна.
• Если в исходной задаче было «докажите», сохрани её как задачу на доказательство (correct_answer = 'доказательство').
• Запрещено: 'сколько решений имеет задача', 'найдите все X такие что …, если они существуют'.
"""


def now_iso():
    return _dt.datetime.now().isoformat(sep=" ", timespec="seconds")


def gather_backups(explicit):
    if explicit:
        return [explicit]
    return sorted(glob.glob(os.path.join(BACKUP_DIR, "deleted_validator_*.json")))


def load_broken_tasks(paths):
    out, seen = [], set()
    for path in paths:
        with open(path, "r", encoding="utf-8") as fp:
            rows = json.load(fp)
        for r in rows:
            tid = r.get("id")
            if tid is None or tid in seen:
                continue
            seen.add(tid)
            info = r.get("_validator") or {}
            out.append({
                "id": tid,
                "class_level": r["class_level"],
                "difficulty_level": r["difficulty_level"],
                "topic": r.get("topic"),
                "subtopic": r.get("subtopic"),
                "task_text": r.get("task_text") or "",
                "correct_answer": r.get("correct_answer") or "",
                "solution": r.get("solution") or "",
                "criteria_1_point": r.get("criteria_1_point") or "",
                "criteria_2_points": r.get("criteria_2_points") or "",
                "validator_reason": info.get("reason") or "(no reason)",
                "validator_confidence": info.get("confidence") or "?",
            })
    return out


def load_done_ids():
    done = set()
    if not os.path.exists(FIXED_PATH):
        return done
    with open(FIXED_PATH, "r", encoding="utf-8") as fp:
        for line in fp:
            try:
                obj = json.loads(line)
                src = obj.get("source_id")
                if isinstance(src, int):
                    done.add(src)
            except Exception:
                continue
    return done


def build_user_prompt(task):
    return (
        f"КЛАСС: {task['class_level']}\n"
        f"УРОВЕНЬ СЛОЖНОСТИ: {task['difficulty_level']}/7\n"
        f"ТЕМА: {task['topic']}\n\n"
        f"ИСХОДНОЕ (БРАКОВАННОЕ) УСЛОВИЕ:\n{task['task_text']}\n\n"
        f"ИСХОДНЫЙ ОТВЕТ: {task['correct_answer']}\n\n"
        f"ИСХОДНОЕ РЕШЕНИЕ:\n{task['solution']}\n\n"
        f"ОБЪЯСНЕНИЕ РЕДАКТОРА (в чём именно ошибка):\n{task['validator_reason']}\n\n"
        "Перепиши задачу, чтобы устранить ошибку, сохранив тему, идею и уровень сложности. "
        "Верни строго один JSON-объект."
    )


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_VALID_KEYS = {"task_text", "correct_answer", "solution",
               "criteria_1_point", "criteria_2_points"}


def parse_json(raw):
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    m = _JSON_RE.search(s)
    if not m:
        return None
    candidate = m.group(0)
    try:
        return json.loads(candidate)
    except Exception:
        # Escape lone backslashes inside JSON strings
        try:
            fixed = re.sub(
                r'"((?:[^"\\]|\\.)*)"',
                lambda mm: '"' + re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\',
                                        mm.group(1)) + '"',
                candidate, flags=re.DOTALL)
            return json.loads(fixed)
        except Exception:
            return None


def normalize_fixed(obj):
    if not isinstance(obj, dict):
        return None
    out = {}
    for k in _VALID_KEYS:
        v = obj.get(k)
        if v is None:
            return None
        if not isinstance(v, str):
            v = str(v)
        out[k] = v.strip()
    if not out["task_text"] or not out["solution"]:
        return None
    return out


def fix_one(task, client):
    prompt = build_user_prompt(task)
    try:
        raw = client.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT,
                              temperature=0.4, max_tokens=2000)
    except DeepSeekAPIError as e:
        return {"source_id": task["id"], "status": "api_error", "reason": str(e)}
    except Exception as e:
        return {"source_id": task["id"], "status": "exc", "reason": str(e)}

    parsed = parse_json(raw)
    fixed = normalize_fixed(parsed)
    if not fixed:
        return {"source_id": task["id"], "status": "parse_failed",
                "raw": (raw or "")[:600]}
    return {
        "source_id": task["id"],
        "status": "candidate",
        "class_level": task["class_level"],
        "difficulty_level": task["difficulty_level"],
        "topic": task["topic"],
        "subtopic": task.get("subtopic"),
        **fixed,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--backup", default=None,
                    help="Path to a single deleted_validator_*.json file. "
                         "Default: aggregate ALL backups in adaptive_data/_backups.")
    ap.add_argument("--reset", action="store_true",
                    help="Drop existing fixed_tasks.jsonl and start over")
    args = ap.parse_args()

    if args.reset and os.path.exists(FIXED_PATH):
        os.remove(FIXED_PATH)
        print(f"Reset: removed {FIXED_PATH}")

    backups = gather_backups(args.backup)
    print(f"Backups to read: {len(backups)}")
    for b in backups:
        print(f"  {b}")
    if not backups:
        print("No backups found.")
        return

    tasks = load_broken_tasks(backups)
    print(f"Total broken tasks (deduplicated): {len(tasks)}")

    done = load_done_ids()
    print(f"Already attempted: {len(done)}")
    tasks = [t for t in tasks if t["id"] not in done]
    if args.limit:
        tasks = tasks[:args.limit]
    print(f"Tasks to fix now: {len(tasks)}")
    if not tasks:
        print("Nothing to do.")
        return

    client = DeepSeekClient()
    file_lock = threading.Lock()
    counters = {"candidate": 0, "parse_failed": 0, "api_error": 0, "exc": 0}
    started = time.time()

    print(f"\n=== fix start: {now_iso()} ===")
    print(f"workers={args.workers}, target={len(tasks)}\n")

    with open(FIXED_PATH, "a", encoding="utf-8") as out_fp, \
            open(ERR_LOG, "a", encoding="utf-8") as err_fp:

        def worker(t):
            res = fix_one(t, client)
            with file_lock:
                out_fp.write(json.dumps(res, ensure_ascii=False) + "\n")
                out_fp.flush()
                counters[res["status"]] = counters.get(res["status"], 0) + 1
                if res["status"] != "candidate":
                    err_fp.write(
                        f"[{now_iso()}] src_id={t['id']} {res['status']} :: "
                        f"{res.get('reason', '')[:200]}\n"
                    )
                    err_fp.flush()
            return res

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(worker, t) for t in tasks]
            done_count = 0
            for fut in as_completed(futures):
                done_count += 1
                if done_count % 25 == 0 or done_count == len(futures):
                    elapsed = time.time() - started
                    rate = done_count / max(elapsed, 1) * 60
                    remaining = (len(futures) - done_count) / max(rate / 60, 1e-3)
                    print(
                        f"  [{done_count}/{len(futures)}] "
                        f"candidates={counters['candidate']} "
                        f"parse_fail={counters['parse_failed']} "
                        f"api_err={counters['api_error']} exc={counters['exc']} "
                        f"| {rate:.0f}/min, ETA ~{remaining/60:.1f} min"
                    )

    print(f"\n=== fix done: {now_iso()} ===")
    print(f"  candidates  = {counters['candidate']}")
    print(f"  parse_fail  = {counters['parse_failed']}")
    print(f"  api_error   = {counters['api_error']}")
    print(f"  exc         = {counters['exc']}")
    print(f"\nResults saved to: {FIXED_PATH}")


if __name__ == "__main__":
    main()

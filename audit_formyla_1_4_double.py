# -*- coding: utf-8 -*-
"""
audit_formyla_1_4_double.py — Двойной аудит задачи «all_formyla_1_4_final_CORRECTED_v2 (3).jsonl».

Методика «задача-2» (двойной аудит двумя разными экспертами + проверка КОРРЕКТНОСТИ УСЛОВИЯ).

DeepSeek-v4-pro проверяет для каждой задачи ТРИ вещи по отдельности:
  1. УСЛОВИЕ (task_text)   — корректно ли оно (однозначно, выполнимо, без противоречий,
                             без пропущенных данных/обозначений, без технических ошибок);
  2. ОТВЕТ (correct_answer) — верен ли он;
  3. РЕШЕНИЕ (solution)      — математически строго, полно, ведёт ли к заявленному ответу.

Каждая задача прогоняется ДВАЖДЫ разными экспертами (SYSTEM_A и SYSTEM_B), затем вердикты
сравниваются и задача раскладывается в один из ТРЁХ файлов:

  * оба «incorrect»            -> FORMYLA_1_4_AUDIT_BOTH_INCORRECT.jsonl
  * оба «correct»              -> FORMYLA_1_4_AUDIT_BOTH_CORRECT.jsonl
  * один «correct», другой нет -> FORMYLA_1_4_AUDIT_DISPUTED.jsonl
  * УСЛОВИЕ некорректно        -> FORMYLA_1_4_AUDIT_DISPUTED.jsonl   (тоже 3-й файл)

Плюс вспомогательный файл ошибок API: FORMYLA_1_4_AUDIT_ERROR.jsonl

Запуск:
    python audit_formyla_1_4_double.py --limit 10 --smoke    # пробный прогон
    python audit_formyla_1_4_double.py                       # полный прогон
    python audit_formyla_1_4_double.py --resume              # продолжить
"""

import argparse
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SRC_PATH = r"C:\Users\Redmi\Downloads\all_formyla_1_4_final_CORRECTED_v2 (3).jsonl"
OUT_INCORRECT = "FORMYLA_1_4_AUDIT_BOTH_INCORRECT.jsonl"
OUT_CORRECT = "FORMYLA_1_4_AUDIT_BOTH_CORRECT.jsonl"
OUT_DISPUTED = "FORMYLA_1_4_AUDIT_DISPUTED.jsonl"
OUT_ERROR = "FORMYLA_1_4_AUDIT_ERROR.jsonl"
CHECKPOINT = "audit_formyla_1_4_double_checkpoint.json"

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
WORKERS = 10
TIMEOUT = (15, 600)
MAX_RETRIES = 6
TEMPERATURE = 0.0
MAX_TOKENS = 24000

# Общая Session с HTTP-ретраями и большим пулом соединений — устраняет
# «HTTPSConnectionPool Max retries exceeded» при параллельной работе.
_SESSION = None


def get_session():
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        retry = Retry(
            total=6,
            connect=6,
            read=6,
            status=6,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["POST"]),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=WORKERS * 2,
                              pool_maxsize=WORKERS * 2)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _SESSION = s
    return _SESSION

SYSTEM_A = (
    "Ты — член жюри Всероссийской олимпиады школьников по математике высшего уровня, "
    "специалист по строгим доказательствам. Проведи бескомпромиссную проверку задачи.\n\n"
    "Проверяй ПО ОТДЕЛЬНОСТИ три компонента:\n"
    "1. УСЛОВИЕ — корректно ли оно: однозначно ли понимается, существует ли решение, "
    "нет ли логического противоречия, технической ошибки в числах/знаках/диапазонах, "
    "не пропущены ли необходимые данные или обозначения, не ссылается ли на отсутствующий "
    "рисунок.\n"
    "2. ОТВЕТ — верен ли (включая вырожденные случаи, множественные решения, ОДЗ)?\n"
    "3. РЕШЕНИЕ — математически полно и строго? Доказаны ли ВСЕ утверждения, разобраны ли "
    "ВСЕ случаи, нет ли логических дыр и арифметических ошибок, ведёт ли решение именно к "
    "заявленному ответу?\n\n"
    "Любая недоказанная оценка, пропущенный случай или неточность = ошибка.\n\n"
    "Отвечай ТОЛЬКО одним JSON-объектом (без markdown, без текста вне JSON):\n"
    "{\n"
    "  \"condition_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"answer_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"solution_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"overall_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"errors\": [\"краткое описание ошибки\"],\n"
    "  \"justification\": \"1-2 предложения\"\n"
    "}"
)

SYSTEM_B = (
    "Ты — эксперт-составитель и рецензент олимпиадных задач по математике, проверяющий "
    "чужую задачу перед публикацией в сборнике.\n\n"
    "Требования:\n"
    "- УСЛОВИЕ корректно: однозначно, выполнимо, без противоречий, без технических ошибок, "
    "без ссылок на отсутствующие объекты/рисунки;\n"
    "- ОТВЕТ единственный и корректный (или корректно описано множество ответов), "
    "согласован с условием и решением;\n"
    "- РЕШЕНИЕ безупречно: каждая оценка доказана, все случаи разобраны, нет запрещённых "
    "ссылок на чертёж/интуицию, нет пропущенных граничных ситуаций, нет ошибок в выкладках.\n\n"
    "Вердикт «correct» в каждом поле — только если соответствующий компонент полностью "
    "корректен. Любая неточность, недоказанный шаг, пропущенный случай, неверный ответ или "
    "некорректное условие = «incorrect» в соответствующем поле.\n\n"
    "Отвечай ТОЛЬКО одним JSON-объектом (без markdown, без пояснений вне JSON):\n"
    "{\n"
    "  \"condition_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"answer_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"solution_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"overall_verdict\": \"correct\" | \"incorrect\",\n"
    "  \"errors\": [\"...\"],\n"
    "  \"justification\": \"...\"\n"
    "}"
)


def load_env():
    global API_KEY
    if API_KEY:
        return
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return


LOG_FILE = "audit_formyla_1_4_double.log"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def build_user_prompt(task) -> str:
    return (
        f"Задача (класс {task.get('grade')}, уровень {task.get('level')}, "
        f"тема «{task.get('topic')}»):\n\n"
        f"УСЛОВИЕ:\n{task.get('task_text', '')}\n\n"
        f"Эталонный ОТВЕТ:\n{task.get('correct_answer', '')}\n\n"
        f"РЕШЕНИЕ, которое нужно проверить:\n{task.get('solution', '')}"
    )


def extract_json(text: str) -> dict:
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return {}
    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        depth = 0
        s = 0
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    s = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[s:i + 1])
                    except json.JSONDecodeError:
                        return {}
        return {}


def call_deepseek(system_prompt, user_prompt):
    session = get_session()
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                },
                timeout=TIMEOUT,
            )
            if resp.status_code == 429:
                time.sleep(min(2 ** attempt, 60))
                last_err = RuntimeError("429")
                continue
            if resp.status_code >= 500:
                time.sleep(min(2 ** attempt, 30))
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                continue
            resp.raise_for_status()
            body = resp.json()
            choices = body.get("choices") or []
            if not choices:
                last_err = RuntimeError("empty choices")
                continue
            msg = choices[0].get("message", {}) or {}
            content = msg.get("content") or msg.get("reasoning_content") or ""
            verdict = extract_json(content)
            if not verdict:
                last_err = RuntimeError("невалидный JSON")
                log(f"    попытка {attempt}: невалидный JSON, повтор…")
                continue
            return verdict
        except requests.RequestException as e:
            last_err = e
            time.sleep(min(2 ** attempt, 30))
    return {"overall_verdict": "error", "_error": str(last_err)}


def normalize_verdict(v):
    v = (v or "").strip().lower()
    if v in ("correct", "true", "pass", "ok", "верно", "правильно", "да", "yes"):
        return "correct"
    if v in ("incorrect", "false", "fail", "неверно", "неправильно", "нет", "no"):
        return "incorrect"
    if v == "error":
        return "error"
    return "unknown"


def audit_one_task(task):
    user_prompt = build_user_prompt(task)
    a = call_deepseek(SYSTEM_A, user_prompt)
    time.sleep(0.1)
    b = call_deepseek(SYSTEM_B, user_prompt)
    return {"task": task, "audit_a": a, "audit_b": b}


def load_tasks(limit=None):
    tasks = []
    with open(SRC_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if limit and len(tasks) >= limit:
                break
    return tasks


def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        try:
            with open(CHECKPOINT, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"done_idx": [], "stats": {}}


def save_checkpoint(cp):
    tmp = CHECKPOINT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False)
    os.replace(tmp, CHECKPOINT)


def append_row(path, row):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


ALL_OUTPUTS = (OUT_INCORRECT, OUT_CORRECT, OUT_DISPUTED, OUT_ERROR)


def collect_done_from_outputs():
    """Собрать уже обработанные _idx из файлов ИСХОДА (кроме ERROR).

    ERROR-строки не считаются «готовыми» — они будут переаудированы при --resume.
    Возвращает (done, error_idx).
    """
    done = set()
    error_idx = set()
    for path in ALL_OUTPUTS:
        if not os.path.exists(path):
            continue
        is_error = (path == OUT_ERROR)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    i = rec.get("_idx")
                    if i is None:
                        continue
                    i = int(i)
                    if is_error:
                        error_idx.add(i)
                    else:
                        done.add(i)
                except json.JSONDecodeError:
                    continue
    return done, error_idx


def rebuild_stats_from_outputs():
    """Пересчитать статистику категорий из выходных файлов (без ERROR)."""
    stats = Counter()
    cat_of = {
        OUT_INCORRECT: "incorrect",
        OUT_CORRECT: "correct",
        OUT_DISPUTED: "disputed",
    }
    for path in (OUT_INCORRECT, OUT_CORRECT, OUT_DISPUTED):
        if not os.path.exists(path):
            continue
        n = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        stats[cat_of[path]] += n
    return stats


def _rewrite_without_errors(error_idx):
    """Удалить строки с указанными _idx из OUT_ERROR (переаудирование)."""
    if not os.path.exists(OUT_ERROR):
        return
    kept = []
    with open(OUT_ERROR, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("_idx") in error_idx:
                continue
            kept.append(rec)
    with open(OUT_ERROR, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args()

    load_env()
    if not API_KEY:
        log("ОШИБКА: DEEPSEEK_API_KEY не задан")
        sys.exit(1)
    log(f"Модель: {MODEL} | потоков: {args.workers}")

    tasks = load_tasks(args.limit)
    log(f"Задач к аудиту: {len(tasks)}")

    # Восстановление прогресса: приоритет — выходные файлы (авторитетный источник).
    # ERROR-строки (сбои API) переаудируются заново при --resume.
    done_idx, error_idx = collect_done_from_outputs()
    stats = rebuild_stats_from_outputs()

    if args.resume and os.path.exists(CHECKPOINT):
        cp = load_checkpoint()
    else:
        cp = {"done_idx": [], "stats": {}}

    if error_idx:
        # удалить ERROR-строки из файла, чтобы переаудировать их заново
        _rewrite_without_errors(error_idx)
        log(f"Найдено {len(error_idx)} задач со сбоем API — переаудирую заново.")

    log(f"Уже обработано (валидные результаты): {len(done_idx)}")

    pending = [i for i in range(len(tasks)) if i not in done_idx]
    log(f"Осталось: {len(pending)}")

    if args.smoke:
        pending = pending[: args.limit or 10]
        log(f"SMOKE: {len(pending)} задач")

    lock = threading.Lock()

    def process(idx):
        task = tasks[idx]
        try:
            res = audit_one_task(task)
        except Exception as e:
            res = {
                "audit_a": {"overall_verdict": "error", "_error": str(e)},
                "audit_b": {"overall_verdict": "error", "_error": str(e)},
            }
        res["_idx"] = idx
        res["task"] = task
        return idx, res

    def verdict_of(a):
        return normalize_verdict(a.get("overall_verdict"))

    def cond_of(a):
        return normalize_verdict(a.get("condition_verdict"))

    def classify(result):
        """Возвращает (category, reason)."""
        a = result["audit_a"]
        b = result["audit_b"]
        va = verdict_of(a)
        vb = verdict_of(b)
        if va in ("error", "unknown") or vb in ("error", "unknown"):
            return "error", "api_failure"
        ca = cond_of(a)
        cb = cond_of(b)
        if ca == "incorrect" or cb == "incorrect":
            return "disputed", "condition_incorrect"
        if va == "incorrect" and vb == "incorrect":
            return "incorrect", "both_incorrect"
        if va == "correct" and vb == "correct":
            return "correct", "both_correct"
        return "disputed", "verdict_disputed"

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process, i): i for i in pending}
        for fut in as_completed(futures):
            idx, result = fut.result()
            category, reason = classify(result)
            result["_reason"] = reason

            with lock:
                done_idx.add(idx)
                stats[category] += 1
                if category == "incorrect":
                    append_row(OUT_INCORRECT, result)
                elif category == "correct":
                    append_row(OUT_CORRECT, result)
                elif category == "disputed":
                    append_row(OUT_DISPUTED, result)
                else:
                    append_row(OUT_ERROR, result)

                if len(done_idx) % 25 == 0:
                    cp["done_idx"] = sorted(done_idx)
                    cp["stats"] = dict(stats)
                    if not args.smoke:
                        save_checkpoint(cp)
                    log(
                        f"прогресс {len(done_idx)}/{len(tasks)} | "
                        f"incorrect={stats.get('incorrect', 0)} "
                        f"correct={stats.get('correct', 0)} "
                        f"disputed={stats.get('disputed', 0)} "
                        f"error={stats.get('error', 0)}"
                    )

    cp["done_idx"] = sorted(done_idx)
    cp["stats"] = dict(stats)
    if not args.smoke:
        save_checkpoint(cp)

    log("=" * 60)
    log(f"ГОТОВО. Задач: {len(tasks)}")
    log(f"  ОБА НЕВЕРНО   (incorrect): {stats.get('incorrect', 0)}  -> {OUT_INCORRECT}")
    log(f"  ОБА ВЕРНО     (correct):   {stats.get('correct', 0)}  -> {OUT_CORRECT}")
    log(f"  СПОРНО/УСЛОВИЕ (disputed): {stats.get('disputed', 0)}  -> {OUT_DISPUTED}")
    log(f"  ОШИБКА API    (error):     {stats.get('error', 0)}  -> {OUT_ERROR}")


if __name__ == "__main__":
    main()

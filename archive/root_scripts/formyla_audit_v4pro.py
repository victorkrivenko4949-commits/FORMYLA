#!/usr/bin/env python3
"""
FORMYLA: аудит условий задач через DeepSeek V4 Pro.

Запуск:
    python formyla_audit_v4pro.py

Вход  : INPUT_FILE  - jsonl базы (по одной задаче на строку)
Выход : audit_output.jsonl - вердикты
        audit_raw.log      - сырые ответы API
"""

import os
import json
import time
import sys
import requests

# ================= НАСТРОЙКИ =================

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

API_URL = "https://api.deepseek.com/chat/completions"
MODEL_NAME = "deepseek-v4-pro"

INPUT_FILE = r"C:\Users\Redmi\Desktop\Новая папка (2)\FORMYLA_L1_L3_FINAL_v3.jsonl"

OUTPUT_FILE = "audit_output.jsonl"
RAW_LOG = "audit_raw.log"

TASKS_PER_BATCH = 3
MAX_TOKENS = 32000
TIMEOUT = 900
MAX_RETRIES = 3
LIMIT = 0          # 0 = все задачи; поставь 15 для пробного прогона
RESUME = True      # пропускать уже проверенные task_uid

# ================= ПРОМТ =================

SYSTEM_PROMPT = """Ты — математический эксперт и аудитор олимпиадных задач.

ЦЕЛЬ: найти задачи с НЕКОРРЕКТНЫМ УСЛОВИЕМ и отделить их от задач,
где условие корректно, но ошибочны ответ или решение.

УСЛОВИЕ НЕКОРРЕКТНО, если выполнено хотя бы одно:
- задача невыполнима: нет решения при естественной школьной интерпретации;
- задача неоднозначна: несколько разных прочтений дают разные ответы;
- в условии логическое противоречие;
- техническая ошибка в данных (числа, знак, коэффициент, диапазон, пропущен параметр);
- используются неопределённые объекты (нет обозначений, ссылка на отсутствующий рисунок).

ЖЁСТКИЕ ПРАВИЛА:
1. НЕ МЕНЯЙ СЛОЖНОСТЬ ЗАДАЧИ. Класс, уровень, тема и тип остаются прежними.
2. Правка МИНИМАЛЬНАЯ: число, знак, слово. Не переписывай задачу заново.
3. Если условие корректно, а неверны ответ или решение — условие НЕ ТРОГАЙ.
4. Решай каждую задачу ЗАНОВО сам. Не доверяй полям answer, solution и меткам критика.
5. Задачи не смешивай, обрабатывай каждую отдельно.
6. Ответ — только json, без текста вокруг.

ФОРМАТ: объект с ключом "results", значение — массив записей:
{"results": [
  {
    "task_uid": "...",
    "grade": 5,
    "level": 1,
    "section": "...",
    "condition_correct": "YES|NO|BORDERLINE",
    "answer_correct": "YES|NO|UNKNOWN",
    "solution_correct": "YES|NO|UNKNOWN",
    "defects": ["перечень найденных дефектов"],
    "reason_condition": "1-2 предложения",
    "proposed_fix": "минимальная правка условия или NONE",
    "re_solved_answer": "твой проверенный ответ или UNSOLVABLE"
  }
]}
"""

# ================= КОД =================


def uid_of(t):
    return t.get("task_uid") or t.get("taskuid") or t.get("uid")


def load_tasks(path):
    if not os.path.exists(path):
        sys.exit(f"НЕ НАЙДЕН ФАЙЛ:\n  {path}\nПоправь INPUT_FILE вверху скрипта.")
    tasks, bad = [], 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    if bad:
        print(f"[warn] строк не в формате JSON: {bad}")
    return tasks


def load_done(path):
    done = set()
    if not (RESUME and os.path.exists(path)):
        return done
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                u = rec.get("task_uid") or rec.get("taskuid")
                if u and not rec.get("error"):
                    done.add(u)
            except json.JSONDecodeError:
                pass
    return done


def chunked(lst, n):
    return [lst[i:i + n] for i in range(0, len(lst), n)]


def slim(t):
    keep = ("task_uid", "taskuid", "grade", "level", "section",
            "theme", "theme_id", "statement", "answer", "solution")
    return {k: v for k, v in t.items() if k in keep}


def log_raw(text):
    with open(RAW_LOG, "a", encoding="utf-8") as f:
        f.write(text + "\n" + "-" * 70 + "\n")


def call_api(messages, key, verbose=False):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
            if r.status_code >= 400:
                log_raw(f"HTTP {r.status_code}\n{r.text[:2000]}")
                if verbose:
                    print(f"  HTTP {r.status_code}: {r.text[:500]}")
                r.raise_for_status()
            data = r.json()
            ch = data["choices"][0]
            msg = ch["message"]
            content = (msg.get("content") or "").strip() or \
                      (msg.get("reasoning_content") or "").strip()
            log_raw(f"finish={ch.get('finish_reason')} usage={data.get('usage')}\n{content[:2000]}")
            if verbose:
                print(f"  finish_reason={ch.get('finish_reason')} usage={data.get('usage')}")
            if not content:
                raise ValueError(f"пустой ответ, finish_reason={ch.get('finish_reason')}")
            return content
        except Exception as e:
            err = e
            print(f"  [retry {attempt}/{MAX_RETRIES}] {e}", file=sys.stderr)
            time.sleep(3 * attempt)
    raise RuntimeError(str(err))


def parse(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        p = raw.split("```")
        raw = p[1] if len(p) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        s, e = raw.find("["), raw.rfind("]")
        if s == -1 or e == -1:
            raise
        obj = json.loads(raw[s:e + 1])
    if isinstance(obj, list):
        return obj
    for k in ("results", "tasks", "audit", "data", "items"):
        if isinstance(obj.get(k), list):
            return obj[k]
    return [obj]


def audit(items, key, verbose=False):
    body = json.dumps([slim(t) for t in items], ensure_ascii=False)
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content":
            "Задачи в формате json. Проверь каждую и верни json с ключом results.\n\n" + body},
    ]
    return parse(call_api(msgs, key, verbose))


def main():
    key = os.getenv("DEEPSEEK_API_KEY") or DEEPSEEK_API_KEY

    all_tasks = load_tasks(INPUT_FILE)
    done = load_done(OUTPUT_FILE)
    tasks = [t for t in all_tasks if uid_of(t) not in done]
    if LIMIT:
        tasks = tasks[:LIMIT]

    print("=" * 62)
    print(f"Модель  : {MODEL_NAME}")
    print(f"База    : {INPUT_FILE}")
    print(f"Размер  : {os.path.getsize(INPUT_FILE) / 1024 / 1024:.1f} МБ")
    print(f"Всего   : {len(all_tasks)} задач")
    if done:
        print(f"Готово  : {len(done)} (пропускаю)")
    print(f"К работе: {len(tasks)}")
    if all_tasks:
        print(f"Ключи   : {', '.join(list(all_tasks[0].keys())[:8])} ...")
    print("=" * 62)

    if not tasks:
        print("Нечего обрабатывать.")
        return

    batches = chunked(tasks, TASKS_PER_BATCH)
    bad_cond = bad_ans = written = failed = 0
    mode = "a" if done else "w"

    with open(OUTPUT_FILE, mode, encoding="utf-8") as out:
        for i, batch in enumerate(batches, 1):
            print(f"[{i}/{len(batches)}] {len(batch)} задач...", flush=True)
            try:
                recs = audit(batch, key, verbose=(i == 1))
            except Exception as e:
                print(f"  батч упал: {e} -> по одной", file=sys.stderr)
                recs = []
                for t in batch:
                    try:
                        recs.extend(audit([t], key))
                    except Exception as e2:
                        failed += 1
                        out.write(json.dumps(
                            {"task_uid": uid_of(t), "error": str(e2)},
                            ensure_ascii=False) + "\n")

            for r in recs:
                if r.get("condition_correct") == "NO":
                    bad_cond += 1
                if r.get("answer_correct") == "NO":
                    bad_ans += 1
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
                written += 1
            out.flush()
            time.sleep(1)

    print("\n" + "=" * 62)
    print(f"Записей             : {written}")
    print(f"Ошибок              : {failed}")
    print(f"НЕКОРРЕКТНЫХ УСЛОВИЙ: {bad_cond}")
    print(f"Неверных ответов    : {bad_ans}")
    print(f"Результат : {os.path.abspath(OUTPUT_FILE)}")
    print("=" * 62)


if __name__ == "__main__":
    main()

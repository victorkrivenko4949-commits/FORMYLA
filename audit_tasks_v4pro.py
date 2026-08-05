#!/usr/bin/env python3
"""
Аудит задач через DeepSeek V4 Pro (thinking mode).

Запуск:
    python audit_tasks_v4pro.py

Вход  : INPUT_FILE  - jsonl, по одной задаче на строку
Выход : OUTPUT_FILE - jsonl, по одной audit-записи на строку
"""

import os
import json
import time
import sys
import requests

# ---------- НАСТРОЙКИ ----------

DEEPSEEK_API_KEY = "sk-ad477f779a1045cba3cc09100e908370"

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
MODEL_NAME = "deepseek-v4-pro"     # ВНИМАНИЕ: deepseek-chat отключён 24.07.2026
REASONING_EFFORT = "high"          # high | max

INPUT_FILE = r"C:\Users\Redmi\Downloads\FORMYLA_L1_L3_FIXED_FINAL.jsonl"
OUTPUT_FILE = "audit_output.jsonl"

TASKS_PER_BATCH = 5
MAX_TOKENS = 16000
REQUEST_TIMEOUT = 600
MAX_RETRIES = 3

# ---------- ПРОМТ ----------

SYSTEM_PROMPT = """Ты — математический эксперт и аудитор олимпиадных задач.

ЦЕЛЬ: найти задачи с НЕКОРРЕКТНЫМ УСЛОВИЕМ и отделить их от задач,
где условие корректно, но ошибочны ответ или решение.

УСЛОВИЕ НЕКОРРЕКТНО, если выполнено хотя бы одно:
- задача невыполнима: нет решения при естественной школьной интерпретации;
- задача неоднозначна: несколько разных прочтений дают разные ответы;
- в условии логическое противоречие;
- техническая ошибка в данных (перепутаны числа, знак, коэффициент, диапазон, пропущен параметр);
- используются неопределённые объекты (нет обозначений, ссылка на отсутствующий рисунок).

ЖЁСТКИЕ ПРАВИЛА:
1. НЕ МЕНЯЙ СЛОЖНОСТЬ ЗАДАЧИ. Класс, уровень, тема и тип остаются прежними.
2. Правка МИНИМАЛЬНАЯ: число, знак, слово. Не переписывай задачу заново.
3. Если условие корректно, а неверны ответ или решение — условие НЕ ТРОГАЙ.
4. Решай каждую задачу ЗАНОВО сам. Не доверяй авторскому ответу и меткам критика.
5. Задачи не смешивай, обрабатывай каждую отдельно.
6. Никакого текста вне JSON.

ФОРМАТ ОТВЕТА — строго JSON-массив:
[
  {
    "taskuid": "...",
    "section": "...",
    "theme": "...",
    "grade": 8,
    "level": 2,
    "condition_correct": "YES" | "NO" | "BORDERLINE",
    "answer_correct": "YES" | "NO" | "UNKNOWN",
    "solution_correct": "YES" | "NO" | "UNKNOWN",
    "defects": ["краткий перечень найденных дефектов"],
    "reason_condition": "1-2 предложения почему условие корректно или нет",
    "proposed_fix": "минимальная правка условия или NONE",
    "re_solved_answer": "твой проверенный ответ или UNSOLVABLE"
  }
]
"""

# ---------- КОД ----------


def get_api_key():
    return os.getenv("DEEPSEEK_API_KEY") or DEEPSEEK_API_KEY


def load_tasks(path):
    if not os.path.exists(path):
        sys.exit(f"Не найден входной файл:\n  {path}\nПоправь INPUT_FILE в скрипте.")
    tasks = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"[warn] строка {i} не JSON, пропускаю", file=sys.stderr)
    return tasks


def chunked(lst, n):
    return [lst[i:i + n] for i in range(0, len(lst), n)]


def slim(task):
    keep = ("taskuid", "task_uid", "grade", "level", "section", "theme",
            "theme_id", "themeid", "statement", "answer", "solution")
    return {k: v for k, v in task.items() if k in keep}


def call_deepseek(messages, api_key):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "enabled"},
        "reasoning_effort": REASONING_EFFORT,
        "response_format": {"type": "json_object"},
    }
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload,
                              timeout=REQUEST_TIMEOUT)
            if r.status_code == 400:
                slim_payload = {k: v for k, v in payload.items()
                                if k not in ("thinking", "reasoning_effort", "response_format")}
                r = requests.post(DEEPSEEK_API_URL, headers=headers, json=slim_payload,
                                  timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            print(f"[warn] попытка {attempt}/{MAX_RETRIES}: {e}", file=sys.stderr)
            time.sleep(3 * attempt)
    raise RuntimeError(f"Запрос к API не удался: {last_err}")


def extract_json(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end != -1:
        return json.loads(raw[start:end + 1])
    obj = json.loads(raw)
    for key in ("results", "tasks", "audit", "data"):
        if isinstance(obj.get(key), list):
            return obj[key]
    return [obj]


def main():
    api_key = get_api_key()
    tasks = load_tasks(INPUT_FILE)
    print(f"Модель: {MODEL_NAME}")
    print(f"Загружено задач: {len(tasks)}")

    batches = chunked(tasks, TASKS_PER_BATCH)
    bad_cond = bad_ans = written = 0

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for idx, batch in enumerate(batches, 1):
            print(f"[{idx}/{len(batches)}] {len(batch)} задач...", flush=True)
            payload = json.dumps([slim(t) for t in batch], ensure_ascii=False)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content":
                    "Пачка задач в JSON. Проверь каждую и верни JSON-массив audit-записей.\n\n" + payload},
            ]
            try:
                records = extract_json(call_deepseek(messages, api_key))
            except Exception as e:
                print(f"[error] батч {idx}: {e}", file=sys.stderr)
                out.write(json.dumps({"batch_index": idx, "error": str(e)},
                                     ensure_ascii=False) + "\n")
                out.flush()
                continue

            for rec in records:
                if rec.get("condition_correct") == "NO":
                    bad_cond += 1
                if rec.get("answer_correct") == "NO":
                    bad_ans += 1
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
            out.flush()
            time.sleep(1)

    print(f"\nГотово. Записей: {written}")
    print(f"Некорректных условий: {bad_cond}")
    print(f"Неверных ответов: {bad_ans}")
    print(f"Результат: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

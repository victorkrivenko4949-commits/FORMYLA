#!/usr/bin/env python3
"""
Аудит задач через DeepSeek.

Запуск (одной командой):
    python audit_tasks.py

Файлы рядом со скриптом:
    tasks.jsonl        - вход: по одной задаче (JSON) на строку
    audit_output.jsonl - выход: по одной audit-записи на строку
"""

import os
import json
import time
import sys
import requests

# ключ зашит здесь; переменная окружения DEEPSEEK_API_KEY, если задана, имеет приоритет
DEEPSEEK_API_KEY = "sk-ad477f779a1045cba3cc09100e908370"

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL_NAME = "deepseek-chat"  # замени на алиас v4-pro, если он доступен на аккаунте

INPUT_FILE = "tasks.jsonl"
OUTPUT_FILE = "audit_output.jsonl"
TASKS_PER_BATCH = 10
MAX_TOKENS = 8000
REQUEST_TIMEOUT = 300
MAX_RETRIES = 3

SYSTEM_PROMPT = """Ты — DeepSeek v4 Pro, математический эксперт и аудитор задач.

ЗАДАЧА ДИАЛОГА: найти все задачи с НЕКОРРЕКТНЫМ УСЛОВИЕМ, отличить их от задач,
где условие корректно, но ошибочны ответ или решение. Затем предложить минимальную
правку условия и решить задачу заново.

УСЛОВИЕ НЕКОРРЕКТНО, если выполнено хотя бы одно:
- задача невыполнима: нет решения при естественной школьной интерпретации;
- задача неоднозначна: несколько существенно разных прочтений дают разные ответы;
- в условии логическое противоречие;
- техническая ошибка в данных (перепутаны числа, знак, коэффициент, диапазон, пропущен параметр);
- используются неопределённые объекты (нет обозначений, ссылка на отсутствующий рисунок и т.п.).

ЖЁСТКИЕ ПРАВИЛА:
1. НЕ МЕНЯЙ СЛОЖНОСТЬ ЗАДАЧИ. Класс, уровень (L1/L2/L3), тема и тип должны остаться прежними.
2. Правка должна быть МИНИМАЛЬНОЙ: меняй число, знак, слово — не переписывай задачу заново.
3. Если условие корректно, а неверны ответ или решение — условие НЕ ТРОГАЙ,
   отметь это в полях answer_correct / solution_correct и дай свой ответ.
4. Каждую задачу решай ЗАНОВО самостоятельно, не доверяй авторскому ответу и меткам критика.
5. Никакого текста вне JSON.

ФОРМАТ ОТВЕТА — строго JSON-массив объектов:
[
  {
    "taskuid": "...",
    "section": "...",
    "theme": "...",
    "grade": 8,
    "condition_correct": "YES" | "NO" | "BORDERLINE",
    "answer_correct": "YES" | "NO" | "UNKNOWN",
    "solution_correct": "YES" | "NO" | "UNKNOWN",
    "reason_condition": "1-2 предложения: почему условие корректно/некорректно",
    "proposed_fix": "минимальная правка условия или NONE",
    "re_solved_answer": "твой проверенный ответ или UNSOLVABLE"
  }
]
"""


def get_api_key():
    return os.getenv("DEEPSEEK_API_KEY") or DEEPSEEK_API_KEY


def load_tasks(path):
    if not os.path.exists(path):
        sys.exit(f"Не найден входной файл {path}. Положи рядом tasks.jsonl.")
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
    }
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload,
                              timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            print(f"[warn] попытка {attempt}/{MAX_RETRIES} не удалась: {e}", file=sys.stderr)
            time.sleep(3 * attempt)
    raise RuntimeError(f"Запрос к API не удался: {last_err}")


def extract_json(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("JSON-массив не найден в ответе")
    return json.loads(raw[start:end + 1])


def main():
    api_key = get_api_key()
    if not api_key:
        sys.exit("Не задан ключ DeepSeek.")

    tasks = load_tasks(INPUT_FILE)
    print(f"Загружено задач: {len(tasks)}")

    batches = chunked(tasks, TASKS_PER_BATCH)
    bad_conditions = 0
    written = 0

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for idx, batch in enumerate(batches, 1):
            print(f"[{idx}/{len(batches)}] отправляю {len(batch)} задач...")
            payload = json.dumps([slim(t) for t in batch], ensure_ascii=False)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content":
                    "Пачка задач в JSON. Проверь каждую и верни JSON-массив audit-записей.\n\n" + payload},
            ]
            try:
                raw = call_deepseek(messages, api_key)
                records = extract_json(raw)
            except Exception as e:
                print(f"[error] батч {idx}: {e}", file=sys.stderr)
                out.write(json.dumps({"batch_index": idx, "error": str(e)},
                                     ensure_ascii=False) + "\n")
                out.flush()
                continue

            for rec in records:
                if rec.get("condition_correct") == "NO":
                    bad_conditions += 1
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
            out.flush()
            time.sleep(1)

    print(f"\nГотово. Записей: {written}. Некорректных условий: {bad_conditions}.")
    print(f"Результат: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

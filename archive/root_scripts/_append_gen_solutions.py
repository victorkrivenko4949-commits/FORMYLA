#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append remaining code to gen_solutions.py"""
import os

target = os.path.join(os.path.dirname(__file__), "..", "..", "Downloads", "gen_solutions.py")
target = os.path.normpath(target)

tail = r'''


# ---------- ПРОМПТ ГЕНЕРАТОРА ПОЛЬЗОВАТЕЛЯ ----------

def gen_user(rec):
    return f"""ПАСПОРТ ЗАДАЧИ (для контекста, не переписывай в ответ):
- Олимпиада: {rec.get('olympiad')}
- Год: {rec.get('year')}
- Класс: {rec.get('grade')}
- Этап/тур: {rec.get('round')}
- Номер задачи: {rec.get('num')}

УСЛОВИЕ:
{rec.get('problem_text')}

Дай полное решение и ответ строго в формате JSON."""


# ---------- ПРОМПТ АУДИТОРА (проверка LaTeX + соответствие) ----------
AUDIT_SYSTEM = """Ты — строгий рецензент олимпиадных решений. Тебе дают паспорт задачи, её условие и предложенное решение с ответом. Проверь ЧЕТЫРЕ вещи и верни строгий JSON.

ПРОВЕРКИ:
1. СООТВЕТСТВИЕ ЗАДАЧЕ: решение решает ИМЕННО это условие (та же задача — не подменена другой), и соответствует паспорту (олимпиада/год/класс/этап/номер не противоречат условию). Условие не искажено внутри решения.
2. LaTeX: все формулы в корректном LaTeX через \( ... \) или \[ ... \]; нет $...$ и $$...$$; нет незакрытых скобок/команд; JSON-экранирование не сломано.
3. МАТЕМАТИЧЕСКАЯ КОРРЕКТНОСТЬ: логика без дыр; для min/max есть и оценка, и пример; ответ согласован с решением; нет заглушек («требует рисунок», «не удалось найти» и т.п.).
4. ЦЕЛОСТНОСТЬ УСЛОВИЯ: если условие само по себе обрывочно/повреждено (нечитаемо, обрезано, бессмысленно) — пометь text_broken=true.

Верни строго JSON без текста вне него:
{
  "pass": <true|false>,
  "matches_task": <true|false>,
  "latex_ok": <true|false>,
  "math_ok": <true|false>,
  "text_broken": <true|false>,
  "issues": ["<кратко каждая проблема>"]
}
pass = true только если matches_task && latex_ok && math_ok && !text_broken."""


def audit_user(rec, gen):
    return f"""ПАСПОРТ: олимпиада={rec.get('olympiad')}, год={rec.get('year')}, класс={rec.get('grade')}, этап={rec.get('round')}, номер={rec.get('num')}.

УСЛОВИЕ:
{rec.get('problem_text')}

ПРЕДЛОЖЕННОЕ РЕШЕНИЕ:
{gen.get('solution')}

ОТВЕТ:
{gen.get('answer')}

Проверь и верни JSON."""


# ---------- API CALL ----------

def call_deepseek(system, user, retries=3):
    """Вызвать DeepSeek API с заданными системным и пользовательским промптами."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0.4,
        "response_format": {"type": "json_object"}
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json"
    }
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(API_URL, json=payload, headers=headers, timeout=180)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            result = _sanitize_json_content(content)
            if result is not None:
                return result
            print(f"    JSON parse failed after sanitization (attempt {attempt}/{retries})")
            if attempt < retries:
                time.sleep(2 * attempt)
        except requests.exceptions.RequestException as e:
            print(f"    API error (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(2 * attempt)
        except Exception as e:
            print(f"    Unexpected error (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(2 * attempt)
    return None


# ---------- MAIN ----------

def main():
    global MODEL
    # Переключаем stdout на utf-8, чтобы избежать UnicodeEncodeError на Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print(f"DeepSeek Solution Generator")
    print(f"Model: {MODEL}")
    print(f"Input: {IN_FILE}")
    print(f"Output: {DB_PATH}")
    print()

    # --- Load input tasks ---
    if not os.path.exists(IN_FILE):
        print(f"ERROR: Input file not found: {IN_FILE}")
        sys.exit(1)

    with open(IN_FILE, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if IN_FILE.endswith(".jsonl"):
        recs = [json.loads(l) for l in raw.split("\n") if l]
    else:
        recs = json.loads(raw)
    print(f"Loaded {len(recs)} tasks from input")
    
    # --- Load existing output (resume support) ---
    existing_keys = set()
    out = []
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "r", encoding="utf-8") as f:
            try:
                out = json.load(f)
                existing_keys = {r["key"] for r in out if "key" in r}
                print(f"Existing output: {len(out)} tasks ({len(existing_keys)} unique keys)")
            except (json.JSONDecodeError, Exception):
                print("Existing output is invalid/corrupt, starting fresh")
                out = []

    # --- Open logs ---
    logf = open(LOG_OK, "a", encoding="utf-8")
    brokenf = open(LOG_BROKEN, "a", encoding="utf-8")
    failf = open(LOG_FAIL, "a", encoding="utf-8")
    
    ok_count = len(existing_keys)
    broken_count = 0
    fail_count = 0
    total = len(recs)
    
    for i, rec in enumerate(recs, 1):
        k = rec.get("key", f"unknown_{i}")
        
        if k in existing_keys:
            print(f"[{i}/{total}] {k} SKIP (already in output)")
            continue
        
        accepted = None
        last_audit = None
        last_gen = None
        
        for attempt in range(3):
            print(f"  [{i}/{total}] {k} generating (attempt {attempt+1}/3)...")
            gen = call_deepseek(GEN_SYSTEM, gen_user(rec))
            if not gen or "solution" not in gen:
                print(f"    Empty/invalid generation")
                continue
            last_gen = gen
            
            print(f"    auditing...")
            audit = call_deepseek(AUDIT_SYSTEM, audit_user(rec, gen))
            last_audit = audit
            
            if audit and audit.get("text_broken"):
                print(f"    TEXT_BROKEN detected")
                break
            
            if audit and audit.get("pass"):
                accepted = gen
                print(f"    PASS (audit accepted)")
                break
            else:
                issues = audit.get("issues", []) if audit else ["audit returned None"]
                print(f"    AUDIT REJECTED: {issues}")
        
        if last_audit and last_audit.get("text_broken"):
            broken_count += 1
            brokenf.write(json.dumps({
                "key": k,
                "olympiad": rec.get("olympiad"),
                "audit": last_audit,
                "gen": last_gen
            }, ensure_ascii=False) + "\n")
            brokenf.flush()
            print(f"  -> TEXT_BROKEN (manual review needed)")
            continue
        
        if not accepted:
            fail_count += 1
            failf.write(json.dumps({
                "key": k,
                "olympiad": rec.get("olympiad"),
                "last_gen": last_gen,
                "last_audit": last_audit
            }, ensure_ascii=False) + "\n")
            failf.flush()
            print(f"  -> FAIL (not accepted after 3 attempts)")
            continue
        
        # Accepted!
        rec["solution"] = accepted["solution"]
        rec["answer"] = accepted["answer"]
        out.append(rec)
        ok_count += 1
        existing_keys.add(k)
        logf.write(json.dumps({
            "key": k,
            "olympiad": rec.get("olympiad"),
            "method_note": accepted.get("method_note", ""),
            "answer": accepted.get("answer", "")
        }, ensure_ascii=False) + "\n")
        logf.flush()
        print(f"  -> OK (method: {accepted.get('method_note', 'N/A')[:60]})")
        
        # Checkpoint
        if ok_count % CHECKPOINT_INTERVAL == 0:
            with open(DB_PATH, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
            print(f"  [CHECKPOINT] Saved {len(out)} tasks to {DB_PATH}")
    
    # Final save
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    
    logf.close()
    brokenf.close()
    failf.close()
    
    print()
    print(f"{'='*50}")
    print(f"  RESULTS:")
    print(f"    Total tasks: {total}")
    print(f"    OK:         {ok_count}")
    print(f"    TEXT_BROKEN: {broken_count}")
    print(f"    FAIL:       {fail_count}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
'''

with open(target, "a", encoding="utf-8") as f:
    f.write(tail)

print(f"Appended {len(tail)} chars to {target}")
print(f"File now has {sum(1 for _ in open(target, 'rb'))} bytes")

import json, time, requests

OPENROUTER_KEY = "ВСТАВЬ_СЮДА_СВОЙ_КЛЮЧ"
MODEL = "anthropic/claude-3.5-sonnet"

PROMPT = (
    "Ты извлекаешь ТОЛЬКО финальный ответ олимпиадной задачи. "
    "Верни строго JSON: {\"answer\": \"...\", \"is_proof\": true/false}. "
    "Если задача на доказательство -> answer пустой, is_proof=true. "
    "Ответ кратко, LaTeX сохраняй. Без пояснений.\n\n"
    "УСЛОВИЕ:\n{text}\n\nРЕШЕНИЕ:\n{solution}"
)

def extract_answer(text, solution):
    body = {
        "model": MODEL,
        "messages": [{"role": "user",
            "content": PROMPT.format(text=text[:4000], solution=solution[:6000])}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + OPENROUTER_KEY},
        json=body, timeout=60)
    r.raise_for_status()
    out = json.loads(r.json()["choices"][0]["message"]["content"])
    return out.get("answer", "").strip(), bool(out.get("is_proof", False))

def run(db_path="OLYMPIADS_DB_final.json"):
    with open(db_path, encoding="utf-8") as f:
        db = json.load(f)
    targets = [t for v in db for t in v["tasks"]
               if t.get("answer_source") == "needs_review"]
    print("К обработке:", len(targets))
    for i, t in enumerate(targets, 1):
        try:
            ans, is_proof = extract_answer(t.get("text", ""), t.get("solution", ""))
            if is_proof:
                t["answer"], t["answer_source"] = "ч.т.д.", "llm_proof"
            elif ans and len(ans) <= 200:
                t["answer"], t["answer_source"] = ans, "llm_extracted"
            else:
                t["answer_source"] = "still_unresolved"
        except Exception as e:
            t["answer_source"] = "llm_error"
            print(i, "error:", e)
        if i % 10 == 0:
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            print("чекпоинт", i)
        time.sleep(0.3)
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print("Готово")

if __name__ == "__main__":
    run()
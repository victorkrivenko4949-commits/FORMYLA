import json, re, csv
from pathlib import Path
from collections import Counter, defaultdict

data = json.loads(Path("formyla_final_rebuilt.json").read_text(encoding="utf-8"))
audit = json.loads(Path("FINAL_RELEASE/checks/template_family_audit.json").read_text(encoding="utf-8"))

bad_families = {
    "quadratic_basic",
    "fraction_of_number",
    "domino_tiling",
    "crt_basic",
    "gcd_lcm_basic",
    "handshake",
    "socks_pigeonhole",
    "complete_graph_edges",
    "chocolate_game_1xn",
    "birthday_pigeonhole",
}

by_id = {str(t.get("id")): t for t in data}

def level(t):
    for k in ["difficulty","level","difficulty_level"]:
        if k in t:
            try:
                return int(t[k])
            except Exception:
                pass
    m = re.search(r"-L(\d+)", str(t.get("id","")))
    return int(m.group(1)) if m else None

def grade(t):
    for k in ["grade","class","class_level"]:
        if k in t:
            try:
                return int(t[k])
            except Exception:
                pass
    m = re.match(r"^(\d+)-", str(t.get("id","")))
    return int(m.group(1)) if m else None

def method_code(t):
    return str(t.get("method_code") or t.get("method") or re.search(r"^\d+-([A-Z]\d+)-", str(t.get("id",""))).group(1) if re.search(r"^\d+-([A-Z]\d+)-", str(t.get("id",""))) else "OLY")

replace_ids = []
for r in audit:
    if not r.get("level") or int(r["level"]) < 6:
        continue
    fams = set(str(r.get("families","")).split(";"))
    if fams & bad_families:
        replace_ids.append(str(r["id"]))

replace_ids = sorted(set(replace_ids))
jobs = []
for i, tid in enumerate(replace_ids, 1):
    t = by_id.get(tid)
    if not t:
        continue
    g = grade(t)
    l = level(t)
    mc = method_code(t)
    old_text = str(t.get("task_text",""))
    old_answer = str(t.get("answer") or t.get("correct_answer") or "")
    jobs.append({
        "job_id": f"semantic-replace-{i:04d}",
        "mode": "replace_bad",
        "replace_id": tid,
        "grade": g,
        "difficulty": l,
        "method_code": mc,
        "old_task_text": old_text,
        "old_answer": old_answer,
        "reason": "semantic_template_repetition_high_level",
        "requirements": [
            "Сгенерировать новую задачу на русском языке.",
            "Сохранить тот же grade, difficulty и method_code.",
            "Не использовать шаблоны: квадратное уравнение с готовыми корнями, НОД/НОК, доля от числа, рукопожатия, домино-паритет, носки/дни рождения, простые CRT-остатки.",
            "Для L6 нужна минимум двухшаговая олимпиадная идея и развёрнутое решение.",
            "Для L7 нужна нетривиальная идея, доказательство или оценка.",
            "Для L8 нужна сложная олимпиадная задача: несколько идей, невозможность/оптимальность/конструкция/параметрический анализ.",
            "Решение должно быть не короче 900 символов для L6, 1200 для L7, 1600 для L8.",
            "Ответ должен быть однозначным."
        ]
    })

Path("semantic_replace_queue").mkdir(exist_ok=True)
for k in range(20):
    part = jobs[k::20]
    Path("semantic_replace_queue", f"worker_{k+1:02d}_jobs.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in part),
        encoding="utf-8"
    )

Path("FINAL_RELEASE/checks/semantic_replace_ids.json").write_text(
    json.dumps(replace_ids, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

with open("FINAL_RELEASE/checks/semantic_replace_queue.csv","w",encoding="utf-8",newline="") as f:
    w = csv.DictWriter(f, fieldnames=["job_id","replace_id","grade","difficulty","method_code","reason"])
    w.writeheader()
    for j in jobs:
        w.writerow({k:j.get(k) for k in ["job_id","replace_id","grade","difficulty","method_code","reason"]})

print("SEMANTIC_REPLACE_IDS", len(replace_ids))
print("SEMANTIC_REPLACE_JOBS", len(jobs))
print("QUEUE_DIR", "semantic_replace_queue")
print("REPORT", "FINAL_RELEASE/checks/semantic_replace_queue.csv")

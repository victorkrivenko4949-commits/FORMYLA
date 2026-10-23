import json, re, csv
from pathlib import Path

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
    x = t.get("method_code") or t.get("method")
    if x:
        return str(x)
    m = re.search(r"^\d+-([A-Z]\d+)-", str(t.get("id","")))
    return m.group(1) if m else "OLY"

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
    jobs.append({
        "job_id": f"semantic-replace-{i:04d}",
        "mode": "replace_bad",
        "replace_id": tid,
        "grade": g,
        "difficulty": l,
        "method_code": mc,
        "bad_task": t,
        "reason": "semantic_template_repetition_high_level",
        "instruction": (
            "Заменить задачу на новую олимпиадную задачу на русском языке. "
            "Сохранить grade, difficulty, method_code. "
            "Запрещены шаблоны: квадратное уравнение с готовыми корнями, НОД/НОК, доля от числа, "
            "рукопожатия, домино-паритет, носки/дни рождения, простые CRT-остатки. "
            "L6: минимум двухшаговая олимпиадная идея и развёрнутое решение. "
            "L7: нетривиальная идея, доказательство или оценка. "
            "L8: несколько идей, невозможность/оптимальность/конструкция/параметрический анализ. "
            "Решение: L6 не короче 900 символов, L7 не короче 1200, L8 не короче 1600. "
            "Ответ однозначный, LaTeX корректный."
        )
    })

q = Path("semantic_replace_queue")
q.mkdir(exist_ok=True)

for k in range(20):
    part = jobs[k::20]
    Path(q, f"formyla_worker_{k+1:02d}_jobs.json").write_text(
        json.dumps({"jobs": part}, ensure_ascii=False, indent=2),
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
        w.writerow({
            "job_id": j["job_id"],
            "replace_id": j["replace_id"],
            "grade": j["grade"],
            "difficulty": j["difficulty"],
            "method_code": j["method_code"],
            "reason": j["reason"],
        })

print("SEMANTIC_REPLACE_IDS", len(replace_ids))
print("SEMANTIC_REPLACE_JOBS", len(jobs))
print("QUEUE_FILES", len(list(q.glob("formyla_worker_*_jobs.json"))))
print("QUEUE_DIR", "semantic_replace_queue")

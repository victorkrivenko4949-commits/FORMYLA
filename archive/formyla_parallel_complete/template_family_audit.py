import json, re, csv
from pathlib import Path
from collections import Counter

p = Path("formyla_final_rebuilt.json")
data = json.loads(p.read_text(encoding="utf-8"))

patterns = [
    ("handshake", [r"пожал[а-яё]* друг другу руки", r"рукопожат"]),
    ("complete_graph_edges", [r"граф[а-яё ]*каждая соединена с каждой", r"сколько р[её]бер"]),
    ("domino_tiling", [r"замостить.*домино", r"доминошк"]),
    ("fraction_of_number", [r"от числа .* взяли его", r"\\d\\frac"]),
    ("gcd_lcm_basic", [r"наибольший общий делитель", r"наименьшее общее кратное"]),
    ("quadratic_basic", [r"решите уравнение.*x\^2", r"x\^2.*x"]),
    ("crt_basic", [r"при делении на .* да[её]т остаток"]),
    ("chocolate_game_1xn", [r"ломают шоколадку.*\\times1"]),
    ("birthday_pigeonhole", [r"общим дн[её]м рождения"]),
    ("socks_pigeonhole", [r"мешке носки", r"пара одного цвета"]),
]

def get_level(t):
    for k in ["difficulty","level","difficulty_level"]:
        if k in t:
            try:
                return int(t[k])
            except Exception:
                pass
    m = re.search(r"-L(\d+)", str(t.get("id","")))
    return int(m.group(1)) if m else None

def get_grade(t):
    for k in ["grade","class","class_level"]:
        if k in t:
            try:
                return int(t[k])
            except Exception:
                pass
    m = re.match(r"^(\d+)-", str(t.get("id","")))
    return int(m.group(1)) if m else None

rows = []
for t in data:
    text = str(t.get("task_text","")).lower()
    sol = str(t.get("solution","") or "")
    fams = []
    for name, regs in patterns:
        if any(re.search(r, text, re.I | re.S) for r in regs):
            fams.append(name)
    if fams:
        rows.append({
            "id": t.get("id"),
            "grade": get_grade(t),
            "level": get_level(t),
            "families": ";".join(fams),
            "solution_len": len(sol.strip()),
            "answer": str(t.get("answer") or t.get("correct_answer") or "")[:120],
            "task_text": str(t.get("task_text",""))[:300]
        })

Path("FINAL_RELEASE/checks").mkdir(parents=True, exist_ok=True)

with open("FINAL_RELEASE/checks/template_family_audit.csv","w",encoding="utf-8",newline="") as f:
    w = csv.DictWriter(f, fieldnames=["id","grade","level","families","solution_len","answer","task_text"])
    w.writeheader()
    w.writerows(rows)

Path("FINAL_RELEASE/checks/template_family_audit.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

cnt = Counter()
high = Counter()
for r in rows:
    for fam in r["families"].split(";"):
        cnt[fam] += 1
        if r["level"] and r["level"] >= 6:
            high[fam] += 1

print("TEMPLATE_TASKS", len(rows))
print("ALL_FAMILIES")
for k,v in cnt.most_common():
    print(k, v)
print("HIGH_LEVEL_FAMILIES_L6_L8")
for k,v in high.most_common():
    print(k, v)
print("FILES")
print("FINAL_RELEASE/checks/template_family_audit.csv")
print("FINAL_RELEASE/checks/template_family_audit.json")

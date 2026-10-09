import json, re
from pathlib import Path

p = Path("formyla_final_rebuilt.json")
data = json.loads(p.read_text(encoding="utf-8", errors="replace"))

bad_markers = ("Р", "С", "Ð", "Ñ", "╨", "╤")
strong_markers = ("Рќ", "Р°", "Рµ", "Рё", "Рѕ", "СЃ", "С‚", "СЂ", "СЋ", "СЏ", "╨", "╤")

def looks_mojibake(s):
    if not isinstance(s, str) or not s:
        return False
    cyr = sum("А" <= ch <= "я" or ch == "ё" or ch == "Ё" for ch in s)
    bad = sum(s.count(x) for x in strong_markers)
    return bad >= 2 and cyr < max(5, bad * 2)

def fix_one(s):
    if not isinstance(s, str):
        return s
    if not looks_mojibake(s):
        return s
    variants = []
    for enc in ("cp1251", "latin1"):
        try:
            variants.append(s.encode(enc, errors="strict").decode("utf-8", errors="strict"))
        except Exception:
            pass
    best = s
    best_score = -10**9
    for v in variants:
        cyr = sum("А" <= ch <= "я" or ch == "ё" or ch == "Ё" for ch in v)
        bad = sum(v.count(x) for x in bad_markers)
        score = cyr * 5 - bad * 20 - v.count("�") * 100
        if score > best_score:
            best_score = score
            best = v
    return best if best != s else s

changed_ids = set()
changed_fields = []

def walk(x, tid=None, path=""):
    if isinstance(x, dict):
        local_tid = x.get("id", tid)
        return {k: walk(v, local_tid, f"{path}.{k}" if path else k) for k, v in x.items()}
    if isinstance(x, list):
        return [walk(v, tid, f"{path}[]") for v in x]
    if isinstance(x, str):
        y = fix_one(x)
        if y != x:
            changed_ids.add(tid)
            changed_fields.append({"id": tid, "field": path, "before": x[:160], "after": y[:160]})
        return y
    return x

fixed = walk(data)

Path("FINAL_RELEASE/checks").mkdir(parents=True, exist_ok=True)
Path("FINAL_RELEASE/checks/mojibake_fixed_fields.json").write_text(
    json.dumps(changed_fields, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

p.write_text(json.dumps(fixed, ensure_ascii=False, indent=2), encoding="utf-8")

print("MOJIBAKE_CHANGED_IDS", len([x for x in changed_ids if x]))
print("MOJIBAKE_CHANGED_FIELDS", len(changed_fields))
print("REPORT", "FINAL_RELEASE/checks/mojibake_fixed_fields.json")

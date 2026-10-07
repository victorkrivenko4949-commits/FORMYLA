import json, glob, shutil
from pathlib import Path

def fix_text(s):
    if not isinstance(s, str):
        return s
    if any(x in s for x in ["Р", "СЃ", "С‚", "вЂ", "С‡", "Рё"]):
        try:
            return s.encode("cp1251", errors="strict").decode("utf-8", errors="strict")
        except Exception:
            return s
    return s

def walk(x):
    if isinstance(x, dict):
        return {k: walk(v) for k, v in x.items()}
    if isinstance(x, list):
        return [walk(v) for v in x]
    if isinstance(x, str):
        return fix_text(x)
    return x

for fn in list(glob.glob("formyla_worker_*_jobs.json")) + ["formyla_20worker_generation_queue.json"]:
    p = Path(fn)
    if not p.exists():
        continue
    shutil.copyfile(p, str(p) + ".bak_encoding")
    data = json.loads(p.read_text(encoding="utf-8"))
    data = walk(data)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

p = Path("deepseek_worker.py")
text = p.read_text(encoding="utf-8")

if "def repair_mojibake_obj" not in text:
    insert = r'''
def repair_mojibake_str(s):
    if not isinstance(s, str):
        return s
    if any(x in s for x in ['Р', 'СЃ', 'С‚', 'вЂ', 'С‡', 'Рё']):
        try:
            return s.encode('cp1251', errors='strict').decode('utf-8', errors='strict')
        except Exception:
            return s
    return s

def repair_mojibake_obj(x):
    if isinstance(x, dict):
        return {k: repair_mojibake_obj(v) for k, v in x.items()}
    if isinstance(x, list):
        return [repair_mojibake_obj(v) for v in x]
    if isinstance(x, str):
        return repair_mojibake_str(x)
    return x
'''
    text = text.replace("\ndef validate_task(t):", insert + "\ndef validate_task(t):")

old = "task = extract_json(raw)\n            if job['mode'] == 'replace_bad':\n                task['id'] = job['id']"
new = "task = repair_mojibake_obj(extract_json(raw))\n            if job['mode'] == 'replace_bad':\n                task['id'] = job['id']\n            else:\n                task['id'] = f\"{job['grade']}-{job.get('method_code','GEN')}-L{job['difficulty']}-{job['job_id']}\""
if old in text:
    text = text.replace(old, new)

p.write_text(text, encoding="utf-8")
print("OK: queues repaired, worker patched")

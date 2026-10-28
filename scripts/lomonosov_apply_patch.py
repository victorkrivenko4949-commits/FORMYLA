# -*- coding: utf-8 -*-
"""Применяет патчи к data/olymp_catalog/lomonosov.json.

Патчи — JSON-файлы в data/olymp_catalog/_patches/lomonosov/*.json, список операций:
  {"op": "update", "uid": "<полный или первые 12 символов uid>", "set": {"round": "...", "grade": 11, ...}}
  {"op": "delete", "uid": "..."}
  {"op": "add", "task": {"year": 2025, "round": "Заключительный этап", "grade": 9, "num": 2,
                         "text": "...", "answer": "...", "solution": "", "source": "https://...",
                         "status": "official_found"}}
Для add: uid = sha256(olymp|year|round|grade|variant|num|normalized text) как в olymp_catalog_fix.py;
остальные поля копируются из шаблона (первая запись файла) со значениями по умолчанию.
Повторное применение безопасно: add с уже существующим uid пропускается, update идемпотентен.
Отчёт: reports/lomonosov_patch_log.md
"""
import glob, hashlib, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "data", "olymp_catalog", "lomonosov.json")
PATCH_DIR = os.path.join(ROOT, "data", "olymp_catalog", "_patches", "lomonosov")
LOG = os.path.join(ROOT, "reports", "lomonosov_patch_log.md")
sys.path.insert(0, HERE)
try:
    import olymp_fix_rules as R
    norm = R.norm_for_compare
except Exception:
    def norm(t):
        t = (t or "").lower()
        t = re.sub(r"\\[()\[\]]", " ", t)
        return re.sub(r"[^0-9a-zа-яё]", "", t)

def make_uid(olymp, year, round_name, grade, num, text, variant=None):
    key = f"{olymp}|{year}|{round_name}|{grade}|{variant or ''}|{num}|{norm(text)[:500]}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

def find(recs, uid):
    hits = [r for r in recs if (r.get("uid") or "").startswith(uid)]
    return hits[0] if len(hits) == 1 else None

def main():
    with open(SRC, encoding="utf-8") as fh:
        recs = json.load(fh)
    template = recs[0] if recs else {}
    olymp = template.get("olymp") or "Ломоносов"
    log = ["# Лог применения патчей к lomonosov.json", ""]
    n_add = n_upd = n_del = n_skip = 0
    for path in sorted(glob.glob(os.path.join(PATCH_DIR, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            ops = json.load(fh)
        log.append(f"## {os.path.basename(path)} — {len(ops)} оп.")
        for op in ops:
            kind = op.get("op")
            if kind == "update":
                r = find(recs, op["uid"])
                if r is None:
                    log.append(f"- ✗ update {op['uid'][:12]}: uid не найден/неоднозначен"); n_skip += 1; continue
                changed = {k: (r.get(k), v) for k, v in op["set"].items() if r.get(k) != v}
                r.update(op["set"])
                log.append(f"- update `{r['uid'][:12]}`: " + (", ".join(f"{k}: {a!r}→{b!r}" for k, (a, b) in changed.items()) or "без изменений"))
                n_upd += bool(changed)
            elif kind == "delete":
                r = find(recs, op["uid"])
                if r is None:
                    log.append(f"- ✗ delete {op['uid'][:12]}: не найден"); n_skip += 1; continue
                recs.remove(r); n_del += 1
                log.append(f"- delete `{r['uid'][:12]}` ({r.get('year')}/{r.get('round')}/{r.get('grade')}/№{r.get('num')})")
            elif kind == "add":
                t = op["task"]
                uid = make_uid(olymp, t["year"], t["round"], t["grade"], t["num"], t["text"])
                if any(r.get("uid") == uid for r in recs):
                    log.append(f"- = add {t['year']}/{t['round']}/{t['grade']}/№{t['num']}: уже есть ({uid[:12]})"); n_skip += 1; continue
                dup = [r for r in recs if r.get("year") == t["year"] and str(r.get("grade")) == str(t["grade"])
                       and norm(r.get("text"))[:120] == norm(t["text"])[:120]]
                if dup:
                    log.append(f"- ✗ add {t['year']}/{t['round']}/{t['grade']}/№{t['num']}: такой текст уже есть как `{dup[0]['uid'][:12]}` ({dup[0].get('round')}/№{dup[0].get('num')}) — используйте update"); n_skip += 1; continue
                rec = {}
                for k, v in template.items():
                    rec[k] = None if v is None else (type(v)() if isinstance(v, (list, dict)) else ("" if isinstance(v, str) else None))
                rec.update({"uid": uid, "olymp": olymp, "year": t["year"], "round": t["round"], "grade": t["grade"],
                            "num": str(t["num"]) if isinstance(template.get("num"), str) else t["num"],
                            "text": t["text"], "answer": t.get("answer", ""), "solution": t.get("solution", ""),
                            "source": t.get("source", ""), "status": t.get("status", "official_found")})
                for k, v in t.items():
                    if k not in rec or rec[k] in (None, ""):
                        rec[k] = v
                recs.append(rec); n_add += 1
                log.append(f"- add `{uid[:12]}` {t['year']}/{t['round']}/{t['grade']}/№{t['num']}: {t['text'][:70]}…")
            else:
                log.append(f"- ✗ неизвестная операция {kind!r}"); n_skip += 1
    with open(SRC, "w", encoding="utf-8") as fh:
        json.dump(recs, fh, ensure_ascii=False, indent=1)
    log.insert(2, f"Добавлено {n_add}, обновлено {n_upd}, удалено {n_del}, пропущено {n_skip}. Задач в файле: {len(recs)}.")
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\n")
    print(log[2])

if __name__ == "__main__":
    sys.exit(main())

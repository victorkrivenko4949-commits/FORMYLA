# -*- coding: utf-8 -*-
"""Компактный индекс каталога «Ломоносов» по годам: reports/lomonosov_index/<year>.md
+ reports/lomonosov_index/_schema.json (одна полная запись — чтобы видеть схему полей)."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "olymp_catalog", "lomonosov.json")
OUT = os.path.join(ROOT, "reports", "lomonosov_index")

def short(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return (s[: n - 1] + "…") if len(s) > n else s

def main():
    with open(SRC, encoding="utf-8") as fh:
        recs = json.load(fh)
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))
    by_year = {}
    for r in recs:
        by_year.setdefault(r.get("year"), []).append(r)
    for y, items in by_year.items():
        items.sort(key=lambda r: (str(r.get("round")), str(r.get("grade")).zfill(2), int(re.search(r"\d+", str(r.get("num") or "0")).group() if re.search(r"\d+", str(r.get("num") or "0")) else 0)))
        L = [f"# Ломоносов {y} — {len(items)} задач", "", "| uid | этап | кл | № | статус | ответ | условие | источник |", "|---|---|---|---|---|---|---|---|"]
        for r in items:
            L.append("| `%s` | %s | %s | %s | %s | %s | %s | %s |" % (
                (r.get("uid") or "")[:12], r.get("round"), r.get("grade"), r.get("num"), r.get("status"),
                short(r.get("answer"), 30).replace("|", "\\|"), short(r.get("text"), 110).replace("|", "\\|"),
                short(r.get("source"), 60).replace("|", "\\|")))
        with open(os.path.join(OUT, f"{y}.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(L) + "\n")
    keys = {}
    for r in recs:
        for k, v in r.items():
            keys.setdefault(k, type(v).__name__)
    with open(os.path.join(OUT, "_schema.json"), "w", encoding="utf-8") as fh:
        json.dump({"keys": keys, "sample": recs[0] if recs else None}, fh, ensure_ascii=False, indent=1)
    print(f"index: {len(by_year)} years, {len(recs)} tasks")

if __name__ == "__main__":
    sys.exit(main())

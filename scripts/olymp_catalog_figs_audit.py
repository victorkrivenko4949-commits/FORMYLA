# -*- coding: utf-8 -*-
"""
Аудит рисунков каталога олимпиад FORMYLA.
Запуск из корня репозитория:  python scripts/olymp_catalog_figs_audit.py [--slug formula-unity] [--csv out.csv]

Находит три типа проблем:
  A. fig_missing      — в JSON указан путь к рисунку, но файла нет в static/olymp_figures
  B. fig_not_linked   — в тексте/решении есть слова «рисунок», «чертёж», «см. рис», «закрашен», «серые клетки»,
                        «на картинке», «фигурк», но fig_statement и fig_solution пустые
  C. fig_orphan       — файл рисунка лежит в папке, но ни одна задача на него не ссылается
"""
import argparse, csv, json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "olymp_catalog"
FIGS = ROOT / "static" / "olymp_figures"

FIG_WORDS = re.compile(
    r"рисун|чертеж|чертёж|см\.\s*рис|на\s+картинк|изображ[её]н|закрашен|заштрихован|серы[хе]\s+клет|"
    r"фигурк|показан[оа]?\s+на|приведен[оа]?\s+на\s+рис|диаграмм|график[еа]?\b|схем[еа]\b",
    re.IGNORECASE,
)

def load(slug):
    p = DATA / f"{slug}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

def all_fig_files():
    out = {}
    for p in FIGS.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".png", ".svg", ".jpg", ".jpeg"):
            out[p.relative_to(FIGS).as_posix()] = p
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="только одна олимпиада (slug)")
    ap.add_argument("--csv", default="olymp_figs_audit.csv")
    ap.add_argument("--all-missing", action="store_true",
                    help="выводить также задачи без рисунка вообще (даже если текст его не упоминает)")
    a = ap.parse_args()

    index = json.loads((DATA / "_index.json").read_text(encoding="utf-8"))
    slugs = [a.slug] if a.slug else [m["slug"] for m in index]
    files = all_fig_files()
    referenced = set()
    rows = []

    for slug in slugs:
        for t in load(slug):
            figs = (t.get("fig_statement") or []) + (t.get("fig_solution") or [])
            text = " ".join(str(t.get(k) or "") for k in ("text", "solution", "answer"))
            base = dict(slug=slug, uid=t["uid"][:12], year=t.get("year"), round=t.get("round"),
                        grade=t.get("grade"), num=t.get("num"), status=t.get("status"),
                        url=f"https://formyla.net/olymp-catalog/{slug}/{t['uid'][:12]}")
            for f in figs:
                f = str(f).replace("\\", "/")
                referenced.add(f)
                if f not in files:
                    rows.append({**base, "problem": "fig_missing", "detail": f})
            if not figs:
                hit = FIG_WORDS.search(text)
                if hit:
                    rows.append({**base, "problem": "fig_not_linked", "detail": hit.group(0)})
                elif a.all_missing:
                    rows.append({**base, "problem": "no_fig", "detail": ""})

    for f in sorted(set(files) - referenced):
        rows.append(dict(slug="", uid=f.split("/")[-1][:12], year="", round="", grade="", num="",
                         status="", url="", problem="fig_orphan", detail=f))

    cols = ["problem", "slug", "year", "round", "grade", "num", "status", "uid", "detail", "url"]
    with open(a.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    from collections import Counter
    c = Counter(r["problem"] for r in rows)
    by = Counter((r["problem"], r["slug"]) for r in rows if r["slug"])
    print("ИТОГО:", dict(c))
    print("\nПо олимпиадам:")
    for (prob, slug), n in sorted(by.items()):
        print(f"  {prob:15s} {slug:16s} {n}")
    print(f"\nПодробности: {a.csv}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

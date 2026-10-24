# -*- coding: utf-8 -*-
"""
Аудит и автопочинка рисунков каталога олимпиад FORMYLA.

  python scripts/olymp_catalog_figs_audit.py [--slug formula-unity] [--csv out.csv] [--fix-orphans] [--all-missing]

Проблемы:
  fig_missing     — путь к рисунку указан в JSON, но файла нет в static/olymp_figures
  fig_not_linked  — текст упоминает рисунок/чертёж/закраску, а fig_statement/fig_solution пустые
  fig_orphan      — файл рисунка есть, но ни одна задача на него не ссылается

--fix-orphans: для каждого «сиротского» файла, имя которого начинается с полного uid задачи,
дописывает путь в fig_statement (…_statement*.png, <uid>.svg) или fig_solution (…_solution*.png, <uid>_aux.svg)
и перезаписывает data/olymp_catalog/<slug>.json. Список правок — reports/olymp_figs_fix.csv.
"""
import argparse, csv, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "olymp_catalog"
FIGS = ROOT / "static" / "olymp_figures"

FIG_WORDS = re.compile(
    r"рисун|чертеж|чертёж|см\.\s*рис|на\s+картинк|изображ[её]н|закрашен|заштрихован|серы[хе]\s+клет|"
    r"фигурк|показан[оа]?\s+на|приведен[оа]?\s+на\s+рис|диаграмм|график[еа]?\b|схем[еа]\b",
    re.IGNORECASE,
)
UID_RE = re.compile(r"^([0-9a-f]{64})(.*)$")

def load(slug):
    p = DATA / f"{slug}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

def save(slug, tasks):
    (DATA / f"{slug}.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")

def all_fig_files():
    return {p.relative_to(FIGS).as_posix(): p for p in FIGS.rglob("*")
            if p.is_file() and p.suffix.lower() in (".png", ".svg", ".jpg", ".jpeg")}

def fig_field(relpath):
    stem = Path(relpath).stem
    m = UID_RE.match(stem)
    if not m:
        return None, None
    uid, tail = m.group(1), m.group(2)
    if tail.startswith("_solution") or tail.startswith("_aux"):
        return uid, "fig_solution"
    return uid, "fig_statement"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--csv", default="olymp_figs_audit.csv")
    ap.add_argument("--fix-csv", default="olymp_figs_fix.csv")
    ap.add_argument("--fix-orphans", action="store_true")
    ap.add_argument("--all-missing", action="store_true")
    a = ap.parse_args()

    index = json.loads((DATA / "_index.json").read_text(encoding="utf-8"))
    slugs = [a.slug] if a.slug else [m["slug"] for m in index]
    files = all_fig_files()
    data = {s: load(s) for s in slugs}

    # --- автопочинка сирот по uid ---
    fixes = []
    if a.fix_orphans:
        referenced = set()
        for ts in data.values():
            for t in ts:
                for f in (t.get("fig_statement") or []) + (t.get("fig_solution") or []):
                    referenced.add(str(f).replace("\\", "/"))
        by_uid = defaultdict(list)
        for f in sorted(set(files) - referenced):
            uid, field = fig_field(f)
            if uid:
                by_uid[uid].append((f, field))
        changed = set()
        for slug, ts in data.items():
            for t in ts:
                for f, field in by_uid.get(t["uid"], []):
                    lst = t.get(field) or []
                    if f not in lst:
                        lst.append(f)
                        t[field] = lst
                        changed.add(slug)
                        fixes.append(dict(slug=slug, uid=t["uid"][:12], year=t.get("year"), grade=t.get("grade"),
                                          num=t.get("num"), field=field, file=f,
                                          url=f"https://formyla.net/olymp-catalog/{slug}/{t['uid'][:12]}"))
        for slug in changed:
            save(slug, data[slug])
        with open(a.fix_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["slug", "year", "grade", "num", "uid", "field", "file", "url"])
            w.writeheader(); w.writerows(fixes)
        print(f"ПОЧИНЕНО: {len(fixes)} привязок в {len(changed)} файлах; список: {a.fix_csv}")
        print("  по олимпиадам:", dict(Counter(x["slug"] for x in fixes)))

    # --- аудит (после починки) ---
    referenced, rows = set(), []
    for slug, ts in data.items():
        for t in ts:
            figs = (t.get("fig_statement") or []) + (t.get("fig_solution") or [])
            text = " ".join(str(t.get(k) or "") for k in ("text", "solution", "answer"))
            base = dict(slug=slug, uid=t["uid"][:12], year=t.get("year"), round=t.get("round"),
                        grade=t.get("grade"), num=t.get("num"), status=t.get("status"),
                        url=f"https://formyla.net/olymp-catalog/{slug}/{t['uid'][:12]}")
            for f in figs:
                f = str(f).replace("\\", "/"); referenced.add(f)
                if f not in files:
                    rows.append({**base, "problem": "fig_missing", "detail": f})
            if not figs:
                hit = FIG_WORDS.search(text)
                if hit:
                    rows.append({**base, "problem": "fig_not_linked", "detail": re.sub(r"\s+", " ", hit.group(0))})
                elif a.all_missing:
                    rows.append({**base, "problem": "no_fig", "detail": ""})
    for f in sorted(set(files) - referenced):
        rows.append(dict(slug="", uid=f.split("/")[-1][:12], year="", round="", grade="", num="",
                         status="", url="", problem="fig_orphan", detail=f))

    cols = ["problem", "slug", "year", "round", "grade", "num", "status", "uid", "detail", "url"]
    with open(a.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    print("ИТОГО:", dict(Counter(r["problem"] for r in rows)))
    print("\nПо олимпиадам:")
    for (prob, slug), n in sorted(Counter((r["problem"], r["slug"]) for r in rows if r["slug"]).items()):
        print(f"  {prob:15s} {slug:16s} {n}")
    print(f"\nПодробности: {a.csv}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

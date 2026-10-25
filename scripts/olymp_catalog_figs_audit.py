# -*- coding: utf-8 -*-
"""
Аудит и автопочинка рисунков каталога олимпиад FORMYLA.

  python scripts/olymp_catalog_figs_audit.py [--slug formula-unity] [--csv out.csv] [--fix-orphans] [--all-missing]

Проблемы:
  fig_missing     — путь к рисунку указан в JSON, но файла нет в static/olymp_figures
  fig_not_linked  — текст упоминает рисунок/чертёж/закраску, а fig_statement/fig_solution пустые
  fig_orphan      — файл рисунка есть, но ни одна задача на него не ссылается

--fix-orphans (три стадии):
  1) uid: имя файла начинается с полного uid задачи;
  2) map-key: по FINAL_FIGURES/tasks.jsonl — (olympiad, year, grade, num) + сходство текста >= MIN_SIM;
  3) map-text: по tasks.jsonl — лучший по сходству текст среди ВСЕХ задач той же олимпиады
     (с алиасами slug: mos→mmo, math-holiday→matprazdnik, пусто→все), порог TEXT_SIM и отрыв от второго.
Всё, что не прошло пороги — в отчёт (ambiguous / low_sim / no_match), JSON не трогается.
Правки пишутся в data/olymp_catalog/<slug>.json; список — reports/olymp_figs_fix.csv.
"""
import argparse, csv, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "olymp_catalog"
FIGS = ROOT / "static" / "olymp_figures"
MAP = FIGS / "FINAL_FIGURES" / "tasks.jsonl"
MIN_SIM = 0.25
TEXT_SIM = 0.45
MARGIN = 0.15
SLUG_ALIAS = {"mos": "mmo", "mmo": "mmo", "math-holiday": "matprazdnik", "matprazdnik": "matprazdnik",
              "formula-unity": "formula-unity", "vysshaya-proba": "vysshaya-proba", "spbgu": "spbgu",
              "phystech": "phystech", "pvg": "pvg", "euler": "euler", "lomonosov": "lomonosov",
              "kurchatov": "kurchatov", "turgor": "turgor", "vsosh": "vsosh"}

FIG_WORDS = re.compile(
    r"рисун|чертеж|чертёж|см\.\s*рис|на\s+картинк|изображ[её]н|закрашен|заштрихован|серы[хе]\s+клет|"
    r"фигурк|показан[оа]?\s+на|приведен[оа]?\s+на\s+рис|диаграмм|график[еа]?\b|схем[еа]\b",
    re.IGNORECASE,
)
UID_RE = re.compile(r"^([0-9a-f]{64})(.*)$")
WORD_RE = re.compile(r"[а-яёa-z0-9]{3,}", re.IGNORECASE)

def load(slug):
    p = DATA / f"{slug}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

def save(slug, tasks):
    (DATA / f"{slug}.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")

def all_fig_files():
    return {p.relative_to(FIGS).as_posix(): p for p in FIGS.rglob("*")
            if p.is_file() and p.suffix.lower() in (".png", ".svg", ".jpg", ".jpeg", ".gif")}

def fig_field(relpath):
    m = UID_RE.match(Path(relpath).stem)
    if not m:
        return None, None
    return m.group(1), ("fig_solution" if m.group(2).startswith(("_solution", "_aux")) else "fig_statement")

def tokens(s):
    return set(w.lower() for w in WORD_RE.findall(s or ""))

def sim(a, b):
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0

def norm_slug(name):
    n = str(name or "").strip().lower().replace("_", "-")
    return SLUG_ALIAS.get(n, n)

def attach(t, field, f):
    lst = t.get(field) or []
    if f in lst:
        return False
    lst.append(f); t[field] = lst
    return True

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

    fixes = []
    if a.fix_orphans:
        def referenced_set():
            r = set()
            for ts in data.values():
                for t in ts:
                    for f in (t.get("fig_statement") or []) + (t.get("fig_solution") or []):
                        r.add(str(f).replace("\\", "/"))
            return r
        changed = set()

        by_uid = defaultdict(list)
        for f in sorted(set(files) - referenced_set()):
            uid, field = fig_field(f)
            if uid:
                by_uid[uid].append((f, field))
        for slug, ts in data.items():
            for t in ts:
                for f, field in by_uid.get(t["uid"], []):
                    if attach(t, field, f):
                        changed.add(slug)
                        fixes.append(dict(status="fixed", method="uid", sim="1.00", slug=slug, uid=t["uid"][:12],
                                          year=t.get("year"), grade=t.get("grade"), num=t.get("num"),
                                          field=field, file=f, url=f"https://formyla.net/olymp-catalog/{slug}/{t['uid'][:12]}"))

        if MAP.exists():
            orphans = set(files) - referenced_set()
            key_index = defaultdict(list)
            for slug, ts in data.items():
                for t in ts:
                    key_index[(slug, str(t.get("year")), str(t.get("grade")), str(t.get("num")))].append((slug, t))
            for line in MAP.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                except Exception:
                    continue
                f = "FINAL_FIGURES/" + str(m.get("file", ""))
                if f not in orphans:
                    continue
                slug = norm_slug(m.get("olympiad"))
                field = "fig_solution" if m.get("kind") == "solution" else "fig_statement"
                stmt = m.get("statement", "")
                rec = dict(slug=slug, uid="", year=m.get("year"), grade=m.get("grade"), num=m.get("num"),
                           field=field, file=f, url="", method="", sim="")

                def try_attach(scored, method, thr):
                    best, s, t = scored[0]
                    second = scored[1][0] if len(scored) > 1 else 0.0
                    rec.update(method=method, uid=t["uid"][:12], sim=f"{best:.2f}",
                               url=f"https://formyla.net/olymp-catalog/{s}/{t['uid'][:12]}")
                    if best >= thr and (len(scored) == 1 or best >= second + MARGIN):
                        if attach(t, field, f):
                            changed.add(s); orphans.discard(f)
                            fixes.append({**rec, "status": "fixed"}); return True
                    return False

                # стадия 2: по ключу
                cands = key_index.get((slug, str(m.get("year")), str(m.get("grade")), str(m.get("num"))), [])
                if cands:
                    scored = sorted(((sim(stmt, t.get("text", "")), s, t) for s, t in cands), key=lambda x: -x[0])
                    if try_attach(scored, "map-key", MIN_SIM):
                        continue
                # стадия 3: по тексту среди всех задач олимпиады (или всех олимпиад, если slug неизвестен)
                pool = [(s, t) for s, ts in data.items() if (s == slug or slug not in data) for t in ts]
                if pool and tokens(stmt):
                    scored = sorted(((sim(stmt, t.get("text", "")), s, t) for s, t in pool), key=lambda x: -x[0])[:5]
                    if try_attach(scored, "map-text", TEXT_SIM):
                        continue
                    best, second = scored[0][0], (scored[1][0] if len(scored) > 1 else 0.0)
                    fixes.append({**rec, "status": "ambiguous" if best >= TEXT_SIM else "low_sim"}); continue
                fixes.append({**rec, "status": "no_match"})

        for slug in changed:
            save(slug, data[slug])
        cols = ["status", "method", "sim", "slug", "year", "grade", "num", "uid", "field", "file", "url"]
        with open(a.fix_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
            for r in fixes:
                w.writerow({c: r.get(c, "") for c in cols})
        print(f"ПОЧИНКА: {dict(Counter(r['status'] for r in fixes))}; изменено файлов JSON: {len(changed)}; список: {a.fix_csv}")
        print("  fixed по олимпиадам:", dict(Counter(r["slug"] for r in fixes if r["status"] == "fixed")))
        print("  fixed по методам:", dict(Counter(r["method"] for r in fixes if r["status"] == "fixed")))

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
            if not figs and not t.get("fig_none_in_source"):
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

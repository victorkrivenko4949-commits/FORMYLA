# -*- coding: utf-8 -*-
"""
Извлечение рисунков из исходных PDF для задач каталога, у которых рисунок упомянут, но не приложен.

  python scripts/olymp_catalog_figs_extract.py --slug formula-unity|all [--limit N] [--dry-run]

Для каждой задачи (fig_statement/fig_solution пустые, текст упоминает рисунок, source содержит .pdf):
  1. скачать PDF (кэш .cache_pdf/); если на странице графики нет — попробовать «соседний» PDF условий
     (sol→tasks, _sol→'' и т.п.);
  2. страница: максимум пересечения слов текста задачи (+решения) со словами страницы;
  3. блок задачи: по номеру ("N." / "N)" / "Задача N") или, если номер не найден, по текстовому якорю
     (поиск 4–6 подряд идущих слов условия на странице); граница снизу — следующий номер;
  4. bbox векторных рисунков + растровых картинок → фильтр колонтитулов/мелочи → кластеры → внутри блока;
  5. рендер (zoom 3) в FINAL_FIGURES/<uid>_statement[_k].png, запись в fig_statement + fig_extracted_auto.
Статусы: extracted / no_figure_on_page / page_not_found / download_failed / no_pdf.
"""
import argparse, csv, hashlib, json, re, sys, time
from collections import Counter
from pathlib import Path

import requests
import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "olymp_catalog"
FIGS = ROOT / "static" / "olymp_figures" / "FINAL_FIGURES"
CACHE = ROOT / ".cache_pdf"
UA = {"User-Agent": "Mozilla/5.0 (FORMYLA figs extractor)"}

FIG_WORDS = re.compile(
    r"рисун|чертеж|чертёж|см\.\s*рис|на\s+картинк|изображ[её]н|закрашен|заштрихован|серы[хе]\s+клет|"
    r"ч[её]рны[ехм]\s+клет|клет(?:ки|ок)\s+ч[её]рн|бел(?:ые|ых)\s+клет|фигурк|показан[оа]?\s+на|"
    r"приведен[оа]?\s+на\s+рис|диаграмм|на\s+доске\s+(?:нарисован|изображ)|развёртк|разверт", re.IGNORECASE)
WORD_RE = re.compile(r"[а-яёa-z]{4,}", re.IGNORECASE)
ZOOM = 3.0
MIN_W, MIN_H = 36, 22
HEADER_FRAC, FOOTER_FRAC = 0.07, 0.06
GAP = 10

def tokens(s):
    return set(w.lower() for w in WORD_RE.findall(s or ""))

def fetch_pdf(url):
    CACHE.mkdir(exist_ok=True)
    p = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".pdf")
    if p.exists():
        return p.read_bytes()
    for _ in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.ok and r.content[:5] == b"%PDF-":
                p.write_bytes(r.content); return r.content
            if r.status_code == 404:
                return None
        except Exception:
            time.sleep(2)
    return None

def sibling_urls(url):
    """Варианты URL файла условий для файла решений."""
    out = []
    for a, b in (("-sol-", "-tasks-"), ("-sol-", "-task-"), ("_sol_", "_"), ("_sol.", "."), ("_sol-", "-"),
                 ("-sol.", "."), ("sol_", ""), ("-solutions", ""), ("_solutions", ""), ("taskssol", "tasks")):
        if a in url:
            out.append(url.replace(a, b, 1))
    return [u for u in dict.fromkeys(out) if u != url]

def pick_page(doc, task):
    want = tokens(task.get("text", "")) | tokens(task.get("solution", "")[:600])
    best, best_i = 0.0, None
    for i, page in enumerate(doc):
        have = tokens(page.get_text())
        if have:
            score = len(want & have) / (len(want) or 1)
            if score > best:
                best, best_i = score, i
    return best_i, best

NUM_RE = re.compile(r"^\s*(?:Задача\s*)?(\d{1,2})\s*[.)]")

def task_block(page, num, text):
    blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
    y0 = None
    for b in blocks:
        m = NUM_RE.match(b[4])
        if m and m.group(1) == str(num):
            y0 = b[1] - 4; break
    anchor = "num"
    if y0 is None:
        words = re.findall(r"[А-Яа-яЁёA-Za-z]{3,}", text or "")
        for n in (6, 5, 4):
            for i in range(0, max(0, len(words) - n), 2):
                hits = page.search_for(" ".join(words[i:i + n]))
                if hits:
                    y0 = min(h.y0 for h in hits) - 4; anchor = "text"; break
            if y0 is not None:
                break
    if y0 is None:
        return None, "none"
    y1 = page.rect.y1
    for b in blocks:
        if b[1] > y0 + 8 and NUM_RE.match(b[4]) and NUM_RE.match(b[4]).group(1) != str(num):
            y1 = b[1] - 2; break
    return (y0, y1), anchor

def rects_on_page(page):
    rects = []
    for d in page.get_drawings():
        r = d.get("rect")
        if r and r.width >= 2 and r.height >= 2:
            rects.append(fitz.Rect(r))
    for img in page.get_images(full=True):
        try:
            rects += [fitz.Rect(r) for r in page.get_image_rects(img[0])]
        except Exception:
            pass
    return rects

def cluster(rects):
    rects = [fitz.Rect(r) for r in rects]
    while True:
        out, changed = [], False
        while rects:
            a = rects.pop()
            grown = fitz.Rect(a.x0 - GAP, a.y0 - GAP, a.x1 + GAP, a.y1 + GAP)
            for i, b in enumerate(out):
                if grown.intersects(b):
                    out[i] = b | a; changed = True; break
            else:
                out.append(a)
        if not changed:
            return out
        rects = out

def extract_for_task(doc, task):
    pi, score = pick_page(doc, task)
    if pi is None or score < 0.12:
        return "page_not_found", None, [], "none"
    page = doc[pi]
    H = page.rect.height
    blk, anchor = task_block(page, task.get("num"), task.get("text", ""))
    y0, y1 = blk if blk else (H * HEADER_FRAC, H * (1 - FOOTER_FRAC))
    cands = []
    for r in cluster(rects_on_page(page)):
        if r.width < MIN_W or r.height < MIN_H:
            continue
        if r.y1 < H * HEADER_FRAC or r.y0 > H * (1 - FOOTER_FRAC):
            continue
        if r.width > page.rect.width * 0.95 and r.height > H * 0.9:
            continue
        cy = (r.y0 + r.y1) / 2
        if y0 - 6 <= cy <= y1 + 6:
            cands.append(r)
    cands.sort(key=lambda r: (r.y0, r.x0))
    return ("extracted" if cands else "no_figure_on_page"), pi, [(page, r) for r in cands], anchor

def process_slug(slug, a, rows):
    path = DATA / f"{slug}.json"
    if not path.exists():
        return
    tasks = json.loads(path.read_text(encoding="utf-8"))
    done, changed = 0, False
    for t in tasks:
        if t.get("fig_statement") or t.get("fig_solution"):
            continue
        blob = " ".join(str(t.get(k) or "") for k in ("text", "solution"))
        if not FIG_WORDS.search(blob):
            continue
        src = (t.get("source") or "").split(";")[0].strip()
        url = src.split("#")[0]
        rec = dict(slug=slug, uid=t["uid"][:12], year=t.get("year"), grade=t.get("grade"), num=t.get("num"),
                   source=url, page="", figs=0, anchor="", status="",
                   url=f"https://formyla.net/olymp-catalog/{slug}/{t['uid'][:12]}")
        if ".pdf" not in url.lower():
            rows.append({**rec, "status": "no_pdf"}); continue
        status, pi, items, anchor, used = "download_failed", None, [], "none", url
        for cand in [url] + sibling_urls(url):
            data = fetch_pdf(cand)
            if not data:
                continue
            try:
                doc = fitz.open(stream=data, filetype="pdf")
            except Exception:
                continue
            status, pi, items, anchor = extract_for_task(doc, t)
            used = cand
            if status == "extracted":
                break
        rec.update(page=(pi + 1) if pi is not None else "", status=status, anchor=anchor, source=used)
        if status == "extracted" and not a.dry_run:
            paths = []
            for k, (page, r) in enumerate(items[:4]):
                name = f"{t['uid']}_statement{'' if k == 0 else '_' + str(k + 1)}.png"
                clip = fitz.Rect(r.x0 - 4, r.y0 - 4, r.x1 + 4, r.y1 + 4) & page.rect
                page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip, alpha=False).save(str(FIGS / name))
                paths.append("FINAL_FIGURES/" + name)
            t["fig_statement"] = paths
            t["fig_extracted_auto"] = True
            t["fig_anchor"] = anchor
            changed = True
            rec["figs"] = len(paths)
        elif status == "extracted":
            rec["figs"] = len(items)
        rows.append(rec)
        done += 1
        if a.limit and done >= a.limit:
            break
    if changed and not a.dry_run:
        path.write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--csv", default="reports/olymp_figs_extract.csv")
    a = ap.parse_args()
    FIGS.mkdir(parents=True, exist_ok=True)
    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    index = json.loads((DATA / "_index.json").read_text(encoding="utf-8"))
    slugs = [m["slug"] for m in index] if a.slug == "all" else [a.slug]
    rows = []
    for s in slugs:
        process_slug(s, a, rows)
        print(f"[{s}] {dict(Counter(r['status'] for r in rows if r['slug'] == s))}", flush=True)
    cols = ["status", "slug", "year", "grade", "num", "uid", "page", "figs", "anchor", "source", "url"]
    with open(a.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    print("ЭКСТРАКЦИЯ:", dict(Counter(r["status"] for r in rows)), "| всего рисунков:", sum(int(r.get("figs") or 0) for r in rows))
    print("  по якорю (extracted):", dict(Counter(r["anchor"] for r in rows if r["status"] == "extracted")))
    print("Отчёт:", a.csv)

if __name__ == "__main__":
    sys.exit(main())

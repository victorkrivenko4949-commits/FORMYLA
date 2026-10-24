# -*- coding: utf-8 -*-
"""
Извлечение рисунков из исходных PDF для задач каталога, у которых рисунок упомянут, но не приложен.

  python scripts/olymp_catalog_figs_extract.py --slug formula-unity [--limit N] [--dry-run]

Алгоритм для каждой задачи (fig_statement/fig_solution пустые, текст упоминает рисунок, source содержит .pdf):
  1. скачать PDF (кэш в .cache_pdf/), открыть PyMuPDF;
  2. выбрать страницу: максимум пересечения слов текста задачи (+решения) со словами страницы;
  3. найти на странице блок задачи: текстовый блок, начинающийся с "<num>." / "<num>)" / "Задача <num>";
     границы блока — от него до начала следующего номера (или до низа страницы);
  4. собрать bbox векторных рисунков (page.get_drawings) и растровых картинок (page.get_image_rects),
     отбросить колонтитулы/логотипы, склеить близкие прямоугольники в кластеры, оставить те, что внутри блока;
  5. отрендерить каждый кластер (zoom 3) в static/olymp_figures/FINAL_FIGURES/<uid>_statement[_k].png,
     дописать пути в fig_statement, записать строку в reports/olymp_figs_extract.csv.
Статусы: extracted / no_figure_on_page (рисунков не нашлось) / page_not_found / download_failed / no_pdf.
"""
import argparse, csv, hashlib, io, json, os, re, sys, time
from collections import Counter
from pathlib import Path

import requests
import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "olymp_catalog"
FIGS = ROOT / "static" / "olymp_figures" / "FINAL_FIGURES"
CACHE = ROOT / ".cache_pdf"
UA = {"User-Agent": "Mozilla/5.0 (FORMYLA figs extractor)"}

FIG_WORDS = re.compile(
    r"рисун|чертеж|чертёж|см\.\s*рис|на\s+картинк|изображ[её]н|закрашен|заштрихован|серы[хе]\s+клет|"
    r"фигурк|показан[оа]?\s+на|приведен[оа]?\s+на\s+рис|диаграмм", re.IGNORECASE)
WORD_RE = re.compile(r"[а-яёa-z]{4,}", re.IGNORECASE)
ZOOM = 3.0
MIN_W, MIN_H = 36, 22        # pt — меньше этого считаем мусором (подчёркивания, маркеры)
HEADER_FRAC, FOOTER_FRAC = 0.07, 0.06
GAP = 10                     # pt — склейка соседних прямоугольников

def tokens(s):
    return set(w.lower() for w in WORD_RE.findall(s or ""))

def fetch_pdf(url):
    CACHE.mkdir(exist_ok=True)
    p = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".pdf")
    if p.exists():
        return p.read_bytes()
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.ok and r.content[:5] == b"%PDF-":
                p.write_bytes(r.content); return r.content
        except Exception:
            time.sleep(2)
    return None

def pick_page(doc, task):
    want = tokens(task.get("text", "")) | tokens(task.get("solution", "")[:600])
    best, best_i = 0.0, None
    for i, page in enumerate(doc):
        have = tokens(page.get_text())
        if not have:
            continue
        score = len(want & have) / (len(want) or 1)
        if score > best:
            best, best_i = score, i
    return best_i, best

def task_block(page, num):
    """Вернуть (y0, y1) блока задачи с номером num; None, если номер не найден."""
    blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
    pat = re.compile(r"^\s*(?:Задача\s*)?%s\s*[.)]" % re.escape(str(num)))
    nxt = re.compile(r"^\s*(?:Задача\s*)?\d{1,2}\s*[.)]")
    y0 = None
    for b in blocks:
        txt = b[4]
        if y0 is None:
            if pat.match(txt):
                y0 = b[1] - 4
        elif nxt.match(txt) and not pat.match(txt):
            return y0, b[1] - 2
    return (y0, page.rect.y1) if y0 is not None else None

def rects_on_page(page):
    rects = []
    for d in page.get_drawings():
        r = d.get("rect")
        if r and r.width >= 2 and r.height >= 2:
            rects.append(fitz.Rect(r))
    for img in page.get_images(full=True):
        try:
            for r in page.get_image_rects(img[0]):
                rects.append(fitz.Rect(r))
        except Exception:
            pass
    return rects

def cluster(rects):
    rects = [fitz.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out = []
        while rects:
            a = rects.pop()
            grown = fitz.Rect(a.x0 - GAP, a.y0 - GAP, a.x1 + GAP, a.y1 + GAP)
            merged = False
            for i, b in enumerate(out):
                if grown.intersects(b):
                    out[i] = b | a; merged = changed = True; break
            if not merged:
                out.append(a)
        rects = out if changed else []
        if not changed:
            return out
    return rects

def extract_for_task(doc, task):
    pi, score = pick_page(doc, task)
    if pi is None or score < 0.12:
        return "page_not_found", None, []
    page = doc[pi]
    H = page.rect.height
    blk = task_block(page, task.get("num"))
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
    return ("extracted" if cands else "no_figure_on_page"), pi, [(page, r, bool(blk)) for r in cands]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--csv", default="reports/olymp_figs_extract.csv")
    a = ap.parse_args()

    path = DATA / f"{a.slug}.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    FIGS.mkdir(parents=True, exist_ok=True)
    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    rows, done, changed = [], 0, False
    for t in tasks:
        if (t.get("fig_statement") or t.get("fig_solution")):
            continue
        blob = " ".join(str(t.get(k) or "") for k in ("text", "solution"))
        if not FIG_WORDS.search(blob):
            continue
        src = (t.get("source") or "").split(";")[0].strip()
        url = src.split("#")[0]
        rec = dict(slug=a.slug, uid=t["uid"][:12], year=t.get("year"), grade=t.get("grade"), num=t.get("num"),
                   source=url, page="", figs=0, block_found="", status="",
                   url=f"https://formyla.net/olymp-catalog/{a.slug}/{t['uid'][:12]}")
        if ".pdf" not in url.lower():
            rows.append({**rec, "status": "no_pdf"}); continue
        data = fetch_pdf(url)
        if not data:
            rows.append({**rec, "status": "download_failed"}); continue
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception:
            rows.append({**rec, "status": "download_failed"}); continue
        status, pi, items = extract_for_task(doc, t)
        rec.update(page=(pi + 1) if pi is not None else "", status=status,
                   block_found=(items[0][2] if items else ""))
        if status == "extracted" and not a.dry_run:
            paths = []
            for k, (page, r, _) in enumerate(items[:4]):
                name = f"{t['uid']}_statement{'' if k == 0 else '_' + str(k + 1)}.png"
                clip = fitz.Rect(r.x0 - 4, r.y0 - 4, r.x1 + 4, r.y1 + 4) & page.rect
                pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip, alpha=False)
                pix.save(str(FIGS / name))
                paths.append("FINAL_FIGURES/" + name)
            t["fig_statement"] = paths
            t["fig_extracted_auto"] = True
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
    cols = ["status", "slug", "year", "grade", "num", "uid", "page", "figs", "block_found", "source", "url"]
    with open(a.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    print("ЭКСТРАКЦИЯ:", dict(Counter(r["status"] for r in rows)), "| всего рисунков:", sum(int(r.get("figs") or 0) for r in rows))
    print("Отчёт:", a.csv)

if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
Извлечение рисунков для задач каталога (v3).

  python scripts/olymp_catalog_figs_extract.py [--slug all] [--limit N] [--dry-run]

Источники:
  * PDF  — страница по словам текста (или по текстовому якорю на любой странице), блок задачи по номеру/якорю,
           графика (вектор + растр) внутри блока; если графики нет — пробуются «соседние» PDF условий;
           ФОЛБЭК: если блок найден, а графики нет — снимок всего блока задачи (fig_anchor = "block_snapshot"),
           чтобы рисунок, набранный символами/таблицей, всё равно был виден.
  * HTML — страница скачивается, ищется якорь задачи (номер или фраза условия), берутся <img> между якорем
           и следующим номером; картинки скачиваются и сохраняются как PNG/оригинал.
Статусы: extracted / snapshot / no_figure_on_page / page_not_found / download_failed / no_source / no_anchor.
"""
import argparse, csv, hashlib, html, json, re, sys, time
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

import requests
import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "olymp_catalog"
FIGS = ROOT / "static" / "olymp_figures" / "FINAL_FIGURES"
CACHE = ROOT / ".cache_pdf"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FORMYLA figs extractor"}

FIG_WORDS = re.compile(
    r"рисун|чертеж|чертёж|см\.\s*рис|на\s+картинк|изображ[её]н|закрашен|заштрихован|серы[хе]\s+клет|"
    r"ч[её]рны[ехм]\s+клет|клет(?:ки|ок)\s+ч[её]рн|бел(?:ые|ых)\s+клет|фигурк|показан[оа]?\s+на|"
    r"приведен[оа]?\s+на\s+рис|диаграмм|на\s+доске\s+(?:нарисован|изображ)|развёртк|разверт", re.IGNORECASE)
WORD_RE = re.compile(r"[а-яёa-z]{4,}", re.IGNORECASE)
NUM_RE = re.compile(r"^\s*(?:Задача\s*)?(\d{1,2})\s*[.)]")
ZOOM = 3.0
MIN_W, MIN_H = 36, 22
HEADER_FRAC, FOOTER_FRAC = 0.07, 0.06
GAP = 10

def tokens(s):
    return set(w.lower() for w in WORD_RE.findall(s or ""))

def http_get(url):
    for verify in (True, False):
        for _ in range(2):
            try:
                r = requests.get(url, headers=UA, timeout=60, verify=verify)
                if r.status_code == 404:
                    return None
                if r.ok:
                    return r
            except Exception:
                time.sleep(1.5)
    return None

def fetch_bytes(url):
    CACHE.mkdir(exist_ok=True)
    p = CACHE / hashlib.sha1(url.encode()).hexdigest()
    if p.exists():
        return p.read_bytes()
    r = http_get(url)
    if r is None:
        return None
    p.write_bytes(r.content)
    return r.content

def sibling_urls(url):
    out = []
    for a, b in (("-sol-", "-tasks-"), ("-sol-", "-task-"), ("-sol-", "-"), ("_sol_", "_"), ("_sol.", "."),
                 ("_sol-", "-"), ("-sol.", "."), ("sol_", ""), ("-solutions", ""), ("_solutions", ""),
                 ("taskssol", "tasks"), ("resh", "usl"), ("otvety", "zadaniya"), ("_otv", ""), ("-otv", "")):
        if a in url:
            out.append(url.replace(a, b, 1))
    return [u for u in dict.fromkeys(out) if u != url]

def phrases(text):
    words = re.findall(r"[А-Яа-яЁёA-Za-z]{3,}", text or "")
    for n in (6, 5, 4):
        for i in range(0, max(1, len(words) - n), 2):
            yield " ".join(words[i:i + n])

def pick_page(doc, task):
    want = tokens(task.get("text", "")) | tokens(task.get("solution", "")[:600])
    best, best_i = 0.0, None
    for i, page in enumerate(doc):
        have = tokens(page.get_text())
        if have:
            score = len(want & have) / (len(want) or 1)
            if score > best:
                best, best_i = score, i
    if best >= 0.12:
        return best_i
    for ph in list(phrases(task.get("text", "")))[:12]:
        for i, page in enumerate(doc):
            if page.search_for(ph):
                return i
    return None

def task_block(page, num, text):
    blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
    y0, anchor = None, "num"
    for b in blocks:
        m = NUM_RE.match(b[4])
        if m and m.group(1) == str(num):
            y0 = b[1] - 4; break
    if y0 is None:
        for ph in phrases(text):
            hits = page.search_for(ph)
            if hits:
                y0 = min(h.y0 for h in hits) - 4; anchor = "text"; break
    if y0 is None:
        return None, "none"
    y1 = page.rect.y1 * (1 - FOOTER_FRAC)
    for b in blocks:
        m = NUM_RE.match(b[4])
        if b[1] > y0 + 8 and m and m.group(1) != str(num):
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

def extract_pdf(doc, task):
    pi = pick_page(doc, task)
    if pi is None:
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
    if cands:
        return "extracted", pi, [(page, r) for r in cands], anchor
    if blk and (y1 - y0) >= 30:
        return "snapshot", pi, [(page, fitz.Rect(page.rect.x0 + 20, y0, page.rect.x1 - 20, y1))], "block_snapshot"
    return "no_figure_on_page", pi, [], anchor

IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")

def extract_html(url, body, task):
    text = html.unescape(body)
    plain = TAG_RE.sub(" ", text)
    pos = None
    for ph in phrases(task.get("text", "")):
        i = plain.find(ph)
        if i >= 0:
            pos = i; break
    if pos is None:
        m = re.search(r"(?:^|[\s>])(?:Задача\s*)?%s\s*[.)]" % re.escape(str(task.get("num"))), plain)
        if m:
            pos = m.start()
    if pos is None:
        return "no_anchor", []
    # перенос позиции из plain-текста в html: грубо — ищем ту же фразу в html
    anchor_phrase = plain[pos:pos + 40].strip()
    hpos = text.find(anchor_phrase[:25])
    if hpos < 0:
        hpos = 0
    tail = text[hpos:]
    nxt = re.search(r">\s*(?:Задача\s*)?%d\s*[.)]" % (int(str(task.get("num")) or 0) + 1 if str(task.get("num")).isdigit() else 999), tail)
    seg = tail[: nxt.start()] if nxt else tail[:6000]
    srcs = [urljoin(url, s) for s in IMG_RE.findall(seg)]
    srcs = [s for s in srcs if not re.search(r"logo|icon|banner|button|counter|spacer|pixel", s, re.I)]
    return ("extracted" if srcs else "no_figure_on_page"), srcs[:4]

def save_pdf_items(items, uid):
    paths = []
    for k, (page, r) in enumerate(items[:4]):
        name = f"{uid}_statement{'' if k == 0 else '_' + str(k + 1)}.png"
        clip = fitz.Rect(r.x0 - 4, r.y0 - 4, r.x1 + 4, r.y1 + 4) & page.rect
        page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip, alpha=False).save(str(FIGS / name))
        paths.append("FINAL_FIGURES/" + name)
    return paths

def save_html_imgs(srcs, uid):
    paths = []
    for k, s in enumerate(srcs):
        data = fetch_bytes(s)
        if not data or len(data) < 800:
            continue
        ext = ".png"
        if data[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        elif data[:4] == b"GIF8":
            ext = ".gif"
        elif b"<svg" in data[:300].lower():
            ext = ".svg"
        name = f"{uid}_statement{'' if not paths else '_' + str(len(paths) + 1)}{ext}"
        (FIGS / name).write_bytes(data)
        paths.append("FINAL_FIGURES/" + name)
    return paths

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
        rec = dict(slug=slug, uid=t["uid"][:12], year=t.get("year"), grade=t.get("grade"), num=t.get("num"),
                   source="", page="", figs=0, anchor="", status="",
                   url=f"https://formyla.net/olymp-catalog/{slug}/{t['uid'][:12]}")
        srcs = [s.strip().split("#")[0] for s in (t.get("source") or "").split(";") if s.strip().startswith("http")]
        if not srcs:
            rows.append({**rec, "status": "no_source"}); continue
        status, paths, anchor, used, pi = "download_failed", [], "", srcs[0], None
        for url in srcs:
            cands = [url] + (sibling_urls(url) if ".pdf" in url.lower() else [])
            for cand in cands:
                data = fetch_bytes(cand)
                if not data:
                    continue
                used = cand
                if data[:5] == b"%PDF-":
                    try:
                        doc = fitz.open(stream=data, filetype="pdf")
                    except Exception:
                        continue
                    st, pi, items, anchor = extract_pdf(doc, t)
                    status = st
                    if st in ("extracted", "snapshot"):
                        if not a.dry_run:
                            paths = save_pdf_items(items, t["uid"])
                        else:
                            paths = ["(dry)"] * len(items)
                        break
                else:
                    body = data.decode("utf-8", "ignore")
                    st, imgs = extract_html(cand, body, t)
                    status = st
                    if st == "extracted":
                        paths = save_html_imgs(imgs, t["uid"]) if not a.dry_run else ["(dry)"] * len(imgs)
                        anchor = "html"
                        if paths:
                            break
                        status = "no_figure_on_page"
            if paths:
                break
        rec.update(source=used, page=(pi + 1) if pi is not None else "", status=status, anchor=anchor, figs=len(paths))
        if paths and not a.dry_run:
            t["fig_statement"] = paths
            t["fig_extracted_auto"] = True
            t["fig_anchor"] = anchor
            changed = True
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
    print("  по якорю:", dict(Counter(r["anchor"] for r in rows if r["figs"])))
    print("Отчёт:", a.csv)

if __name__ == "__main__":
    sys.exit(main())

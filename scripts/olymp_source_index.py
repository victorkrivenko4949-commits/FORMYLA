#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Индекс официальных PDF-материалов олимпиад (для этапов 18, 20, 21).

Строится в два шага:
  Шаг 1 — из существующих source в базе: извлекаются id олимпиады, год,
  класс, этап и тип материала (условия/решения/ответы) из имён файлов.
  Шаг 2 — обход страницы олимпиады https://olimpiada.ru/activity/<id>
  и её подстраниц с заданиями: собираются все ссылки на PDF.

Кэш: work/source_index/<slug>.json (TTL по умолчанию неделя,
переменная OLYMP_INDEX_TTL_HOURS; OLYMP_INDEX_CRAWL=0 отключает шаг 2).
"""

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olymp_fix_rules as R  # canon_round_key и др.

log = logging.getLogger("olymp_source_index")

UA = {"User-Agent": "Mozilla/5.0 (olymp-fix pipeline; FORMYLA)"}
DEFAULT_TTL_HOURS = 168

# Известные id олимпиад на olimpiada.ru (остальные определяются по source в базе)
KNOWN_ACTIVITY_IDS = {"phystech": "395", "kurchatov": "389"}

# Хосты, из которых индексируем PDF: официальные сайты + сам olimpiada.ru
# (агрегатор официальных материалов, с него раздаются задания)
INDEX_HOSTS = R.OFFICIAL_DOMAINS | {"olimpiada.ru"}

# Извлечение id олимпиады из существующих source
SOURCE_ID_PATTERNS = [
    re.compile(r"tasks\.olimpiada\.ru/upload/files/tasks/(\d+)"),
    re.compile(r"rsr-olymp\.ru/upload/files/tasks/(\d+)"),
]
ACTIVITY_URL_RE = re.compile(r"olimpiada\.ru/activity/(\d+)")

# Разбор имени файла / текста ссылки
YEAR_RE = re.compile(r"(19|20)\d{2}")
# Сезон «24-25» -> год 2024 (начало сезона)
SEASON_RE = re.compile(r"(?:^|[-_])(\d{2})-(\d{2})(?=\.|$|[-_])")
GRADE_PATTERNS = [
    re.compile(r"(\d{1,2})\s*[–—‒\-_]\s*(\d{1,2})\s*klass", re.I),
    re.compile(r"(\d{1,2})[\s_\-]*klass", re.I),
    re.compile(r"klass[\s_\-]*(\d{1,2})", re.I),
    re.compile(r"(\d{1,2})\s*класс", re.I),
    # olimpiada.ru: «395-tasks-math-11-tur1-otbor-24-25.pdf» — класс после math
    re.compile(r"math[\-_](\d{1,2})(?:[\-_](\d{1,2}))?[\-_]", re.I),
]
ROUND_PATTERNS = [
    (re.compile(r"final|zakl|закл|финал", re.I), "final"),
    (re.compile(r"otbor|qualif|отбор", re.I), "qual"),
    (re.compile(r"regional|регион", re.I), "regional"),
    (re.compile(r"2\s*tour|tour\s*2|2\s*тур|2\s*etap|2\s*этап|второй", re.I), "final"),
    (re.compile(r"1\s*tour|tour\s*1|1\s*тур|1\s*etap|1\s*этап|первый", re.I), "qual"),
]
KIND_PATTERNS = [
    (re.compile(r"reshen|otvet|otvety|решен|ответ|[\-_]sol[\-_\.]|sol_", re.I), "sol"),
    (re.compile(r"krit|критер", re.I), "ans"),
    (re.compile(r"zadach|zadani|zad\b|uslov|услов|задач|задани|[\-_]tasks[\-_\.]", re.I), "tasks"),
]

LINK_RE = re.compile(r'<a\s[^>]*?href="([^"#]+)"[^>]*>([\s\S]*?)</a>', re.I)


def is_allowed_host(url: str) -> bool:
    """Хост URL — из числа индексируемых официальных."""
    m = re.match(r"https?://([^/?#\s]+)", url)
    if not m:
        return False
    host = m.group(1).lower()
    host = host[4:] if host.startswith("www.") else host
    return host in INDEX_HOSTS or any(host.endswith("." + d) for d in INDEX_HOSTS)


def parse_filename_meta(name: str) -> dict:
    """Метаданные из имени PDF-файла или текста ссылки.

    Возвращает {"year": int|None, "grades": [int]|None,
                "round_key": str|None, "kind": "sol"|"tasks"|"ans"|None}.
    Год: полный (2024) или сезон «24-25» -> 2024.
    """
    meta = {"year": None, "grades": None, "round_key": None, "kind": None}
    m = YEAR_RE.search(name)
    if m:
        meta["year"] = int(m.group(0))
    else:
        # Сезон «24-25» (например, 2024/2025 учебный год) -> 2024
        m = SEASON_RE.search(name)
        if m:
            y = 2000 + int(m.group(1))
            if 2000 <= y <= 2100:
                meta["year"] = y
    grades = set()
    for pat in GRADE_PATTERNS:
        for m in pat.finditer(name):
            lo = int(m.group(1))
            hi = int(m.group(2)) if (m.lastindex and m.lastindex >= 2 and m.group(2)) else lo
            # Диапазон «9-11» раскрываем полностью: 9, 10, 11
            if hi > lo:
                grades.update(range(lo, min(hi, 11) + 1))
            else:
                grades.add(lo)
    if grades:
        meta["grades"] = sorted(g for g in grades if 1 <= g <= 11)
    for pat, key in ROUND_PATTERNS:
        if pat.search(name):
            meta["round_key"] = key
            break
    for pat, kind in KIND_PATTERNS:
        if pat.search(name):
            meta["kind"] = kind
            break
    return meta


def catalog_index_records(slug: str, records: list) -> tuple[list, str | None]:
    """Шаг 1: записи индекса из существующих source в базе.

    Возвращает (records, activity_id). Метаданные берём из самой записи
    (год/класс/этап надёжнее), недостающее — из имени файла.
    """
    out_by_url: dict[str, dict] = {}
    activity_id = None
    for rec in records:
        src = (rec.get("source") or "").strip()
        if not src:
            continue
        # id олимпиады из любого source (не только PDF)
        if activity_id is None:
            for pat in SOURCE_ID_PATTERNS:
                m = pat.search(src)
                if m:
                    activity_id = m.group(1)
                    break
            if activity_id is None:
                m = ACTIVITY_URL_RE.search(src)
                if m:
                    activity_id = m.group(1)
        clean = src.split("?")[0]
        if not clean.lower().endswith(".pdf"):
            continue
        if not is_allowed_host(src):
            continue
        name = unquote(clean.split("/")[-1])
        meta = parse_filename_meta(name)
        year = meta.get("year") or rec.get("year")
        grades = meta.get("grades")
        try:
            grade_int = int(str(rec.get("grade", "")))
            grades = [grade_int]
        except (ValueError, TypeError):
            pass
        round_key = R.canon_round_key(rec.get("round") or "", slug) or meta.get("round_key")
        kind = meta.get("kind")
        if not kind:
            kind = "sol" if re.search(r"resh|otv|otvet|решен|ответ", name, re.I) else "tasks"
        entry = {"url": src, "year": year, "grades": grades,
                 "round_key": round_key, "kind": kind, "origin": "catalog"}
        prev = out_by_url.get(src)
        if prev is None:
            out_by_url[src] = entry
        else:
            # Один и тот же PDF в source многих задач: сливаем метаданные
            if prev.get("year") is None and year is not None:
                prev["year"] = year
            if not prev.get("grades") and grades:
                prev["grades"] = grades
            if not prev.get("round_key") and round_key:
                prev["round_key"] = round_key
            if not prev.get("kind") and kind:
                prev["kind"] = kind
    return list(out_by_url.values()), activity_id


# Последовательный разбор: заголовки секций и PDF-ссылки в порядке документа
PAGE_TOKEN_RE = re.compile(
    r"<(h[1-4]|b|strong)[^>]*>([\s\S]*?)</\1>"
    r"|<a\s[^>]*?href=\"([^\"]+)\"[^>]*>([\s\S]*?)</a>", re.I)


# Заголовки секций: только названия этапов, БЕЗ тур-паттернов —
# иначе h4 «2 тур» затирает контекст родительского h3 «Отборочный этап»
HEADER_ROUND_PATTERNS = ROUND_PATTERNS[:3]


def _round_key_from_header(text: str) -> str | None:
    """Этап из заголовка секции («Отборочный этап», «Заключительный» и т.п.).

    Подтуры («1 тур», «2 тур») НЕ считаем этапом — они вложены в этап.
    """
    t = text.strip().lower()
    if not (2 <= len(t) <= 60):
        return None
    for pat, key in HEADER_ROUND_PATTERNS:
        if pat.search(t):
            return key
    return None


def _parse_tasks_page(url: str, html: str, pdfs: dict):
    """Разбор страницы заданий olimpiada.ru с контекстом заголовков.

    Структура: h3 «Отборочный этап» / h4 «1 тур», внутри — ссылки на PDF
    («Задания», «Решения», «Критерии»). Год и класс — из query (?class=..&year=..)
    или пути /tasks/<year>, метаданные — из имени файла + текста ссылки + контекста.
    """
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    page_year = None
    page_class = None
    if "year" in qs and qs["year"][0].isdigit():
        page_year = int(qs["year"][0])
    if "class" in qs and qs["class"][0].isdigit():
        page_class = int(qs["class"][0])
    m = re.search(r"/tasks/(\d{4})", parsed.path)
    if page_year is None and m:
        page_year = int(m.group(1))
    ctx_round = None
    for m in PAGE_TOKEN_RE.finditer(html):
        if m.group(1):  # заголовок секции — обновляем контекст этапа
            text = re.sub(r"<[^>]+>", " ", m.group(2))
            text = re.sub(r"\s+", " ", text).strip()
            rk = _round_key_from_header(text)
            if rk:
                ctx_round = rk
            continue
        href, text = m.group(3), m.group(4)
        href = href.strip()
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if ".pdf" not in href.lower().split("?")[0]:
            continue
        absu = urljoin(url, href)
        if not is_allowed_host(absu):
            continue
        name = unquote(absu.split("?")[0].split("/")[-1])
        meta = parse_filename_meta(name + " " + text)
        # Дополняем из контекста страницы
        if meta.get("year") is None and page_year:
            meta["year"] = page_year
        if not meta.get("grades") and page_class:
            meta["grades"] = [page_class]
        if not meta.get("round_key") and ctx_round:
            meta["round_key"] = ctx_round
        prev = pdfs.get(absu)
        if prev is None:
            pdfs[absu] = meta
        else:
            for k, v in meta.items():
                if prev.get(k) in (None, [], "") and v:
                    prev[k] = v


def crawl_activity(activity_id: str, max_pages: int = 150, timeout: int = 30) -> list:
    """Шаг 2: обход страницы олимпиады и её подстраниц, сбор PDF-ссылок.

    Стартуем с главной и /tasks (там лежат задания по годам).
    /tasks-страницы разбираются с контекстом заголовков (_parse_tasks_page),
    остальные — простым сбором ссылок. Приоритет обхода: /tasks страницы первыми.
    """
    crawl_enabled = os.environ.get("OLYMP_INDEX_CRAWL", "1") != "0"
    if not crawl_enabled:
        log.info("Индекс: обход olimpiada.ru отключён (OLYMP_INDEX_CRAWL=0).")
        return []
    from collections import deque
    root = f"https://olimpiada.ru/activity/{activity_id}"
    tasks_root = f"{root}/tasks"
    visited = set()
    queue = deque([root, tasks_root])
    pdfs: dict[str, dict] = {}
    pages = 0
    while queue and pages < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        try:
            resp = requests.get(url, headers=UA, timeout=timeout)
        except Exception as e:
            log.warning("Индекс: не удалось скачать %s: %s", url, str(e)[:120])
            continue
        if resp.status_code != 200:
            continue
        pages += 1
        html = resp.text
        if "/tasks" in url:
            # Страница заданий: разбор с контекстом заголовков секций
            _parse_tasks_page(url, html, pdfs)
        # Ссылки для дальнейшего обхода + PDF на любых страницах
        for m in LINK_RE.finditer(html):
            href = m.group(1).strip()
            absu = urljoin(url, href)
            if ".pdf" in absu.lower().split("?")[0]:
                # PDF мог быть уже собран с контекстом на /tasks-странице;
                # здесь только дополняем недостающее
                if is_allowed_host(absu):
                    text = re.sub(r"<[^>]+>", " ", m.group(2))
                    text = re.sub(r"\s+", " ", text).strip()
                    name = unquote(absu.split("?")[0].split("/")[-1])
                    meta = parse_filename_meta(name + " " + text)
                    prev = pdfs.get(absu)
                    if prev is None:
                        pdfs[absu] = meta
                    else:
                        for k, v in meta.items():
                            if prev.get(k) in (None, [], "") and v:
                                prev[k] = v
                continue
            if re.search(rf"olimpiada\.ru/activity/{activity_id}(/|$)", absu) \
                    and absu not in visited:
                if "/tasks" in absu:
                    queue.appendleft(absu)   # задания — приоритет
                else:
                    queue.append(absu)
    records = [{"url": u, **meta, "origin": "crawl"} for u, meta in pdfs.items()]
    log.info("Индекс: activity %s — %d страниц, %d PDF.", activity_id, pages, len(records))
    return records


class SourceIndex:
    """Кэшируемый индекс официальных PDF по олимпиадам."""

    def __init__(self, cache_dir: Path, rebuild: bool = False, ttl_hours: int = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rebuild = rebuild
        self.ttl_hours = ttl_hours or int(os.environ.get("OLYMP_INDEX_TTL_HOURS",
                                                        str(DEFAULT_TTL_HOURS)))
        self._cache: dict[str, dict] = {}

    def build(self, slug: str, records: list) -> dict:
        """Строит или загружает из кэша индекс для олимпиады."""
        cache_path = self.cache_dir / f"{slug}.json"
        if not self.rebuild and cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                age_h = (time.time() - data.get("built_at_ts", 0)) / 3600.0
                if age_h < self.ttl_hours:
                    self._cache[slug] = data
                    log.info("Индекс %s: из кэша (%d записей, возраст %.1f ч).",
                             slug, len(data.get("records", [])), age_h)
                    return data
            except Exception as e:
                log.warning("Индекс %s: кэш повреждён (%s) — перестраиваем.", slug, e)
        # Шаг 1: из source в базе
        cat_records, activity_id = catalog_index_records(slug, records)
        if activity_id is None:
            activity_id = KNOWN_ACTIVITY_IDS.get(slug)
        # Шаг 2: обход страницы олимпиады
        crawl_records = []
        if activity_id:
            try:
                crawl_records = crawl_activity(activity_id)
            except Exception as e:
                log.warning("Индекс %s: обход olimpiada.ru не удался: %s", slug, str(e)[:200])
        # Слияние по URL: один PDF не должен занимать несколько слотов
        merged: dict[str, dict] = {}
        for r in cat_records + crawl_records:
            url = r.get("url", "")
            prev = merged.get(url)
            if prev is None:
                merged[url] = dict(r)
            else:
                for k, v in r.items():
                    if prev.get(k) in (None, [], "") and v:
                        prev[k] = v
        index = {
            "slug": slug,
            "activity_id": activity_id,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "built_at_ts": time.time(),
            "records": list(merged.values()),
        }
        # Атомарная запись кэша
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, cache_path)
        self._cache[slug] = index
        log.info("Индекс %s построен: %d записей из базы, %d с сайта (activity_id=%s).",
                 slug, len(cat_records), len(crawl_records), activity_id)
        return index

    def get(self, slug: str) -> dict:
        if slug not in self._cache:
            self._cache[slug] = {"slug": slug, "activity_id": None,
                                 "records": [], "built_at_ts": 0}
        return self._cache[slug]

    def find(self, slug: str, year, round_key: str | None, grade,
             kinds=("sol", "ans", "tasks")) -> list[dict]:
        """Поиск PDF в индексе по (год, этап, класс).

        Записи без года/этапа/класса считаются подходящими любому
        (совпадение по остальным полям), но ранжируются ниже.
        """
        idx = self._cache.get(slug)
        if idx is None:
            return []
        try:
            year = int(year) if year is not None else None
        except (ValueError, TypeError):
            year = None
        try:
            grade_int = int(grade) if grade is not None else None
        except (ValueError, TypeError):
            grade_int = None
        matches = []
        for r in idx.get("records", []):
            if kinds and r.get("kind") not in kinds:
                continue
            r_year = r.get("year")
            if year is not None and r_year is not None and int(r_year) != year:
                continue
            if round_key and r.get("round_key") and r["round_key"] != round_key:
                continue
            r_grades = r.get("grades")
            if grade_int is not None and r_grades \
               and grade_int not in [int(g) for g in r_grades]:
                continue
            matches.append(r)

        def score(r):
            return (
                0 if r.get("kind") == "sol" else 1,   # решения приоритетнее
                0 if r.get("year") == year else 1,
                0 if (round_key and r.get("round_key") == round_key) else 1,
                0 if (grade_int is not None and r.get("grades")
                      and grade_int in [int(g) for g in r["grades"]]) else 1,
            )

        # Дедупликация по URL до ограничения сверху
        seen_urls = set()
        deduped = []
        for r in sorted(matches, key=score):
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                deduped.append(r)
        return deduped

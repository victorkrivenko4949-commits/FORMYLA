#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Индекс официальных PDF-материалов олимпиад (для этапов 18, 20, 21).

Строится в два шага:
  Шаг 1 — из существующих source в базе: извлекаются id олимпиады, год,
  класс, этап, вариант и тип материала из имён файлов.
  Шаг 2 — обход архивов на родных сайтах олимпиад (у каждой — свой обходчик):
    mmo.mccme.ru (ММО), olympiads.mccme.ru/matprazdnik (Матпраздник),
    matol.ru (Эйлер), olymp.mipt.ru + olimpiada.ru/activity/395 (Физтех),
    kurchatov-olymp.ru + olimpiada.ru/activity/389 (Курчатов),
    turgor.ru/problems (Турнир городов), olymp.hse.ru (Высшая проба),
    olimpiada.spbu.ru (СПбГУ), pvg.mk.ru (ПВГ), formulo.org (Формула Единицы),
    olymp.msu.ru (Ломоносов), vos.olimpiada.ru (ВсОШ закл.).
  Для Турнира городов один PDF покрывает несколько классов — grades=None
  (подходит любому классу).

Кэш: work/source_index/<slug>.json (TTL 7 дней, OLYMP_INDEX_TTL_HOURS;
OLYMP_INDEX_CRAWL=0 отключает обход сайтов; --rebuild-index).
"""

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olymp_fix_rules as R  # canon_round_key и др.

log = logging.getLogger("olymp_source_index")

# Полноценный браузерный User-Agent (часть сайтов режет «curl-like» UA)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
      "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}

DEFAULT_TTL_HOURS = 168  # неделя

# Известные id олимпиад на olimpiada.ru (остальные определяются по source в базе)
KNOWN_ACTIVITY_IDS = {
    "vsosh": "72",
    "mmo": "1",
    "kurchatov": "389",
    "turgor": "5",
    "lomonosov": "348",
    "formula-unity": "223",
    "pvg": "115",
    "euler": "29",
    "vysshaya-proba": "149",
    "matprazdnik": "7",
    "spbgu": "443",
    "phystech": "395",
}

# Извлечение id олимпиады из существующих source
SOURCE_ID_PATTERNS = [
    re.compile(r"tasks\.olimpiada\.ru/upload/files/tasks/(\d+)"),
    re.compile(r"rsr-olymp\.ru/upload/files/tasks/(\d+)"),
]
ACTIVITY_URL_RE = re.compile(r"olimpiada\.ru/activity/(\d+)")

# ---------------------------------------------------------------------
# Обходчики родных сайтов: seeds + follow (регулярка для подстраниц)
# ---------------------------------------------------------------------
SITE_SPECS: dict[str, dict] = {
    "mmo": {"seeds": ["https://mmo.mccme.ru/"],
            "follow": re.compile(r"mmo\.mccme\.ru(/\d{4}/|/[^/]*\.htm)", re.I)},
    "matprazdnik": {"seeds": ["https://olympiads.mccme.ru/matprazdnik/"],
                    "follow": re.compile(r"olympiads\.mccme\.ru/matprazdnik", re.I)},
    "euler": {"seeds": ["https://matol.ru/"], "follow": None},
    "phystech": {"seeds": ["https://olymp.mipt.ru/"],
                 "follow": re.compile(r"olymp\.mipt\.ru", re.I),
                 "activity": "395"},
    "kurchatov": {"seeds": ["https://kurchatov-olymp.ru/"], "follow": None,
                  "activity": "389"},
    "turgor": {"seeds": ["https://turgor.ru/problems/"],
               # один PDF покрывает несколько классов -> grades=None
               "follow": re.compile(r"turgor\.ru/(problems|arch)", re.I)},
    "vysshaya-proba": {"seeds": ["https://olymp.hse.ru/olymp"],
                       "follow": re.compile(r"olymp\.hse\.ru", re.I)},
    "spbgu": {"seeds": ["https://olimpiada.spbu.ru/"], "follow": None},
    "pvg": {"seeds": ["https://pvg.mk.ru/archive/archive/"],
            "follow": re.compile(r"pvg\.mk\.ru", re.I)},
    "formula-unity": {"seeds": ["https://www.formulo.org/ru/olymp/"],
                     "follow": re.compile(r"formulo\.org", re.I)},
    "lomonosov": {"seeds": ["https://olymp.msu.ru/"],
                  "follow": re.compile(r"olymp\.msu\.ru/rus/", re.I)},
    "vsosh": {"seeds": ["https://vos.olimpiada.ru/"],
              "follow": re.compile(r"vos\.olimpiada\.ru/20\d\d/", re.I)},
}

# ---------------------------------------------------------------------
# Разбор имени файла / текста ссылки
# ---------------------------------------------------------------------
YEAR_RE = re.compile(r"(19|20)\d{2}")
# Сезон «24-25» -> 2025: год ФИНАЛА, как принято в базе
# (отборочный сезона 23-24 лежит в базе под 2024).
# Валидируем: второй год = первый + 1 (иначе «11-01» ложно распознаётся как сезон)
SEASON_RE = re.compile(r"(?:^|[-_])(\d{2})-(\d{2})(?=\.|$|[-_])")
SEASON_4_RE = re.compile(r"(20[012]\d)\s*[-_/–—]\s*(20[012]\d)")
SEASON_4_2_RE = re.compile(r"(20[012]\d)\s*[-_–—]\s*([012]\d)(?!\d)")
SEASON_2_1_RE = re.compile(r"(?:^|[-_])([12]\d)-(\d)(?=\.|$|[-_])")
GRADE_PATTERNS = [
    re.compile(r"(\d{1,2})\s*[–—‒\-_]\s*(\d{1,2})\s*klass", re.I),
    re.compile(r"(\d{1,2})[\s_\-]*klass", re.I),
    # «klass_1-4» — это варианты, а не класс 1: не брать число с диапазоном вслед
    re.compile(r"klass[\s_\-]*(\d{1,2})(?![\-\_]\d)", re.I),
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
    (re.compile(r"reshen|otvet|otvety|решен|ответ|[\-_]sol[\-_.]|sol_", re.I), "sol"),
    (re.compile(r"krit|критер", re.I), "ans"),
    (re.compile(r"zadach|zadani|zad\b|uslov|услов|задач|задани|[\-_]tasks[\-_.]", re.I), "tasks"),
]
# Вариант: «Вариант N», «Билет N», «в. N», «var N»
VARIANT_PATTERNS = [
    # «Вариант 2», «билет 5» — но НЕ «вариантов 11-01» (варианты класса 11)
    # «Вариант 2», «билеты 1-2» — но НЕ «вариантов 11-01» (класс-вариант)
    # и не «11-01» с нулём во второй паре (разрешаем диапазон «1-2»)
    re.compile(r"вариант(?:а|ы)?\s*№?\s*(\d+)(?!\d)(?!\s*-\s*0\d)", re.I),
    re.compile(r"билет(?:а|ы)?\s*№?\s*(\d+)(?!\d)(?!\s*-\s*0\d)", re.I),
    re.compile(r"(?:^|[\s\-_.,(])в\.\s*(\d+)(?!\d)(?!\s*-\s*0\d)", re.I),
    re.compile(r"(?:^|[\-_])variant[^\d]{0,5}(\d+)", re.I),
    re.compile(r"(?:^|[\-_])var[\-_\.]?(\d+)", re.I),
]
# День: «(день M)», «день M»
DAY_RE = re.compile(r"день[^\d]{0,5}(\d+)|day[\-_](\d+)", re.I)
# Служебные PDF, не содержащие задач: регистрации, положения, регламенты
JUNK_PDF_RE = re.compile(
    r"reg(istr|pred|lament|ional|ul)|pravil|polozh|appell|appeal|"
    r"shkala|shedule|raspisan|schedule|sostav|itog|diplom|prikaz|zayavl|"
    r"zayavlen|blank[._-]|obrazec|sample|provision|tutorial|soglas|"
    r"uchastnik|trebovan|soglashen|forma[._-]otchet", re.I)

LINK_RE = re.compile(r'<a\s[^>]*?href="([^"#]+)"[^>]*>([\s\S]*?)</a>', re.I)

# Заголовки блоков в PDF: «Вариант N», «Билет N», «в. N»
BLOCK_HEADER_RE = re.compile(
    r"(?:вариант|билет)\s*№?\s*(\d+)|(?:^|[\s(])в\.\s*(\d+)", re.I)


def is_allowed_host(url: str) -> bool:
    """Хост URL — из числа индексируемых официальных."""
    m = re.match(r"https?://([^/?#\s]+)", url)
    if not m:
        return False
    host = m.group(1).lower()
    host = host[4:] if host.startswith("www.") else host
    return host in INDEX_HOSTS or any(host.endswith("." + d) for d in INDEX_HOSTS)


INDEX_HOSTS = R.OFFICIAL_DOMAINS | {
    "olimpiada.ru", "mmo.mccme.ru", "olimpiada.spbu.ru", "pvg.mk.ru",
}


def parse_filename_meta(name: str) -> dict:
    """Метаданные из имени PDF-файла или текста ссылки.

    Возвращает {"year", "grades", "round_key", "kind", "variant", "day"}.
    Год: полный (2024) или сезон «24-25» -> 2025 (год финала).
    """
    meta = {"year": None, "grades": None, "round_key": None, "kind": None,
            "variant": None, "day": None}
    sy = season_year_from_url(name)
    if sy is not None:
        meta["year"] = sy
    if meta["year"] is None:
        m = YEAR_RE.search(name)
        if m:
            meta["year"] = int(m.group(0))
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
    for pat in VARIANT_PATTERNS:
        m = pat.search(name)
        if m:
            meta["variant"] = str(int(m.group(1)))
            break
    m = DAY_RE.search(name)
    if m:
        day = m.group(1) or m.group(2)
        if day:
            meta["day"] = int(day)
    return meta



def season_year_from_url(url: str):
    """Год финала из сезона в имени файла URL («...-24-25.pdf» -> 2025) или None."""
    if not url:
        return None
    try:
        decoded = unquote((url or "").split("?")[0])
        name = decoded.split("/")[-1]
    except Exception:
        return None
    for m in SEASON_4_RE.finditer(decoded):
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y2 == y1 + 1 and 2000 <= y2 <= 2100:
            return y2
    for m in SEASON_4_2_RE.finditer(name):
        y1, b = int(m.group(1)), int(m.group(2))
        if b == (y1 % 100) + 1 and 2000 <= 2000 + b <= 2100:
            return 2000 + b
    for m in SEASON_RE.finditer(name):
        a, b = int(m.group(1)), int(m.group(2))
        # Исключаем «10-11» (классы 10–11, а не сезон 2010–2011)
        if a == 10 and b == 11:
            continue
        if b == a + 1 and 11 <= a <= 29:
            return 2000 + b
    for m in SEASON_2_1_RE.finditer(name):
        a, b = int(m.group(1)), int(m.group(2))
        if 11 <= a <= 29 and b == (a + 1) % 10 and f"20{a}" in decoded:
            return 2000 + a + 1
    return None


def year_from_url(url: str) -> int | None:
    """Год олимпиады из URL: сначала сезон (год финала), иначе одиночный 20xx."""
    if not url:
        return None
    sy = season_year_from_url(url)
    if sy is not None:
        return sy
    try:
        decoded = unquote((url or "").split("?")[0])
        name = decoded.split("/")[-1]
    except Exception:
        name = url
    name_years = [int(m.group(0)) for m in re.finditer(r"(?<!\d)(?:199\d|20[012]\d)(?!\d)", name)]
    if len(set(name_years)) == 1:
        return name_years[0]
    all_years = [int(m.group(0)) for m in re.finditer(r"(?<!\d)(?:199\d|20[012]\d)(?!\d)", decoded)]
    if len(set(all_years)) == 1:
        return all_years[0]
    return None


def is_junk_pdf(url: str, text: str = "") -> bool:
    """Служебный PDF (регистрация, положение, регламент) — не задачи."""
    name = unquote(url.split("?")[0].split("/")[-1])
    return bool(JUNK_PDF_RE.search(name + " " + text))


# ---------------------------------------------------------------------
# Шаг 1: записи индекса из существующих source в базе
# ---------------------------------------------------------------------

def catalog_index_records(slug: str, records: list) -> tuple[list, str | None]:
    """Шаг 1: записи индекса из существующих source в базе.

    Возвращает (records, activity_id). Метаданные берём из самой записи
    (год/класс/этап/вариант надёжнее), недостающее — из имени файла.
    """
    out_by_url: dict[str, dict] = {}
    known_aid = KNOWN_ACTIVITY_IDS.get(slug)
    activity_id = known_aid
    for rec in records:
        src = (rec.get("source") or "").strip()
        if not src:
            continue
        # Проверяем id олимпиады в URL olimpiada.ru / rsr-olymp.ru
        src_aid = None
        for pat in SOURCE_ID_PATTERNS:
            m = pat.search(src)
            if m:
                src_aid = m.group(1)
                break
        if src_aid is None:
            m = ACTIVITY_URL_RE.search(src)
            if m:
                src_aid = m.group(1)
        if activity_id is None and src_aid is not None:
            activity_id = src_aid
        # Если у олимпиады известен свой activity_id, не тащим чужие PDF (напр. 74 физика в vsosh)
        if known_aid and src_aid and src_aid != known_aid:
            continue
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
                 "round_key": round_key, "kind": kind,
                 "variant": rec.get("variant") or meta.get("variant"),
                 "day": meta.get("day"), "origin": "catalog"}
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
            if not prev.get("variant"):
                prev["variant"] = entry.get("variant")
    return list(out_by_url.values()), activity_id


# ---------------------------------------------------------------------
# Шаг 2а: обход родного сайта олимпиады (generic)
# ---------------------------------------------------------------------

def crawl_site(slug: str, spec: dict, max_pages: int = 60, timeout: int = 30) -> list:
    """Обход архива на родном сайте: страница архива -> ссылки на PDF.

    seeds — стартовые страницы; follow — регулярка для подстраниц
    (None — не ходить дальше стартовых). PDF собираем с каждой страницы,
    метаданные — из имени файла + текста ссылки.
    """
    from collections import deque
    visited = set()
    queue = deque(spec.get("seeds", []))
    follow = spec.get("follow")
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
            log.warning("Индекс %s: не удалось скачать %s: %s", slug, url, str(e)[:120])
            continue
        if resp.status_code != 200:
            continue
        pages += 1
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype and "xml" not in ctype:
            continue
        html = resp.text
        # Последовательный разбор: контекст секций (год/этап/классы из
        # заголовков) действует на PDF-ссылки внутри секции
        # (Турнир городов, ММО и др.)
        ctx_year, ctx_round, ctx_grades = None, None, None

        def _header_ctx(htext: str):
            """(год, этап, классы) из текста заголовка."""
            year, rk, grades = None, None, None
            ym = YEAR_RE.search(htext)
            if ym:
                try:
                    y = int(ym.group(0))
                    if 1990 <= y <= 2100:
                        year = y
                except ValueError:
                    pass
            rk = _round_key_from_header(htext)
            # «8-9 классы», «9–11 класс», «10 и 11 класс»
            g = re.search(r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*класс", htext, re.I)
            if g:
                lo, hi = int(g.group(1)), int(g.group(2))
                if 5 <= lo <= hi <= 11:
                    grades = list(range(lo, hi + 1))
            else:
                gs = re.findall(r"(\d{1,2})\s*класс", htext, re.I)
                gs = [int(x) for x in gs if 5 <= int(x) <= 11]
                if gs:
                    grades = sorted(set(gs))
            return year, rk, grades

        def _handle_link(href: str, text: str, y, rk, grades):
            absu = urljoin(url, href)
            if ".pdf" not in absu.lower().split("?")[0]:
                # Подстраницы архива
                if follow is not None and follow.search(absu) and absu not in visited:
                    same_host = urlparse(absu).netloc == urlparse(url).netloc
                    if same_host:
                        queue.append(absu)
                return
            if not is_allowed_host(absu) or is_junk_pdf(absu, text):
                return
            name = unquote(absu.split("?")[0].split("/")[-1])
            meta = parse_filename_meta(name + " " + text)
            # год/этап/классы из контекста секции страницы
            if meta.get("year") is None and y:
                meta["year"] = y
            if meta.get("round_key") is None and rk:
                meta["round_key"] = rk
            if not meta.get("grades") and grades:
                meta["grades"] = grades
            prev = pdfs.get(absu)
            if prev is None:
                pdfs[absu] = meta
            else:
                for k, v in meta.items():
                    if prev.get(k) in (None, [], "") and v:
                        prev[k] = v

        for m in PAGE_TOKEN_RE.finditer(html):
            if m.group(1):   # заголовок секции h1-h4/b/strong
                hhtml = m.group(2)
                htext = re.sub(r"<[^>]+>", " ", hhtml)
                htext = re.sub(r"\s+", " ", htext).strip()
                hy, hrk, hg = _header_ctx(htext)
                if hy:
                    ctx_year = hy
                if hrk:
                    ctx_round = hrk
                if hg:
                    ctx_grades = hg
                # ссылки ВНУТРИ заголовка: локальный контекст заголовка,
                # недостающее — из внешней секции (год раздела не теряется)
                for lm in LINK_RE.finditer(hhtml):
                    ltext = re.sub(r"<[^>]+>", " ", lm.group(2))
                    ltext = re.sub(r"\s+", " ", ltext).strip()
                    _handle_link(lm.group(1).strip(), ltext,
                                 hy or ctx_year, hrk or ctx_round,
                                 hg or ctx_grades)
                continue
            href = (m.group(3) or "").strip()
            text = re.sub(r"<[^>]+>", " ", m.group(4) or "")
            text = re.sub(r"\s+", " ", text).strip()
            if not href:
                continue
            _handle_link(href, text, ctx_year, ctx_round, ctx_grades)
    records = [{"url": u, **meta, "origin": "site"} for u, meta in pdfs.items()]
    log.info("Индекс %s: родной сайт — %d страниц, %d PDF.", slug, pages, len(records))
    return records


# ---------------------------------------------------------------------
# Шаг 2б: обход olimpiada.ru/activity/<id> (задания по годам)
# ---------------------------------------------------------------------

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
    from urllib.parse import parse_qs
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
        meta = parse_filename_meta(name)
        tmeta = parse_filename_meta(text)
        for _k, _v in tmeta.items():
            if meta.get(_k) in (None, [], "") and _v:
                meta[_k] = _v
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
    """Обход страницы олимпиады на olimpiada.ru и её /tasks-подстраниц."""
    crawl_enabled = os.environ.get("OLYMP_INDEX_CRAWL", "1") != "0"
    if not crawl_enabled:
        log.info("Индекс: обход сайтов отключён (OLYMP_INDEX_CRAWL=0).")
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


# ---------------------------------------------------------------------
# Индекс с кэшем
# ---------------------------------------------------------------------

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
        # Шаг 2: обходы — родной сайт + olimpiada.ru/activity (если есть)
        site_records = []
        spec = SITE_SPECS.get(slug)
        if spec:
            try:
                site_records = crawl_site(slug, spec)
            except Exception as e:
                log.warning("Индекс %s: обход родного сайта не удался: %s",
                            slug, str(e)[:200])
        crawl_records = []
        if activity_id:
            try:
                crawl_records = crawl_activity(activity_id)
            except Exception as e:
                log.warning("Индекс %s: обход olimpiada.ru не удался: %s", slug, str(e)[:200])
        # Слияние по URL: один PDF не должен занимать несколько слотов
        merged: dict[str, dict] = {}
        for r in cat_records + site_records + crawl_records:
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
        log.info("Индекс %s построен: %d из базы, %d с родного сайта, "
                 "%d с olimpiada.ru (activity_id=%s).",
                 slug, len(cat_records), len(site_records), len(crawl_records),
                 activity_id)
        return index

    def get(self, slug: str) -> dict:
        if slug not in self._cache:
            self._cache[slug] = {"slug": slug, "activity_id": None,
                                 "records": [], "built_at_ts": 0}
        return self._cache[slug]

    def find(self, slug: str, year, round_key: str | None, grade,
             kinds=("sol", "ans", "tasks"), variant: str = None) -> list[dict]:
        """Поиск PDF в индексе по (год, этап, класс, вариант).

        Записи без года/этапа/класса/варианта считаются подходящими любому
        (совпадение по остальным полям), но ранжируются ниже.
        Для Турнира городов grades=None — подходит любому классу.
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
                # точное совпадение варианта ранжирует выше
                0 if (variant and r.get("variant") == str(variant)) else 1,
            )

        # Дедупликация по URL до ограничения сверху
        seen_urls = set()
        deduped = []
        for r in sorted(matches, key=score):
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                deduped.append(r)
        return deduped

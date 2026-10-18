#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пайплайн чистки базы олимпиадных задач FORMYLA (22 этапа).

Этапы 1-4, 8-10, 12-17 — чистка (детерминированная + DeepSeek),
этапы 18-21 — поиск официальных источников (Gemini через OdiRouter),
этап 22 — финальная валидация и отчёт.

Использование:
    python scripts/olymp_catalog_fix.py --stages 1-17 --dry-run
    python scripts/olymp_catalog_fix.py --stages 1-17
    python scripts/olymp_catalog_fix.py --stages 18-22 --slug phystech
    python scripts/olymp_catalog_fix.py --apply

Ключи: ODIROUTER_API_KEY, ODIROUTER_BASE_URL, DEEPSEEK_API_KEY.
"""

import argparse
import copy
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Не установлена библиотека requests: pip install requests")
    sys.exit(1)

try:
    import pdfplumber
    from pypdf import PdfReader
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

try:
    from openai import OpenAI, APIError
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import olymp_fix_rules as R
import olymp_fix_prompts as P
import olymp_source_index as SI

# =====================================================================
# Константы путей и настройки
# =====================================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "olymp_catalog"
FIXED_DIR = BASE_DIR / "data" / "olymp_catalog_fixed"
REPORTS_DIR = BASE_DIR / "reports"
WORK_DIR = BASE_DIR / "work"
BACKUP_DIR = BASE_DIR / "backup"
CHECKPOINT_PATH = WORK_DIR / "checkpoint.json"
DIFF_PATH = REPORTS_DIR / "olymp_catalog_fix_diff.jsonl"
REPORT_PATH = REPORTS_DIR / "olymp_catalog_fix.md"
SEARCH_LOG_PATH = WORK_DIR / "search_log.jsonl"
SOURCE_INDEX_DIR = WORK_DIR / "source_index"

DEFAULT_WORKERS = 8
MAX_RETRIES = 5
TIMEOUT_S = 120
MAX_TOKENS = 4096
FINGERPRINT_FIELDS = ["olymp", "year", "round", "grade", "num", "status",
                      "answer", "source", "text", "solution",
                      "geo", "fig_statement", "fig_solution"]

STAGES_COUNT = 22

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("olymp_fix")

# Реентерабельный замок: apply_field держит лок и вызывает diff.log,
# который тоже берёт лок (один и тот же поток — RLock безопасен)
_lock = threading.RLock()


# =====================================================================
# Утилиты
# =====================================================================

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def record_fingerprint(rec: dict) -> str:
    """Хеш входных полей записи (без qa) — для чекпоинта идемпотентности."""
    data = {k: rec.get(k) for k in FINGERPRINT_FIELDS}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def normalized_prefix(text: str, n: int = 60) -> str:
    """Нормализованный префикс для сравнения дублей условия в решении."""
    t = re.sub(r"\s+", " ", (text or "").lower())
    t = R.norm_for_compare(t)
    return t[:n]


def similarity(a: str, b: str) -> float:
    """Нечёткое совпадение двух текстов (0..1)."""
    if not a or not b:
        return 0.0
    if HAS_RAPIDFUZZ:
        return fuzz.ratio(a, b) / 100.0
    # Простейший fallback (по общим словам)
    wa, wb = set(a.lower().split()), set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa | wb), 1)


# =====================================================================
# LLM-клиенты
# =====================================================================

class RetryableStageError(Exception):
    """Инфраструктурный сбой этапа (нет ключей/API недоступен) — запись НЕ
    помечается обработанной в чекпоинте, повторный запуск повторит её."""


class LLMError(Exception):
    pass


class LLMClient:
    """Базовый OpenAI-совместимый клиент с ретраями и логом токенов."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str,
                 timeout: float = None):
        if not HAS_OPENAI:
            raise LLMError("Не установлена библиотека openai")
        self.name = name
        self.base_url = base_url
        self.model = model
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
        self._json_supported = True
        self._client = OpenAI(base_url=base_url, api_key=api_key,
                             timeout=timeout or TIMEOUT_S, max_retries=0)

    def _log_usage(self, resp):
        try:
            u = resp.usage
            if u:
                self.usage["prompt_tokens"] += u.prompt_tokens or 0
                self.usage["completion_tokens"] += u.completion_tokens or 0
        except Exception:
            pass
        self.usage["calls"] += 1

    def chat(self, system: str, user: str, json_mode: bool = True,
             temperature: float = 0.0, extra_body: dict = None,
             stream: bool = False) -> str | None:
        """Вызов с ретраями; возвращает текст ответа или None при исчерпании попыток.

        stream=True — потоковый режим (обходит 504-таймауты nginx у OdiRouter при
        включённом web-search: чанки приходят сразу, соединение не простаивает).
        """
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                    "max_tokens": MAX_TOKENS,
                }
                if json_mode and self._json_supported:
                    kwargs["response_format"] = {"type": "json_object"}
                if extra_body:
                    kwargs["extra_body"] = extra_body
                if stream:
                    kwargs["stream"] = True
                try:
                    resp = self._client.chat.completions.create(**kwargs)
                except Exception as e:
                    # response_format может не поддерживаться — переключаемся и ретраим
                    if json_mode and self._json_supported and "response_format" in str(e).lower():
                        self._json_supported = False
                        continue
                    raise
                if stream:
                    content, usage = "", None
                    for chunk in resp:
                        try:
                            if getattr(chunk, "usage", None):
                                usage = chunk.usage
                        except Exception:
                            pass
                        try:
                            delta = chunk.choices[0].delta
                            if delta and delta.content:
                                content += delta.content
                        except (IndexError, AttributeError, TypeError):
                            continue
                    if content:
                        if usage is not None:
                            self._add_usage(usage.prompt_tokens, usage.completion_tokens)
                        else:
                            self.usage["calls"] += 1
                        return content
                    last_err = LLMError("пустой потоковый ответ")
                else:
                    self._log_usage(resp)
                    content = resp.choices[0].message.content
                    if content:
                        return content
                    last_err = LLMError("пустой ответ")
            except Exception as e:
                self.usage["errors"] += 1
                last_err = e
                log.warning("%s: попытка %d/%d не удалась: %s",
                            self.name, attempt, MAX_RETRIES, str(e)[:200])
                time.sleep(min(2 ** attempt, 30))
        log.error("%s: все %d попыток исчерпаны (%s)", self.name, MAX_RETRIES, last_err)
        return None

    def _add_usage(self, prompt_tokens, completion_tokens):
        """Учёт токенов из потокового ответа."""
        self.usage["prompt_tokens"] += prompt_tokens or 0
        self.usage["completion_tokens"] += completion_tokens or 0
        self.usage["calls"] += 1

    def chat_json(self, system: str, user: str, temperature: float = 0.0,
                  extra_body: dict = None, stream: bool = False) -> dict | None:
        """Вызов с JSON-режимом и парсингом ответа; None при неудаче."""
        content = self.chat(system, user, json_mode=True, temperature=temperature,
                            extra_body=extra_body, stream=stream)
        if content is None:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Пробуем вытащить JSON-блок из текста
            m = re.search(r"\{[\s\S]*\}", content)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
            log.warning("%s: не удалось разобрать JSON-ответ", self.name)
            return None


class DeepSeekClient(LLMClient):
    """DeepSeek: deepseek-chat для чистки, deepseek-reasoner для математики."""

    BASE_URL = "https://api.deepseek.com"

    @classmethod
    def from_env(cls, model: str) -> "DeepSeekClient":
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise LLMError("Не задан DEEPSEEK_API_KEY. Выполните: export DEEPSEEK_API_KEY=...")
        return cls("deepseek", cls.BASE_URL, key, model)




class OdiRouterClient(LLMClient):
    """OdiRouter (OpenAI-совместимый). Gemini 3.6 Flash — поиск и grounding.

    Таймаут клиента 55 с (меньше 60-секундного 504-таймаута nginx OdiRouter).
    При web-search вызовы идут потоками (stream=True), search_context_size=low,
    компактный промт (≤ 400 токенов) — чтобы grounding не висел без данных.
    """

    SEARCH_TIMEOUT_S = 55

    def __init__(self, model: str, web_search: bool = False, timeout: float = None):
        base_url = os.environ.get("ODIROUTER_BASE_URL",
                                  "https://api.odirouter.ai/v1").rstrip("/")
        api_key = os.environ.get("ODIROUTER_API_KEY")
        if not api_key:
            raise LLMError("Не задан ODIROUTER_API_KEY. Выполните: export ODIROUTER_API_KEY=...")
        super().__init__("odirouter", base_url, api_key, model,
                         timeout=timeout or self.SEARCH_TIMEOUT_S)
        self.web_search = web_search

    def search_candidates(self, user_payload: str) -> dict | None:
        """Компактный поисковый запрос (≤ 400 токенов) с grounding.

        При web_search: stream=True + search_context_size=low — обходит 504.
        """
        extra = {"web_search_options": {"search_context_size": "low"}} if self.web_search else None
        return self.chat_json(P.SEARCH_CANDIDATES_COMPACT, user_payload,
                              extra_body=extra, stream=self.web_search)

    def search_variant_pdf(self, user_payload: str) -> dict | None:
        """Поиск PDF варианта (этап 21): компактный промт, тот же обход таймаута."""
        extra = {"web_search_options": {"search_context_size": "low"}} if self.web_search else None
        return self.chat_json(P.SEARCH_VARIANT_PDF_COMPACT, user_payload,
                              extra_body=extra, stream=self.web_search)


def resolve_gemini_model() -> tuple[str | None, bool]:
    """Определяет id модели Gemini 3.6 Flash через GET /models.

    Возвращает (model_id, web_search_enabled).
    ODIROUTER_MODEL — ручное переопределение (принимается как есть, без
    проверки подстроки; /models не запрашивается).
    Web-search: по умолчанию ВКЛЮЧЁН без пробы (стрим + low context —
    меры против 504); ODIROUTER_WEB_SEARCH=0 выключает, =1 то же, что по
    умолчанию. Ленивая инициализация: вызывается только при этапах 18-21.
    """
    if not os.environ.get("ODIROUTER_API_KEY"):
        log.warning("ODIROUTER_API_KEY не задан — поиск (этапы 18-21) будет недоступен.")
        return None, False
    # Ручное управление моделью — фильтр по подстроке не применяем
    manual_model = os.environ.get("ODIROUTER_MODEL", "").strip()
    web_mode = os.environ.get("ODIROUTER_WEB_SEARCH", "").strip().lower()
    web_search = web_mode != "0"   # по умолчанию включён (без пробы — лениво)
    if web_mode == "0":
        log.info("OdiRouter: web-search отключён (ODIROUTER_WEB_SEARCH=0) — "
                 "Gemini вернёт URL-кандидатов, скрипт проверит их сам.")
    if manual_model:
        log.info("OdiRouter: модель задана вручную через ODIROUTER_MODEL: %s "
                 "(web_search=%s).", manual_model, web_search)
        return manual_model, web_search
    base_url = os.environ.get("ODIROUTER_BASE_URL", "https://api.odirouter.ai/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {os.environ['ODIROUTER_API_KEY']}"}
    candidates = []
    try:
        resp = requests.get(f"{base_url}/models", headers=headers, timeout=30)
        if resp.status_code != 200:
            log.warning("OdiRouter: GET %s/models вернул %d. "
                        "Проверьте ODIROUTER_BASE_URL (по умолчанию %s). "
                        "Или задайте модель вручную: export ODIROUTER_MODEL=<id>.",
                        base_url, resp.status_code, "https://api.odirouter.ai/v1")
        else:
            data = resp.json()
            models = data.get("data", data if isinstance(data, list) else [])
            candidates = [m.get("id", "") for m in models]
    except Exception as e:
        log.warning("OdiRouter: не удалось получить /models (%s). "
                    "Задайте модель вручную: export ODIROUTER_MODEL=<id>.", str(e)[:200])
        return None, False
    gemini_flash = [c for c in candidates if "gemini-3.8-flash" in c.lower()]
    if not gemini_flash:
        all_gemini = [c for c in candidates if "gemini" in c.lower()]
        log.error("Модель с подстрокой 'gemini-3.8-flash' не найдена на OdiRouter.")
        if all_gemini:
            log.error("Доступные gemini-модели:\n  %s", "\n  ".join(all_gemini))
        else:
            log.error("Gemini-модели недоступны. Полный список моделей:\n  %s",
                      "\n  ".join(candidates[:50]) or "(пусто)")
        return None, False
    if web_search:
        log.info("OdiRouter: web-search (grounding) включён: stream=True + "
                 "search_context_size=low (меры против 504-таймаута nginx).")
    return gemini_flash[0], web_search


# =====================================================================
# Чекпоинт
# =====================================================================

class Checkpoint:
    """Чекпоинт по uid+этап с хешем входа. Атомарная запись через os.replace."""

    def __init__(self, path: Path):
        self.path = path
        self.data = {"version": 2, "updated": now_iso(), "stages": {}, "records": {},
                     "removed": [], "added": [], "search_queue": [], "usage": {}}

    def load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
                # Миграция со старой версии: без records
                self.data.setdefault("stages", {})
                self.data.setdefault("records", {})
                self.data.setdefault("removed", [])
                self.data.setdefault("added", [])
                self.data.setdefault("search_queue", [])
                self.data.setdefault("usage", {})
                log.info("Чекпоинт загружен: %d записей, %d этапов завершено.",
                         len(self.data["records"]), len(self.data["stages"]))
            except Exception as e:
                log.warning("Не удалось загрузить чекпоинт (%s) — начинаем с нуля.", e)

    def record_done(self, uid: str, stage: int, input_fp: str, output_fp: str = None):
        """Отметить этап завершённым для записи.

        input_fp — хеш записи ДО этапа, output_fp — ПОСЛЕ.
        При --resume пропускамся, если текущий хеш совпадает с любым из них
        (необработанный вход либо уже применённый результат).
        """
        if not uid:
            return
        with _lock:
            rec = self.data["records"].setdefault(uid, {})
            rec[str(stage)] = {"fp": input_fp, "out_fp": output_fp or input_fp,
                               "ts": now_iso()}

    def is_done(self, uid: str, stage: int, current_fp: str) -> bool:
        info = self.data["records"].get(uid, {}).get(str(stage))
        if not info:
            return False
        return current_fp in (info.get("fp"), info.get("out_fp"))

    def stage_complete(self, stage: int):
        with _lock:
            self.data["stages"][str(stage)] = {"completed": now_iso()}

    def stage_failed(self, stage: int, reason: str):
        with _lock:
            self.data["stages"][str(stage)] = {"failed": now_iso(), "reason": reason[:500]}

    def stage_is_complete(self, stage: int) -> bool:
        return str(stage) in self.data["stages"]

    def save(self):
        with _lock:
            self.data["updated"] = now_iso()
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)


# =====================================================================
# Отчётность
# =====================================================================

class DiffLogger:
    """Лог изменений в JSONL: uid, этап, поле, было, стало."""

    def __init__(self, path: Path, enabled: bool):
        self.path = path
        self.enabled = enabled
        self.entries = []

    def log(self, uid: str, stage: int, field: str, old, new, slug: str = ""):
        entry = {"ts": now_iso(), "uid": uid, "slug": slug, "stage": stage,
                 "field": field, "old": old, "new": new}
        self.entries.append(entry)
        if self.enabled:
            with _lock:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def count(self, stage: int = None) -> int:
        if stage is None:
            return len(self.entries)
        return sum(1 for e in self.entries if e["stage"] == stage)


class SearchLogger:
    """Лог поиска источников: work/search_log.jsonl.

    Для каждого запроса: запрос, источник кандидата (index|gemini|none),
    URL, статус скачивания, результат проверки — видно, почему отказ.
    """

    def __init__(self, path: Path, enabled: bool):
        self.path = path
        self.enabled = enabled
        self.entries = []

    def log(self, uid: str, slug: str, stage: int, query: str, origin: str,
            url: str, status: str, result: str):
        entry = {"ts": now_iso(), "uid": uid, "slug": slug, "stage": stage,
                 "query": query, "origin": origin, "url": url,
                 "status": status, "result": result}
        self.entries.append(entry)
        if self.enabled:
            with _lock:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def summary(self) -> str:
        """Краткая сводка для отчёта."""
        total = len(self.entries)
        if not total:
            return "поиск не выполнялся"
        ok = sum(1 for e in self.entries if e.get("result", "").startswith(("найдено", "совп", "официальн")))
        return (f"{total} запросов: индекс — "
                f"{sum(1 for e in self.entries if e['origin'] == 'index')}, "
                f"gemini — {sum(1 for e in self.entries if e['origin'] == 'gemini')}, "
                f"успешных — {ok}")


# =====================================================================
# Каталог
# =====================================================================

class Catalog:
    """Каталог задач: {slug: [records]}. Порядок slug фиксирован."""

    def __init__(self):
        self.data: dict[str, list[dict]] = {}
        self.index: dict = {}
        self._by_uid: dict[str, tuple[str, dict]] = {}

    def load(self, src_dir: Path, only_slug: str = None, limit: int = None):
        if not src_dir.exists():
            raise FileNotFoundError(f"Каталог не найден: {src_dir}")
        files = sorted(p for p in src_dir.glob("*.json") if p.stem != "_index")
        if only_slug:
            files = [p for p in files if p.stem == only_slug]
            if not files:
                raise FileNotFoundError(f"Файл олимпиады не найден: {only_slug}.json")
        loaded = 0
        for fp in files:
            try:
                records = json.loads(fp.read_text(encoding="utf-8"))
            except Exception as e:
                log.error("Не удалось прочитать %s: %s", fp.name, e)
                continue
            # ВАЖНО: --limit НЕ обрезает каталог при загрузке (иначе выходной файл
            # заменил бы полный усечённым); ограничение применяется только
            # к выборке обработки в run_parallel.
            self.data[fp.stem] = records
            loaded += len(records)
        idx_path = src_dir / "_index.json"
        if idx_path.exists():
            try:
                self.index = json.loads(idx_path.read_text(encoding="utf-8"))
            except Exception:
                self.index = {}
        log.info("Загружено %d задач из %d файлов (%s).", loaded, len(self.data), src_dir)
        self._rebuild_index_map()

    def _rebuild_index_map(self):
        self._by_uid.clear()
        for slug, records in self.data.items():
            for rec in records:
                self._by_uid[rec.get("uid", "")] = (slug, rec)

    def slugs(self) -> list[str]:
        return list(self.data.keys())

    def all_records(self) -> list[tuple[str, dict]]:
        return [(slug, rec) for slug in self.data for rec in self.data[slug]]

    def find(self, uid: str) -> tuple[str, dict] | None:
        return self._by_uid.get(uid)

    def variant_tasks(self, slug: str, year, round_name: str, grade) -> list[dict]:
        return [r for r in self.data.get(slug, [])
                if r.get("year") == year and r.get("round") == round_name
                and str(r.get("grade")) == str(grade)]

    def find_task(self, slug: str, year, round_name: str, num: str, grade=None) -> dict | None:
        for r in self.data.get(slug, []):
            if r.get("year") == year and r.get("round") == round_name \
               and str(r.get("num")) == str(num):
                if grade is None or str(r.get("grade")) == str(grade):
                    return r
        return None

    def save(self, out_dir: Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        for slug, records in self.data.items():
            (out_dir / f"{slug}.json").write_text(
                json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        # _index.json: обновляем только загруженные slug;
        # записи остальных олимпиад (если --slug/--limit) сохраняем как есть,
        # чтобы индекс не «терял» нетронутые файлы.
        old_files = {}
        if isinstance(self.index, dict) and isinstance(self.index.get("files"), dict):
            old_files = self.index["files"]
        files_idx = {}
        years_all = set()
        with_figs = 0
        for slug, records in self.data.items():
            years = sorted({r.get("year") for r in records if r.get("year")})
            figs = sum(1 for r in records if (r.get("fig_statement") or r.get("fig_solution")))
            with_figs += figs
            files_idx[slug] = {"count": len(records), "with_figs": figs, "years": years}
            years_all.update(years)
        for s, entry in old_files.items():
            if s not in files_idx:
                files_idx[s] = entry
        idx = {"updated": now_iso(),
               "total": sum((e.get("count", 0) for e in files_idx.values())),
               "files": files_idx}
        idx["years"] = sorted(years_all)
        idx["with_figs_total"] = with_figs
        (out_dir / "_index.json").write_text(
            json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("Каталог сохранён в %s (%d файлов, %d задач).",
                 out_dir, len(files_idx), idx["total"])


# =====================================================================
# Пайплайн
# =====================================================================

class Pipeline:
    """Контекст пайплайна: каталог, клиенты, чекпоинт, diff, статистика."""

    def __init__(self, args):
        self.args = args
        self.dry_run = args.dry_run
        self.checkpoint = Checkpoint(args.checkpoint)
        # Чекпоинт загружаем всегда, если существует: иначе очередь поиска
        # (search_queue) терялась бы между запусками без --resume.
        # --resume лишь явно документирует продолжение.
        if args.checkpoint.exists():
            self.checkpoint.load()
        self.diff = DiffLogger(DIFF_PATH, enabled=not self.dry_run)
        self.search_log = SearchLogger(SEARCH_LOG_PATH, enabled=not self.dry_run)
        self._source_index: SI.SourceIndex | None = None
        self.catalog = Catalog()
        self.llm_changes = []          # предложенные, но не применённые (dry-run)
        self.stats = {s: {"processed": 0, "changed": 0, "skipped": 0,
                          "errors": 0, "notes": []}
                      for s in range(1, STAGES_COUNT + 1)}
        # Накопленная статистика из чекпоинта (переживает несколько запусков)
        for s, st in (self.checkpoint.data.get("stats") or {}).items():
            if int(s) in self.stats:
                for k in ("processed", "changed", "errors"):
                    self.stats[int(s)][k] += st.get(k, 0)
                self.stats[int(s)]["notes"].extend(st.get("notes", [])[:20])
        self.deepseek_chat: LLMClient | None = None
        self.deepseek_reasoner: LLMClient | None = None
        self.gemini: OdiRouterClient | None = None
        self.usage_snapshot = {}
        self._init_clients()
        self._load_catalog()
        # Снимок проблем «было» — для отчёта было/стало
        self.before_issues = R.detect_issues(self.catalog.data)

    # -----------------------------------------------------------------
    # Инициализация
    # -----------------------------------------------------------------

    def _init_clients(self):
        """Инициализация LLM-клиентов. DeepSeek — при наличии ключа,
        OdiRouter — с проверкой /models и web-search.

        В dry-run клиенты не создаются вообще: никаких API-вызовов и затрат.
        """
        if self.dry_run:
            log.info("dry-run: LLM-клиенты не инициализируются (API не вызывается).")
            return
        need_models = any(s in self.stages for s in (4, 5, 6, 7, 8, 10, 11, 12))
        need_search = any(s in self.stages for s in (18, 19, 20, 21))
        if need_models or need_search:
            if not os.environ.get("DEEPSEEK_API_KEY"):
                log.warning("DEEPSEEK_API_KEY не задан — модельные этапы будут пропущены. "
                            "Выполните: export DEEPSEEK_API_KEY=...")
            else:
                try:
                    self.deepseek_chat = DeepSeekClient.from_env("deepseek-chat")
                    self.deepseek_reasoner = DeepSeekClient.from_env("deepseek-reasoner")
                    log.info("DeepSeek клиенты готовы (deepseek-chat, deepseek-reasoner).")
                except Exception as e:
                    log.warning("DeepSeek недоступен: %s", e)
        if need_search:
            model_id, web_search = resolve_gemini_model()
            if model_id:
                try:
                    self.gemini = OdiRouterClient(model_id, web_search=web_search)
                    log.info("OdiRouter готов: модель %s.", model_id)
                except Exception as e:
                    log.warning("OdiRouter недоступен: %s", e)
        self.usage_snapshot = self._usage_total()

    def _usage_total(self) -> dict:
        usage = {}
        for cli in (self.deepseek_chat, self.deepseek_reasoner, self.gemini):
            if cli:
                usage[cli.name + ":" + cli.model] = dict(cli.usage)
        return usage

    def _load_catalog(self):
        src = Path(self.args.source) if self.args.source else DATA_DIR
        self.catalog.load(src, only_slug=self.args.slug, limit=self.args.limit)
        # Пропускаем записи, уже удалённые ранее (чекпоинт)
        removed = set(self.checkpoint.data.get("removed", []))
        if removed:
            for slug in self.catalog.slugs():
                before = len(self.catalog.data[slug])
                self.catalog.data[slug] = [r for r in self.catalog.data[slug]
                                         if r.get("uid") not in removed]
                if len(self.catalog.data[slug]) != before:
                    log.info("%s: пропущено %d записей, удалённых в прошлых запусках.",
                             slug, before - len(self.catalog.data[slug]))
            self.catalog._rebuild_index_map()

    @property
    def stages(self) -> set[int]:
        return self.args.stages_set

    # -----------------------------------------------------------------
    # Вспомогательные методы правок
    # -----------------------------------------------------------------

    def apply_field(self, slug: str, rec: dict, stage: int, field: str, new_value,
                   model: str = "") -> bool:
        """Правка поля записи с логом diff и qa. Потокобезопасно.

        Возвращает True, если изменено. Единственная точка мутации записей:
        и рабочие потоки, и главный поток меняют каталог только здесь.
        """
        with _lock:
            old = rec.get(field)
            if old == new_value:
                return False
            if self.dry_run:
                self.llm_changes.append({"uid": rec.get("uid"), "slug": slug, "stage": stage,
                                         "field": field, "old": old, "new": new_value})
                self.diff.log(rec.get("uid", ""), stage, field, old, new_value, slug)
                return True
            rec[field] = new_value
            qa = rec.setdefault("qa", {})
            stage_key = f"stage{stage}"
            entry = qa.setdefault(stage_key, {"stage": stage, "model": model or "deterministic",
                                             "changes": {}})
            entry["changes"][field] = {"old": old}
            entry["ts"] = now_iso()
            self.diff.log(rec.get("uid", ""), stage, field, old, new_value, slug)
            return True

    def add_to_search_queue(self, uid: str):
        """Потокобезопасное добавление в очередь поиска этапа 20."""
        if not uid:
            return
        with _lock:
            sq = self.checkpoint.data.setdefault("search_queue", [])
            if uid not in sq:
                sq.append(uid)

    def remove_from_search_queue(self, uid: str):
        with _lock:
            sq = self.checkpoint.data.get("search_queue", [])
            if uid in sq:
                sq.remove(uid)

    def add_qa_note(self, rec: dict, stage: int, note: str, model: str = ""):
        """Добавить пометку в qa без правки полей."""
        if self.dry_run:
            return
        qa = rec.setdefault("qa", {})
        stage_key = f"stage{stage}"
        entry = qa.setdefault(stage_key, {"stage": stage, "model": model or "deterministic",
                                         "changes": {}})
        notes = entry.setdefault("notes", [])
        if note not in notes:
            notes.append(note)

    def needs_review(self, rec: dict, stage: int, reason: str):
        self.add_qa_note(rec, stage, f"needs_review: {reason}")

    def run_parallel(self, stage: int, items: list, worker, desc: str = ""):
        """Параллельный прогон worker(slug, rec) с чекпоинтом и прогресс-логами.

        Чекпоинт: запись пропускается, если её текущий хеш совпадает с входом
        или результатом прошлой обработки этого этапа (идемпотентность --resume).
        """
        stats = self.stats[stage]
        if not items:
            return
        items = self.limited(items)  # --limit: обрабатываем первые N, остальные не трогаем
        if not items:
            return
        workers = self.args.workers

        def wrapped(slug, rec):
            uid = rec.get("uid", "")
            fp_before = record_fingerprint(rec)
            if not self.dry_run and uid and self.checkpoint.is_done(uid, stage, fp_before):
                return
            try:
                worker(slug, rec)
            except RetryableStageError as e:
                # Инфраструктурный сбой: запись НЕ помечаем обработанной —
                # повторный запуск повторит её (когда появятся ключи/API)
                stats["skipped"] += 1
                log.warning("Этап %d: запись %s отложена (%s)",
                            stage, uid[:8], str(e)[:150])
                return
            if not self.dry_run and uid:
                self.checkpoint.record_done(uid, stage, fp_before, record_fingerprint(rec))

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(wrapped, slug, rec): (slug, rec) for slug, rec in items}
            for i, fut in enumerate(as_completed(futures), 1):
                slug, rec = futures[fut]
                try:
                    fut.result()
                    stats["processed"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    log.error("Этап %d: ошибка на %s/%s: %s", stage, slug,
                              rec.get("uid", "?")[:8], str(e)[:200])
                if i % 500 == 0 or i == len(items):
                    log.info("Этап %d%s: %d/%d обработано.", stage,
                             f" ({desc})" if desc else "", i, len(items))

    def limited(self, items: list) -> list:
        """Ограничение --limit: обрабатываем первые N, остальные не трогаем."""
        if self.args.limit:
            return items[: self.args.limit]
        return items

    def get_source_index(self) -> SI.SourceIndex:
        """Индекс официальных PDF (кэш work/source_index/<slug>.json).

        Строится лениво при первом обращении этапов 18/20/21.
        Потокобезопасно: параллельные воркеры этапа 18 не строят индекс дважды.
        """
        with _lock:
            if self._source_index is None:
                rebuild = getattr(self.args, "rebuild_index", False)
                self._source_index = SI.SourceIndex(SOURCE_INDEX_DIR, rebuild=rebuild)
            for slug in self.catalog.slugs():
                if slug not in self._source_index._cache:
                    try:
                        self._source_index.build(slug, self.catalog.data.get(slug, []))
                    except Exception as e:
                        log.warning("Индекс для %s не построен: %s", slug, str(e)[:200])
            return self._source_index

    def save_state(self):
        """Сохранить каталог в FIXED_DIR и чекпоинт."""
        if self.dry_run:
            return
        self.catalog.save(FIXED_DIR)
        self.checkpoint.data["usage"] = self._usage_total()
        self.checkpoint.data["stats"] = {
            str(s): {k: v for k, v in st.items() if k != "notes"}
            for s, st in self.stats.items()}
        self.checkpoint.save()


# =====================================================================
# ЭТАПЫ 1-3: детерминированная чистка
# =====================================================================

def stage_01(p: Pipeline):
    """Этап 1: нормализация Unicode-символов (без моделей)."""
    def worker(slug, rec):
        for field in ("text", "solution", "answer"):
            old = rec.get(field) or ""
            new = R.normalize_unicode_math(old)
            if new != old:
                p.apply_field(slug, rec, 1, field, new)

    items = p.catalog.all_records()
    p.run_parallel(1, items, worker, "нормализация символов")
    p.stats[1]["changed"] = p.diff.count(1)


def stage_02(p: Pipeline):
    """Этап 2: удаление PDF-мусора по словарю регулярок."""
    cut_report: dict[str, int] = {}

    def clean_text(text: str) -> tuple[str, int]:
        if not text:
            return text, 0
        total_cut = 0
        for rx, desc in R.PDF_GARBAGE_PATTERNS:
            matches = rx.findall(text)
            if matches:
                cut_report[desc] = cut_report.get(desc, 0) + len(matches)
                total_cut += sum(len(m) for m in matches)
                text = rx.sub("", text)
        text, repeated = R.remove_repeated_lines(text)
        if repeated:
            cut_report["повторяющиеся колонтитулы"] = cut_report.get("повторяющиеся колонтитулы", 0) + len(repeated)
            total_cut += sum(len(r) for r in repeated)
        return text, total_cut

    def worker(slug, rec):
        for field in ("text", "solution"):
            old = rec.get(field) or ""
            new, _ = clean_text(old)
            if new != old:
                p.apply_field(slug, rec, 2, field, new)

    items = p.catalog.all_records()
    p.run_parallel(2, items, worker, "PDF-мусор")
    for desc, cnt in sorted(cut_report.items(), key=lambda kv: -kv[1]):
        p.stats[2]["notes"].append(f"{desc}: {cnt} вхождений")
    p.stats[2]["changed"] = p.diff.count(2)


def stage_03(p: Pipeline):
    """Этап 3: Markdown-мусор."""
    def worker(slug, rec):
        sol = rec.get("solution") or ""
        ans = rec.get("answer") or ""
        changed = False
        # **Решение.** -> Решение.
        new_sol = R.MD_BOLD_SOLUTION.sub(lambda m: m.group(0).replace("*", "").strip(), sol)
        new_ans = R.MD_BOLD_ANSWER.sub(lambda m: m.group(0).replace("*", "").strip(), ans)
        # Ведущие ** в answer
        new_ans = R.LEADING_TRAILING_MD.sub("", new_ans).strip()
        # Markdown-ссылки: сначала вытащить URL (позже строка с ними удаляется)
        urls_found = []
        def link_repl(m):
            label, url = m.group(1), m.group(2)
            urls_found.append(url)
            return label
        new_sol = R.MD_LINK.sub(link_repl, new_sol)
        # Строки «[Официальное решение] Источник: ...» — удаляются целиком
        new_sol = R.OFFICIAL_SOLUTION_LINE.sub("", new_sol)
        new_sol = R.MD_HEADER.sub("", new_sol)
        if new_sol != sol:
            p.apply_field(slug, rec, 3, "solution", new_sol)
            changed = True
        if new_ans != ans:
            p.apply_field(slug, rec, 3, "answer", new_ans)
            changed = True
        for url in urls_found:
            if not (rec.get("source") or "").strip() and R.is_official_url(url):
                p.apply_field(slug, rec, 3, "source", url)
                changed = True
        if changed and urls_found:
            p.add_qa_note(rec, 3, f"markdown-ссылки вынесены: {urls_found}")

    items = p.catalog.all_records()
    p.run_parallel(3, items, worker, "markdown-мусор")
    p.stats[3]["changed"] = p.diff.count(3)


# =====================================================================
# ЭТАП 4: LaTeX-разделители
# =====================================================================

def stage_04(p: Pipeline):
    """Этап 4: $...$ -> \\( ... \\), $$...$$ -> \\[ ... \\], проверка баланса."""
    def fix_with_model(slug, rec, field, text) -> str | None:
        """DeepSeek-chat для сложных случаев (вложенные $, экранированные \\$)."""
        if p.deepseek_chat is None or p.dry_run:
            return None
        payload = {"text": text}
        resp = p.deepseek_chat.chat_json(P.STAGE4_LATEX_DELIMS, json.dumps(payload, ensure_ascii=False))
        if not resp or not resp.get("ok"):
            return None
        return resp.get("text")

    def worker(slug, rec):
        for field in ("text", "solution"):
            text = rec.get(field) or ""
            if not text:
                continue
            new = R.convert_dollar_delims(text)
            # Сложные случаи: экранированные \$ или вложенные $
            if re.search(r"\\\$|\$[^\n]*\$[^\n]*\$", new):
                model_result = fix_with_model(slug, rec, field, new)
                if model_result is not None and _math_gate(p, new, model_result, rec, 4):
                    new = model_result
            ok, problem = R.delimiters_balanced(new)
            if new != text:
                p.apply_field(slug, rec, 4, field, new, model="deepseek-chat")
            if not ok:
                p.needs_review(rec, 4, f"баланс разделителей: {problem} ({field})")

    items = p.catalog.all_records()
    p.run_parallel(4, items, worker, "LaTeX-разделители")
    p.stats[4]["changed"] = p.diff.count(4)


# =====================================================================
# ЭТАП 5: LaTeX-окружения в решении
# =====================================================================

def _reasoner_verify(p: Pipeline, prompt: str, payload: dict) -> dict | None:
    """Сверка через deepseek-reasoner: {'ok': bool, 'reason': str}."""
    if p.deepseek_reasoner is None:
        return None
    resp = p.deepseek_reasoner.chat_json(prompt, json.dumps(payload, ensure_ascii=False))
    return resp


def _math_gate(p: Pipeline, old: str, new: str, rec: dict, stage: int) -> bool:
    """LaTeX-инвариант: reasoner ЯВНО подтверждает эквивалентность математики.

    Правка принимается только при положительном вердикте.
    None / ok=false / equivalent!=true / ошибка -> отклонение + needs_review.
    """
    if old == new:
        return True
    if p.deepseek_reasoner is None or p.dry_run:
        p.needs_review(rec, stage, "правка отклонена: reasoner недоступен")
        return False
    payload = {"old": old, "new": new}
    resp = p.deepseek_reasoner.chat_json(P.MATH_EQUIVALENCE,
                                         json.dumps(payload, ensure_ascii=False))
    if not resp or resp.get("ok") is not True or resp.get("equivalent") is not True:
        reason = (resp or {}).get("reason", "нет явного вердикта")
        p.needs_review(rec, stage, f"правка отклонена гейтом эквивалентности: {reason}")
        return False
    return True


def stage_05(p: Pipeline):
    """Этап 5: LaTeX-окружения -> обычный текст, cases оставить."""
    def worker(slug, rec):
        sol = rec.get("solution") or ""
        if not sol or "\\begin{" not in sol:
            return
        # cases оставляем: если только cases — не трогаем
        sol_wo_cases = re.sub(r"\\begin\{cases\}[\s\S]*?\\end\{cases\}", "", sol)
        if "\\begin{" not in sol_wo_cases and "\\item" not in sol:
            return
        if p.deepseek_chat is None or p.dry_run:
            p.needs_review(rec, 5, "LaTeX-окружения в решении — модель недоступна")
            return
        payload = {"solution": sol, "text": rec.get("text") or ""}
        resp = p.deepseek_chat.chat_json(P.STAGE5_LATEX_ENVS, json.dumps(payload, ensure_ascii=False))
        if not resp or not resp.get("ok"):
            p.needs_review(rec, 5, "не удалось переписать окружения")
            return
        new_sol = resp.get("solution") or ""
        if not new_sol or new_sol == sol:
            return
        # LaTeX-инвариант: reasoner явно подтверждает эквивалентность
        if not _math_gate(p, sol, new_sol, rec, 5):
            return
        p.apply_field(slug, rec, 5, "solution", new_sol, model="deepseek-chat")

    items = [(s, r) for s, r in p.catalog.all_records()
             if "\\begin{" in (r.get("solution") or "")]
    p.run_parallel(5, items, worker, "LaTeX-окружения")
    p.stats[5]["changed"] = p.diff.count(5)


# =====================================================================
# ЭТАП 6: порезанные формулы
# =====================================================================

def stage_06(p: Pipeline):
    """Этап 6: восстановление порезанных формул (DeepSeek-chat + reasoner)."""
    def is_broken(text: str) -> bool:
        return any(rx.search(text) for rx in R.BROKEN_FORMULA_HINTS)

    def worker(slug, rec):
        text = rec.get("text") or ""
        sol = rec.get("solution") or ""
        if not (is_broken(text) or is_broken(sol)):
            return
        if p.deepseek_chat is None or p.dry_run:
            p.needs_review(rec, 6, "порезанные формулы — модель недоступна")
            return
        payload = {"text": text, "solution": sol}
        resp = p.deepseek_chat.chat_json(P.STAGE6_BROKEN_FORMULAS, json.dumps(payload, ensure_ascii=False))
        if not resp or not resp.get("ok"):
            p.needs_review(rec, 6, "не удалось восстановить формулы")
            return
        new_text = resp.get("text") or text
        new_sol = resp.get("solution") or sol
        # Сверка reasoner-ом: та же математика (явный вердикт)
        if not _math_gate(p, text, new_text, rec, 6):
            return
        if not _math_gate(p, sol, new_sol, rec, 6):
            return
        if new_text != text:
            p.apply_field(slug, rec, 6, "text", new_text, model="deepseek-chat")
        if new_sol != sol:
            p.apply_field(slug, rec, 6, "solution", new_sol, model="deepseek-chat")

    items = [(s, r) for s, r in p.catalog.all_records()
             if any(rx.search(r.get("text") or "") or rx.search(r.get("solution") or "")
                    for rx in R.BROKEN_FORMULA_HINTS)]
    p.run_parallel(6, items, worker, "порезанные формулы")
    p.stats[6]["changed"] = p.diff.count(6)


# =====================================================================
# ЭТАП 7: формулы без LaTeX
# =====================================================================

def stage_07(p: Pipeline):
    """Этап 7: сырой текст с √, ⇔, ∠ -> LaTeX."""
    def worker(slug, rec):
        text = rec.get("text") or ""
        sol = rec.get("solution") or ""
        has_raw = bool(R.RAW_MATH_SYMBOLS_RE.search(text)) and "\\(" not in text[:200]
        has_raw_sol = bool(R.RAW_MATH_SYMBOLS_RE.search(sol)) and "\\(" not in sol[:200]
        if not (has_raw or has_raw_sol):
            return
        if p.deepseek_chat is None or p.dry_run:
            p.needs_review(rec, 7, "формулы без LaTeX — модель недоступна")
            return
        payload = {"text": text, "solution": sol}
        resp = p.deepseek_chat.chat_json(P.STAGE7_RAW_TO_LATEX, json.dumps(payload, ensure_ascii=False))
        if not resp or not resp.get("ok"):
            p.needs_review(rec, 7, "не удалось перевести в LaTeX")
            return
        new_text = resp.get("text") or text
        new_sol = resp.get("solution") or sol
        # Явный вердикт эквивалентности для обоих полей
        if not _math_gate(p, text, new_text, rec, 7):
            return
        if not _math_gate(p, sol, new_sol, rec, 7):
            return
        if new_text != text:
            p.apply_field(slug, rec, 7, "text", new_text, model="deepseek-chat")
        if new_sol != sol:
            p.apply_field(slug, rec, 7, "solution", new_sol, model="deepseek-chat")

    items = [(s, r) for s, r in p.catalog.all_records()
             if (R.RAW_MATH_SYMBOLS_RE.search(r.get("text") or "")
                 and "\\(" not in (r.get("text") or "")[:200])]
    p.run_parallel(7, items, worker, "сырые формулы -> LaTeX")
    p.stats[7]["changed"] = p.diff.count(7)


# =====================================================================
# ЭТАП 8: решение/критерии/ответ внутри условия
# =====================================================================

def stage_08(p: Pipeline):
    """Этап 8: отделить решение и ответ от условия."""
    def worker(slug, rec):
        text = rec.get("text") or ""
        sol = rec.get("solution") or ""
        has_sol_mark = bool(R.RE_SOLUTION_MARK.search(text))
        has_ans_mark = bool(R.RE_ANSWER_MARK.search(text))
        has_criteria = bool(R.RE_CRITERIA_LINE.search(text))
        if not (has_sol_mark or has_ans_mark or has_criteria):
            return
        # Простые случаи: детерминированно
        if p.deepseek_chat is None or p.dry_run:
            p.needs_review(rec, 8, "решение внутри условия — модель недоступна")
            return
        payload = {"text": text, "solution": sol, "answer": rec.get("answer") or ""}
        resp = p.deepseek_chat.chat_json(P.STAGE8_SPLIT_TEXT_SOLUTION, json.dumps(payload, ensure_ascii=False))
        if not resp or not resp.get("ok"):
            p.needs_review(rec, 8, "не удалось разделить условие и решение")
            return
        new_text = (resp.get("text_new") or "").strip()
        sol_part = (resp.get("solution_part") or "").strip()
        ans_part = (resp.get("answer_part") or "").strip()
        criteria = resp.get("criteria") or []
        # Гейт: разделение не должно менять математику
        if new_text and new_text != text and not _math_gate(p, text, new_text, rec, 8):
            return
        if sol_part and sol_part != sol and not _math_gate(p, text[: len(sol_part) * 2], sol_part, rec, 8):
            # sol_part вырезан из text — сверяем с исходным текстом
            return
        if new_text and new_text != text:
            p.apply_field(slug, rec, 8, "text", new_text, model="deepseek-chat")
        # Решение переносим, если там пусто или новое лучше
        if sol_part and (not sol.strip() or len(sol_part) > len(sol)):
            p.apply_field(slug, rec, 8, "solution", sol_part, model="deepseek-chat")
        # Ответ — в answer, если был мусор или пусто
        if ans_part and R.is_answer_garbage(rec.get("answer") or ""):
            p.apply_field(slug, rec, 8, "answer", ans_part, model="deepseek-chat")
        if criteria:
            p.add_qa_note(rec, 8, f"удалены критерии: {criteria[:3]}")

    items = [(s, r) for s, r in p.catalog.all_records()
             if R.RE_SOLUTION_MARK.search(r.get("text") or "")
             or R.RE_ANSWER_MARK.search(r.get("text") or "")
             or R.RE_CRITERIA_LINE.search(r.get("text") or "")]
    p.run_parallel(8, items, worker, "разделение условия/решения")
    p.stats[8]["changed"] = p.diff.count(8)


# =====================================================================
# ЭТАП 9: дубль условия в начале решения
# =====================================================================

def stage_09(p: Pipeline):
    """Этап 9: вырезать дубль условия из начала решения (префикс >= 60 симв.)."""
    def worker(slug, rec):
        text = rec.get("text") or ""
        sol = rec.get("solution") or ""
        if len(text) < 60 or len(sol) < 60:
            return
        text_norm = R.norm_for_compare(text)
        if not text_norm:
            return
        # Карта: позиция в нормализованной строке -> позиция в исходной sol.
        norm_chars, idx_map = [], []
        for pos, ch in enumerate(sol):
            n = R.norm_for_compare(ch)
            for nch in n:
                norm_chars.append(nch)
                idx_map.append(pos)
        sol_norm = "".join(norm_chars)
        if not sol_norm.startswith(text_norm[:60]):
            return
        match_len = 0
        limit = min(len(text_norm), len(sol_norm))
        while match_len < limit and text_norm[match_len] == sol_norm[match_len]:
            match_len += 1
        if match_len < int(len(text_norm) * 0.95):
            return
        cut = idx_map[match_len - 1] + 1 if match_len <= len(idx_map) else len(sol)
        m = re.match(r"[\s.;:,—\-)\]]*", sol[cut:])
        cut += m.end() if m else 0
        new_sol = sol[cut:].lstrip()
        if len(new_sol) < 40:
            p.needs_review(rec, 9, "text_equals_solution: решение совпадает с условием")
            return
        if len(new_sol) < len(sol):
            p.apply_field(slug, rec, 9, "solution", new_sol)

    items = [(s, r) for s, r in p.catalog.all_records()
             if len(r.get("text") or "") >= 60 and len(r.get("solution") or "") >= 60]
    p.run_parallel(9, items, worker, "дубль условия в решении")
    p.stats[9]["changed"] = p.diff.count(9)


# =====================================================================
# ЭТАП 10: мусорные ответы
# =====================================================================

def stage_10(p: Pipeline):
    """Этап 10: чистка мусорных ответов, извлечение из решения."""
    def worker(slug, rec):
        ans = rec.get("answer") or ""
        sol = rec.get("solution") or ""
        text = rec.get("text") or ""
        is_proof = bool(re.search(r"дока(?:жите|зать|жите)", text, re.I))
        if is_proof and not ans.strip():
            return  # уже пусто — норма для доказательства
        if is_proof and R.is_answer_garbage(ans):
            p.apply_field(slug, rec, 10, "answer", "")
            return
        garbage = R.is_answer_garbage(ans)
        too_long = len(ans) > R.MAX_ANSWER_LEN
        if not (garbage or too_long):
            return
        if p.deepseek_reasoner is None or p.dry_run:
            p.needs_review(rec, 10, "мусорный ответ — модель недоступна")
            return
        payload = {"text": text, "solution": sol}
        resp = p.deepseek_reasoner.chat_json(P.STAGE10_EXTRACT_ANSWER,
                                            json.dumps(payload, ensure_ascii=False))
        if not resp or not resp.get("ok"):
            p.needs_review(rec, 10, "не удалось извлечь ответ из решения")
            return
        new_ans = (resp.get("answer") or "").strip()
        if resp.get("is_proof"):
            new_ans = ""
        if new_ans != ans:
            p.apply_field(slug, rec, 10, "answer", new_ans, model="deepseek-reasoner")

    items = [(s, r) for s, r in p.catalog.all_records()
             if R.is_answer_garbage(r.get("answer") or "")
             or len(r.get("answer") or "") > R.MAX_ANSWER_LEN]
    p.run_parallel(10, items, worker, "мусорные ответы")
    p.stats[10]["changed"] = p.diff.count(10)


# =====================================================================
# ЭТАП 11: сверка answer и solution
# =====================================================================

def stage_11(p: Pipeline):
    """Этап 11: answer должен совпадать с выводом решения."""
    def worker(slug, rec):
        ans = (rec.get("answer") or "").strip()
        sol = (rec.get("solution") or "").strip()
        text = rec.get("text") or ""
        if not ans or not sol:
            return
        if p.deepseek_reasoner is None or p.dry_run:
            return
        payload = {"text": text, "answer": ans, "solution": sol}
        resp = p.deepseek_reasoner.chat_json(P.STAGE11_ANSWER_CHECK,
                                            json.dumps(payload, ensure_ascii=False))
        if not resp or not resp.get("ok"):
            return
        verdict = resp.get("verdict")
        if verdict == "mismatch":
            p.add_qa_note(rec, 11, "answer_conflict", model="deepseek-reasoner")
            p.add_qa_note(rec, 11,
                          f"answer_conflict: наш ответ: {ans!r}; "
                          f"из решения: {resp.get('answer_from_solution')!r}",
                          model="deepseek-reasoner")
        elif verdict == "incomplete":
            p.add_qa_note(rec, 11, "решение не завершено — ответ не сверен",
                          model="deepseek-reasoner")

    items = [(s, r) for s, r in p.catalog.all_records()
             if (r.get("answer") or "").strip() and (r.get("solution") or "").strip()]
    p.run_parallel(11, items, worker, "сверка ответа с решением")
    p.stats[11]["changed"] = p.diff.count(11)


# =====================================================================
# ЭТАП 12: решения-заглушки
# =====================================================================

def stage_12(p: Pipeline):
    """Этап 12: пометка solution_placeholder, попытка подтянуть решение."""
    def worker(slug, rec):
        sol = rec.get("solution") or ""
        if not sol:
            return
        is_placeholder = any(rx.search(sol) for rx, _ in R.PLACEHOLDER_PATTERNS)
        if not is_placeholder:
            return
        p.add_qa_note(rec, 12, "solution_placeholder")
        # «См. задачу N для K класса» — подтянуть из базы
        m = R.SEE_TASK_RE.search(sol)
        if m:
            ref_num, ref_grade = m.group(1), m.group(2)
            src_rec = p.catalog.find_task(slug, rec.get("year"), rec.get("round"),
                                          ref_num, grade=ref_grade)
            if src_rec is None:
                src_rec = p.catalog.find_task(slug, rec.get("year"), rec.get("round"), ref_num)
            if src_rec and (src_rec.get("solution") or "").strip() \
               and not any(rx.search(src_rec.get("solution") or "")
                           for rx, _ in R.PLACEHOLDER_PATTERNS):
                p.apply_field(slug, rec, 12, "solution", src_rec["solution"])
                p.add_qa_note(rec, 12, f"решение подтянуто из задачи №{ref_num}")
                p.remove_from_search_queue(rec.get("uid"))
                return
            # В очередь поиска
            p.add_to_search_queue(rec.get("uid"))
        else:
            p.add_to_search_queue(rec.get("uid"))

    items = [(s, r) for s, r in p.catalog.all_records()
             if any(rx.search(r.get("solution") or "") for rx, _ in R.PLACEHOLDER_PATTERNS)]
    p.run_parallel(12, items, worker, "заглушки решений")
    p.stats[12]["changed"] = p.diff.count(12)


# =====================================================================
# ЭТАПЫ 13-15: обрезанные решения/условия, рисунки
# =====================================================================

def stage_13(p: Pipeline):
    """Этап 13: решения, обрезанные на 8000 символах."""
    def worker(slug, rec):
        sol = rec.get("solution") or ""
        if len(sol) < 7990:
            return
        # Обрыв мид-фразы: нет финальной пунктуации
        if sol.rstrip() and sol.rstrip()[-1] not in ".!?»":
            p.add_qa_note(rec, 13, "solution_truncated")
            p.add_to_search_queue(rec.get("uid"))

    items = [(s, r) for s, r in p.catalog.all_records() if len(r.get("solution") or "") >= 7990]
    p.run_parallel(13, items, worker, "обрезанные решения")
    p.stats[13]["changed"] = p.diff.count(13)


def stage_14(p: Pipeline):
    """Этап 14: обрезанные условия."""
    def worker(slug, rec):
        text = (rec.get("text") or "").strip()
        if not text:
            return
        truncated = False
        if len(text) < 40:
            truncated = True
        elif text[-1] not in ".?!:;»\"'" and not text.endswith("..."):
            # Обрыв слова: заканчивается строчной буквой без пунктуации
            if text[-1].islower():
                truncated = True
        if truncated:
            p.add_qa_note(rec, 14, "text_truncated")
            p.add_to_search_queue(rec.get("uid"))

    items = [(s, r) for s, r in p.catalog.all_records() if (r.get("text") or "").strip()]
    p.run_parallel(14, items, worker, "обрезанные условия")
    p.stats[14]["changed"] = p.diff.count(14)


def stage_15(p: Pipeline):
    """Этап 15: упомянутый рисунок без файла."""
    def worker(slug, rec):
        text = rec.get("text") or ""
        if not R.FIGURE_MENTION_RE.search(text):
            return
        if rec.get("fig_statement") or rec.get("fig_solution"):
            return
        p.add_qa_note(rec, 15, "figure_missing")
        p.add_qa_note(rec, 15, "нужно найти официальный PDF с рисунком")
        p.add_to_search_queue(rec.get("uid"))

    items = [(s, r) for s, r in p.catalog.all_records()
             if R.FIGURE_MENTION_RE.search(r.get("text") or "")
             and not (r.get("fig_statement") or r.get("fig_solution"))]
    p.run_parallel(15, items, worker, "отсутствующие рисунки")
    p.stats[15]["changed"] = p.diff.count(15)


# =====================================================================
# ЭТАП 16: дубли внутри варианта
# =====================================================================

def stage_16(p: Pipeline):
    """Этап 16: точные дубли внутри варианта и класса."""
    total_removed = 0
    for slug in p.catalog.slugs():
        records = p.catalog.data[slug]
        groups: dict[tuple, list[int]] = {}
        for i, rec in enumerate(records):
            # Полный нормализованный текст с сохранением операторов
            key = (rec.get("year"), rec.get("round"), str(rec.get("grade")),
                   R.norm_for_dedupe(rec.get("text") or ""))
            groups.setdefault(key, []).append(i)
        to_remove: list[int] = []
        for key, idxs in groups.items():
            if len(idxs) < 2:
                continue
            # Сортируем по качеству, оставляем лучшего
            idxs_sorted = sorted(idxs, key=lambda i: R.record_quality(records[i]), reverse=True)
            best = idxs_sorted[0]
            for i in idxs_sorted[1:]:
                to_remove.append(i)
                p.diff.log(records[i].get("uid", ""), 16, "__record__", "duplicate",
                           f"удалён, дубликат {records[best].get('uid')}", slug)
                p.checkpoint.data["removed"].append(records[i].get("uid"))
                p.stats[16]["notes"].append(
                    f"{slug}: {records[i].get('uid','')[:8]} дубликат {records[best].get('uid','')[:8]}")
        if to_remove:
            records = [r for i, r in enumerate(records) if i not in set(to_remove)]
            p.catalog.data[slug] = records
            total_removed += len(to_remove)
    p.catalog._rebuild_index_map()
    p.stats[16]["changed"] = total_removed
    log.info("Этап 16: удалено %d дублей внутри вариантов.", total_removed)


# =====================================================================
# ЭТАП 17: дубли между этапами и унификация round
# =====================================================================

def stage_17(p: Pipeline):
    """Этап 17: унификация названий этапов, дубли между этапами, round vs source."""
    log.info("Этап 17: таблица соответствий этапов олимпиад:")
    for slug, table in R.ROUND_ALIAS_TABLE.items():
        log.info("  %s: %s", slug, table)

    # 1) Унификация round по таблице + каноническим ключевым словам
    for slug in p.catalog.slugs():
        for rec in p.catalog.data[slug]:
            round_name = rec.get("round") or ""
            key = R.canon_round_key(round_name, slug)
            canon_name = R.ROUND_CANON.get(key) if key else None
            if canon_name and canon_name != round_name:
                p.apply_field(slug, rec, 17, "round", canon_name)

    # 2) Несовпадение round с source: приоритет у источника
    for slug in p.catalog.slugs():
        for rec in p.catalog.data[slug]:
            src = rec.get("source") or ""
            if not src:
                continue
            url_key = R.url_round_key(src)
            round_key = R.canon_round_key(rec.get("round") or "", slug)
            if url_key and round_key and url_key != round_key:
                # URL точнее: исправляем round по источнику
                canon_name = R.ROUND_CANON[url_key]
                p.apply_field(slug, rec, 17, "round", canon_name)
                p.add_qa_note(rec, 17, f"round исправлен по source: {url_key}")

    # 3) Слияние дублей между этапами (после унификации — те же ключи)
    total_merged = 0
    for slug in p.catalog.slugs():
        records = p.catalog.data[slug]
        groups: dict[tuple, list[int]] = {}
        for i, rec in enumerate(records):
            key = (rec.get("year"), str(rec.get("grade")), str(rec.get("num")),
                   R.norm_for_dedupe(rec.get("text") or ""))
            groups.setdefault(key, []).append(i)
        to_remove = []
        for key, idxs in groups.items():
            if len(idxs) < 2:
                continue
            # Разные round после унификации -> сливаем
            rounds = {p.catalog.data[slug][i].get("round") for i in idxs}
            if len(rounds) < 2:
                continue
            idxs_sorted = sorted(idxs, key=lambda i: R.record_quality(records[i]), reverse=True)
            best = idxs_sorted[0]
            for i in idxs_sorted[1:]:
                to_remove.append(i)
                p.diff.log(records[i].get("uid", ""), 17, "__record__", "cross-round duplicate",
                           f"слит с {records[best].get('uid')}", slug)
                p.checkpoint.data["removed"].append(records[i].get("uid"))
        if to_remove:
            p.catalog.data[slug] = [r for i, r in enumerate(records) if i not in set(to_remove)]
            total_merged += len(to_remove)
    p.catalog._rebuild_index_map()
    p.stats[17]["changed"] = p.diff.count(17)
    log.info("Этап 17: слито %d дублей между этапами.", total_merged)


# =====================================================================
# ЭТАП 18: пустой source
# =====================================================================

def _download_and_check(p: Pipeline, rec: dict, url: str) -> tuple[bool, str]:
    """Скачивает URL, извлекает текст, проверяет нечёткое совпадение условия.

    Проверяет также конечный домен ПОСЛЕ редиректов: неофициальный редирект
    отклоняется. Пустое условие — не «доверие URL», а отказ.
    """
    try:
        resp = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"},
                           allow_redirects=True)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        # Конечный URL после редиректов должен остаться официальным
        final_url = str(resp.url)
        if not R.is_official_url(final_url):
            return False, f"редирект на неофициальный домен: {final_url[:80]}"
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            if not HAS_PDF:
                return False, "PDF-библиотеки не установлены"
        # Текст документа — постранично (кэш), сверка по ВСЕМУ документу
        pages = _fetch_doc_pages(url)
        doc_text = "\n".join(pages)
        # Нечёткое совпадение: первые 200 симв. условия в документе
        our_head = R.norm_for_compare((rec.get("text") or "")[:200])
        if not our_head:
            # Нечему сверять — НЕ принимаем по доверию, откладываем на ручную проверку
            return False, "условие пустое — сверка невозможна"
        doc_norm = R.norm_for_compare(doc_text)
        # Ищем вхождения фрагментов условия
        probes = [our_head[i:i+60] for i in range(0, min(len(our_head), 180), 60)]
        hits = sum(1 for pr in probes if pr and pr in doc_norm)
        if probes and hits >= len(probes) * 0.6:
            return True, f"совпадение {hits}/{len(probes)} фрагментов"
        if HAS_RAPIDFUZZ:
            score = fuzz.partial_ratio(our_head, doc_norm) / 100.0
            if score >= 0.8:
                return True, f"нечёткое совпадение {score:.2f}"
        return False, "условие не найдено в документе"
    except Exception as e:
        return False, str(e)[:200]


def _collect_pdf_candidates(p: Pipeline, slug: str, rec: dict, stage: int,
                            kinds=("sol", "ans", "tasks")) -> list[tuple[str, str]]:
    """Кандидаты (origin, url): СНАЧАЛА индекс официальных PDF, потом Gemini.

    Индекс строит olymp_source_index: существующие source из базы + обход
    страницы олимпиады на olimpiada.ru. Gemini — только если в индексе пусто.
    """
    uid = rec.get("uid", "")
    query_desc = (f"{rec.get('olymp')} {rec.get('year')} {rec.get('round')} "
                  f"{rec.get('grade')} кл. №{rec.get('num')}")
    candidates: list[tuple[str, str]] = []
    # 1) Индекс официальных PDF
    try:
        idx = p.get_source_index()
        round_key = R.canon_round_key(rec.get("round") or "", slug)
        found = idx.find(slug, rec.get("year"), round_key, rec.get("grade"),
                          kinds=kinds)
        candidates = [("index", r["url"]) for r in found[:8]]
        p.search_log.log(uid, slug, stage, query_desc, "index", "", "",
                         f"найдено {len(found)} кандидатов")
    except Exception as e:
        log.warning("Этап %d: индекс источников недоступен: %s", stage, str(e)[:150])
    if candidates:
        return candidates
    # 2) Gemini (grounding со stream, компактный промт ≤ 400 токенов).
    #    В dry-run API не вызывается.
    if p.gemini is not None and not p.dry_run:
        payload = {"olymp": rec.get("olymp"), "year": rec.get("year"),
                   "round": rec.get("round"), "grade": rec.get("grade"),
                   "num": rec.get("num"),
                   "text_head": (rec.get("text") or "")[:150]}
        resp = p.gemini.search_candidates(json.dumps(payload, ensure_ascii=False))
        if resp and resp.get("ok"):
            for cand in resp.get("candidates", [])[:5]:
                url = cand.get("url", "")
                if R.is_official_url(url):
                    candidates.append(("gemini", url))
        p.search_log.log(uid, slug, stage, query_desc, "gemini", "", "",
                         f"получено {len(candidates)} кандидатов")
    if not candidates and not p.dry_run:
        # Ни индекс, ни Gemini не дали кандидатов. Если Gemini недоступен
        # (нет ключа) — это инфраструктурный сбой: отложим запись на повтор.
        if p.gemini is None:
            raise RetryableStageError("поиск недоступен: нет OdiRouter/Gemini")
    return candidates


def _official_search(p: Pipeline, slug: str, rec: dict, stage: int,
                     want_solution: bool) -> tuple[bool, str]:
    """Поиск официального PDF: индекс -> Gemini. Скачивание, проверка условия.

    want_solution=True — дополнительно извлечь решение (DeepSeek-chat,
    постранично из PDF) и сверить совпадение условия/ответа (DeepSeek-reasoner).
    Возвращает (found, url_или_причина_отказа). Все попытки логируются
    в work/search_log.jsonl.
    """
    uid = rec.get("uid", "")
    query_desc = (f"{rec.get('olymp')} {rec.get('year')} {rec.get('round')} "
                  f"{rec.get('grade')} кл. №{rec.get('num')}")
    candidates = _collect_pdf_candidates(p, slug, rec, stage)
    if not candidates:
        p.search_log.log(uid, slug, stage, query_desc, "none", "", "",
                         "кандидатов нет")
        return False, "кандидатов нет"
    for origin, url in candidates:
        ok, reason = _download_and_check(p, rec, url)
        p.search_log.log(uid, slug, stage, query_desc, origin, url,
                         "скачан" if ok else "не скачан", reason)
        if not ok:
            continue
        if not want_solution:
            # Достаточно проверить, что условие в документе, — пишем source.
            # Из очереди поиска НЕ убираем: найденный source не решает проблемы
            # заглушек/обрывов/рисунков — этим займётся этап 20.
            p.apply_field(slug, rec, stage, "source", url,
                          model="index" if origin == "index" else "gemini")
            p.search_log.log(uid, slug, stage, query_desc, origin, url, "скачан",
                             f"принято (source): {reason}")
            return True, url
        # Извлечение задачи из документа: постранично.
        # Ищем страницу с условием и передаём её с соседними (решение
        # часто продолжается на следующих страницах), а не весь PDF.
        pages = _fetch_doc_pages(url)
        if not pages:
            p.search_log.log(uid, slug, stage, query_desc, origin, url,
                             "не скачан", "пустой документ")
            continue
        task_pages = _find_task_pages(pages, (rec.get("text") or "")[:200])
        if task_pages:
            i = task_pages[0]
            doc_text = "\n".join(pages[max(0, i - 1): i + 4])
        else:
            doc_text = _fetch_doc_text(url)[:30000]
        payload = {"doc_text": doc_text[:30000], "olymp": rec.get("olymp"),
                   "year": rec.get("year"), "round": rec.get("round"),
                   "grade": rec.get("grade"), "num": rec.get("num"),
                   "text_head": (rec.get("text") or "")[:200]}
        e_resp = (p.deepseek_chat.chat_json(P.STAGE20_EXTRACT_TASK,
                                            json.dumps(payload, ensure_ascii=False))
                  if p.deepseek_chat else None)
        if not e_resp or not e_resp.get("ok"):
            p.search_log.log(uid, slug, stage, query_desc, origin, url, "скачан",
                             "ошибка извлечения задачи из документа")
            continue
        # Верификация reasoner-ом: условие совпадает, решение к тому же ответу
        v_payload = {"our_text": rec.get("text") or "",
                     "our_answer": rec.get("answer") or "",
                     "doc_task_text": e_resp.get("text") or "",
                     "doc_solution": e_resp.get("solution") or "",
                     "doc_answer": e_resp.get("answer") or ""}
        v_resp = _reasoner_verify(p, P.STAGE20_VERIFY_MATCH, v_payload)
        if not v_resp or not v_resp.get("ok"):
            p.search_log.log(uid, slug, stage, query_desc, origin, url, "скачан",
                             "нет вердикта reasoner")
            continue
        if not v_resp.get("condition_match", False):
            p.search_log.log(uid, slug, stage, query_desc, origin, url, "скачан",
                             "условие не совпало (reasoner)")
            continue
        our_ans = (rec.get("answer") or "").strip()
        doc_ans = (e_resp.get("answer") or "").strip()
        # answer_match=False при непустых ответах — тот же конфликт, не выбираем сами
        if v_resp.get("answer_conflict", False) or (
                our_ans and doc_ans and v_resp.get("answer_match") is False):
            # Конфликт: НИЧЕГО не перезаписываем автоматически,
            # оба ответа и URL — в qa с пометкой answer_conflict
            p.add_qa_note(rec, stage, "answer_conflict: найденный документ даёт другой ответ",
                          model="deepseek-reasoner")
            p.add_qa_note(rec, stage,
                          f"answer_conflict: наш: {rec.get('answer')!r}; "
                          f"из документа: {e_resp.get('answer')!r}; документ: {url}",
                          model="deepseek-reasoner")
            p.remove_from_search_queue(uid)
            return False, url
        doc_solution = (e_resp.get("solution") or "").strip()
        doc_answer = (e_resp.get("answer") or "").strip()
        if doc_solution:
            p.apply_field(slug, rec, stage, "solution", doc_solution,
                          model="deepseek-chat+reasoner")
        if doc_answer:
            p.apply_field(slug, rec, stage, "answer", doc_answer,
                          model="deepseek-chat+reasoner")
        p.apply_field(slug, rec, stage, "source", url,
                      model="index" if origin == "index" else "gemini+deepseek")
        # official_found — только когда реально есть решение из официального документа
        if doc_solution:
            p.apply_field(slug, rec, stage, "status", "official_found",
                          model="index" if origin == "index" else "gemini+deepseek")
        else:
            p.add_qa_note(rec, stage,
                          "source найден, но решение в документе отсутствует — "
                          "статус не менялся", model="deepseek-chat+reasoner")
        p.add_qa_note(rec, stage, f"официальное решение найдено: {reason}")
        p.search_log.log(uid, slug, stage, query_desc, origin, url, "скачан",
                         f"принято: {reason}")
        p.remove_from_search_queue(uid)
        return True, url
    p.search_log.log(uid, slug, stage, query_desc, "all", "",
                     "исчерпаны кандидаты", "ни один не прошёл проверку")
    return False, "ни один кандидат не прошёл проверку"


def stage_18(p: Pipeline):
    """Этап 18: заполнение пустого source (индекс -> Gemini)."""
    def worker(slug, rec):
        src = (rec.get("source") or "").strip()
        if src:
            return
        # 1) Официальная ссылка в solution/answer?
        for field in ("solution", "answer"):
            m = re.search(r"https?://[^\s\)\]]+", rec.get(field) or "")
            if m and R.is_official_url(m.group(0)):
                p.apply_field(slug, rec, 18, "source", m.group(0))
                return
        # 2) Поиск: индекс официальных PDF, при пустоте — Gemini.
        #    Модели для индексного пути не нужны (только скачивание и сверка).
        found, result = _official_search(p, slug, rec, 18, want_solution=False)
        if not found:
            p.add_qa_note(rec, 18, f"source_not_found: {result}")

    items = [(s, r) for s, r in p.catalog.all_records() if not (r.get("source") or "").strip()]
    p.run_parallel(18, items, worker, "пустой source")
    p.stats[18]["changed"] = p.diff.count(18)


# =====================================================================
# ЭТАП 19: пересмотр статусов
# =====================================================================

def stage_19(p: Pipeline):
    """Этап 19: пересмотр статусов gemini_solved/AI_*/unresolved."""
    def worker(slug, rec):
        status = rec.get("status") or ""
        if status in ("gemini_solved", "AI_verified", "AI_generated",
                     "AI_generated_with_hints", "unresolved", "broken_text", "figure_only"):
            p.add_to_search_queue(rec.get("uid"))
            p.add_qa_note(rec, 19, f"в очереди поиска (status={status})")

    items = [(s, r) for s, r in p.catalog.all_records()
             if (r.get("status") or "") in
             ("gemini_solved", "AI_verified", "AI_generated", "AI_generated_with_hints",
              "unresolved", "broken_text", "figure_only")]
    p.run_parallel(19, items, worker, "пересмотр статусов")
    p.stats[19]["changed"] = p.diff.count(19)


# =====================================================================
# ЭТАП 20: поиск официальных решений
# =====================================================================

def stage_20(p: Pipeline):
    """Этап 20: поиск официальных решений (индекс -> Gemini + DeepSeek)."""
    if p.deepseek_chat is None or p.deepseek_reasoner is None:
        # Это сбой этапа, а не «пропуск»: если пометить завершённым,
        # --resume больше не вернётся к этим задачам
        raise LLMError("Этап 20: нет доступа к DeepSeek "
                       "(извлечение решения и сверка невозможны)")
    queue = list(dict.fromkeys(p.checkpoint.data.get("search_queue", [])))
    # Пустой source тоже в очередь
    for slug, rec in p.catalog.all_records():
        if not (rec.get("source") or "").strip():
            uid = rec.get("uid")
            if uid not in queue:
                queue.append(uid)
    if p.args.limit:
        queue = queue[: p.args.limit]
    log.info("Этап 20: очередь поиска — %d задач.", len(queue))
    processed = 0
    for uid in queue:
        found = p.catalog.find(uid)
        if found is None:
            continue
        slug, rec = found
        processed += 1
        try:
            _official_search(p, slug, rec, 20, want_solution=True)
        except Exception as e:
            log.error("Этап 20: ошибка на %s: %s", uid[:8], str(e)[:200])
        if processed % 50 == 0:
            log.info("Этап 20: %d/%d обработано.", processed, len(queue))
    p.stats[20]["changed"] = p.diff.count(20)


_DOC_PAGES_CACHE: dict[str, list[str]] = {}


def _fetch_doc_pages(url: str) -> list[str]:
    """Скачивает документ и возвращает тексты СТРАНИЦ по отдельности (с кэшем).

    Постранично — чтобы искать нужную задачу и передавать модели не весь
    документ, а страницу задачи с соседними (решение часто на следующих).
    """
    if url in _DOC_PAGES_CACHE:
        return _DOC_PAGES_CACHE[url]
    pages: list[str] = []
    try:
        resp = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        if "pdf" in resp.headers.get("Content-Type", "") or url.lower().endswith(".pdf"):
            import io
            if not HAS_PDF:
                return []
            try:
                with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                    pages = [(page.extract_text() or "") for page in pdf.pages]
            except Exception:
                try:
                    reader = PdfReader(io.BytesIO(resp.content))
                    pages = [(p.extract_text() or "") for p in reader.pages]
                except Exception:
                    return []
        else:
            html = resp.text
            text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            pages = [text]
    except Exception:
        return []
    _DOC_PAGES_CACHE[url] = pages
    return pages


def _find_task_pages(pages: list[str], text_head: str) -> list[int]:
    """Ищет страницы, содержащие начало условия задачи (нормализованное)."""
    head = R.norm_for_compare(text_head)
    if not head:
        return []
    probe = head[:60]
    return [i for i, pg in enumerate(pages) if probe in R.norm_for_compare(pg)]


def _fetch_doc_text(url: str) -> str:
    """Весь текст документа (для совместимости; внутри — постраничный кэш)."""
    return "\n".join(_fetch_doc_pages(url))


# =====================================================================
# ЭТАП 21: заполнение дыр в нумерации
# =====================================================================

def _make_uid(olymp, year, round_name, grade, num, text) -> str:
    """uid = sha256(olymp|year|round|grade|num|normalized text)."""
    normalized = R.norm_for_compare(text)[:500]
    key = f"{olymp}|{year}|{round_name}|{grade}|{num}|{normalized}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def stage_21(p: Pipeline):
    """Этап 21: заполнение пропущенных номеров в вариантах (индекс -> Gemini)."""
    if p.deepseek_chat is None:
        raise LLMError("Этап 21: нет доступа к DeepSeek (извлечение задач)")
    if p.dry_run:
        log.info("Этап 21: dry-run — новые задачи не добавляются.")
        return
    # Группировка по вариантам
    variants: dict[tuple, list[dict]] = {}
    for slug in p.catalog.slugs():
        for rec in p.catalog.data[slug]:
            key = (slug, rec.get("year"), rec.get("round"), str(rec.get("grade")))
            variants.setdefault(key, []).append(rec)
    # Приоритет: заключительные 9-11 классов последних лет
    def priority(key):
        slug, year, round_name, grade = key
        rk = R.canon_round_key(round_name or "", slug)
        round_p = {"final": 0, "qual": 1, "regional": 2}.get(rk, 3)
        grade_p = {"9": 0, "10": 0, "11": 0}.get(grade, 1)
        return (round_p, grade_p, -(year or 0))

    added = 0
    ordered_keys = sorted(variants, key=priority)
    # --limit для этапа 21 — это число ОБРАБАТЫВАЕМЫХ ВАРИАНТОВ
    if p.args.limit:
        log.info("Этап 21: --limit %d — обрабатываем первые %d вариантов.",
                 p.args.limit, min(p.args.limit, len(ordered_keys)))
        ordered_keys = ordered_keys[: p.args.limit]
    for key in ordered_keys:
        slug, year, round_name, grade = key
        recs = variants[key]
        # Нумерация сквозная по дням (ВсОШ): объединяем дни
        nums = set()
        max_num = 0
        for r in recs:
            try:
                n = int(str(r.get("num", "0")).strip() or 0)
            except ValueError:
                continue
            nums.add(n)
            max_num = max(max_num, n)
        if max_num == 0:
            continue
        missing = [n for n in range(1, max_num + 1) if n not in nums]
        if not missing:
            continue
        log.info("Этап 21: %s %s %s %s класс: пропущены %s (макс %d).",
                 slug, year, round_name, grade, missing, max_num)
        context = recs[0]
        query_desc = f"{slug} {year} {round_name} {grade} кл."
        # Кандидаты PDF варианта: СНАЧАЛА индекс, потом Gemini
        candidates: list[tuple[str, str]] = []
        try:
            idx = p.get_source_index()
            round_key = R.canon_round_key(round_name or "", slug)
            found = idx.find(slug, year, round_key, grade, kinds=("tasks", "sol"))
            candidates = [("index", r["url"]) for r in found[:5]]
            p.search_log.log("", slug, 21, query_desc, "index", "", "",
                             f"найдено {len(found)} кандидатов")
        except Exception as e:
            log.warning("Этап 21: индекс недоступен: %s", str(e)[:150])
        if not candidates and p.gemini is not None:
            payload = {"olymp": context.get("olymp"), "year": year, "round": round_name,
                       "grade": grade, "missing_nums": [str(n) for n in missing]}
            s_resp = p.gemini.search_variant_pdf(json.dumps(payload, ensure_ascii=False))
            if s_resp and s_resp.get("ok"):
                for cand in s_resp.get("candidates", [])[:5]:
                    url = cand.get("url", "")
                    if R.is_official_url(url):
                        candidates.append(("gemini", url))
            p.search_log.log("", slug, 21, query_desc, "gemini", "", "",
                             f"получено {len(candidates)} кандидатов")
        for origin, url in candidates:
            # Скачиваем документ (постранично) — логируем фактический результат
            pages = _fetch_doc_pages(url)
            if not pages:
                p.search_log.log("", slug, 21, query_desc, origin, url,
                                 "не скачан", "пустой документ")
                continue
            doc_text = "\n".join(pages)
            p.search_log.log("", slug, 21, query_desc, origin, url,
                             "скачан", f"{len(pages)} страниц")
            e_payload = {"doc_text": doc_text[:30000],
                         "missing_nums": [str(n) for n in missing],
                         "grade": grade,
                         "context_task": (recs[0].get("text") or "")[:300]}
            e_resp = p.deepseek_chat.chat_json(P.STAGE21_EXTRACT_MISSING,
                                               json.dumps(e_payload, ensure_ascii=False))
            if not e_resp or not e_resp.get("ok"):
                p.search_log.log("", slug, 21, query_desc, origin, url, "скачан",
                                 "ошибка извлечения задач из документа")
                continue
            for task in e_resp.get("tasks", []):
                num = str(task.get("num", "")).strip()
                if not num or int(num) not in missing:
                    continue
                text = (task.get("text") or "").strip()
                if not text:
                    continue
                # Проверка 1: извлечённый текст реально содержится в документе
                head = R.norm_for_compare(text[:120])
                doc_norm = R.norm_for_compare(doc_text)
                if head and head[:60] not in doc_norm:
                    log.warning("Этап 21: задача №%s не найдена в документе дословно — пропущена.", num)
                    p.search_log.log("", slug, 21, query_desc, origin, url, "скачан",
                                     f"задача №{num}: нет в документе дословно — пропущена")
                    continue
                # Проверка 2 (reasoner): решение приводит к извлечённому ответу
                task_sol = (task.get("solution") or "").strip()
                task_ans = (task.get("answer") or "").strip()
                if task_sol and task_ans and p.deepseek_reasoner is not None:
                    chk = p.deepseek_reasoner.chat_json(
                        P.STAGE11_ANSWER_CHECK,
                        json.dumps({"text": text, "answer": task_ans,
                                    "solution": task_sol}, ensure_ascii=False))
                    if not chk or chk.get("verdict") == "mismatch":
                        p.search_log.log("", slug, 21, query_desc, origin, url, "скачан",
                                         f"задача №{num}: ответ не сходится с решением — пропущена")
                        continue
                uid = _make_uid(context.get("olymp"), year, round_name, grade, num, text)
                if p.catalog.find(uid):
                    continue
                new_rec = {
                    "uid": uid,
                    "olymp": context.get("olymp"),
                    "year": year,
                    "round": round_name,
                    "day": context.get("day", 0),
                    "grade": grade,
                    "num": num,
                    "status": "official_found",
                    "answer": task.get("answer") or "",
                    "source": url,
                    "text": text,
                    "solution": task.get("solution") or "",
                    # day/geo — по аналогии с соседями; fig_* НЕ копируем
                    # (файлы рисунков соседа относятся к другой задаче)
                    "geo": any(r.get("geo") for r in recs),
                    "fig_statement": [],
                    "fig_solution": [],
                    "qa": {"stage21": {"stage": 21, "model": "gemini+deepseek",
                                       "changes": {}, "notes": [f"добавлена задача №{num} из {url}"]}},
                }
                p.catalog.data[slug].append(new_rec)
                p.checkpoint.data["added"].append(uid)
                p.diff.log(uid, 21, "__record__", "missing", f"добавлена задача №{num}", slug)
                added += 1
            break  # Нашли рабочий источник — дальше не ищем
    p.catalog._rebuild_index_map()
    p.stats[21]["changed"] = added
    log.info("Этап 21: добавлено %d задач.", added)


# =====================================================================
# ЭТАП 22: финальная валидация и отчёт
# =====================================================================

def stage_22(p: Pipeline):
    """Этап 22: валидация, пересчёт _index.json, отчёт."""
    issues = []
    # 1) JSON валиден (мы его сериализуем — проверка круглым путём)
    for slug in p.catalog.slugs():
        try:
            json.dumps(p.catalog.data[slug], ensure_ascii=False)
        except Exception as e:
            issues.append(f"{slug}: невалидный JSON ({e})")
    # 2) uid уникальны
    seen: dict[str, str] = {}
    for slug, rec in p.catalog.all_records():
        uid = rec.get("uid", "")
        if not uid:
            issues.append(f"{slug}: запись без uid")
            continue
        if uid in seen:
            issues.append(f"дубликат uid {uid[:8]} в {slug} и {seen[uid]}")
        seen[uid] = slug
    # 3) Пересчёт индекса и сохранение
    if not p.dry_run:
        p.catalog.save(FIXED_DIR)
    # 4) Запуск отчёта о дырах
    gaps_result = ""
    gaps_script = BASE_DIR / "scripts" / "olymp_catalog_gaps.py"
    if gaps_script.exists() and not p.dry_run:
        try:
            res = subprocess.run(
                [sys.executable, str(gaps_script)],
                capture_output=True, text=True, timeout=600)
            gaps_result = (res.stdout or "") + (res.stderr or "")
        except Exception as e:
            gaps_result = f"не удалось запустить: {e}"
    # 5) Отчёт
    _write_report(p, issues, gaps_result)


def _write_report(p: Pipeline, validation_issues: list[str], gaps_result: str):
    """Сводный отчёт reports/olymp_catalog_fix.md."""
    REPORTS_DIR.mkdir(exist_ok=True)
    lines = ["# Отчёт: чистка каталога олимпиадных задач FORMYLA", "",
             f"Дата: {now_iso()}  ", f"Режим: {'DRY RUN' if p.dry_run else 'обычный'}  ",
             f"Этапы: {','.join(str(s) for s in sorted(p.stages))}  ",
             f"Олимпиада: {p.args.slug or 'все'}", "",
             "## Сводка по этапам", "",
             "| Этап | Обработано | Изменено | Ошибки | Примечания |",
             "|---|---|---|---|---|"]
    stage_names = {
        1: "нормализация символов", 2: "PDF-мусор", 3: "Markdown-мусор",
        4: "LaTeX-разделители", 5: "LaTeX-окружения", 6: "порезанные формулы",
        7: "формулы без LaTeX", 8: "условие+решение", 9: "дубль условия",
        10: "мусорные ответы", 11: "сверка ответа", 12: "заглушки решений",
        13: "обрезанные решения", 14: "обрезанные условия", 15: "рисунки",
        16: "дубли в вариантах", 17: "этапы олимпиад", 18: "пустой source",
        19: "статусы", 20: "поиск решений", 21: "дыры в нумерации",
        22: "валидация",
    }
    for s in range(1, STAGES_COUNT + 1):
        st = p.stats[s]
        notes = "; ".join(st["notes"][:5]) or stage_names.get(s, "")
        lines.append(f"| {s} | {st['processed']} | {st['changed']} | "
                     f"{st['errors']} | {notes} |")
    # Валидация
    lines += ["", "## Валидация", ""]
    if validation_issues:
        lines += [f"- ПРОБЛЕМА: {i}" for i in validation_issues[:20]]
    else:
        lines.append("- JSON валиден, uid уникальны.")
    # Дыры
    if gaps_result:
        lines += ["", "## Отчёт о дырах (olymp_catalog_gaps.py)", "",
                  "```", gaps_result[:3000], "```"]
    # Было/стало по типам проблем и олимпиадам
    if p.before_issues is not None:
        after = R.detect_issues(p.catalog.data)
        all_keys = sorted(set(p.before_issues) | set(after))
        lines += ["", "## Было / стало (по типам проблем и олимпиадам)", "",
                  "| Тип проблемы | Олимпиада | Было | Стало |",
                  "|---|---|---|---|"]
        shown = 0
        for (issue, slug) in all_keys:
            b = p.before_issues.get((issue, slug), 0)
            a = after.get((issue, slug), 0)
            if b == 0 and a == 0:
                continue
            lines.append(f"| {issue} | {slug} | {b} | {a} |")
            shown += 1
            if shown > 400:
                lines.append("| ... | | | |")
                break
        if shown == 0:
            lines.append("| (изменений по детекторам не найдено) | | | |")
    # Токены
    lines += ["", "## Использование токенов по провайдерам", ""]
    lines.append(f"- Поиск источников: {p.search_log.summary()} "
                 f"(детали: work/search_log.jsonl)")
    usage = p._usage_total()
    for name, u in usage.items():
        lines.append(f"- **{name}**: {u['calls']} вызовов, "
                     f"{u['prompt_tokens']} ток. ввода, "
                     f"{u['completion_tokens']} ток. вывода, "
                     f"ошибок: {u['errors']}")
    lines.append("")
    lines.append("_Стоимость в деньгах не рассчитана: тарифы провайдеров не заданы._")
    # Список needs_review
    lines += ["", "## Задачи для ручной проверки (needs_review)", ""]
    review_count = 0
    for slug, rec in p.catalog.all_records():
        qa = rec.get("qa") or {}
        for stage_key, entry in qa.items():
            notes = entry.get("notes", [])
            if any("needs_review" in n or "answer_conflict" in n for n in notes):
                lines.append(f"- `{slug}` {rec.get('year')}/{rec.get('round')}/"
                             f"{rec.get('grade')} №{rec.get('num')} "
                             f"(uid {rec.get('uid','')[:8]}): "
                             f"{'; '.join(notes)[:200]}")
                review_count += 1
                if review_count > 200:
                    lines.append("- ... (сокращено, полный список в qa-полях)")
                    break
        if review_count > 200:
            break
    if review_count == 0:
        lines.append("- Пусто.")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log.info("Отчёт записан: %s", REPORT_PATH)


# =====================================================================
# Применение результата (--apply)
# =====================================================================

def apply_fixed(p: Pipeline):
    """Копирует data/olymp_catalog_fixed -> data/olymp_catalog с бэкапом."""
    if p.dry_run:
        log.error("--apply не работает вместе с --dry-run.")
        sys.exit(2)
    if not FIXED_DIR.exists():
        log.error("Каталог %s не найден. Сначала запустите этапы без --apply.", FIXED_DIR)
        sys.exit(2)
    backup = BACKUP_DIR / f"olymp_catalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if DATA_DIR.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copytree(DATA_DIR, backup)
        log.info("Бэкап оригинала: %s", backup)
    # Валидация перед копированием
    for fp in sorted(FIXED_DIR.glob("*.json")):
        try:
            json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            log.error("Валидация не пройдена: %s (%s). Копирование отменено.", fp.name, e)
            sys.exit(2)
    uids = set()
    for fp in sorted(FIXED_DIR.glob("*.json")):
        if fp.stem == "_index":
            continue
        for rec in json.loads(fp.read_text(encoding="utf-8")):
            uid = rec.get("uid", "")
            if uid in uids:
                log.error("Дубликат uid %s — копирование отменено.", uid[:8])
                sys.exit(2)
            uids.add(uid)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for fp in FIXED_DIR.glob("*.json"):
        shutil.copy2(fp, DATA_DIR / fp.name)
    log.info("Применено: %d файлов скопировано в %s.", len(list(FIXED_DIR.glob('*.json'))), DATA_DIR)


# =====================================================================
# CLI
# =====================================================================

def parse_stages(spec: str) -> set[int]:
    """Парсинг '1,3,5-9' в множество номеров этапов."""
    spec = (spec or "").strip()
    if spec.lower() == "all":
        return set(range(1, STAGES_COUNT + 1))
    result = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                result.update(range(int(lo), int(hi) + 1))
            except ValueError:
                raise argparse.ArgumentTypeError(f"Некорректный диапазон: {part}")
        else:
            result.add(int(part))
    if not result or any(s < 1 or s > STAGES_COUNT for s in result):
        raise argparse.ArgumentTypeError(f"Этапы должны быть в 1..{STAGES_COUNT}")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Пайплайн чистки базы олимпиадных задач FORMYLA (22 этапа).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--stages", type=parse_stages, default=None,
                        help="Этапы: '1,3,5-9' или 'all' (по умолчанию 1-22)")
    parser.add_argument("--slug", help="Одна олимпиада (например, phystech)")
    parser.add_argument("--limit", type=int, help="Максимум задач для обработки")
    parser.add_argument("--dry-run", action="store_true",
                        help="Не изменять данные и чекпоинт, только отчёт")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="Число параллельных потоков")
    parser.add_argument("--resume", action="store_true",
                        help="Продолжить с чекпоинта")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="Перестроить индекс официальных PDF (work/source_index)")
    parser.add_argument("--apply", action="store_true",
                        help="Скопировать результат в data/olymp_catalog с бэкапом")
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT_PATH,
                        help="Путь к чекпоинту")
    parser.add_argument("--source", help="Каталог-источник (по умолчанию: "
                        "data/olymp_catalog_fixed если существует, иначе data/olymp_catalog)")
    return parser


STAGE_FUNCS = {1: stage_01, 2: stage_02, 3: stage_03, 4: stage_04, 5: stage_05,
               6: stage_06, 7: stage_07, 8: stage_08, 9: stage_09, 10: stage_10,
               11: stage_11, 12: stage_12, 13: stage_13, 14: stage_14, 15: stage_15,
               16: stage_16, 17: stage_17, 18: stage_18, 19: stage_19,
               20: stage_20, 21: stage_21, 22: stage_22}


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.stages is None:
        args.stages_set = set(range(1, STAGES_COUNT + 1))
    else:
        args.stages_set = set(args.stages)
    if args.dry_run and args.apply:
        log.error("--dry-run и --apply несовместимы.")
        sys.exit(2)
    # Автовыбор источника: fixed если уже есть (продолжение работы)
    if args.source is None:
        if FIXED_DIR.exists() and not args.apply:
            have = {p.stem for p in FIXED_DIR.glob("*.json") if p.stem != "_index"}
            needed = {args.slug} if args.slug else set()
            if not needed or needed <= have:
                args.source = str(FIXED_DIR)
                log.info("Источник: %s (результат предыдущего запуска). "
                         "Для принудительной чистки оригинала: --source data/olymp_catalog",
                         args.source)
            else:
                log.warning("В %s нет файла %s.json — источник: data/olymp_catalog.",
                            FIXED_DIR, args.slug)
                args.source = str(DATA_DIR)
        else:
            args.source = str(DATA_DIR)
    if args.dry_run:
        REPORTS_DIR.mkdir(exist_ok=True)
    else:
        WORK_DIR.mkdir(exist_ok=True)
        REPORTS_DIR.mkdir(exist_ok=True)

    p = Pipeline(args)

    if args.apply:
        apply_fixed(p)
        return

    log.info("Запуск этапов: %s", sorted(args.stages_set))
    stage_ran_22 = False
    for stage_num in sorted(args.stages_set):
        func = STAGE_FUNCS[stage_num]
        log.info("=" * 60)
        log.info("ЭТАП %d: %s", stage_num, func.__doc__.splitlines()[0] if func.__doc__ else "")
        try:
            func(p)
            if stage_num == 22:
                stage_ran_22 = True
        except Exception as e:
            log.error("Этап %d завершился ошибкой: %s", stage_num, e, exc_info=True)
            p.stats[stage_num]["errors"] += 1
            # Провалившийся этап НЕ помечаем завершённым — повторный запуск повторит его
            p.checkpoint.stage_failed(stage_num, str(e))
            continue
        if not p.dry_run:
            p.checkpoint.stage_complete(stage_num)
            p.save_state()

    if not p.dry_run:
        p.checkpoint.data["usage"] = p._usage_total()
        p.checkpoint.save()
    # Отчёт пишем всегда (этап 22 пишет свой — с валидацией и дырами)
    if not stage_ran_22:
        if p.dry_run:
            _write_report(p, ["dry-run: изменения не применены (API не вызывался)"], "")
        else:
            _write_report(p, ["этап 22 не выполнялся — полная валидация не проводилась"], "")
    log.info("=" * 60)
    log.info("Готово. Отчёт: %s, каталог: %s", REPORT_PATH, FIXED_DIR)
    if p.dry_run:
        log.info("Это был dry-run: данные не изменены. "
                 "Изменений предложено: %d (см. отчёт).", len(p.llm_changes))


if __name__ == "__main__":
    main()

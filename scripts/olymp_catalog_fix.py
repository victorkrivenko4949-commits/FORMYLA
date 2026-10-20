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
import difflib
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
MAX_TOKENS = 8192
PDF_BLOCK_CHUNK_SIZE = 12000
PDF_BLOCK_CHUNK_OVERLAP = 1500
FINGERPRINT_FIELDS = ["olymp", "year", "round", "grade", "num", "status",
                      "answer", "source", "text", "solution",
                      "geo", "fig_statement", "fig_solution"]

OLYMP_NAMES: dict[str, str] = {
    "vsosh": "ВсОШ по математике",
    "mmo": "Московская математическая олимпиада",
    "kurchatov": "Олимпиада «Курчатов»",
    "turgor": "Турнир городов",
    "lomonosov": "Олимпиада «Ломоносов»",
    "formula-unity": "Олимпиада «Формула Единства» / «Третье тысячелетие»",
    "pvg": "Покори Воробьёвы горы!",
    "euler": "Математическая олимпиада им. Леонарда Эйлера",
    "vysshaya-proba": "Олимпиада «Высшая проба»",
    "matprazdnik": "Математический праздник",
    "spbgu": "Олимпиада школьников СПбГУ",
    "phystech": "Олимпиада «Физтех»",
}

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
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _salvage_truncated_tasks_json(raw: str) -> dict | None:
    """Спасает закрытые объекты задач {...} из обрезанного JSON-ответа с массивом "tasks".

    Когда выход модели обрезается по MAX_TOKENS посередине следующей задачи,
    все полностью закрытые задачи до обрыва сохраняются, а оставшиеся номера
    добираются повторным точечным запросом STAGE21_EXTRACT_MISSING.
    """
    if not raw:
        return None
    m = re.search(r'"tasks"\s*:\s*\[', raw)
    if not m:
        return None
    tasks: list[dict] = []
    in_str = False
    escape = False
    depth = 0
    obj_start = None
    for idx in range(m.end(), len(raw)):
        ch = raw[idx]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                obj_start = idx
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and obj_start is not None:
                    frag = raw[obj_start: idx + 1]
                    obj_start = None
                    try:
                        obj = json.loads(frag)
                        if isinstance(obj, dict) and ("num" in obj or "text" in obj or "solution" in obj):
                            tasks.append(obj)
                    except json.JSONDecodeError:
                        pass
        elif ch == "]" and depth == 0:
            break
    if tasks:
        return {"ok": True, "tasks": tasks, "_salvaged": True}
    return None


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
            salvaged = _salvage_truncated_tasks_json(content)
            if salvaged is not None:
                log.info("%s: спасено %d закрытых задач из обрезанного JSON-ответа",
                         self.name, len(salvaged.get("tasks", [])))
                return salvaged
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
        if enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, uid: str, stage: int, field: str, old, new, slug: str = ""):
        entry = {"ts": now_iso(), "uid": uid, "slug": slug, "stage": stage,
                 "field": field, "old": old, "new": new}
        self.entries.append(entry)
        if self.enabled:
            with _lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
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
        if enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, uid: str, slug: str, stage: int, query: str, origin: str,
            url: str, status: str, result: str):
        entry = {"ts": now_iso(), "uid": uid, "slug": slug, "stage": stage,
                 "query": query, "origin": origin, "url": url,
                 "status": status, "result": result}
        self.entries.append(entry)
        if self.enabled:
            with _lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
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

    only_uids = None   # если задано — all_records() отдаёт только эти uid (повторная чистка импорта)

    def all_records(self) -> list[tuple[str, dict]]:
        recs = [(slug, rec) for slug in self.data for rec in self.data[slug]]
        if self.only_uids:
            recs = [(s, r) for s, r in recs if r.get("uid") in self.only_uids]
        return recs

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
        # _index.json: формат массива [{"slug", "name", "count", "with_figs", "years": [min, max]}],
        # совместимый с routes/olymp_catalog.py и scripts/olymp_catalog_gaps.py.
        # Записи нетронутых олимпиад (при --slug) сохраняем из существующего _index.json.
        existing_entries: dict[str, dict] = {}
        order_slugs: list[str] = []

        def _ingest_index(raw):
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict) and item.get("slug"):
                        s = item["slug"]
                        existing_entries[s] = dict(item)
                        if s not in order_slugs:
                            order_slugs.append(s)
            elif isinstance(raw, dict) and isinstance(raw.get("files"), dict):
                for s, item in raw["files"].items():
                    if isinstance(item, dict):
                        yrs = item.get("years") or []
                        yr_range = [min(yrs), max(yrs)] if yrs else []
                        existing_entries[s] = {
                            "slug": s,
                            "name": item.get("name") or OLYMP_NAMES.get(s, s),
                            "count": item.get("count", 0),
                            "with_figs": item.get("with_figs", 0),
                            "years": yr_range,
                        }
                        if s not in order_slugs:
                            order_slugs.append(s)

        for cand_idx in (DATA_DIR / "_index.json", out_dir / "_index.json"):
            if cand_idx.exists():
                try:
                    _ingest_index(json.loads(cand_idx.read_text(encoding="utf-8")))
                except Exception:
                    pass
        _ingest_index(self.index)

        for slug, records in self.data.items():
            years = sorted({int(r["year"]) for r in records
                            if r.get("year") is not None and str(r.get("year")).isdigit()})
            yr_range = [years[0], years[-1]] if years else []
            figs = sum(1 for r in records if (r.get("fig_statement") or r.get("fig_solution")))
            prev = existing_entries.get(slug) or {}
            name = (prev.get("name")
                    or (records[0].get("olympiad") if records and records[0].get("olympiad") else None)
                    or OLYMP_NAMES.get(slug, slug))
            existing_entries[slug] = {
                "slug": slug,
                "name": name,
                "count": len(records),
                "with_figs": figs,
                "years": yr_range,
            }
            if slug not in order_slugs:
                order_slugs.append(slug)

        idx_list = [existing_entries[s] for s in order_slugs if s in existing_entries]
        total_tasks = sum(e.get("count", 0) for e in idx_list)
        (out_dir / "_index.json").write_text(
            json.dumps(idx_list, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Каталог сохранён в %s (%d файлов, %d задач).",
                 out_dir, len(idx_list), total_tasks)


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
        self.stage21_report: dict[str, dict] = {}   # отчёт этапа 21 по олимпиадам
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
        # Ведущие и парные ** / ~~ в answer и solution
        new_ans = R.LEADING_TRAILING_MD.sub("", new_ans).strip()
        new_ans = re.sub(r"\*\*([^\n*]+?)\*\*", r"\1", new_ans)
        new_ans = new_ans.replace("**", "").strip()
        new_sol = re.sub(r"\*\*([^\n*]+?)\*\*", r"\1", new_sol)
        new_sol = re.sub(r"~~([^\n~]+?)~~", r"\1", new_sol)
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
    if old == new or (old and new and old.strip() == new.strip()):
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
        # Сверка reasoner-ом независимо для каждого изменённого непустого поля
        if text and new_text != text:
            if _math_gate(p, text, new_text, rec, 6):
                p.apply_field(slug, rec, 6, "text", new_text, model="deepseek-chat")
        if sol and new_sol != sol:
            if _math_gate(p, sol, new_sol, rec, 6):
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
        # Явный вердикт эквивалентности независимо для каждого изменённого поля
        if text and new_text != text:
            if _math_gate(p, text, new_text, rec, 7):
                p.apply_field(slug, rec, 7, "text", new_text, model="deepseek-chat")
        if sol and new_sol != sol:
            if _math_gate(p, sol, new_sol, rec, 7):
                p.apply_field(slug, rec, 7, "solution", new_sol, model="deepseek-chat")

    items = [(s, r) for s, r in p.catalog.all_records()
             if ((R.RAW_MATH_SYMBOLS_RE.search(r.get("text") or "")
                  and "\\(" not in (r.get("text") or "")[:200])
                 or (R.RAW_MATH_SYMBOLS_RE.search(r.get("solution") or "")
                     and "\\(" not in (r.get("solution") or "")[:200]))]
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
        # Гейт: разделение не должно менять математику (дословный префикс/подстрока
        # исходного поля не требует отдельного вызова reasoner; иначе сверяем
        # соответствующий префикс или реконструкцию «условие + решение + ответ»).
        if new_text and new_text != text:
            if new_text not in text:
                head_orig = text[: max(len(new_text) + 40, len(new_text))]
                if not _math_gate(p, head_orig, new_text, rec, 8):
                    return
        if sol_part and sol_part != sol:
            if sol_part not in text:
                reconstructed = "\n".join(x for x in (new_text or text, sol_part, ans_part) if x)
                if not _math_gate(p, text, reconstructed, rec, 8):
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
            # Сортируем по качеству, оставляем лучшего и обогащаем недостающими полями
            idxs_sorted = sorted(idxs, key=lambda i: R.record_quality(records[i]), reverse=True)
            best = idxs_sorted[0]
            for i in idxs_sorted[1:]:
                for fld in ("source", "solution", "answer", "variant", "fig_statement", "fig_solution"):
                    if not (records[best].get(fld) or "") and (records[i].get(fld) or ""):
                        p.apply_field(slug, records[best], 16, fld, records[i][fld])
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

    # 3) Слияние дублей между этапами (в том числе тех, у которых шаги 1–2
    #    уже привели round к одному каноническому названию)
    total_merged = 0
    for slug in p.catalog.slugs():
        records = p.catalog.data[slug]
        groups: dict[tuple, list[int]] = {}
        for i, rec in enumerate(records):
            key = (rec.get("year"), str(rec.get("grade")), str(rec.get("num")),
                   str(rec.get("variant") or "").strip(),
                   R.norm_for_dedupe(rec.get("text") or ""))
            groups.setdefault(key, []).append(i)
        to_remove = []
        for key, idxs in groups.items():
            if len(idxs) < 2:
                continue
            idxs_sorted = sorted(idxs, key=lambda i: R.record_quality(records[i]), reverse=True)
            best = idxs_sorted[0]
            for i in idxs_sorted[1:]:
                for fld in ("source", "solution", "answer", "variant", "fig_statement", "fig_solution"):
                    if not (records[best].get(fld) or "") and (records[i].get(fld) or ""):
                        p.apply_field(slug, records[best], 17, fld, records[i][fld])
                to_remove.append(i)
                p.diff.log(records[i].get("uid", ""), 17, "__record__", "cross-round duplicate",
                           f"слит с {records[best].get('uid')}", slug)
                p.checkpoint.data["removed"].append(records[i].get("uid"))
        if to_remove:
            p.catalog.data[slug] = [r for i, r in enumerate(records) if i not in set(to_remove)]
            total_merged += len(to_remove)
        # Дополнительный проход внутри (year, round, grade) после унификации round
        records = p.catalog.data[slug]
        same_round_groups: dict[tuple, list[int]] = {}
        for i, rec in enumerate(records):
            r_key = (rec.get("year"), rec.get("round"), str(rec.get("grade")),
                     R.norm_for_dedupe(rec.get("text") or ""))
            same_round_groups.setdefault(r_key, []).append(i)
        to_remove_2 = []
        for r_key, idxs in same_round_groups.items():
            if len(idxs) < 2:
                continue
            idxs_sorted = sorted(idxs, key=lambda i: R.record_quality(records[i]), reverse=True)
            best = idxs_sorted[0]
            for i in idxs_sorted[1:]:
                for fld in ("source", "solution", "answer", "variant", "fig_statement", "fig_solution"):
                    if not (records[best].get(fld) or "") and (records[i].get(fld) or ""):
                        p.apply_field(slug, records[best], 17, fld, records[i][fld])
                to_remove_2.append(i)
                p.diff.log(records[i].get("uid", ""), 17, "__record__", "same-round duplicate after round unification",
                           f"слит с {records[best].get('uid')}", slug)
                p.checkpoint.data["removed"].append(records[i].get("uid"))
        if to_remove_2:
            p.catalog.data[slug] = [r for i, r in enumerate(records) if i not in set(to_remove_2)]
            total_merged += len(to_remove_2)
    p.catalog._rebuild_index_map()
    p.stats[17]["changed"] = p.diff.count(17)
    log.info("Этап 17: слито %d дублей между этапами.", total_merged)


# =====================================================================
# ЭТАП 18: пустой source
# =====================================================================

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
              "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
              "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}


# =====================================================================
# ЭТАП 19: пересмотр статусов
# =====================================================================

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


def _fetch_doc_result(url: str) -> dict:
    """Скачивает документ и возвращает страницы + диагностику.

    Единая точка скачивания для этапов 18/20/21: браузерный User-Agent,
    редиректы, PDF и octet-stream. Возвращает
    {ok, pages, http_code, content_type, final_url, error} — код и тип
    логируются, чтобы отказы были объяснимы.
    """
    res = {"ok": False, "pages": [], "http_code": "", "content_type": "",
           "final_url": "", "error": ""}
    try:
        resp = requests.get(url, timeout=60, headers=BROWSER_UA, allow_redirects=True)
        res["http_code"] = str(resp.status_code)
        res["content_type"] = (resp.headers.get("Content-Type", "") or "")
        res["final_url"] = str(resp.url)
        # Конечный домен ПОСЛЕ редиректов должен остаться официальным —
        # проверка в единой точке скачивания (этапы 18/20/21)
        if res["final_url"] and not R.is_official_url(res["final_url"]):
            res["error"] = (f"редирект на неофициальный домен: "
                            f"{res['final_url'][:80]}")
            return res
        if resp.status_code != 200:
            res["error"] = f"HTTP {resp.status_code}"
            return res
        ctype = res["content_type"].lower()
        is_pdf_url = ".pdf" in url.lower().split("?")[0]
        looks_binary = ("pdf" in ctype or "octet-stream" in ctype
                        or "binary" in ctype)
        pages: list[str] = []
        if "pdf" in ctype or looks_binary or is_pdf_url:
            if not HAS_PDF:
                res["error"] = "PDF-библиотеки не установлены"
                return res
            pages = _pdf_pages_from_bytes(resp.content)
            if not pages and not resp.content.lstrip()[:5].startswith(b"%PDF"):
                # не PDF на самом деле — пробуем как HTML
                html = resp.text
                text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text)
                pages = [text] if text.strip() else []
        else:
            html = resp.text
            text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            pages = [text] if text.strip() else []
        res["pages"] = pages
        res["ok"] = bool(pages)
        if not pages:
            res["error"] = "пустой документ"
    except Exception as e:
        res["error"] = str(e)[:200]
    return res


def _pdf_pages_from_bytes(content: bytes) -> list[str]:
    """Тексты страниц PDF (pdfplumber, fallback pypdf)."""
    import io
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return [(page.extract_text() or "") for page in pdf.pages]
    except Exception:
        try:
            reader = PdfReader(io.BytesIO(content))
            return [(p.extract_text() or "") for p in reader.pages]
        except Exception:
            return []


def _fetch_doc_pages(url: str) -> list[str]:
    """Страницы документа (с кэшем) — обёртка над _fetch_doc_result."""
    if url in _DOC_PAGES_CACHE:
        return _DOC_PAGES_CACHE[url]
    res = _fetch_doc_result(url)
    pages = res["pages"]
    if res["ok"]:
        _DOC_PAGES_CACHE[url] = pages
    return pages


def _download_and_check(p: Pipeline, rec: dict, url: str) -> tuple[bool, str, str, str]:
    """Скачивает URL, извлекает текст, проверяет нечёткое совпадение условия.

    Возвращает (ok, причина, http_code, content_type) — код и тип пишутся
    в search_log, чтобы отказы были объяснимы. Единое скачивание через
    _fetch_doc_result (браузерный UA, редиректы, PDF и octet-stream).
    Конечный домен ПОСЛЕ редиректов: неофициальный редирект отклоняется.
    Пустое условие — не «доверие URL», а отказ.
    """
    res = _fetch_doc_result(url)
    http_code, content_type = res["http_code"], res["content_type"]
    if res["final_url"] and not R.is_official_url(res["final_url"]):
        return (False, f"редирект на неофициальный домен: {res['final_url'][:80]}",
                http_code, content_type)
    if not res["ok"]:
        return False, res["error"] or "пустой документ", http_code, content_type
    pages = res["pages"]
    _DOC_PAGES_CACHE[url] = pages   # кэш: этап 20/21 не качает повторно
    doc_text = "\n".join(pages)
    # Нечёткое совпадение: первые 200 симв. условия в документе
    our_head = R.norm_for_compare((rec.get("text") or "")[:200])
    if not our_head:
        # Нечему сверять — НЕ принимаем по доверию, откладываем на ручную проверку
        return False, "условие пустое — сверка невозможна", http_code, content_type
    doc_norm = R.norm_for_compare(doc_text)
    doc_cyr = _cyr_only(doc_text)
    if _text_in_doc(rec.get("text") or "", doc_norm, doc_cyr):
        return True, "совпадение по кириллице (_text_in_doc)", http_code, content_type
    # Ищем вхождения фрагментов условия
    probes = [our_head[i:i+60] for i in range(0, min(len(our_head), 180), 60)]
    hits = sum(1 for pr in probes if pr and pr in doc_norm)
    if probes and hits >= len(probes) * 0.6:
        return True, f"совпадение {hits}/{len(probes)} фрагментов", http_code, content_type
    score = _text_contained((rec.get("text") or "")[:200], doc_text)
    if score >= 0.8:
        return (True, f"нечёткое совпадение {score:.2f}", http_code, content_type)
    return False, "условие не найдено в документе", http_code, content_type


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
    # 1) Индекс официальных PDF (с учётом варианта, если задан)
    try:
        idx = p.get_source_index()
        round_key = R.canon_round_key(rec.get("round") or "", slug)
        found = idx.find(slug, rec.get("year"), round_key, rec.get("grade"),
                          kinds=kinds, variant=rec.get("variant"))
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
    source_only_url = None
    for origin, url in candidates:
        if want_solution and not _extract_allowed(url):
            p.search_log.log(uid, slug, stage, query_desc, origin, url, "пропущен",
                             "домен только для подтверждения источника (mathus.ru)")
            continue
        ok, reason, http_code, ctype = _download_and_check(p, rec, url)
        p.search_log.log(uid, slug, stage, query_desc, origin, url,
                         "скачан" if ok else "не скачан",
                         f"{reason} [HTTP {http_code or '—'}; {ctype or '—'}]")
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
            doc_text = _fetch_doc_text(url)[:PDF_BLOCK_CHUNK_SIZE]
        payload = {"doc_text": doc_text[:PDF_BLOCK_CHUNK_SIZE], "olymp": rec.get("olymp"),
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
        if not doc_solution:
            # Документ содержит только условие (или ответ без решения):
            # фиксируем source/answer, если были пустыми, и ПРОДОЛЖАЕМ искать
            # решение в следующих кандидатах PDF!
            if not (rec.get("source") or "").strip():
                p.apply_field(slug, rec, stage, "source", url,
                              model="index" if origin == "index" else "gemini+deepseek")
            if doc_answer and not (rec.get("answer") or "").strip():
                p.apply_field(slug, rec, stage, "answer", doc_answer,
                              model="deepseek-chat+reasoner")
            source_only_url = source_only_url or url
            p.search_log.log(uid, slug, stage, query_desc, origin, url, "скачан",
                             "условие подтверждено, но решения в этом PDF нет — проверяем следующие кандидаты")
            continue
        p.apply_field(slug, rec, stage, "solution", doc_solution,
                      model="deepseek-chat+reasoner")
        if doc_answer:
            p.apply_field(slug, rec, stage, "answer", doc_answer,
                          model="deepseek-chat+reasoner")
        p.apply_field(slug, rec, stage, "source", url,
                      model="index" if origin == "index" else "gemini+deepseek")
        p.apply_field(slug, rec, stage, "status", "official_found",
                      model="index" if origin == "index" else "gemini+deepseek")
        p.add_qa_note(rec, stage, f"официальное решение найдено: {reason}")
        p.search_log.log(uid, slug, stage, query_desc, origin, url, "скачан",
                         f"принято: {reason}")
        p.remove_from_search_queue(uid)
        return True, url
    if source_only_url:
        p.add_qa_note(rec, stage,
                      "source найден, но решение в документе отсутствует — "
                      "статус не менялся", model="deepseek-chat+reasoner")
        return True, source_only_url
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

def _find_task_pages(pages: list[str], text_head: str) -> list[int]:
    """Ищет страницы, содержащие начало условия задачи (нормализованное или по кириллице)."""
    head = R.norm_for_compare(text_head)
    cyr = _cyr_only(text_head)
    if not head and not cyr:
        return []
    probe = head[:60] if head else ""
    cyr_probe = cyr[:40] if len(cyr) >= 15 else ""
    out = []
    for i, pg in enumerate(pages):
        if (probe and probe in R.norm_for_compare(pg)) or (cyr_probe and cyr_probe in _cyr_only(pg)):
            out.append(i)
    return out


def _fetch_doc_text(url: str) -> str:
    """Весь текст документа (для совместимости; внутри — постраничный кэш)."""
    return "\n".join(_fetch_doc_pages(url))


# =====================================================================
# ЭТАП 21: заполнение дыр в нумерации
# =====================================================================

def _make_uid(olymp, year, round_name, grade, num, text, variant=None) -> str:
    """uid = sha256(olymp|year|round|grade|variant|num|normalized text)."""
    normalized = R.norm_for_compare(text)[:500]
    key = f"{olymp}|{year}|{round_name}|{grade}|{variant or ''}|{num}|{normalized}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# Заголовок блока в PDF: «Вариант N», «Билет N», «в. N»
# (строже, чем в индексе: «вариантов 11-01» не распознаётся как вариант 11)
BLOCK_HEADER_RE = re.compile(
    r"(?:вариант|билет)\s*№?\s*(\d+)(?![\d\-])|(?:^|[\s(])в\.\s*(\d+)(?![\d\-])",
    re.I)
BLOCK_GRADE_RE = re.compile(r"(\d{1,2})\s*класс", re.I)
BLOCK_DAY_RE = re.compile(r"день[^\d]{0,5}(\d+)", re.I)


def _parse_block_header(page: str) -> dict:
    """Заголовок блока на странице PDF: вариант/класс/день."""
    hdr = {"variant": None, "grade": None, "day": None}
    m = BLOCK_HEADER_RE.search(page)
    if m:
        v = m.group(1) or m.group(2)
        hdr["variant"] = str(int(v))
    g = BLOCK_GRADE_RE.search(page)
    if g:
        try:
            hdr["grade"] = str(int(g.group(1)))
        except ValueError:
            pass
    d = BLOCK_DAY_RE.search(page)
    if d:
        try:
            hdr["day"] = int(d.group(1))
        except ValueError:
            pass
    return hdr


def _page_headers(page: str):
    """Все заголовки блоков НА СТРАНИЦЕ с позициями (одна страница может
    начинаться серединой блока и содержать несколько заголовков).

    Метаданные (вариант/класс/день) привязаны к СВОЕЙ строке заголовка —
    соседний заголовок не может перезаписать класс варианта.
    """
    out = []
    # позиции начал строк — границы заголовков
    line_starts = [m.start() for m in re.finditer(r"(?m)^", page)]
    for m in BLOCK_HEADER_RE.finditer(page):
        v = m.group(1) or m.group(2)
        # строка, в которой найден заголовок варианта
        ls = max([s for s in line_starts if s <= m.start()] or [0])
        le = next((s for s in line_starts if s > m.start()), len(page))
        line = page[ls:le]
        h = {"pos": ls, "variant": str(int(v)), "grade": None, "day": None}
        gm = BLOCK_GRADE_RE.search(line)
        if gm:
            try:
                h["grade"] = str(int(gm.group(1)))
            except ValueError:
                pass
        dm = BLOCK_DAY_RE.search(line)
        if dm:
            try:
                h["day"] = int(dm.group(1))
            except ValueError:
                pass
        out.append(h)
    # класс без варианта — самостоятельный заголовок (своей строкой)
    for m in BLOCK_GRADE_RE.finditer(page):
        try:
            g = str(int(m.group(1)))
        except ValueError:
            continue
        ls = max([s for s in line_starts if s <= m.start()] or [0])
        # класс уже учтён в заголовке варианта этой строки?
        if any(h["pos"] == ls and h["grade"] for h in out):
            continue
        if any(h["pos"] == ls for h in out):
            for h in out:
                if h["pos"] == ls and not h["grade"]:
                    h["grade"] = g
            continue
        out.append({"pos": ls, "variant": None, "grade": g, "day": None})
    return sorted(out, key=lambda h: h["pos"])


def _find_blocks(pages: list[str]) -> list[dict]:
    """Блоки документа: диапазоны страниц между заголовками.

    Заголовок — «Вариант N»/«Билет N» или «N класс»; на одной странице
    может быть НЕСКОЛЬКО заголовков — страница режется по позициям.
    Возвращает [{start, end, variant, grade, day, text}], end — исключительно.
    """
    # (page_idx, pos_in_page, header) для всех заголовков
    marks = []
    for i, pg in enumerate(pages):
        for h in _page_headers(pg):
            marks.append((i, h["pos"], h))
    if not marks:
        return []
    # «11 класс» на строку выше «Вариант 1» — не отдельный блок:
    # класс-заголовок ПЕРЕДАЁТСЯ следующему заголовку варианта
    drop = set()
    for i, m in enumerate(marks):
        if m[2]["variant"] is None and m[2]["grade"] is not None \
           and i + 1 < len(marks):
            n = marks[i + 1]
            if n[0] == m[0] and n[2]["variant"] is not None \
               and 0 <= n[1] - m[1] < 150:
                if not n[2].get("grade"):
                    n[2]["grade"] = m[2]["grade"]
                drop.add(i)
    marks = [m for i, m in enumerate(marks) if i not in drop]
    blocks = []
    cur_grade = None   # класс наследуется до следующего явного изменения
    for k, (pi, pos, h) in enumerate(marks):
        if h["grade"]:
            cur_grade = h["grade"]
        elif cur_grade:
            h = dict(h, grade=cur_grade)   # вариант без класса — наследует
        if k + 1 < len(marks):
            np, npos = marks[k + 1][0], marks[k + 1][1]
            if np == pi:
                text = pages[pi][pos:npos]
                end = np + 1
            else:
                text = pages[pi][pos:] + "\n" + "\n".join(pages[pi + 1:np])
                if npos:
                    text += "\n" + pages[np][:npos]
                    end = np + 1
                else:
                    end = np
        else:
            text = pages[pi][pos:] + "\n" + "\n".join(pages[pi + 1:])
            end = len(pages)
        blocks.append({"start": pi, "end": end, "variant": h["variant"],
                       "grade": h["grade"], "day": h["day"], "text": text})
    return blocks


def _select_blocks(blocks: list[dict], grade, variant) -> list[dict]:
    """Блоки, соответствующие классу И варианту (None — не задан).

    Страница блока ДРУГОГО варианта не подходит, даже если на ней
    упомянут нужный класс.
    """
    def norm(v):
        try:
            return str(int(v)) if v not in (None, "") else ""
        except (ValueError, TypeError):
            return str(v or "")

    grade_str, var_str = norm(grade), norm(variant)
    sel = []
    for b in blocks:
        if var_str:
            if b["variant"] != var_str:
                continue          # чужой вариант
            if grade_str and b["grade"] and b["grade"] != grade_str:
                continue
        elif grade_str:
            # группа БЕЗ варианта: берём блоки ЛЮБОГО варианта этого класса —
            # вариант извлечённой задаче даст заголовок блока (block_var);
            # атрибуция существующих записей — только после сверки и гейта
            if b["grade"] and b["grade"] != grade_str:
                continue
        sel.append(b)
    return sel


def _grade_ok(block: dict, cmeta: dict | None, grade) -> bool:
    """Класс подтверждён заголовком блока ИЛИ метаданными кандидата.

    Неподтверждённый класс не импортируется под классом запроса —
    иначе воспроизводится исходная проблема неверной атрибуции.
    """
    if grade in (None, ""):
        return True
    bg = block.get("grade")
    if bg is not None:
        # явный класс блока — приоритетен; противоречие не перекрывается
        # метаданными индекса
        return str(bg) == str(grade)
    # класс блока неизвестен — индекс может подтвердить
    cgrades = (cmeta or {}).get("grades")
    if cgrades:
        try:
            if int(grade) in {int(g) for g in cgrades if str(g).lstrip("-").isdigit()}:
                return True
        except (ValueError, TypeError):
            pass
    return False


def _block_task_nums(block_text: str) -> set[int]:
    """Номера задач, упомянутые в блоке: «12.», «3)» и «Задача 5» в
    начале строк (живые PDF используют оба формата)."""
    nums = set()
    for m in re.finditer(r"(?m)^\s*(\d{1,2})[\.\)]", block_text):
        nums.add(int(m.group(1)))
    for m in re.finditer(r"(?m)^\s*Задача\s+(\d{1,2})\b", block_text, re.I):
        nums.add(int(m.group(1)))
    return nums



def _cyr_only(s: str) -> str:
    """Только кириллические буквы в нижнем регистре — сверка «текст есть в документе»
    независимо от разметки формул (LaTeX в извлечении vs Unicode в PDF)."""
    return re.sub(r"[^а-яё]", "", (s or "").lower())


def _text_in_doc(text: str, doc_norm: str, doc_cyr: str) -> bool:
    """Извлечённое условие действительно содержится в документе."""
    cyr = _cyr_only(text)
    if len(cyr) >= 15:
        probe = cyr[:40]
        if probe in doc_cyr:
            return True
        if len(cyr) >= 60 and cyr[20:60] in doc_cyr:
            return True
        return False
    head = R.norm_for_compare(text[:120])
    return (not head) or (head[:60] in doc_norm)


CONFIRM_ONLY_HOSTS = ("mathus.ru",)


def _extract_allowed(url: str) -> bool:
    """С этих доменов решения/ответы НЕ извлекаем (текст PDF даёт зеркальные цифры:
    91<->19, 0295<->5920); они годятся только как подтверждение источника."""
    u = (url or "").lower()
    return not any(h in u for h in CONFIRM_ONLY_HOSTS)


def _year_ok(cmeta: dict | None, pages: list[str], year) -> bool:
    """Год кандидата подтверждён: документом ИЛИ метаданными индекса.

    Порядок силы:
    1. ЯВНАЯ датировка документа (строки «Заключительный этап 2024 года»,
       «Олимпиада 2025») — сильнейший сигнал: противоречие = отказ,
       даже если индекс «знает» год. Числа внутри условий задач
       датировкой НЕ считаются.
    2. Сезон «2024/25» («24/25», «2024-2025») — подтверждение года финала.
    3. Метаданные индекса (год == год группы) — подтверждение архивом.
    4. Молчание документа и неизвестный год индекса — НЕ подтверждение.
    """
    if year in (None, ""):
        return True
    y = int(year)
    try:
        from olymp_source_index import season_year_from_url as _syu
    except Exception:
        _syu = None
    if _syu and cmeta and cmeta.get("url"):
        sy = _syu(cmeta["url"])
        if sy is not None:
            return sy == y
    doc_text = "\n".join(pages)
    # 1. Явная датировка в заголовочных строках. Заголовок: короткая строка,
    # год в первых 60 символах (числа внутри условий задач не считаются).
    # Сезон «2024/25» нормализуется к году ФИНАЛА (2025).
    dated = set()
    for line in doc_text.splitlines()[:200]:
        stripped = line.strip()
        if len(stripped) > 150:
            continue   # длинная строка — похоже на условие задачи
        # строка условия задачи («Задача 1.», «12.», «3)») — не заголовок:
        # числа внутри условий годом проведения не считаются
        if re.match(r"(?:Задача|Задание|Решение|Ответ)\b|\d{1,2}\s*[\.\)]",
                    stripped, re.I):
            continue
        if not re.search(r"этап|олимпиад|тур|сезон|год|класс|©|\(c\)|copyright|мфти", stripped, re.I):
            continue
        m = re.search(r"(19|20)\d{2}", stripped[:60])
        if not m:
            continue
        # сезонная форма в начале строки -> год финала
        sm = re.match(r"\s*(?:[А-Яа-яЁё\s]*?)?(19|20)(\d{2})\s*[-/]\s*(\d{2,4})",
                      stripped)
        if sm:
            y1 = int(sm.group(1) + sm.group(2))
            y2s = sm.group(3)
            y2 = int(y2s) if len(y2s) == 4 else 2000 + int(y2s)
            if y2 == y1 + 1:
                dated.add(y2)
                continue
        dated.add(int(m.group(0)))
    if dated:
        if y in dated:
            return True
        # в датированных строках только другие годы — противоречие
        if not dated & {y}:
            return False
    # 2. Сезон подтверждает только ДАТИРОВКА заголовков (выше) или
    # метаданные архива — НЕ произвольное «24/25» в тексте (дробь
    # в условии задачи годом не считается)
    # 3. Метаданные индекса
    if cmeta and cmeta.get("year") is not None:
        return int(cmeta["year"]) == int(year)
    # 4. Не подтверждено
    return False


def _year_confirmed(doc_text: str, year) -> bool:
    """Год подтверждён документом: искомой год (или сезон «YYYY/YY») в тексте.

    Если документ вообще не упоминает четырёхзначные годы — подтвердить
    нельзя, но и противоречия нет (True). Явное упоминание ДРУГИХ годов
    без искомого — противоречие (False).
    """
    if year in (None, ""):
        return True
    years = {int(m.group(0)) for m in re.finditer(r"(19|20)\d{2}", doc_text)}
    if not years:
        return True
    y = int(year)
    season_tail = f"{(y - 1) % 100:02d}/{y % 100:02d}"   # «24/25»
    if y in years:
        return True
    if season_tail in doc_text or f"{y - 1}/{y}" in doc_text:
        return True
    return False


def _text_similarity(a: str, b: str) -> float:
    """Схожесть двух текстов (0..1) по нормализованным строкам."""
    if not a or not b:
        return 0.0
    na, nb = R.norm_for_compare(a), R.norm_for_compare(b)
    if not na or not nb:
        return 0.0
    if HAS_RAPIDFUZZ:
        return fuzz.ratio(na, nb) / 100.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _raw_similarity(a: str, b: str) -> float:
    """Схожесть БЕЗ удаления математической структуры.

    Для подтверждения атрибуции: склеиваем только пробелы/переносы,
    LaTeX-структура (скобки, backslash) и знаки сохраняются —
    \frac{1}{23} и \frac{12}{3} НЕ считаются одинаковыми.
    """
    if not a or not b:
        return 0.0
    na = re.sub(r"\s+", " ", a.strip())
    nb = re.sub(r"\s+", " ", b.strip())
    if HAS_RAPIDFUZZ:
        return fuzz.ratio(na, nb) / 100.0
    import difflib
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _answer_norm_strict(ans: str) -> str:
    """Нормализация ответа с СОХРАНЕНИЕМ математической структуры.

    Удаляются только пробелы и регистр; Unicode-минус (−), дефисы
    унифицируются в «-». Скобки LaTeX и все знаки сохраняются:
    «1» и «−1» — разные ответы; \frac{1}{23} ≠ \frac{12}{3}.
    Различие трактуется как конфликт (безопасная сторона), а не равенство.
    """
    # регистр СОХРАНЯЕТСЯ: \Gamma и \gamma, \Delta и \delta — разные
    # символы; различие трактуется как конфликт (безопасная сторона)
    t = (ans or "").strip()
    t = t.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    t = re.sub(r"[\s\u00a0]+", "", t)
    return t


def _text_contained(short: str, long: str) -> float:
    """Вложенность короткого текста в длинный (0..1) — для атрибуции
    задачи к блоку PDF: текст задачи содержится в многостраничном блоке."""
    if not short or not long:
        return 0.0
    na, nb = R.norm_for_compare(short), R.norm_for_compare(long)
    if not na or not nb:
        return 0.0
    if HAS_RAPIDFUZZ:
        return fuzz.partial_ratio(na, nb) / 100.0
    if na in nb:
        return 1.0
    sm = difflib.SequenceMatcher(None, na, nb)
    matched = sum(bl.size for bl in sm.get_matching_blocks())
    return matched / len(na)


def stage_21(p: Pipeline):
    """Этап 21: заполнение пропущенных номеров в вариантах (индекс -> Gemini).

    Порядок работы:
    1. Атрибуция: записям без `variant` вариант проставляется по вложенности
       текста в блок PDF (схожесть ≥ 0.9; класс блока должен совпадать).
       Неоднозначное совпадение (несколько разных блоков) — needs_review.
    2. Дыры считаются по (year, round, grade, variant) ПОСЛЕ атрибуции.
    3. Вариант импортируется целиком: все задачи блока с условием, ответом,
       решением, баллами (в qa.notes). У каждой задачи сохраняется источник
       (URL PDF, откуда извлечено поле). Решение обязано пройти сверку
       deepseek-reasoner с извлечённым ИЛИ существующим ответом (явный
       вердикт match); без ответа для сверки — needs_review, решение
       не перезаписывается. Конфликт ответов — needs_review.
    4. Дубль по тексту (схожесть ≥ 0.9, задачи ТОЙ ЖЕ олимпиады того же
       года/класса) не добавляется, а обогащает существующую запись:
       variant, source, официальное решение (при gemini_solved/AI_* ->
       official_found, только после сверки).
    5. --limit — число обрабатываемых вариантов (и групп атрибуции);
       необработанный остаток показывается в отчёте и сохраняется в
       чекпоинте (stage21_tried) — при повторном запуске нерешённые
       группы не занимают лимит повторно.
    6. Отчёт по каждой олимпиаде: PDF (уникальные URL), импортировано
       вариантов (полностью/частично), задач добавлено, обогащено
       (уникальные записи), дублей пропущено, остаток дыр с причинами —
       пересчитывается по итоговому каталогу.
    """
    if p.dry_run:
        log.info("Этап 21: dry-run — новые задачи не добавляются.")
        return
    if p.deepseek_chat is None or p.deepseek_reasoner is None:
        raise LLMError("Этап 21: нет доступа к DeepSeek (извлечение и сверка задач)")

    report = p.stage21_report

    def _st(slug: str) -> dict:
        st = report.get(slug)
        if st is None:
            st = report[slug] = {"pdfs": 0, "variants": 0, "variants_partial": 0,
                                 "needs_review": 0,
                                 "tasks_added": 0, "enriched": 0, "dup_skipped": 0,
                                 "gaps": [], "unprocessed": 0}
        # служебные множества для честных счётчиков
        st.setdefault("_pdf_urls", set())
        st.setdefault("_enriched_uids", set())
        return st

    for slug in p.catalog.slugs():
        _st(slug)

    # Бюджеты --limit: импорт — число вариантов (по ТЗ), атрибуция —
    # своя квота (группы с уже проставленным вариантом пропускаются
    # мгновенно, повторные прогоны дёшевы)
    import_budget = p.args.limit if p.args.limit else None
    attr_budget = p.args.limit if p.args.limit else None
    # Попытки прошлых запусков: сохраняем номер прогона для каждой группы.
    # Сортировка — по номеру прогона (давности попытки): между запусками
    # группы чередуются, ни одна не «голодает» при --limit 1.
    tried = p.checkpoint.data.setdefault("stage21_tried", {})  # key -> run №
    run_no = p.checkpoint.data.get("stage21_runs", 0) + 1
    p.checkpoint.data["stage21_runs"] = run_no

    def _mark_tried(key):
        k = json.dumps(list(key), ensure_ascii=False)
        tried[k] = run_no

    def _tried_run(key):
        return tried.get(json.dumps(list(key), ensure_ascii=False), 0)

    def _group_variants() -> dict[tuple, list[dict]]:
        variants: dict[tuple, list[dict]] = {}
        for slug in p.catalog.slugs():
            for rec in p.catalog.data[slug]:
                key = (slug, rec.get("year"), rec.get("round"), str(rec.get("grade")),
                       str(rec.get("variant") or "").strip() or None)
                variants.setdefault(key, []).append(rec)
        return variants

    def _candidates_for(slug, year, round_name, grade, variant, missing, context):
        """Кандидаты PDF: СНАЧАЛА индекс, потом Gemini.

        Возвращает (origin, url, meta): meta — метаданные индекса (год/
        класс/этап), чтобы атрибуция года подтверждалась архивом, а не
        молчанием документа.
        """
        candidates: list[tuple[str, str, dict]] = []
        query_desc = f"{slug} {year} {round_name} {grade} кл." \
                     + (f" вар. {variant}" if variant else "")
        try:
            idx = p.get_source_index()
            round_key = R.canon_round_key(round_name or "", slug)
            found = idx.find(slug, year, round_key, grade,
                             kinds=("tasks", "sol"), variant=variant)
            candidates = [("index", r["url"], dict(r)) for r in found[:5]]
            p.search_log.log("", slug, 21, query_desc, "index", "", "",
                             f"найдено {len(found)} кандидатов")
        except Exception as e:
            log.warning("Этап 21: индекс недоступен: %s", str(e)[:150])
        if not candidates and p.gemini is not None:
            payload = {"olymp": context.get("olymp"), "year": year,
                       "round": round_name, "grade": grade, "variant": variant,
                       "missing_nums": [str(n) for n in missing]}
            s_resp = p.gemini.search_variant_pdf(json.dumps(payload, ensure_ascii=False))
            if s_resp and s_resp.get("ok"):
                for cand in s_resp.get("candidates", [])[:5]:
                    url = cand.get("url", "")
                    if R.is_official_url(url):
                        candidates.append(("gemini", url, {}))
            p.search_log.log("", slug, 21, query_desc, "gemini", "", "",
                             f"получено {len(candidates)} кандидатов")
        return candidates

    def _verify_solution(text: str, solution: str, answer: str):
        """Сверка reasoner: решение приводит к ответу. Явный вердикт match.

        Возвращает (ok, reason). Неопределённость = отказ.
        """
        chk = p.deepseek_reasoner.chat_json(
            P.STAGE11_ANSWER_CHECK,
            json.dumps({"text": text, "answer": answer,
                        "solution": solution}, ensure_ascii=False))
        if not chk:
            return False, "reasoner не ответил"
        if chk.get("verdict") != "match":
            return False, f"вердикт {chk.get('verdict')}"
        return True, "match"

    def _missing_nums(recs: list[dict]):
        nums, max_num = set(), 0
        for r in recs:
            try:
                n = int(str(r.get("num", "0")).strip() or 0)
            except ValueError:
                continue
            nums.add(n)
            max_num = max(max_num, n)
        missing = [n for n in range(1, max_num + 1) if n not in nums] if max_num else []
        return nums, max_num, missing

    def _confirm_attribution(slug: str, r: dict, prop: dict, query_desc: str,
                             extract_cache: dict):
        """Подтверждение предложения атрибуции перед применением variant.

        Предложение (нечёткое совпадение текста с блоком PDF) — НЕ атрибуция:
        нормализация «склеивает» разные дроби (\frac{1}{23} и \frac{12}{3})
        и теряет Unicode-минус. Подтверждение: извлекаем полное условие
        соответствующей задачи блока, сверяем эквивалентность гейтом
        reasoner (_math_gate) и ответы (структурно, знаки сохраняются).
        Без подтверждения — только needs_review, поля записи не меняются.
        Извлечение блока кэшируется (один блок — один вызов deepseek-chat).
        """
        nonlocal attributed
        rec_text = (r.get("text") or "").strip()
        if not rec_text:
            return
        st = _st(slug)
        for (var, day), (block_text, url) in prop.items():
            ckey = (url, var, day)
            if ckey not in extract_cache:
                tasks: list[dict] = []
                try:
                    # Длинные блоки режем по PDF_BLOCK_CHUNK_SIZE (12 000 симв.) с перекрытием,
                    # чтобы ответ не обрезался на MAX_TOKENS
                    if len(block_text) <= PDF_BLOCK_CHUNK_SIZE:
                        b_chunks = [block_text]
                    else:
                        b_chunks, ci = [], 0
                        while ci < len(block_text):
                            b_chunks.append(block_text[ci: ci + PDF_BLOCK_CHUNK_SIZE])
                            ci += PDF_BLOCK_CHUNK_SIZE - PDF_BLOCK_CHUNK_OVERLAP
                    for b_chunk in b_chunks:
                        resp = p.deepseek_chat.chat_json(
                            P.STAGE21_EXTRACT_VARIANT_BLOCK,
                            json.dumps({"doc_text": b_chunk}, ensure_ascii=False))
                        tasks.extend((resp or {}).get("tasks") or [])
                except Exception as e:
                    log.warning("Этап 21 (атрибуция): извлечение блока не удалось: %s",
                                str(e)[:150])
                extract_cache[ckey] = tasks
            tasks = extract_cache[ckey]
            # лучший кандидат — по схожести БЕЗ удаления математики
            best, best_sim = None, 0.0
            for t in tasks:
                sim = _raw_similarity(rec_text, (t.get("text") or ""))
                if sim > best_sim:
                    best, best_sim = t, sim
            # порог финальной атрибуции — 0.9 (требование: существующим задачам
            # вариант ставится только по совпадению текста ≥ 0.9; 0.6 — лишь
            # нижняя граница для поиска кандидата, атрибуцию не даёт)
            if best is None or best_sim < 0.9:
                p.needs_review(r, 21,
                               "условие не найдено среди задач блока PDF — "
                               "вариант не проставлен")
                st["needs_review"] += 1
                return
            # конфликт ответов — структурное сравнение, знаки сохраняются
            t_ans = (best.get("answer") or "").strip()
            r_ans = (r.get("answer") or "").strip()
            if t_ans and r_ans and \
                    _answer_norm_strict(t_ans) != _answer_norm_strict(r_ans):
                p.needs_review(r, 21,
                               f"конфликт ответов: в PDF «{t_ans[:60]}», "
                               f"в базе «{r_ans[:60]}» — вариант не проставлен")
                st["needs_review"] += 1
                return
            # гейт эквивалентности условий (reasoner); идентичный текст
            # эквивалентен без вызова
            best_text = (best.get("text") or "").strip()
            if rec_text != best_text and \
                    not _math_gate(p, rec_text, best_text, r, 21):
                st["needs_review"] += 1
                return   # needs_review уже проставлен гейтом
            if p.apply_field(slug, r, 21, "variant", var, model="index"):
                attributed += 1
                st["_enriched_uids"].add(r.get("uid"))
            if day and not r.get("day"):
                p.apply_field(slug, r, 21, "day", day, model="index")
            p.add_qa_note(r, 21,
                          f"вариант {var} подтверждён по блоку PDF ({url})",
                          model="index")
            return (var, block_text)

    # =================================================================
    # ФАЗА А: атрибуция — проставить variant записям без него
    # =================================================================
    variants = _group_variants()
    attributed = 0
    # группы с ХВОСТОМ официального блока за пределами каталога
    # (найден и подтверждён блок с номерами, которых нет в каталоге) —
    # фаза Б обязана обработать их даже без внутренних пропусков;
    # key -> множество (вариант, номер) хвостовых задач
    tail_pending: dict = {}

    def _jkey(k) -> str:
        return json.dumps(list(k), ensure_ascii=False)
    varless_keys = [k for k in variants if k[4] is None]
    for key in varless_keys:
        if attr_budget is not None and attr_budget <= 0:
            for k2 in varless_keys[varless_keys.index(key):]:
                slug2 = k2[0]
                _st(slug2)["unprocessed"] += 1
                _st(slug2)["gaps"].append({
                    "year": k2[1], "round": k2[2], "grade": k2[3],
                    "variant": None,
                    "reason": "атрибуция не выполнена: --limit"})
            break
        slug, year, round_name, grade, _ = key
        recs = [r for r in variants[key] if not (r.get("variant") or "").strip()]
        if not recs:
            continue
        st = _st(slug)
        log.info("Этап 21 (атрибуция): %s %s %s %s класс: %d записей без варианта.",
                 slug, year, round_name, grade, len(recs))
        query_desc = f"{slug} {year} {round_name} {grade} кл. (атрибуция)"
        candidates = _candidates_for(slug, year, round_name, grade, None, [], recs[0])
        if not candidates:
            continue
        processed_any = False
        # Совпадения собираем ПО ВСЕМ кандидатам: совпадение одного и того же
        # текста с разными вариантами в разных документах = неоднозначность
        # uid -> {(variant, day): (текст блока, url)} — предложения
        rec_matches: dict[str, dict] = {}
        for origin, url, cmeta in candidates:
            if not _extract_allowed(url):
                continue
            res = _fetch_doc_result(url)
            # Год подтверждается метаданными индекса ИЛИ документом;
            # молчание документа при неизвестном годе индекса = нет
            # подтверждения — атрибуцию не подставляем
            if res["ok"] and not _year_ok(cmeta, res["pages"], year):
                p.search_log.log("", slug, 21, query_desc, origin, url,
                                 "не скачан", "год не подтверждён (индекс/документ)")
                continue
            p.search_log.log("", slug, 21, query_desc, origin, url,
                             "скачан" if res["ok"] else "не скачан",
                             f"{res['error']} [HTTP {res['http_code'] or '—'}; "
                             f"{res['content_type'] or '—'}]")
            if not res["ok"]:
                continue
            processed_any = True
            st["_pdf_urls"].add(url)
            _DOC_PAGES_CACHE[url] = res["pages"]
            all_blocks = _find_blocks(res["pages"])
            for b in all_blocks:
                if not b["variant"]:
                    continue
                if not _grade_ok(b, cmeta, grade):
                    continue   # класс не подтверждён — не атрибутируем
                for r in recs:
                    # ПОЛНЫЙ текст записи (не первые 300 символов) — различия
                    # в хвосте условия тоже должны учитываться
                    rt = (r.get("text") or "").strip()
                    if not rt:
                        continue
                    # совпадение — ПРЕДЛОЖЕНИЕ атрибуции, а не атрибуция:
                    # подтверждение (извлечение + гейт reasoner) — в
                    # _confirm_attribution / фазе Б
                    if _text_contained(rt, b["text"]) >= 0.9:
                        rec_matches.setdefault(r.get("uid"), {})[
                            (b["variant"], b.get("day"))] = (b["text"], url)
        # Назначение: ПРЕДЛОЖЕНИЯ, а не атрибуция. Нечёткое совпадение
        # текста — только кандидат: нормализация «склеивает» разные дроби и
        # теряет Unicode-минус. Применение variant — после подтверждения
        # (извлечение задачи блока + гейт reasoner).
        proposals: dict[str, dict] = {}
        for r in recs:
            if (r.get("variant") or "").strip():
                continue
            uid = r.get("uid")
            matches = rec_matches.get(uid) or {}
            variants_found = {v for v, _d in matches}
            if len(variants_found) == 1:
                proposals[uid] = dict(matches)
            elif len(variants_found) > 1:
                # неоднозначно — не угадываем
                p.needs_review(r, 21,
                               f"задача совпала с блоками вариантов "
                               f"{sorted(variants_found)} — вариант не проставлен")
                st["needs_review"] += 1
        # Подтверждение предложений — ВСЕГДА (и для групп без дыр: фаза Б
        # для них не запустится, атрибуция была бы потеряна): извлечение
        # задачи блока + гейт reasoner. Кэш извлечения — на группу.
        extract_cache: dict = {}
        for uid, prop in proposals.items():
            r = next((x for x in recs if x.get("uid") == uid), None)
            if r is None:
                continue
            confirmed = _confirm_attribution(slug, r, prop, query_desc,
                                             extract_cache)
            if not confirmed:
                continue
            var, block_text = confirmed
            # ХВОСТ официального блока за пределами каталога: найденный и
            # подтверждённый блок обрабатывается ЦЕЛИКОМ (импорт варианта
            # целиком), даже если внутренних пропусков в каталоге нет —
            # группа (…, вариант) отправляется в фазу Б
            bnums = _block_task_nums(block_text)
            cat_nums = set()
            for r2 in variants[key]:
                try:
                    cat_nums.add(int(str(r2.get("num", "0")).strip() or 0))
                except ValueError:
                    pass
            extra = bnums - cat_nums
            if extra:
                key_t = (slug, year, round_name, grade, str(var))
                tail_pending.setdefault(key_t, set()).update(
                    (str(var), n) for n in extra)
        if processed_any:
            attr_budget = attr_budget - 1 if attr_budget is not None else None

    # =================================================================
    # ФАЗА Б: дыры по (year, round, grade, variant) и импорт варианта
    # =================================================================
    def priority(key):
        slug, year, round_name, grade, variant = key
        rk = R.canon_round_key(round_name or "", slug)
        round_p = {"final": 0, "qual": 1, "regional": 2}.get(rk, 3)
        grade_p = {"9": 0, "10": 0, "11": 0}.get(grade, 1)
        # давно пробовавшиеся группы — в конец, но чередуются (ротация)
        tried_p = _tried_run(key)
        return (1 if tried_p else 0, tried_p, round_p, grade_p, -(year or 0))

    variants = _group_variants()   # ПЕРЕГРУППИРОВКА после атрибуции
    # Незакрытые хвосты прошлых запусков — в checkpoint: очередь
    # продолжается между запусками независимо от variant и внутренних
    # пропусков (иначе отклонённая задача хвоста недоступна для повтора).
    # Ключ pending — ВАРИАНТ (slug, year, round, grade, variant), а не группа:
    # после атрибуции безвариантная группа расформировывается, а хвост
    # конкретного варианта обязан выжить
    pending_cp = p.checkpoint.data.setdefault("stage21_pending", {})
    pending_virtual = set()
    for jk in list(pending_cp):
        try:
            k = tuple(json.loads(jk))
        except Exception:
            continue
        if len(k) == 5 and k not in variants:
            pending_virtual.add(k)   # вариант без записей в каталоге
    # группы к обработке: внутренние пропуски, хвост этого запуска ИЛИ
    # незакрытый хвост из checkpoint (включая виртуальные группы)
    def _orig_of(recs: list[dict]) -> list[dict]:
        # записи каталога, НЕ импортированные этапом 21: только они задают
        # базовые диапазонные ожидания (импорт определяет нумерацию блока PDF)
        return [r for r in recs
                if not (r.get("qa") or {}).get("stage21", {}).get("imported")]

    def _base_missing(key, recs: list[dict]) -> list[int]:
        """Базовый остаток группы: диапазонные ожидания ИСХОДНЫХ записей
        минус номера всех принятых записей той же области. Импортированная
        №2 не создаёт ожиданий, но и ЗАКРЫВАЕТ дыру №2. Область покрытия
        совпадает с финальным расчётом: вариантная группа — записи того же
        варианта, безвариантная — все записи года/класса/этапа."""
        miss = _missing_nums(_orig_of(recs))[2]
        if not miss:
            return []
        slug, year, round_name, grade, variant = key
        covered = set()
        for r2 in p.catalog.data.get(slug, []):
            if r2.get("year") != year \
               or (r2.get("round") or "") != (round_name or "") \
               or str(r2.get("grade")) != str(grade):
                continue
            if variant and str(r2.get("variant") or "") != str(variant):
                continue
            try:
                n2 = int(str(r2.get("num", "0")).strip() or 0)
            except ValueError:
                continue
            if n2:
                covered.add(n2)
        return [n for n in miss if n not in covered]

    gap_keys = [k for k in list(variants) + list(pending_virtual)
               if (k in variants and _base_missing(k, variants[k]))
               or k in tail_pending or _jkey(k) in pending_cp]
    ordered_keys = sorted(gap_keys, key=priority)
    unprocessed = 0
    if import_budget is not None:
        # отбрасываем обработанные в рамках бюджета
        remaining = []
        for key in ordered_keys:
            if import_budget > 0:
                remaining.append(key)
                import_budget -= 1
            else:
                unprocessed += 1
        ordered_keys = remaining
        if unprocessed:
            log.info("Этап 21: --limit: не обработано %d вариантов с дырами "
                     "(нерешённые ранее идут в конце).", unprocessed)

    added = 0
    processed_keys = set()
    for key in ordered_keys:
        slug, year, round_name, grade, variant = key
        processed_keys.add(key)
        # Хвост этой группы (обнаружен в фазе А) — в checkpoint ДО обработки:
        # даже если кандидатов/извлечённых задач не будет, очередь сохранится
        if key in tail_pending:
            jk0 = _jkey(key)
            prev0 = {tuple(pr) for pr in pending_cp.get(jk0, [])}
            pending_cp[jk0] = [list(pr)
                               for pr in sorted(prev0 | tail_pending[key])]
        recs = variants.get(key) or []
        nums, max_num, _ = _missing_nums(recs)
        # дыры: ожидания исходных записей МИНУС закрытые (в т.ч. импортом)
        missing = _base_missing(key, recs)
        st = _st(slug)
        var_desc = f" вар. {variant}" if variant else ""
        log.info("Этап 21: %s %s %s %s класс%s: пропущены %s (макс %d).",
                 slug, year, round_name, grade, var_desc, missing, max_num)
        _mark_tried(key)   # при следующем запуске эта группа не займёт лимит
        if recs:
            context = recs[0]
        else:
            # виртуальная группа (хвост варианта без записей в каталоге)
            ctx_rec = next(iter(p.catalog.data.get(slug) or []), None)
            context = {"olymp": (ctx_rec or {}).get("olymp") or slug,
                       "day": 0}
        budget_charged_vars = set()
        query_desc = f"{slug} {year} {round_name} {grade} кл.{var_desc}"
        candidates = _candidates_for(slug, year, round_name, grade, variant,
                                     missing, context)
        if not candidates:
            st["gaps"].append({"year": year, "round": round_name, "grade": grade,
                               "variant": variant,
                               "reason": "нет PDF (кандидатов нет)"})
            continue
        # Собираем задачи блока ПО ВСЕМ кандидатам: условия могут быть в одном
        # PDF, решения — в другом (sol). У каждой задачи — источник (URL).
        # Ключ — (вариант блока, номер): задачи разных вариантов с одним
        # номером — РАЗНЫЕ задачи, они не должны сталкиваться.
        collected: dict[tuple, dict] = {}   # (block_var, num) -> {**task, _url}
        attempt_reasons: list[str] = []
        # учёт ПО ВАРИАНТАМ БЛОКОВ (номера разных вариантов не смешиваются)
        rejected: dict[tuple, str] = {}   # (вариант блока, num) -> причина
        # вариант блока -> номера задач, упомянутые в блоках
        block_nums_seen: dict[str, set[int]] = {}
        for origin, url, cmeta in candidates:
            if not _extract_allowed(url):
                continue
            res = _fetch_doc_result(url)
            # Год подтверждается метаданными индекса ИЛИ документом
            if res["ok"] and not _year_ok(cmeta, res["pages"], year):
                attempt_reasons.append(f"год не подтверждён: {url[:60]}")
                p.search_log.log("", slug, 21, query_desc, origin, url,
                                 "не скачан", "год не подтверждён (индекс/документ)")
                continue
            p.search_log.log("", slug, 21, query_desc, origin, url,
                             "скачан" if res["ok"] else "не скачан",
                             f"{res['error']} [HTTP {res['http_code'] or '—'}; "
                             f"{res['content_type'] or '—'}]")
            if not res["ok"]:
                attempt_reasons.append(f"не скачан ({res['error']}): {url[:60]}")
                continue
            st["_pdf_urls"].add(url)
            _DOC_PAGES_CACHE[url] = res["pages"]
            doc_text = "\n".join(res["pages"])
            doc_norm = R.norm_for_compare(doc_text)
            doc_cyr = _cyr_only(doc_text)
            all_blocks = _find_blocks(res["pages"])
            blocks = _select_blocks(all_blocks, grade, variant)
            if all_blocks and not blocks:
                # в документе есть блоки, но нужного класса/варианта НЕТ —
                # не подсовываем модели весь документ
                attempt_reasons.append(
                    f"класс/вариант не найдены в документе: {url[:60]}")
                continue
            # Класс и вариант подтверждаются НЕЗАВИСИМО (не elif):
            # подтверждённый вариант не подтверждает класс и наоборот
            if blocks and grade not in (None, ""):
                confirmed = [b for b in blocks if _grade_ok(b, cmeta, grade)]
                if not confirmed:
                    attempt_reasons.append(
                        f"класс не подтверждён (заголовок/индекс): {url[:60]}")
                    continue
                blocks = confirmed
            if not blocks and not all_blocks and variant:
                # беззаголовочный документ + запрошенный ВАРИАНТ:
                # вариант подтверждается заголовком (нет) или индексом
                cv = str((cmeta or {}).get("variant") or "").strip()
                if cv != str(variant):
                    attempt_reasons.append(
                        f"вариант не подтверждён (нет заголовков, индекс молчит): "
                        f"{url[:60]}")
                    continue
            if not blocks and not all_blocks and grade not in (None, ""):
                # беззаголовочный документ: класс подтверждает только индекс
                cgrades = (cmeta or {}).get("grades")
                ok_g = False
                if cgrades:
                    try:
                        ok_g = int(grade) in {
                            int(g) for g in cgrades
                            if str(g).lstrip("-").isdigit()}
                    except (ValueError, TypeError):
                        pass
                if not ok_g:
                    attempt_reasons.append(
                        f"класс не подтверждён (нет заголовков, индекс молчит): "
                        f"{url[:60]}")
                    continue
            # тексты для модели: блок целиком, длинный — кусками по 12к с
            # перекрытием 1.5к (задачу не режем посередине без запаса, не превышаем MAX_TOKENS)
            def _chunks(t: str, size: int = PDF_BLOCK_CHUNK_SIZE, overlap: int = PDF_BLOCK_CHUNK_OVERLAP):
                if len(t) <= size:
                    return [t]
                out, i = [], 0
                while i < len(t):
                    out.append(t[i:i + size])
                    i += size - overlap
                return out

            # Бюджет --limit — число ВАРИАНТОВ (по ТЗ), а не групп:
            # каждый новый вариант внутри безвариантной группы расходует
            # отдельную единицу; исчерпанные — в очередь (pending)
            if import_budget is not None and blocks:
                kept_blocks, deferred_blocks = [], []
                for b in blocks:
                    bv = str(b.get("variant") or "")
                    if bv in budget_charged_vars:
                        kept_blocks.append(b)
                    elif not budget_charged_vars:
                        budget_charged_vars.add(bv)   # первый — оплачен группой
                        kept_blocks.append(b)
                    elif import_budget > 0:
                        import_budget -= 1
                        budget_charged_vars.add(bv)
                        kept_blocks.append(b)
                    else:
                        deferred_blocks.append(b)
                for b in deferred_blocks:
                    bv = str(b.get("variant") or "")
                    jk_d = _jkey((slug, year, round_name, grade, bv))
                    prev_d = {tuple(pr) for pr in pending_cp.get(jk_d, [])}
                    dnums = _block_task_nums(b["text"])
                    pending_cp[jk_d] = [list(pr) for pr in
                                       sorted(prev_d | {(bv, n) for n in dnums})]
                    st["unprocessed"] += 1
                    for n_d in sorted(dnums):
                        st["gaps"].append({
                            "year": year, "round": round_name, "grade": grade,
                            "variant": bv or None, "num": n_d,
                            "reason": "не обработано: --limit (вариант)"})
                blocks = kept_blocks
            if blocks:
                # (кусок текста, вариант блока) — вариант блока становится
                # вариантом извлечённых задач (для групп без варианта)
                block_texts = []
                for b in blocks:
                    for chunk in _chunks(b["text"]):
                        block_texts.append((chunk, b.get("variant")))
                    bv = str(b.get("variant") or "")
                    block_nums_seen.setdefault(bv, set()).update(
                        _block_task_nums(b["text"]))
            else:
                block_texts = [(c, variant) for c in _chunks(doc_text)]
                block_nums_seen.setdefault(str(variant or ""), set()).update(
                    _block_task_nums(doc_text))
            for block_text, block_var in block_texts:
                e_payload = {"doc_text": block_text,
                             "grade": grade, "variant": block_var or variant,
                             "missing_nums": [str(n) for n in missing],
                             "known_text_head": ((recs[0].get("text") or "")
                                                  if recs else "")[:300]}
                try:
                    e_resp = p.deepseek_chat.chat_json(
                        P.STAGE21_EXTRACT_VARIANT_BLOCK,
                        json.dumps(e_payload, ensure_ascii=False))
                except Exception as e:
                    log.warning("Этап 21: извлечение не удалось: %s", str(e)[:150])
                    continue
                if not e_resp or not e_resp.get("ok"):
                    attempt_reasons.append(
                        f"вариант не найден в документе: {url[:60]}")
                    continue
                for task in e_resp.get("tasks", []):
                    num = str(task.get("num", "")).strip()
                    text = (task.get("text") or "").strip()
                    task_sol = (task.get("solution") or "").strip()
                    if not num or (not text and not task_sol):
                        continue
                    # Проверка 1: извлечённый текст реально содержится
                    # в ИСХОДНОМ документе (борьба с галлюцинациями).
                    # Для решений БЕЗ условия (sol-PDF) проверки условия нет —
                    # решение присоединится по номеру блока.
                    if text and not _text_in_doc(text, doc_norm, doc_cyr):
                        log.warning("Этап 21: задача №%s не найдена в документе "
                                    "дословно — пропущена.", num)
                        continue
                    # Объединяем с уже собранными по (вариант, номер);
                    # условие должно совпасть — иначе это другая задача
                    prev = collected.get((block_var, num))
                    if prev:
                        if text and (prev.get("text") or "").strip() \
                           and _text_similarity(prev.get("text") or "", text) < 0.9:
                            log.warning("Этап 21: задача №%s в разных PDF с разными "
                                        "условиями — пропущена.", num)
                            continue
                        if text and not (prev.get("text") or "").strip():
                            prev["text"] = text   # условие из tasks-PDF
                            prev["_url"] = url
                        for fld in ("answer", "solution", "points"):
                            if not (prev.get(fld) or "").strip() \
                               and (task.get(fld) or "").strip():
                                prev[fld] = task.get(fld)
                                prev["_url_" + fld] = url
                    else:
                        t = dict(task)
                        # происхождение КАЖДОГО непустого поля — сразу
                        t["_url"] = url
                        for fld in ("answer", "solution", "points"):
                            if (t.get(fld) or "").strip():
                                t["_url_" + fld] = url
                        collected[(block_var, num)] = t
            # Повтор: номера, упомянутые в блоке, но не извлечённые за один вызов —
            # точечный запрос «вырежи задачи №…» по тому же блоку (до 2 попыток).
            try:
                for block_text, block_var in block_texts:
                    bv_key = str(block_var or "")
                    seen_nums = block_nums_seen.get(bv_key, set())
                    got_nums = {int(k[1]) for k in collected if k[0] == block_var and str(k[1]).isdigit()}
                    miss_nums = sorted(n for n in seen_nums if n not in got_nums)
                    if not miss_nums or not p.deepseek_chat:
                        continue
                    ctx_task = next((t.get("text") for k, t in collected.items()
                                     if k[0] == block_var and (t.get("text") or "").strip()), "")
                    for attempt in range(2):
                        r_payload = {"doc_text": block_text, "grade": grade,
                                     "missing_nums": [str(n) for n in miss_nums],
                                     "context_task": (ctx_task or "")[:300]}
                        try:
                            r_resp = p.deepseek_chat.chat_json(
                                P.STAGE21_EXTRACT_MISSING, json.dumps(r_payload, ensure_ascii=False))
                        except Exception as e:  # noqa: BLE001
                            log.warning("Этап 21: повторное извлечение не удалось: %s", str(e)[:150])
                            break
                        added_now = 0
                        for task in (r_resp or {}).get("tasks", []) or []:
                            num = str(task.get("num", "")).strip()
                            text = (task.get("text") or "").strip()
                            if not num or not text or not num.isdigit() or int(num) not in miss_nums:
                                continue
                            if not _text_in_doc(text, doc_norm, doc_cyr):
                                continue
                            if (block_var, num) in collected:
                                continue
                            t = dict(task)
                            t["_url"] = url
                            for fld in ("answer", "solution", "points"):
                                if (t.get(fld) or "").strip():
                                    t["_url_" + fld] = url
                            collected[(block_var, num)] = t
                            added_now += 1
                        if added_now:
                            p.search_log.log("", slug, 21, query_desc, "index", url, "скачан",
                                             f"повторное извлечение: +{added_now} задач "
                                             f"(вариант {bv_key or '-'})")
                        got_nums = {int(k[1]) for k in collected if k[0] == block_var and str(k[1]).isdigit()}
                        miss_nums = sorted(n for n in seen_nums if n not in got_nums)
                        if not miss_nums:
                            break
            except Exception as e:  # noqa: BLE001
                log.warning("Этап 21: повтор извлечения пропущен: %s", str(e)[:150])
        if not collected:
            reason = (attempt_reasons[-1] if attempt_reasons
                      else "ни один кандидат не дал блок варианта")
            st["gaps"].append({"year": year, "round": round_name, "grade": grade,
                               "variant": variant, "reason": reason[:200]})
            continue
        # Существующие задачи ТОЙ ЖЕ олимпиады того же года/класса — для дублей
        same_grade = [r for r in p.catalog.data[slug]
                      if r.get("year") == year and str(r.get("grade")) == grade]
        local_uids = {r.get("uid") for r in p.catalog.data[slug]}
        accepted_by_var: dict[str, set] = {}   # вариант блока -> принятые №

        def _gap_exists(n, gap_variant):
            # уникальность по ПОЛНОМУ ключу (year, round, grade, variant, num):
            # остатки разных вариантов/лет не подавляют друг друга
            return any(g.get("num") == n and g.get("year") == year
                       and (g.get("round") or "") == (round_name or "")
                       and str(g.get("grade")) == str(grade)
                       and (g.get("variant") or None) == (gap_variant or None)
                       for g in st["gaps"])

        def _num_in_collected(n):
            return any(k[1] == str(n) for k in collected)

        # Неоднозначность: один и тот же номер с ПОХОЖИМ условием встречен в
        # НЕСКОЛЬКИХ вариантах — атрибуция неоднозначна (needs_review,
        # вариант не проставляем). Определяется ДО обработки, поэтому не
        # зависит от порядка блоков.
        entries_by_num: dict[str, list] = {}
        for (bvar, num), task in collected.items():
            entries_by_num.setdefault(num, []).append((bvar, task))
        # Неоднозначность привязана к КОНКРЕТНЫМ записям (вариант + номер +
        # похожий текст): иная задача того же номера из другого варианта
        # не «заражается» неоднозначностью
        ambiguous_keys: set = set()
        for num, entries in entries_by_num.items():
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    v1, t1 = entries[i]
                    v2, t2 = entries[j]
                    if str(v1 or "") != str(v2 or "") and _text_similarity(
                            (t1.get("text") or ""), (t2.get("text") or "")) >= 0.9:
                        ambiguous_keys.add((str(v1 or ""), num))
                        ambiguous_keys.add((str(v2 or ""), num))
        new_recs_group: list[dict] = []   # новые записи этой группы (для остатка)
        for (bvar, num), task in sorted(
                collected.items(),
                key=lambda kv: (int(kv[0][1]) if kv[0][1].isdigit() else 0,
                                str(kv[0][0] or ""))):
            text = (task.get("text") or "").strip()
            task_ans = (task.get("answer") or "").strip()
            task_sol = (task.get("solution") or "").strip()
            task_url = task.get("_url") or task.get("_url_solution") or ""
            if not text:
                # Решение без условия (sol-PDF): присоединяем по номеру к
                # существующей записи этой группы, решение хранит свой URL
                target = next((r for r in recs
                               if str(r.get("num", "")).strip() == num), None)
                if target is None:
                    p.search_log.log("", slug, 21, query_desc, "index",
                                     task_url, "скачан",
                                     f"решение №{num} без условия: нет записи "
                                     f"с таким номером — пропущено")
                    continue
                if task_sol and target.get("answer"):
                    ok_v, reason_v = _verify_solution(
                        target.get("text") or "", task_sol, target["answer"])
                    if ok_v:
                        t_status = (target.get("status") or "")
                        if t_status == "gemini_solved" or t_status.startswith("AI_"):
                            sol_url = task.get("_url_solution") or task_url
                            p.apply_field(slug, target, 21, "solution", task_sol,
                                          model="deepseek-chat+reasoner")
                            p.apply_field(slug, target, 21, "status", "official_found",
                                          model="deepseek-chat+reasoner")
                            p.add_qa_note(target, 21,
                                          f"официальное решение подтянуто из {sol_url}",
                                          model="deepseek-chat+reasoner")
                            st["_enriched_uids"].add(target.get("uid"))
                    else:
                        p.needs_review(target, 21,
                                      f"решение №{num} не сверено ({reason_v})")
                continue
            # Дубль по тексту (схожесть ≥ 0.9) с задачами этой олимпиады?
            dup = None
            for ex in same_grade:
                if _text_similarity(ex.get("text") or "", text) >= 0.9:
                    dup = ex
                    break
            # Эквивалентность условия дубля и извлечённого (гейт reasoner):
            # отрицательный вердикт = математически ДРУГАЯ задача — никакой
            # атрибуции (variant/source) и пометки «принято», только needs_review
            dup_equivalent = True
            if dup is not None and (dup.get("text") or "").strip() != text:
                dup_equivalent = _math_gate(p, (dup.get("text") or "").strip(),
                                             text, dup, 21)
            if dup is not None and not dup_equivalent:
                if num.isdigit() and int(num) not in nums:
                    rejected[(str(bvar or ""), num)] = "условие не эквивалентно существующей записи (reasoner)"
                p.search_log.log("", slug, 21, query_desc, "reasoner", "",
                                 "скачан",
                                 f"задача №{num}: условие не эквивалентно "
                                 f"существующему дублю — обогащение запрещено")
                continue
            # Ответ для сверки: извлечённый, иначе — существующий у дубля
            check_ans = task_ans or ((dup.get("answer") or "").strip() if dup else "")
            # Проверка 2 (reasoner): решение приводит к ответу — НУЖЕН явный
            # вердикт match. Решение без ответа для сверки — needs_review,
            # ничего не перезаписываем.
            verified = False
            if task_sol:
                if not check_ans:
                    if dup is not None:
                        p.needs_review(dup, 21,
                                       "решение найдено, но ответ для сверки "
                                       "отсутствует — решение не записано")
                    rejected[(str(bvar or ""), num)] = ("нет ответа для сверки решения "
                                          "(needs_review)")
                    continue
                ok_v, reason_v = _verify_solution(text, task_sol, check_ans)
                if not ok_v:
                    rejected[(str(bvar or ""), num)] = f"решение не сверено reasoner ({reason_v})"
                    if dup is not None:
                        p.needs_review(dup, 21,
                                       f"решение не сверено ({reason_v}) — "
                                       f"существующие данные не изменены")
                    p.search_log.log("", slug, 21, query_desc, "reasoner", "",
                                     "скачан",
                                     f"задача №{num}: {reason_v} — пропущена")
                    continue
                # конфликт ответов: у дубля другой ответ — не перезаписываем
                if dup is not None and task_ans and (dup.get("answer") or "").strip() \
                   and _answer_norm_strict(task_ans) != _answer_norm_strict(dup.get("answer")):
                    p.needs_review(dup, 21,
                                   f"конфликт ответов: в PDF «{task_ans[:60]}», "
                                   f"в базе «{(dup.get('answer') or '')[:60]}»")
                    rejected[(str(bvar or ""), num)] = "конфликт ответов с существующей записью"
                    continue
                verified = True
            # Вариант задачи: приоритет у ПОДТВЕРЖДЁННОГО заголовка блока.
            # Ответ модели (поле variant) не может перекрыть заголовок;
            # противоречие — только отметка, не атрибуция
            tv_model = str(task.get("variant") or "").strip()
            bvar_str = str(bvar or "").strip()
            variant_model_conflict = bool(bvar_str and tv_model
                                          and tv_model != bvar_str)
            task_variant = bvar_str or tv_model or (variant or "")
            # Задача встретилась в НЕСКОЛЬКИХ вариантах — атрибуция
            # неоднозначна: вариант не проставляем, только needs_review
            variant_ambiguous = (str(bvar or ""), num) in ambiguous_keys
            if variant_ambiguous:
                task_variant = ""
            if dup is not None:
                # Дубль: НЕ добавляем, обогащаем существующую запись
                st["dup_skipped"] += 1
                changed = False
                if variant_model_conflict:
                    p.add_qa_note(
                        dup, 21,
                        f"поле variant модели («{tv_model}») противоречит "
                        f"заголовку блока («{bvar_str}») — проигнорировано")
                if variant_ambiguous and not (dup.get("variant") or "").strip():
                    # только варианты, УЧАСТВУЮЩИЕ в неоднозначной паре
                    amb_vars = sorted({str(v or "") for v, _t
                                       in entries_by_num.get(num, [])
                                       if (str(v or ""), num) in ambiguous_keys})
                    p.needs_review(dup, 21,
                                   f"задача №{num} встречена в вариантах "
                                   f"{amb_vars} — вариант не "
                                   f"проставлен (неоднозначно)")
                    # дыра в КАЖДОМ из неоднозначных вариантов: задача без
                    # подтверждённого варианта не закрывает конкретный вариант
                    for bv_amb in amb_vars:
                        if _gap_exists(int(num) if num.isdigit() else num,
                                       bv_amb or None):
                            continue
                        st["gaps"].append({
                            "year": year, "round": round_name, "grade": grade,
                            "variant": bv_amb or None,
                            "num": int(num) if num.isdigit() else num,
                            "reason": "задача в нескольких вариантах "
                                      "(неоднозначно)"})
                if task_variant and not (dup.get("variant") or "").strip():
                    changed |= p.apply_field(slug, dup, 21, "variant", task_variant,
                                             model="deepseek-chat")
                    # вариант подтверждён извлечённой задачей (после сверки
                    # и гейта)
                    attributed += 1
                if not (dup.get("source") or "").strip() and task_url:
                    changed |= p.apply_field(slug, dup, 21, "source", task_url,
                                              model="deepseek-chat")
                # Официальное решение для AI-статусов — только после сверки
                # И эквивалентности условия (гейт _math_gate выше)
                dup_status = (dup.get("status") or "")
                if task_sol and verified and dup_equivalent and (
                        dup_status == "gemini_solved"
                        or dup_status.startswith("AI_")):
                    sol_url = task.get("_url_solution") or task_url
                    changed |= p.apply_field(slug, dup, 21, "solution", task_sol,
                                             model="deepseek-chat+reasoner")
                    if task_ans:   # пустым ответом не перезаписываем
                        changed |= p.apply_field(slug, dup, 21, "answer", task_ans,
                                                  model="deepseek-chat+reasoner")
                    changed |= p.apply_field(slug, dup, 21, "status", "official_found",
                                              model="deepseek-chat+reasoner")
                    p.add_qa_note(dup, 21,
                                  f"официальное решение подтянуто из {sol_url}",
                                  model="deepseek-chat+reasoner")
                    if sol_url != task_url:
                        p.add_qa_note(dup, 21,
                                      f"условие — из {task_url}, решение — из {sol_url}")
                if task.get("points"):
                    p.add_qa_note(dup, 21, f"points: {task['points']}")
                if changed:
                    st["_enriched_uids"].add(dup.get("uid"))
                p.search_log.log("", slug, 21, query_desc, "index", task_url,
                                 "скачан",
                                 f"задача №{num}: дубль — обогащена существующая")
                if not variant_ambiguous:
                    # неоднозначная задача не закрывает конкретный вариант
                    accepted_by_var.setdefault(str(bvar or ""), set()).add(
                        int(num) if num.isdigit() else num)
                continue
            # Новая задача
            amb_note = ""
            if variant_ambiguous:
                # только варианты, УЧАСТВУЮЩИЕ в неоднозначной паре
                amb_vars = sorted({str(v or "") for v, _t
                                   in entries_by_num.get(num, [])
                                   if (str(v or ""), num) in ambiguous_keys})
                amb_note = (f"needs_review: новая задача №{num} встречена в "
                            f"вариантах {amb_vars} — импорт с неопределённым "
                            f"вариантом")
                # дыра в КАЖДОМ из неоднозначных вариантов (без записи в
                # accepted_by_var — вариант не подтверждён)
                for bv_amb in amb_vars:
                    if _gap_exists(int(num) if num.isdigit() else num,
                                   bv_amb or None):
                        continue
                    st["gaps"].append({
                        "year": year, "round": round_name, "grade": grade,
                        "variant": bv_amb or None,
                        "num": int(num) if num.isdigit() else num,
                        "reason": "задача в нескольких вариантах "
                                  "(неоднозначно)"})
            uid = _make_uid(context.get("olymp"), year, round_name, grade,
                            num, text, variant=task_variant)
            if uid in local_uids:
                continue   # уже добавили в этом прогоне
            new_rec = {
                "uid": uid,
                "olymp": context.get("olymp"),
                "year": year,
                "round": round_name,
                "day": context.get("day", 0),
                "grade": grade,
                "num": num,
                # official_found — только с проверенным решением;
                # без решения — unresolved (условие из официального источника)
                "status": "official_found" if (task_sol and verified) else "unresolved",
                "answer": task_ans,
                "source": task_url,
                "text": text,
                "solution": task_sol if verified else "",
                # day/geo — по аналогии с соседями; fig_* НЕ копируем
                # (файлы рисунков соседа относятся к другой задаче)
                "geo": any(r.get("geo") for r in recs),
                "fig_statement": [],
                "fig_solution": [],
                "variant": task_variant,
            }
            qa_notes = [f"добавлена задача №{num} из {task_url}"]
            if variant_model_conflict:
                qa_notes.append(
                    f"поле variant модели («{tv_model}») противоречит "
                    f"заголовку блока («{bvar_str}») — проигнорировано")
            if task.get("points"):
                qa_notes.append(f"points: {task['points']}")
            if not task_sol:
                qa_notes.append("в источнике только условие: решение не найдено "
                                "(статус unresolved)")
            if task_sol and verified and task.get("_url_solution") \
               and task["_url_solution"] != task_url:
                qa_notes.append(f"условие — из {task_url}, "
                                f"решение — из {task['_url_solution']}")
            if task_sol and not verified:
                # не должно случаться (см. выше), но на всякий случай
                qa_notes.append("решение не записано: не сверено")
                new_rec["solution"] = ""
            if amb_note:
                qa_notes.append(amb_note)
            new_rec["qa"] = {"stage21": {"stage": 21,
                                         "model": "index+deepseek",
                                         "imported": True,
                                         "changes": {}, "notes": qa_notes}}
            p.catalog.data[slug].append(new_rec)
            p.checkpoint.data["added"].append(uid)
            p.diff.log(uid, 21, "__record__", "missing",
                       f"добавлена задача №{num}", slug)
            same_grade.append(new_rec)     # защита от повтора в этом ответе
            local_uids.add(uid)
            new_recs_group.append(new_rec)   # для расчёта остатка группы
            added += 1
            st["tasks_added"] += 1
            if not variant_ambiguous:
                # неоднозначная задача не закрывает конкретный вариант
                accepted_by_var.setdefault(str(bvar or ""), set()).add(
                    int(num) if num.isdigit() else num)

        # Остаток дыр: исходная группа + новые записи. Записи, получившие
        # вариант при обработке (дубль), остаются в расчёте — их номер
        # не «теряется»; новые записи любого варианта закрывают дыру номера.
        # Диапазонные дыры считаются только по записям каталога:
        # импортированные этапом 21 задачи определяют нумерацию блока PDF,
        # и выводить из них «пропущенные номера» — фантомные дыры.
        orig_recs = _orig_of(recs)
        final_recs = list(recs) + new_recs_group
        if orig_recs:
            # базовые диапазонные ожидания — из записей каталога:
            # импорт №4 не должен сам создавать ожидание №2-3
            _, _, still_missing = _missing_nums(orig_recs)
        else:
            # виртуальная группа (хвост варианта без записей в каталоге) или
            # группа из одних импортированных записей: понятие диапазона
            # не применимо
            still_missing = []
        # Остаток — ПО ВАРИАНТАМ БЛОКОВ (смешивание скрывало реальные дыры:
        # принятая №2 варианта 2 не закрывает отклонённую №2 варианта 1).
        # Покрытие варианта = номера итоговых записей ЭТОГО варианта
        # (включая записи, получившие вариант при обработке) + принятые
        # из этого варианта задачи.
        covered_by_var: dict[str, set[int]] = {}
        for r in final_recs:
            rv = str((r.get("variant") or "").strip() or "")
            try:
                rn = int(str(r.get("num", "0")).strip() or 0)
            except ValueError:
                continue
            if rn:
                covered_by_var.setdefault(rv, set()).add(rn)
        for bv, nums in accepted_by_var.items():
            covered_by_var.setdefault(bv, set()).update(nums)
        # "" (блоки без заголовка варианта) — ДОПУСТИМЫЙ ключ: вариант по ТЗ
        # необязателен, хвост безвариантного блока не должен теряться
        block_vars_list = sorted(block_nums_seen)
        # Сохранённые незакрытые пары прошлых запусков — в ожидаемом
        # остатке до ПОДТВЕРЖДЁННОГО закрытия: отсутствие номера в новом
        # кандидате не доказывает закрытие дыры
        def _pending_nums(bv):
            prs = pending_cp.get(
                _jkey((slug, year, round_name, grade, bv)), [])
            return {n for _bv, n in (tuple(pr) for pr in prs)}

        # ЕДИНЫЙ остаток варианта — и для счётчика полноты, и для отчёта
        # (нельзя записать дыру и назвать вариант полностью закрытым)
        def _variant_remaining(bv):
            base = set(block_nums_seen.get(bv, set()))
            if bv == str(variant or ""):
                # дыры диапазона группы относятся только к её варианту
                base |= set(still_missing)
            base |= _pending_nums(bv)
            return base - covered_by_var.get(bv, set())

        # счётчики полных/частичных вариантов — ПО КАЖДОМУ варианту отдельно
        for bv in block_vars_list:
            if not accepted_by_var.get(bv):
                continue
            rem_v = _variant_remaining(bv)
            rej_v = any(k[0] == bv for k in rejected)
            if rem_v or rej_v:
                st["variants_partial"] += 1
            else:
                st["variants"] += 1        # вариант закрыт полностью

        # остаток по каждому варианту блока (тот же расчёт, что у счётчика)
        for bv in block_vars_list:
            remaining_v = _variant_remaining(bv)
            for n in sorted(remaining_v):
                if _gap_exists(n, bv):
                    continue
                # НЕ затираем переменную цикла групп (key) — свой ключ
                rej_key = (bv, str(n))
                if rej_key in rejected:
                    reason = rejected[rej_key]
                elif n in _pending_nums(bv) and n not in block_nums_seen.get(bv, set()):
                    reason = ("задача из очереди повтора не найдена в новом "
                              "кандидате — закрытие не подтверждено")
                elif n in still_missing:
                    reason = (f"задача №{n} не найдена в документе"
                              if _num_in_collected(n)
                              else (attempt_reasons[-1] if attempt_reasons
                                    else "вариант не найден в документе"))
                else:
                    reason = "задача упомянута в блоке, но не извлечена"
                st["gaps"].append({"year": year, "round": round_name,
                                   "grade": grade, "variant": bv, "num": n,
                                   "reason": reason[:200]})
        # группа БЕЗ варианта: дыры диапазона, не закрытые НИ ОДНИМ
        # вариантом (безвариантная запись не доказывает наличие задачи
        # в конкретном варианте)
        if not variant:
            # запись, получившая вариант при атрибуции, покидает группу —
            # её номер всё равно закрывает дыру диапазона
            covered_any = set()
            for r2 in p.catalog.data.get(slug, []):
                if r2.get("year") != year \
                   or (r2.get("round") or "") != (round_name or "") \
                   or str(r2.get("grade")) != str(grade):
                    continue
                try:
                    n2 = int(str(r2.get("num", "0")).strip() or 0)
                except ValueError:
                    continue
                if n2:
                    covered_any.add(n2)
            for nums in covered_by_var.values():
                covered_any |= nums
            for n in sorted(set(still_missing) - covered_any):
                if _gap_exists(n, None):
                    continue
                reason = (f"задача №{n} не найдена в документе"
                          if _num_in_collected(n)
                          else (attempt_reasons[-1] if attempt_reasons
                                else "вариант не найден в документе"))
                st["gaps"].append({"year": year, "round": round_name,
                                   "grade": grade, "variant": None, "num": n,
                                   "reason": reason[:200]})

        # Незакрытый хвост — в checkpoint ПО ВАРИАНТАМ (ключ — вариант:
        # после атрибуции безвариантная группа расформировывается, а хвост
        # конкретного варианта обязан выжить для повтора)
        for bv in block_vars_list:
            rem_bv = sorted(_variant_remaining(bv))
            jk_bv = _jkey((slug, year, round_name, grade, bv))
            if rem_bv:
                pending_cp[jk_bv] = [[bv, n] for n in rem_bv]
            else:
                pending_cp.pop(jk_bv, None)

    # Необработанные в этом запуске хвосты (--limit) — сохраняем в
    # checkpoint: очередь продолжится в следующем запуске
    for key_t, pairs in tail_pending.items():
        if key_t in processed_keys:
            continue
        jk = _jkey(key_t)
        prev = {tuple(pr) for pr in pending_cp.get(jk, [])}
        pending_cp[jk] = [list(pr) for pr in sorted(prev | pairs)]

    # Дыры, оставшиеся ПОСЛЕ импорта (для отчёта)
    p.catalog._rebuild_index_map()
    # необработанные из-за --limit группы
    if unprocessed:
        for key in sorted(gap_keys, key=priority):
            if key not in ordered_keys:
                slug, year, round_name, grade, variant = key
                st = _st(slug)
                st["unprocessed"] += 1
                st["gaps"].append({
                    "year": year, "round": round_name, "grade": grade,
                    "variant": variant,
                    "reason": "не обработано: --limit"})
    # счётчики из служебных множеств
    for slug, st in report.items():
        st["pdfs"] = len(st.pop("_pdf_urls", set()) or set())
        st["enriched"] = len(st.pop("_enriched_uids", set()) or set())
    p.stats[21]["changed"] = added
    log.info("Этап 21: атрибутировано вариантов: %d, добавлено задач: %d "
             "(отчёт по олимпиадам — в отчёте).", attributed, added)


# =====================================================================
# ЭТАП 22: финальная валидация и отчёт
# =====================================================================


def stage_21b(p: Pipeline):
    """Этап 21b: повторная чистка задач, добавленных этапом 21 (этапы 1–7, 10, 11),
    и запуск поиска решений (этап 20) для импортированных записей без решения."""
    added = [u for u in (p.checkpoint.data.get("added") or []) if u]
    if not added:
        log.info("Этап 21b: новых задач нет — пропуск.")
        return
    uids = set(added)
    present = {r.get("uid") for _s, r in p.catalog.all_records()}
    uids &= present
    if not uids:
        log.info("Этап 21b: добавленные задачи не найдены в каталоге — пропуск.")
        return
    log.info("Этап 21b: чистка %d импортированных задач (этапы 1-7, 10, 11).", len(uids))
    p.catalog.only_uids = uids
    try:
        for st_num in (1, 2, 3, 4, 5, 6, 7, 10, 11):
            try:
                STAGE_FUNCS[st_num](p)
            except Exception as e:  # noqa: BLE001
                log.warning("Этап 21b: этап %d на импорте завершился ошибкой: %s", st_num, str(e)[:150])
        # импортированные без решения -> очередь поиска, затем этап 20
        queued = 0
        for _s, r in p.catalog.all_records():
            if r.get("uid") in uids and not (r.get("solution") or "").strip():
                p.add_to_search_queue(r.get("uid"))
                queued += 1
        if queued:
            log.info("Этап 21b: %d импортированных задач без решения -> этап 20.", queued)
            try:
                STAGE_FUNCS[20](p)
            except Exception as e:  # noqa: BLE001
                log.warning("Этап 21b: этап 20 для импорта завершился ошибкой: %s", str(e)[:150])
    finally:
        p.catalog.only_uids = None
    p.save_state()


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
    try:
        sys.path.insert(0, str(BASE_DIR))
        from routes.olymp_catalog_gaps import summarize as _gaps_summarize, report_md as _gaps_report_md
        summaries = []
        for slug, recs in p.catalog.data.items():
            name = (recs[0].get("olympiad") if recs and recs[0].get("olympiad") else None) or OLYMP_NAMES.get(slug, slug)
            summaries.append(_gaps_summarize(slug, name, recs))
        gaps_result = _gaps_report_md(summaries)
    except Exception:
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
    # Отчёт этапа 21: по каждой олимпиаде
    if p.stage21_report:
        lines += ["", "## Этап 21: заполнение дыр в нумерации", "",
                  "| Олимпиада | PDF | Вариантов: полностью | Вариантов: частично | "
                  "Задач добавлено | Обогащено существующих | Дублей пропущено | "
                  "Не обработано (--limit) | Осталось дыр |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for slug, st in sorted(p.stage21_report.items()):
            lines.append(f"| {slug} | {st.get('pdfs', 0)} | {st.get('variants', 0)} | "
                         f"{st.get('variants_partial', 0)} | "
                         f"{st.get('tasks_added', 0)} | {st.get('enriched', 0)} | "
                         f"{st.get('dup_skipped', 0)} | {st.get('unprocessed', 0)} | "
                         f"{len(st.get('gaps', []))} |")
        lines += ["", "### Остаток дыр (этап 21)", ""]
        shown = 0
        for slug, st in sorted(p.stage21_report.items()):
            for g in st.get("gaps", [])[:100]:
                num_part = f" №{g['num']}" if g.get("num") else ""
                lines.append(f"- `{slug}` {g.get('year')}/{g.get('round')}/"
                             f"{g.get('grade')} кл."
                             f"{(' вар. ' + str(g.get('variant'))) if g.get('variant') else ''}"
                             f"{num_part}: "
                             f"{g.get('reason', '')[:120]}")
                shown += 1
            if shown > 150:
                lines.append("- ... (сокращено)")
                break
        if shown == 0:
            nr_total = sum(st.get("needs_review", 0)
                           for st in p.stage21_report.values())
            unp_total = sum(st.get("unprocessed", 0)
                            for st in p.stage21_report.values())
            if nr_total or unp_total:
                lines.append(
                    f"- Зарегистрированных дыр нет, но полнота НЕ подтверждена: "
                    f"неподтверждённых атрибуций (needs_review) — {nr_total}, "
                    f"необработанных групп (--limit) — {unp_total}.")
            else:
                # записи, для которых не нашлось предложения атрибуции,
                # молча остаются без варианта — «все дыры закрыты» без
                # независимой проверки покрытия заявлять нельзя
                lines.append("- Зарегистрированных дыр нет; полное закрытие "
                             "подтверждайте независимой сверкой с официальными "
                             "PDF (валидация JSON/UID полноту не доказывает).")
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
    # Каталоги для артефактов (work/, reports/) — создаём заранее,
    # чтобы логи/чекпоинт не падали на свежем окружении
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
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
            if stage_num == 21 and not p.dry_run:
                log.info("=" * 60)
                log.info("ЭТАП 21b: чистка импортированных задач и поиск решений для них.")
                try:
                    stage_21b(p)
                except Exception as e:  # noqa: BLE001
                    log.warning("Этап 21b завершился ошибкой: %s", str(e)[:200])
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

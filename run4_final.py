#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
run4_final.py — аудит и починка базы FORMYLA. Один файл, ничего настраивать не нужно.

ЗАПУСК:
    python run4_final.py

    Подхватывает старый прогресс из базы, доаудирует остаток, чинит проблемные
    задачи, собирает чистую базу. Сам перезапускается после любого падения.

ПРОЧЕЕ:
    python run4_final.py --status      посмотреть состояние
    python run4_final.py --stage fix   только починка
    python run4_final.py --threads 2   меньше потоков, если мало памяти

ФАЙЛЫ РЯДОМ С БАЗОЙ:
    state_audit.jsonl / state_fix.jsonl   прогресс (append-only, fsync)
    run4.log / crash.log                  журналы
    *_CLEAN.jsonl / *_UNRESOLVED.jsonl    результат
"""

import argparse
import faulthandler
import json
import os
import queue
import random
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

# ============================================================================
# НАСТРОЙКИ
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "FORMYLA_L1_L3_FINAL_v3.jsonl")

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")   # или впиши строкой сюда
API_BASE = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-pro"
EXTRA_BODY = {"thinking": True}   # отключится само, если провайдер не поймёт

ID_FIELD = "task_uid"
TASK_FIELD = "statement"
ANSWER_FIELD = "answer"
SOLUTION_FIELD = "solution"

THREADS = 3
MAX_TOKENS = 8000
MAX_TOKENS_RETRY = 20000
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 180
ATTEMPTS = 4
FIX_CYCLES = 5

HEARTBEAT_SEC = 30
MEM_LIMIT_MB = 3500
MIGRATE_OLD_STATE = True   # забрать вердикты run3 из полей _audit_* внутри базы

MAX_CHARS = 6000   # обрезка длинных текстов, чтобы не жечь токены впустую

# ============================================================================
# ПРОМПТЫ
# ============================================================================

AUDIT_SYSTEM = (
    "Ты придирчивый проверяющий математических задач. "
    "Отвечай ТОЛЬКО валидным JSON без markdown-обёрток. "
    "Рассуждай кратко: важен вердикт, а не длинный разбор."
)

AUDIT_USER = """Проверь задачу, её решение и ответ.

УСЛОВИЕ:
{task}

РЕШЕНИЕ:
{solution}

ОТВЕТ:
{answer}

Верни JSON строго такой формы:
{{"condition": "YES|NO|BORDERLINE", "answer_ok": "YES|NO", "problems": "что именно не так, 1-3 предложения"}}

condition: корректно, полно и однозначно ли сформулировано условие.
answer_ok: верны ли решение и ответ по существу.
problems: пустая строка, если всё чисто."""

FIX_SYSTEM = (
    "Ты редактор базы математических задач. Исправляешь условие, решение и ответ, "
    "сохраняя исходный смысл, тему и уровень сложности. "
    "Отвечай ТОЛЬКО валидным JSON без markdown-обёрток."
)

FIX_USER = """Исправь задачу с учётом замечаний.

УСЛОВИЕ:
{task}

РЕШЕНИЕ:
{solution}

ОТВЕТ:
{answer}

ЗАМЕЧАНИЯ ПРОВЕРЯЮЩЕГО:
{problems}

Верни JSON строго такой формы:
{{"statement": "исправленное условие", "solution": "исправленное решение", "answer": "исправленный ответ", "changes": "что поменял, кратко"}}"""

# ============================================================================
# ИНФРАСТРУКТУРА
# ============================================================================

STATE_AUDIT = os.path.join(BASE_DIR, "state_audit.jsonl")
STATE_FIX = os.path.join(BASE_DIR, "state_fix.jsonl")
LOG_PATH = os.path.join(BASE_DIR, "run4.log")
CRASH_PATH = os.path.join(BASE_DIR, "crash.log")
MIGRATE_MARK = os.path.join(BASE_DIR, ".migrated")

_log_lock = threading.Lock()
_log_fh = None
_crash_fh = None
_stop = threading.Event()


def log(msg):
    line = "%s | %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    with _log_lock:
        try:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except Exception:
            pass
        if _log_fh:
            try:
                _log_fh.write(line + "\n")
                _log_fh.flush()
            except Exception:
                pass


def open_log():
    global _log_fh
    _log_fh = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    _log_fh.write("\n%s ЗАПУСК pid=%s argv=%s\n" % ("=" * 30, os.getpid(), sys.argv[1:]))
    _log_fh.flush()


def enable_crash_dump():
    global _crash_fh
    try:
        _crash_fh = open(CRASH_PATH, "ab", buffering=0)
        faulthandler.enable(_crash_fh)
    except Exception:
        pass


def mem_mb():
    try:
        import ctypes
        import ctypes.wintypes as wt

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        c = PMC()
        c.cb = ctypes.sizeof(c)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return int(c.WorkingSetSize / (1024 * 1024))
    except Exception:
        return -1


def cut(x):
    s = "" if x is None else (x if isinstance(x, str) else json.dumps(x, ensure_ascii=False))
    return s if len(s) <= MAX_CHARS else s[:MAX_CHARS] + "\n...[обрезано]"


class StateFile:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.fh = open(path, "a", encoding="utf-8", errors="replace")

    def add(self, obj):
        line = json.dumps(obj, ensure_ascii=False)
        with self.lock:
            self.fh.write(line + "\n")
            self.fh.flush()
            try:
                os.fsync(self.fh.fileno())
            except Exception:
                pass

    def close(self):
        try:
            self.fh.close()
        except Exception:
            pass

    @staticmethod
    def load(path):
        out = {}
        if not os.path.exists(path):
            return out
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    o = json.loads(raw)
                except Exception:
                    continue
                k = o.get("key")
                if k is not None:
                    out[str(k)] = o
        return out


# ============================================================================
# API
# ============================================================================

import urllib.error
import urllib.request

_thinking_ok = True
_thinking_lock = threading.Lock()


def raw_call(messages, max_tokens, use_thinking, timeout):
    body = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    if use_thinking and _thinking_ok:
        body.update(EXTRA_BODY)

    req = urllib.request.Request(
        API_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))

    ch = (data.get("choices") or [{}])[0]
    finish = ch.get("finish_reason") or ""
    msg = ch.get("message") or {}
    content = (msg.get("content") or "").strip()
    return content, finish


def ask_json(messages, tag=""):
    """dict или None. finish=length -> повтор без thinking и с большим лимитом."""
    global _thinking_ok
    tokens = MAX_TOKENS
    thinking = True
    last = ""

    for attempt in range(1, ATTEMPTS + 1):
        if _stop.is_set():
            return None
        try:
            content, finish = raw_call(messages, tokens, thinking,
                                       CONNECT_TIMEOUT + READ_TIMEOUT)
            if content:
                try:
                    return json.loads(content)
                except Exception:
                    s = content.find("{")
                    e = content.rfind("}")
                    if s >= 0 and e > s:
                        try:
                            return json.loads(content[s:e + 1])
                        except Exception:
                            pass
                    last = "невалидный JSON"
            else:
                last = "пустой ответ, finish=%s" % finish

            if finish == "length" or not content:
                tokens = MAX_TOKENS_RETRY
                thinking = False

        except urllib.error.HTTPError as e:
            last = "HTTP %s" % e.code
            if e.code == 400 and thinking:
                with _thinking_lock:
                    if _thinking_ok:
                        _thinking_ok = False
                        log("  thinking не поддержан — отключаю глобально")
                thinking = False
                continue
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(30, 2 ** attempt) + random.random())
                continue
            if 400 <= e.code < 500:
                break
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, str(e)[:120])
            time.sleep(min(20, 2 ** attempt) + random.random())

    log("  ! отказ [%s]: %s" % (tag, last))
    return None


# ============================================================================
# БАЗА
# ============================================================================

def load_db():
    recs = []
    bad = 0
    with open(DB_PATH, "r", encoding="utf-8", errors="replace") as f:
        for i, raw in enumerate(f):
            raw = raw.strip()
            if not raw:
                continue
            try:
                o = json.loads(raw)
            except Exception:
                bad += 1
                continue
            if o.get(ID_FIELD) is not None:
                o["__key"] = str(o.get(ID_FIELD))
            else:
                o["__key"] = "row%d" % i
            recs.append(o)

    if not recs:
        raise SystemExit("База пуста или не читается: %s" % DB_PATH)
    if bad:
        log("Битых строк пропущено: %d" % bad)

    seen = {}
    for r in recs:
        k = r["__key"]
        if k in seen:
            seen[k] += 1
            r["__key"] = "%s#%d" % (k, seen[k])
        else:
            seen[k] = 0
    return recs


def norm_v(x, allowed, default):
    s = str(x or "").strip().upper()
    return s if s in allowed else default


def is_clean(v):
    return v.get("condition") in ("YES", "BORDERLINE") and v.get("answer_ok") == "YES"


# ============================================================================
# ПЕРЕНОС СТАРОГО ПРОГРЕССА ИЗ ПОЛЕЙ _audit_*
# ============================================================================

def extract_old(rec):
    st = rec.get("_audit_status")
    vd = rec.get("_audit_verdicts")
    if st is None and vd is None:
        return None
    if isinstance(st, str) and st.strip().lower() in ("err", "error", "fail", "failed", ""):
        return None

    found = {"cond": None, "ans": None}

    def scan(o, depth=0):
        if depth > 5 or o is None:
            return
        if isinstance(o, dict):
            for kk, vv in o.items():
                kl = str(kk).lower()
                if isinstance(vv, str):
                    tok = vv.strip().upper()
                    if tok in ("YES", "NO", "BORDERLINE"):
                        if ("cond" in kl or "усл" in kl) and found["cond"] is None:
                            found["cond"] = tok
                        elif ("ans" in kl or "отв" in kl) and found["ans"] is None:
                            found["ans"] = tok
                else:
                    scan(vv, depth + 1)
        elif isinstance(o, list):
            for it in o:
                scan(it, depth + 1)

    scan(vd)
    scan(st)

    if found["cond"] is None and found["ans"] is None:
        s = str(st).strip().lower()
        q = str(rec.get("quality_status") or "").strip().lower()
        if s in ("clean", "ok", "good", "pass", "passed") or q == "clean":
            found["cond"], found["ans"] = "YES", "YES"
        else:
            return None

    problems = rec.get("_expert_comment") or rec.get("critic_report") or ""
    return {
        "condition": found["cond"] or "BORDERLINE",
        "answer_ok": found["ans"] or "NO",
        "problems": cut(problems)[:2000],
    }


def migrate(recs):
    if not MIGRATE_OLD_STATE or os.path.exists(MIGRATE_MARK):
        return
    existing = StateFile.load(STATE_AUDIT)
    sf = StateFile(STATE_AUDIT)
    n = 0
    try:
        for r in recs:
            k = r["__key"]
            if existing.get(k, {}).get("status") == "OK":
                continue
            v = extract_old(r)
            if not v:
                continue
            v.update({"key": k, "status": "OK", "src": "run3"})
            sf.add(v)
            n += 1
    finally:
        sf.close()
    with open(MIGRATE_MARK, "w", encoding="utf-8") as f:
        f.write(str(n))
    log("Перенесено вердиктов из старой базы: %d" % n)


# ============================================================================
# ПУЛ ЗАДАЧ
# ============================================================================

def run_pool(items, worker, threads, label):
    q = queue.Queue()
    for it in items:
        q.put(it)

    total = len(items)
    done = [0]
    started = {}
    lk = threading.Lock()
    t0 = time.time()

    def loop(wid):
        while not _stop.is_set():
            try:
                item = q.get_nowait()
            except queue.Empty:
                return
            while not _stop.is_set():
                m = mem_mb()
                if m < 0 or m < MEM_LIMIT_MB:
                    break
                time.sleep(5)
            with lk:
                started[wid] = time.time()
            try:
                worker(item)
            except Exception as e:
                log("  ! поток %d: %s: %s" % (wid, type(e).__name__, str(e)[:150]))
            finally:
                with lk:
                    started.pop(wid, None)
                    done[0] += 1
                    n = done[0]
                if n % 5 == 0 or n == total:
                    el = time.time() - t0
                    eta = (el / n) * (total - n) / 60 if n else 0
                    log("[%s %d/%d %.1f%%] осталось ~%d мин | память %d МБ"
                        % (label, n, total, 100.0 * n / total, eta, mem_mb()))

    def beat():
        while not _stop.is_set() and done[0] < total:
            time.sleep(HEARTBEAT_SEC)
            with lk:
                longest = max([time.time() - v for v in started.values()] or [0])
                busy = len(started)
            if done[0] < total and not _stop.is_set():
                log("    ~ пульс: занято %d, самый долгий %d с, готово %d/%d, память %d МБ"
                    % (busy, longest, done[0], total, mem_mb()))

    ths = [threading.Thread(target=loop, args=(i,), daemon=True) for i in range(max(1, threads))]
    threading.Thread(target=beat, daemon=True).start()
    for t in ths:
        t.start()
    for t in ths:
        while t.is_alive():
            t.join(timeout=1.0)
    log("%s: обработано %d/%d за %.1f мин" % (label, done[0], total, (time.time() - t0) / 60))


# ============================================================================
# ЭТАП 1: АУДИТ
# ============================================================================

def audit_payload(task, solution, answer):
    return [{"role": "system", "content": AUDIT_SYSTEM},
            {"role": "user", "content": AUDIT_USER.format(
                task=cut(task), solution=cut(solution), answer=cut(answer))}]


def audit_one(rec, sf):
    r = ask_json(audit_payload(rec.get(TASK_FIELD), rec.get(SOLUTION_FIELD),
                               rec.get(ANSWER_FIELD)), "audit " + rec["__key"])
    if r is None:
        sf.add({"key": rec["__key"], "status": "ERR"})
        return
    sf.add({"key": rec["__key"], "status": "OK",
            "condition": norm_v(r.get("condition"), {"YES", "NO", "BORDERLINE"}, "BORDERLINE"),
            "answer_ok": norm_v(r.get("answer_ok"), {"YES", "NO"}, "NO"),
            "problems": str(r.get("problems") or "")[:2000]})


def stage_audit(recs, threads):
    state = StateFile.load(STATE_AUDIT)
    todo = [r for r in recs if state.get(r["__key"], {}).get("status") != "OK"]

    log("=" * 64)
    log("ЭТАП 1: АУДИТ")
    log("Всего в базе : %d" % len(recs))
    log("Уже проверено: %d" % (len(recs) - len(todo)))
    log("К работе     : %d" % len(todo))
    log("=" * 64)
    if not todo:
        return

    sf = StateFile(STATE_AUDIT)
    try:
        run_pool(todo, lambda r: audit_one(r, sf), threads, "audit")
    finally:
        sf.close()


# ============================================================================
# ЭТАП 2: ФИКС
# ============================================================================

def fix_one(rec, verdict, sf):
    task = rec.get(TASK_FIELD) or ""
    solution = rec.get(SOLUTION_FIELD) or ""
    answer = rec.get(ANSWER_FIELD) or ""
    problems = verdict.get("problems") or "ответ или решение неверны либо условие неполно"
    trail = []

    for cycle in range(1, FIX_CYCLES + 1):
        if _stop.is_set():
            return
        fr = ask_json(
            [{"role": "system", "content": FIX_SYSTEM},
             {"role": "user", "content": FIX_USER.format(
                 task=cut(task), solution=cut(solution),
                 answer=cut(answer), problems=cut(problems))}],
            "fix %s c%d" % (rec["__key"], cycle))
        if fr is None:
            break

        task = str(fr.get("statement") or task).strip()
        solution = str(fr.get("solution") or solution).strip()
        answer = str(fr.get("answer") or answer).strip()
        trail.append(str(fr.get("changes") or "")[:300])

        ar = ask_json(audit_payload(task, solution, answer),
                      "recheck %s c%d" % (rec["__key"], cycle))
        if ar is None:
            break

        v = {"condition": norm_v(ar.get("condition"), {"YES", "NO", "BORDERLINE"}, "BORDERLINE"),
             "answer_ok": norm_v(ar.get("answer_ok"), {"YES", "NO"}, "NO")}
        if is_clean(v):
            sf.add({"key": rec["__key"], "status": "FIXED", "cycles": cycle,
                    "statement": task, "solution": solution, "answer": answer,
                    "trail": trail})
            return
        problems = str(ar.get("problems") or problems)[:2000]

    sf.add({"key": rec["__key"], "status": "UNRESOLVED", "cycles": len(trail),
            "statement": task, "solution": solution, "answer": answer, "trail": trail})


def stage_fix(recs, threads):
    audit = StateFile.load(STATE_AUDIT)
    fixed = StateFile.load(STATE_FIX)

    todo = []
    no_verdict = 0
    for r in recs:
        k = r["__key"]
        if k in fixed:
            continue
        v = audit.get(k)
        if not v or v.get("status") != "OK":
            no_verdict += 1
            continue
        if not is_clean(v):
            todo.append((r, v))

    log("=" * 64)
    log("ЭТАП 2: ФИКС")
    log("Требуют правки : %d" % len(todo))
    log("Уже обработано : %d" % len(fixed))
    log("Без вердикта   : %d" % no_verdict)
    log("Потоков %d, токены %d/%d, циклов до %d"
        % (threads, MAX_TOKENS, MAX_TOKENS_RETRY, FIX_CYCLES))
    log("=" * 64)
    if not todo:
        return

    sf = StateFile(STATE_FIX)
    try:
        run_pool(todo, lambda p: fix_one(p[0], p[1], sf), threads, "fix")
    finally:
        sf.close()


# ============================================================================
# ЭТАП 3: ЭКСПОРТ
# ============================================================================

def stage_export(recs):
    audit = StateFile.load(STATE_AUDIT)
    fixed = StateFile.load(STATE_FIX)
    root = os.path.splitext(DB_PATH)[0]
    clean_path = root + "_CLEAN.jsonl"
    bad_path = root + "_UNRESOLVED.jsonl"

    n_clean = n_bad = n_skip = 0
    with open(clean_path, "w", encoding="utf-8") as fc, \
         open(bad_path, "w", encoding="utf-8") as fb:
        for r in recs:
            k = r["__key"]
            out = {kk: vv for kk, vv in r.items() if kk != "__key"}
            f = fixed.get(k)
            if f:
                out[TASK_FIELD] = f.get("statement", out.get(TASK_FIELD))
                out[SOLUTION_FIELD] = f.get("solution", out.get(SOLUTION_FIELD))
                out[ANSWER_FIELD] = f.get("answer", out.get(ANSWER_FIELD))
                out["_fix_cycles"] = f.get("cycles")
                if f.get("status") == "FIXED":
                    out["quality_status"] = "clean"
                    fc.write(json.dumps(out, ensure_ascii=False) + "\n")
                    n_clean += 1
                else:
                    fb.write(json.dumps(out, ensure_ascii=False) + "\n")
                    n_bad += 1
                continue
            v = audit.get(k)
            if v and v.get("status") == "OK" and is_clean(v):
                out["quality_status"] = "clean"
                fc.write(json.dumps(out, ensure_ascii=False) + "\n")
                n_clean += 1
            else:
                n_skip += 1

    log("=" * 64)
    log("ЭКСПОРТ")
    log("  чистых        : %d" % n_clean)
    log("  не исправлено : %d" % n_bad)
    log("  без вердикта  : %d" % n_skip)
    log("  файл: %s" % os.path.basename(clean_path))
    log("=" * 64)


def count_left(recs):
    audit = StateFile.load(STATE_AUDIT)
    fixed = StateFile.load(STATE_FIX)
    left_audit = 0
    left_fix = 0
    for r in recs:
        k = r["__key"]
        v = audit.get(k)
        if not v or v.get("status") != "OK":
            left_audit += 1
        elif not is_clean(v) and k not in fixed:
            left_fix += 1
    return left_audit, left_fix


def show_status(recs):
    audit = StateFile.load(STATE_AUDIT)
    fixed = StateFile.load(STATE_FIX)
    ok = [v for v in audit.values() if v.get("status") == "OK"]
    need = [v for v in ok if not is_clean(v)]
    la, lf = count_left(recs)
    log("Задач в базе     : %d" % len(recs))
    log("Аудировано       : %d (чистых %d, к правке %d)"
        % (len(ok), len(ok) - len(need), len(need)))
    log("Починка записана : %d (успешно %d)"
        % (len(fixed), sum(1 for v in fixed.values() if v.get("status") == "FIXED")))
    log("Осталось: аудит %d, фикс %d" % (la, lf))


# ============================================================================
# НАДЗИРАТЕЛЬ
# ============================================================================

def supervise(argv):
    cmd = [sys.executable, "-X", "faulthandler", "-u", os.path.abspath(__file__),
           "--no-supervise"] + argv
    for run in range(1, 61):
        log(">>> надзиратель: запуск %d" % run)
        t0 = time.time()
        try:
            rc = subprocess.call(cmd, cwd=BASE_DIR)
        except KeyboardInterrupt:
            return 130
        el = (time.time() - t0) / 60
        log(">>> надзиратель: код=%s, работал %.1f мин" % (rc, el))
        if rc == 0:
            log(">>> ГОТОВО")
            return 0
        if rc in (2, 130):
            log(">>> остановлено пользователем")
            return rc
        if el < 0.2:
            log(">>> падает мгновенно — смотри run4.log, перезапуск бессмыслен")
            return rc
        log(">>> пауза 10 с, продолжаем с того же места")
        time.sleep(10)
    return 1


# ============================================================================
# MAIN
# ============================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["all", "audit", "fix", "export"], default="all")
    ap.add_argument("--threads", type=int, default=THREADS)
    ap.add_argument("--no-supervise", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    open_log()
    enable_crash_dump()

    def on_sig(sig, frm):
        log("сигнал %s — останавливаюсь аккуратно" % sig)
        _stop.set()

    try:
        signal.signal(signal.SIGINT, on_sig)
        signal.signal(signal.SIGTERM, on_sig)
    except Exception:
        pass

    if not a.no_supervise and not a.status and a.stage in ("all", "audit", "fix"):
        return supervise([x for x in sys.argv[1:] if x != "--no-supervise"])

    if not a.status and not API_KEY:
        raise SystemExit("Нет API-ключа. setx DEEPSEEK_API_KEY \"...\" и новое окно PowerShell.")

    log("run4 | %s | потоков %d | токены %d/%d"
        % (MODEL, a.threads, MAX_TOKENS, MAX_TOKENS_RETRY))
    log("База: %s" % DB_PATH)

    recs = load_db()
    migrate(recs)

    if a.status:
        show_status(recs)
        return 0

    if a.stage in ("all", "audit"):
        stage_audit(recs, a.threads)
    if a.stage in ("all", "fix"):
        stage_fix(recs, a.threads)
    if a.stage in ("all", "export"):
        stage_export(recs)

    if _stop.is_set():
        return 2

    if a.stage == "all":
        la, lf = count_left(recs)
        if la or lf:
            log("не доделано: аудит %d, фикс %d — надзиратель продолжит" % (la, lf))
            return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

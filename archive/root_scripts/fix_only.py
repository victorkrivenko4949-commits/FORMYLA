#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fix_only.py — ТОЛЬКО ПОЧИНКА. Аудита нет.

Вердикты берутся из самой базы: _audit_verdicts / _audit_status / quality_status.
Задача идёт в починку, если хотя бы один вердикт BAD.

ЗАПУСК:
    python fix_only.py                 починка + сборка чистой базы
    python fix_only.py --status        только посчитать, сколько к правке (бесплатно)
    python fix_only.py --export        только пересобрать итог из готового прогресса
    python fix_only.py --threads 2     меньше потоков
    python fix_only.py --limit 20      прогнать 20 задач для пробы

Прогресс пишется в state_fix.jsonl построчно с fsync: убийство процесса
не теряет сделанное, повторный запуск продолжает с того же места.
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

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_BASE = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-pro"
EXTRA_BODY = {"thinking": True}

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
FIX_CYCLES = 3
MAX_CHARS = 6000
HEARTBEAT_SEC = 30
MEM_LIMIT_MB = 3500

GOOD = {"GOOD", "YES", "OK", "PASS", "PASSED", "CLEAN", "APPROVE", "TRUE"}
BAD = {"BAD", "NO", "FAIL", "FAILED", "REJECT", "FALSE"}
SOFT = {"BORDERLINE", "SOFT", "MINOR", "WARN"}
CLEAN_STATUS = {"clean", "ok", "approve", "approved", "pass", "passed", "fixed", "done"}

STATE_FIX = os.path.join(BASE_DIR, "state_fix.jsonl")
LOG_PATH = os.path.join(BASE_DIR, "fix_only.log")
CRASH_PATH = os.path.join(BASE_DIR, "crash.log")

# ============================================================================
# ПРОМПТЫ
# ============================================================================

FIX_SYSTEM = (
    "Ты редактор базы олимпиадных математических задач. "
    "Исправляешь условие, решение и ответ, сохраняя тему и уровень сложности. "
    "Решение пиши компактно и по делу, без перебора вариантов и размышлений вслух. "
    "Отвечай ТОЛЬКО валидным JSON без markdown-обёрток."
)

FIX_USER = """Исправь задачу.

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

CHECK_SYSTEM = (
    "Ты проверяющий математических задач. Отвечай ТОЛЬКО валидным JSON "
    "без markdown-обёрток. Рассуждай кратко."
)

CHECK_USER = """Проверь исправленную задачу.

УСЛОВИЕ:
{task}

РЕШЕНИЕ:
{solution}

ОТВЕТ:
{answer}

Верни JSON строго такой формы:
{{"condition": "YES|NO|BORDERLINE", "answer_ok": "YES|NO", "problems": "что осталось не так, кратко"}}"""

# ============================================================================
# ИНФРАСТРУКТУРА
# ============================================================================

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
    global _log_fh, _crash_fh
    _log_fh = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    _log_fh.write("\n%s ЗАПУСК pid=%s argv=%s\n" % ("=" * 30, os.getpid(), sys.argv[1:]))
    _log_fh.flush()
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
    if x is None:
        s = ""
    elif isinstance(x, str):
        s = x
    else:
        s = json.dumps(x, ensure_ascii=False)
    return s if len(s) <= MAX_CHARS else s[:MAX_CHARS] + "\n...[обрезано]"


class StateFile:
    def __init__(self, path):
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
                if o.get("key") is not None:
                    out[str(o["key"])] = o
        return out


# ============================================================================
# API
# ============================================================================

import urllib.error
import urllib.request

_thinking_ok = True
_tlock = threading.Lock()


def raw_call(messages, max_tokens, thinking, timeout):
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
            "temperature": 0.2, "response_format": {"type": "json_object"}}
    if thinking and _thinking_ok:
        body.update(EXTRA_BODY)
    req = urllib.request.Request(
        API_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + API_KEY},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    ch = (data.get("choices") or [{}])[0]
    return ((ch.get("message") or {}).get("content") or "").strip(), (ch.get("finish_reason") or "")


def ask_json(messages, tag=""):
    global _thinking_ok
    tokens, thinking, last = MAX_TOKENS, True, ""
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
                    s, e = content.find("{"), content.rfind("}")
                    if s >= 0 and e > s:
                        try:
                            return json.loads(content[s:e + 1])
                        except Exception:
                            pass
                    last = "невалидный JSON"
            else:
                last = "пустой ответ, finish=%s" % finish
            if finish == "length" or not content:
                tokens, thinking = MAX_TOKENS_RETRY, False
        except urllib.error.HTTPError as e:
            last = "HTTP %s" % e.code
            if e.code == 400 and thinking:
                with _tlock:
                    if _thinking_ok:
                        _thinking_ok = False
                        log("  thinking не поддержан — отключаю")
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
# ЧТЕНИЕ БАЗЫ И СТАРЫХ ВЕРДИКТОВ
# ============================================================================

def collect(o, acc, depth=0):
    if depth > 6 or o is None:
        return
    if isinstance(o, bool):
        acc.append("GOOD" if o else "BAD")
    elif isinstance(o, str):
        t = o.strip().upper()
        if t in GOOD or t in BAD or t in SOFT:
            acc.append(t)
    elif isinstance(o, list):
        for it in o:
            collect(it, acc, depth + 1)
    elif isinstance(o, dict):
        for vv in o.values():
            collect(vv, acc, depth + 1)


def verdict_of(rec):
    """('clean'|'dirty'|'unknown', текст замечаний)"""
    toks = []
    collect(rec.get("_audit_verdicts"), toks)
    problems = rec.get("_expert_comment") or rec.get("critic_report") or ""
    problems = cut(problems)[:2000]

    if toks:
        return ("dirty" if any(t in BAD for t in toks) else "clean"), problems

    st = str(rec.get("_audit_status") or "").strip().lower()
    q = str(rec.get("quality_status") or "").strip().lower()
    if st in CLEAN_STATUS or q in CLEAN_STATUS:
        return "clean", ""
    if st:
        return "dirty", problems
    return "unknown", problems


def load_db():
    recs, bad = [], 0
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
            o["__key"] = str(o.get(ID_FIELD)) if o.get(ID_FIELD) is not None else "row%d" % i
            recs.append(o)
    if not recs:
        raise SystemExit("База не читается: %s" % DB_PATH)
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


def split_db(recs):
    clean, dirty, unknown = [], [], []
    for r in recs:
        st, pr = verdict_of(r)
        r["__problems"] = pr
        if st == "clean":
            clean.append(r)
        elif st == "dirty":
            dirty.append(r)
        else:
            unknown.append(r)
    return clean, dirty, unknown


# ============================================================================
# ПУЛ
# ============================================================================

def run_pool(items, worker, threads, label):
    q = queue.Queue()
    for it in items:
        q.put(it)
    total, done, started, lk, t0 = len(items), [0], {}, threading.Lock(), time.time()

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
                    log("[%s %d/%d %.1f%%] осталось ~%d мин | память %d МБ"
                        % (label, n, total, 100.0 * n / total,
                           (el / n) * (total - n) / 60, mem_mb()))

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
# ПОЧИНКА
# ============================================================================

def norm(x, allowed, default):
    s = str(x or "").strip().upper()
    return s if s in allowed else default


def ok_check(v):
    return v.get("condition") in ("YES", "BORDERLINE") and v.get("answer_ok") == "YES"


def fix_one(rec, sf):
    task = rec.get(TASK_FIELD) or ""
    solution = rec.get(SOLUTION_FIELD) or ""
    answer = rec.get(ANSWER_FIELD) or ""
    problems = rec.get("__problems") or "решение или ответ неверны, условие требует уточнения"
    trail = []

    for cycle in range(1, FIX_CYCLES + 1):
        if _stop.is_set():
            return
        fr = ask_json([{"role": "system", "content": FIX_SYSTEM},
                       {"role": "user", "content": FIX_USER.format(
                           task=cut(task), solution=cut(solution),
                           answer=cut(answer), problems=cut(problems))}],
                      "fix %s c%d" % (rec["__key"], cycle))
        if fr is None:
            return

        task = str(fr.get("statement") or task).strip()
        solution = str(fr.get("solution") or solution).strip()
        answer = str(fr.get("answer") or answer).strip()
        trail.append(str(fr.get("changes") or "")[:300])

        cr = ask_json([{"role": "system", "content": CHECK_SYSTEM},
                       {"role": "user", "content": CHECK_USER.format(
                           task=cut(task), solution=cut(solution), answer=cut(answer))}],
                      "check %s c%d" % (rec["__key"], cycle))
        if cr is None:
            break

        v = {"condition": norm(cr.get("condition"), {"YES", "NO", "BORDERLINE"}, "BORDERLINE"),
             "answer_ok": norm(cr.get("answer_ok"), {"YES", "NO"}, "NO")}
        if ok_check(v):
            sf.add({"key": rec["__key"], "status": "FIXED", "cycles": cycle,
                    "statement": task, "solution": solution, "answer": answer, "trail": trail})
            return
        problems = str(cr.get("problems") or problems)[:2000]

    sf.add({"key": rec["__key"], "status": "UNRESOLVED", "cycles": len(trail),
            "statement": task, "solution": solution, "answer": answer, "trail": trail})


# ============================================================================
# ЭКСПОРТ
# ============================================================================

def export(recs):
    fixed = StateFile.load(STATE_FIX)
    root = os.path.splitext(DB_PATH)[0]
    clean_path, bad_path = root + "_CLEAN.jsonl", root + "_UNRESOLVED.jsonl"
    n_clean = n_bad = n_skip = 0

    with open(clean_path, "w", encoding="utf-8") as fc, \
         open(bad_path, "w", encoding="utf-8") as fb:
        for r in recs:
            out = {k: v for k, v in r.items() if not k.startswith("__")}
            f = fixed.get(r["__key"])
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
            st, _ = verdict_of(r)
            if st == "clean":
                out["quality_status"] = "clean"
                fc.write(json.dumps(out, ensure_ascii=False) + "\n")
                n_clean += 1
            else:
                n_skip += 1

    log("=" * 60)
    log("ЭКСПОРТ: чистых %d | не исправлено %d | не обработано %d"
        % (n_clean, n_bad, n_skip))
    log("Файл: %s" % os.path.basename(clean_path))
    log("=" * 60)


# ============================================================================
# НАДЗИРАТЕЛЬ И MAIN
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
            return rc
        if el < 0.2:
            log(">>> падает мгновенно — смотри fix_only.log")
            return rc
        time.sleep(10)
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=THREADS)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--no-supervise", action="store_true")
    a = ap.parse_args()

    open_log()

    def on_sig(sig, frm):
        log("сигнал %s — останавливаюсь аккуратно" % sig)
        _stop.set()

    try:
        signal.signal(signal.SIGINT, on_sig)
        signal.signal(signal.SIGTERM, on_sig)
    except Exception:
        pass

    if not a.no_supervise and not a.status and not a.export:
        return supervise([x for x in sys.argv[1:] if x != "--no-supervise"])

    recs = load_db()
    clean, dirty, unknown = split_db(recs)
    already = StateFile.load(STATE_FIX)
    todo = [r for r in dirty if r["__key"] not in already]

    log("=" * 60)
    log("Всего задач      : %d" % len(recs))
    log("Чисто по аудиту  : %d" % len(clean))
    log("К починке        : %d" % len(dirty))
    log("Уже починено ран.: %d (успешно %d)"
        % (len(already), sum(1 for v in already.values() if v.get("status") == "FIXED")))
    log("Без вердикта     : %d" % len(unknown))
    log("В работу сейчас  : %d" % len(todo))
    log("=" * 60)

    if a.status:
        return 0
    if a.export:
        export(recs)
        return 0
    if not API_KEY:
        raise SystemExit("Нет API-ключа. setx DEEPSEEK_API_KEY \"...\" и новое окно PowerShell.")

    if a.limit:
        todo = todo[:a.limit]
        log("Пробный прогон: только %d задач" % len(todo))

    if todo:
        sf = StateFile(STATE_FIX)
        try:
            run_pool(todo, lambda r: fix_one(r, sf), a.threads, "fix")
        finally:
            sf.close()

    if _stop.is_set():
        return 2

    export(recs)

    done = StateFile.load(STATE_FIX)
    left = sum(1 for r in dirty if r["__key"] not in done)
    if left and not a.limit:
        log("осталось %d — надзиратель продолжит" % left)
        return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

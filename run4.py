#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
run4.py — аудит и починка базы задач. Один файл, устойчивый к падениям.

ЗАПУСК (то, что нужно в 99% случаев):
    python run4.py

    Сам себя перезапускает после любой смерти, идёт аудит -> фикс -> экспорт,
    прогресс никогда не теряется.

ОСТАЛЬНЫЕ РЕЖИМЫ:
    python run4.py --stage audit      только аудит
    python run4.py --stage fix        только починка
    python run4.py --stage export     только пересборка чистой базы
    python run4.py --no-supervise     без надзирателя (для отладки)
    python run4.py --status           показать состояние и выйти
    python run4.py --threads 2        переопределить число потоков

ЧТО СОЗДАЁТ РЯДОМ С БАЗОЙ:
    state_audit.jsonl        вердикты аудита (append-only, с fsync)
    state_fix.jsonl          результаты починки (append-only, с fsync)
    run4.log                 полный журнал всех запусков
    crash.log                нативные падения (faulthandler)
    *_CLEAN.jsonl            итоговая чистая база
    *_UNRESOLVED.jsonl       что починить не удалось
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
# НАСТРОЙКИ — правь только этот блок
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "FORMYLA_L1_L3_FINAL_v3.jsonl")

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")   # или впиши строкой сюда
API_BASE = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-pro"

# Доп. поля тела запроса (то, что старый скрипт проверял как "thinking: OK").
# Если провайдер не понимает — скрипт сам отключит и пойдёт дальше.
EXTRA_BODY = {"thinking": True}

THREADS = 3                  # 8 съедало память и убивало процесс. 3 — безопасно.
MAX_TOKENS = 8000            # первая попытка
MAX_TOKENS_RETRY = 20000     # попытка после finish=length, thinking выключается
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 180           # было 240 — столько ждать бессмысленно
ATTEMPTS = 4                 # попыток на один запрос
FIX_CYCLES = 5               # циклов правки на одну задачу

HEARTBEAT_SEC = 30
MEM_LIMIT_MB = 3500          # мягкий тормоз: выше — новые задачи не берём

# Имена полей в твоём JSONL. None = автоопределение по первой строке.
ID_FIELD = None
TASK_FIELD = None
ANSWER_FIELD = None

ID_CANDIDATES = ["id", "uid", "task_id", "idx", "index", "hash"]
TASK_CANDIDATES = ["task", "problem", "question", "condition", "text", "prompt"]
ANSWER_CANDIDATES = ["answer", "solution", "response", "output", "final_answer"]

# ============================================================================
# ПРОМПТЫ — вставь сюда свои формулировки из run3.py
# ============================================================================

AUDIT_SYSTEM = (
    "Ты придирчивый проверяющий математических задач. "
    "Отвечай ТОЛЬКО валидным JSON без markdown-обёрток. "
    "Будь краток в рассуждениях: главное — вердикт."
)

AUDIT_USER = """Проверь задачу и её ответ.

УСЛОВИЕ:
{task}

ОТВЕТ:
{answer}

Верни JSON строго такой формы:
{{"condition": "YES|NO|BORDERLINE", "answer_ok": "YES|NO", "problems": "что именно не так, 1-3 предложения"}}

condition: корректно ли, полно ли и однозначно ли сформулировано условие.
answer_ok: верен ли ответ по существу.
problems: пустая строка, если всё чисто."""

FIX_SYSTEM = (
    "Ты редактор базы математических задач. Исправляешь условие и/или ответ, "
    "сохраняя исходный смысл и уровень сложности. "
    "Отвечай ТОЛЬКО валидным JSON без markdown-обёрток."
)

FIX_USER = """Исправь задачу с учётом замечаний.

УСЛОВИЕ:
{task}

ОТВЕТ:
{answer}

ЗАМЕЧАНИЯ ПРОВЕРЯЮЩЕГО:
{problems}

Верни JSON строго такой формы:
{{"task": "исправленное условие", "answer": "исправленный ответ", "changes": "что поменял, кратко"}}"""

# ============================================================================
# ИНФРАСТРУКТУРА
# ============================================================================

STATE_AUDIT = os.path.join(BASE_DIR, "state_audit.jsonl")
STATE_FIX = os.path.join(BASE_DIR, "state_fix.jsonl")
LOG_PATH = os.path.join(BASE_DIR, "run4.log")
CRASH_PATH = os.path.join(BASE_DIR, "crash.log")

_log_lock = threading.Lock()
_log_fh = None
_crash_fh = None
_stop = threading.Event()


def log(msg, quiet=False):
    line = "%s | %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    with _log_lock:
        if not quiet:
            try:
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
            except Exception:
                pass
        if _log_fh:
            _log_fh.write(line + "\n")
            _log_fh.flush()


def open_log():
    global _log_fh
    _log_fh = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    _log_fh.write("\n%s ЗАПУСК pid=%s argv=%s\n" % ("=" * 30, os.getpid(), sys.argv[1:]))
    _log_fh.flush()


def enable_crash_dump():
    """Небуферизованный бинарный файл: буфер не потеряется при жёстком убийстве."""
    global _crash_fh
    _crash_fh = open(CRASH_PATH, "ab", buffering=0)
    faulthandler.enable(_crash_fh)


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
        try:
            import resource
            return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
        except Exception:
            return -1


class StateFile:
    """Append-only журнал с fsync. Убийство процесса не рвёт файл."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.fh = open(path, "a", encoding="utf-8", errors="replace")

    def add(self, obj):
        line = json.dumps(obj, ensure_ascii=False)
        with self.lock:
            self.fh.write(line + "\n")
            self.fh.flush()
            os.fsync(self.fh.fileno())

    def close(self):
        try:
            self.fh.close()
        except Exception:
            pass

    @staticmethod
    def load(path):
        """Битые хвостовые строки молча отбрасываются."""
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
    content = ((ch.get("message") or {}).get("content") or "").strip()
    return content, finish


def ask_json(messages, tag=""):
    """
    Возвращает dict или None. Лечит главную болезнь run3:
    finish=length -> повтор БЕЗ thinking и с большим лимитом.
    """
    global _thinking_ok
    tokens, thinking = MAX_TOKENS, True
    last = ""

    for attempt in range(1, ATTEMPTS + 1):
        if _stop.is_set():
            return None
        try:
            content, finish = raw_call(
                messages, tokens, thinking, CONNECT_TIMEOUT + READ_TIMEOUT)

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
            if e.code == 400 and thinking and _thinking_ok:
                _thinking_ok = False
                log("  thinking не поддержан — отключаю глобально")
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

def pick(keys, cands):
    for c in cands:
        if c in keys:
            return c
    return None


def load_db():
    global ID_FIELD, TASK_FIELD, ANSWER_FIELD
    recs = []
    with open(DB_PATH, "r", encoding="utf-8", errors="replace") as f:
        for i, raw in enumerate(f):
            raw = raw.strip()
            if not raw:
                continue
            try:
                o = json.loads(raw)
            except Exception:
                log("  строка %d не парсится — пропуск" % (i + 1))
                continue
            recs.append(o)

    if not recs:
        raise SystemExit("База пуста или не читается: %s" % DB_PATH)

    keys = set()
    for r in recs[:50]:
        keys |= set(r.keys())
    ID_FIELD = ID_FIELD or pick(keys, ID_CANDIDATES)
    TASK_FIELD = TASK_FIELD or pick(keys, TASK_CANDIDATES)
    ANSWER_FIELD = ANSWER_FIELD or pick(keys, ANSWER_CANDIDATES)

    if not TASK_FIELD or not ANSWER_FIELD:
        raise SystemExit(
            "Не нашёл поля условия/ответа. Есть: %s\n"
            "Пропиши TASK_FIELD и ANSWER_FIELD в настройках." % sorted(keys))

    log("Поля: id=%s task=%s answer=%s" % (ID_FIELD, TASK_FIELD, ANSWER_FIELD))
    for i, r in enumerate(recs):
        if ID_FIELD and r.get(ID_FIELD) is not None:
            r["__key"] = str(r.get(ID_FIELD))
        else:
            r["__key"] = "row%d" % i
    return recs


# ============================================================================
# ПУЛ ЗАДАЧ (главная защита от смерти по памяти)
# ============================================================================

def run_pool(items, worker, threads, label):
    """
    Потоки тянут из очереди. В памяти живёт максимум `threads` ответов,
    а не все 405 сразу — именно на этом умирал run3 с 8 потоками.
    """
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
                log("  ! поток %d упал на задаче: %s: %s"
                    % (wid, type(e).__name__, str(e)[:150]))
            finally:
                with lk:
                    started.pop(wid, None)
                    done[0] += 1
                    n = done[0]
                q.task_done()
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
            if done[0] < total:
                log("    ~ пульс: занято %d, самый долгий %d с, готово %d/%d, память %d МБ"
                    % (busy, longest, done[0], total, mem_mb()))

    ths = [threading.Thread(target=loop, args=(i,), daemon=True) for i in range(threads)]
    hb = threading.Thread(target=beat, daemon=True)
    hb.start()
    for t in ths:
        t.start()
    for t in ths:
        while t.is_alive():
            t.join(timeout=1.0)
    log("%s: завершено %d/%d за %.1f мин" % (label, done[0], total, (time.time() - t0) / 60))


# ============================================================================
# ЭТАП 1: АУДИТ
# ============================================================================

def norm_v(x, allowed, default):
    s = str(x or "").strip().upper()
    return s if s in allowed else default


def audit_one(rec, sf):
    msgs = [{"role": "system", "content": AUDIT_SYSTEM},
            {"role": "user", "content": AUDIT_USER.format(
                task=rec.get(TASK_FIELD, ""), answer=rec.get(ANSWER_FIELD, ""))}]
    r = ask_json(msgs, "audit " + rec["__key"])
    if r is None:
        sf.add({"key": rec["__key"], "status": "ERR"})
        return
    sf.add({
        "key": rec["__key"],
        "status": "OK",
        "condition": norm_v(r.get("condition"), {"YES", "NO", "BORDERLINE"}, "BORDERLINE"),
        "answer_ok": norm_v(r.get("answer_ok"), {"YES", "NO"}, "NO"),
        "problems": str(r.get("problems") or "")[:2000],
    })


def stage_audit(recs, threads):
    state = StateFile.load(STATE_AUDIT)
    # ERR из прошлых прогонов пробуем заново — с новой логикой токенов они пройдут
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

def is_clean(v):
    return v.get("condition") in ("YES", "BORDERLINE") and v.get("answer_ok") == "YES"


def fix_one(rec, verdict, sf):
    task = rec.get(TASK_FIELD, "")
    answer = rec.get(ANSWER_FIELD, "")
    problems = verdict.get("problems") or "ответ неверен либо условие неполно"
    trail = []

    for cycle in range(1, FIX_CYCLES + 1):
        if _stop.is_set():
            return
        fr = ask_json(
            [{"role": "system", "content": FIX_SYSTEM},
             {"role": "user", "content": FIX_USER.format(
                 task=task, answer=answer, problems=problems)}],
            "fix %s c%d" % (rec["__key"], cycle))
        if fr is None:
            break

        new_task = str(fr.get("task") or task).strip()
        new_answer = str(fr.get("answer") or answer).strip()
        trail.append(str(fr.get("changes") or "")[:300])

        ar = ask_json(
            [{"role": "system", "content": AUDIT_SYSTEM},
             {"role": "user", "content": AUDIT_USER.format(
                 task=new_task, answer=new_answer)}],
            "recheck %s c%d" % (rec["__key"], cycle))
        if ar is None:
            task, answer = new_task, new_answer
            break

        v = {"condition": norm_v(ar.get("condition"), {"YES", "NO", "BORDERLINE"}, "BORDERLINE"),
             "answer_ok": norm_v(ar.get("answer_ok"), {"YES", "NO"}, "NO")}
        task, answer = new_task, new_answer

        if is_clean(v):
            sf.add({"key": rec["__key"], "status": "FIXED", "cycles": cycle,
                    "task": task, "answer": answer, "trail": trail})
            return
        problems = str(ar.get("problems") or problems)[:2000]

    sf.add({"key": rec["__key"], "status": "UNRESOLVED", "cycles": len(trail),
            "task": task, "answer": answer, "trail": trail})


def stage_fix(recs, threads):
    audit = StateFile.load(STATE_AUDIT)
    fixed = StateFile.load(STATE_FIX)

    todo, no_verdict = [], 0
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
    log("Без вердикта   : %d  (прогони аудит ещё раз)" % no_verdict)
    log("Потоков        : %d, лимит токенов %d/%d" % (threads, MAX_TOKENS, MAX_TOKENS_RETRY))
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
    clean_path, bad_path = root + "_CLEAN.jsonl", root + "_UNRESOLVED.jsonl"

    n_clean = n_bad = n_skip = 0
    with open(clean_path, "w", encoding="utf-8") as fc, \
         open(bad_path, "w", encoding="utf-8") as fb:
        for r in recs:
            k = r["__key"]
            out = {kk: vv for kk, vv in r.items() if kk != "__key"}
            f = fixed.get(k)
            if f:
                out[TASK_FIELD] = f.get("task", out.get(TASK_FIELD))
                out[ANSWER_FIELD] = f.get("answer", out.get(ANSWER_FIELD))
                if f.get("status") == "FIXED":
                    fc.write(json.dumps(out, ensure_ascii=False) + "\n")
                    n_clean += 1
                else:
                    fb.write(json.dumps(out, ensure_ascii=False) + "\n")
                    n_bad += 1
                continue
            v = audit.get(k)
            if v and v.get("status") == "OK" and is_clean(v):
                fc.write(json.dumps(out, ensure_ascii=False) + "\n")
                n_clean += 1
            else:
                n_skip += 1

    log("=" * 64)
    log("ЭКСПОРТ")
    log("  чистых          : %d" % n_clean)
    log("  не исправлено   : %d" % n_bad)
    log("  без вердикта    : %d" % n_skip)
    log("  файл: %s" % os.path.basename(clean_path))
    log("=" * 64)


def show_status(recs):
    audit = StateFile.load(STATE_AUDIT)
    fixed = StateFile.load(STATE_FIX)
    ok = [v for v in audit.values() if v.get("status") == "OK"]
    need = [v for v in ok if not is_clean(v)]
    log("Задач в базе      : %d" % len(recs))
    log("Аудировано        : %d" % len(ok))
    log("  из них чистых   : %d" % (len(ok) - len(need)))
    log("  требуют правки  : %d" % len(need))
    log("Починка записана  : %d (успешно %d)"
        % (len(fixed), sum(1 for v in fixed.values() if v.get("status") == "FIXED")))
    log("Осталось аудита   : %d" % (len(recs) - len(ok)))


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


# ============================================================================
# НАДЗИРАТЕЛЬ
# ============================================================================

def supervise(argv):
    """Перезапускает сам себя, пока работа не будет доделана."""
    cmd = [sys.executable, "-X", "faulthandler", "-u", os.path.abspath(__file__),
           "--no-supervise"] + argv
    for run in range(1, 61):
        log(">>> надзиратель: запуск %d" % run)
        t0 = time.time()
        rc = subprocess.call(cmd, cwd=BASE_DIR)
        el = (time.time() - t0) / 60
        log(">>> надзиратель: выход код=%s, работал %.1f мин" % (rc, el))
        if rc == 0:
            log(">>> ГОТОВО, работа доделана")
            return 0
        if rc in (2, 130):
            log(">>> остановлено пользователем")
            return rc
        if el < 0.2:
            log(">>> падает мгновенно — дальше смысла нет, смотри run4.log")
            return rc
        log(">>> пауза 10 с и продолжаем с того же места")
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
        log("получен сигнал %s — доводим текущие запросы и выходим" % sig)
        _stop.set()

    signal.signal(signal.SIGINT, on_sig)
    try:
        signal.signal(signal.SIGTERM, on_sig)
    except Exception:
        pass

    if not a.no_supervise and not a.status and a.stage in ("all", "audit", "fix"):
        raw = [x for x in sys.argv[1:] if x != "--no-supervise"]
        return supervise(raw)

    if not API_KEY:
        raise SystemExit("Нет API-ключа. Задай DEEPSEEK_API_KEY или впиши в настройки.")

    log("run4 | %s | потоков %d | токены %d/%d"
        % (MODEL, a.threads, MAX_TOKENS, MAX_TOKENS_RETRY))
    log("База: %s" % DB_PATH)
    recs = load_db()

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
        left_audit, left_fix = count_left(recs)
        if left_audit or left_fix:
            log("не доделано: аудит %d, фикс %d — надзиратель продолжит"
                % (left_audit, left_fix))
            return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

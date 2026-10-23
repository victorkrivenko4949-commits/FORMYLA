#!/usr/bin/env python3
"""
FORMYLA: аудит + фикс базы задач. Версия против зависаний.

ЗАПУСК:
    python -u run3.py            # аудит, затем фикс
    python -u run3.py audit
    python -u run3.py fix
    python -u run3.py stats
    python -u run3.py test

ЧТО ИЗМЕНЕНО ПРОТИВ run2.py:
- таймаут разбит на connect=15 с и read=240 с вместо общих 1200 с,
  зависший поток отваливается через 4 минуты, а не через 20;
- keep-alive отключён: каждое соединение новое, оборванные сессии
  из пула больше не используются;
- у каждого потока своя requests.Session;
- пульс раз в 30 секунд: видно, сколько потоков в работе и сколько
  секунд висит самый долгий запрос;
- max_tokens снижен до 16000, ответу аудита столько не нужно;
- прогресс печатается каждые 2 задачи, а не каждые 10.
"""

import os
import sys
import json
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== НАСТРОЙКИ ====================

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = "https://api.deepseek.com/chat/completions"
MODEL_NAME = "deepseek-v4-pro"
FALLBACK_MODEL = "deepseek-v4-flash"

BASE_DIR = r"C:\Users\Redmi\Desktop\Новая папка (2)"
IN_DB = os.path.join(BASE_DIR, "FORMYLA_L1_L3_FINAL_v3.jsonl")
OUT_DB = os.path.join(BASE_DIR, "FORMYLA_L1_L3_FINAL_v4.jsonl")
AUDIT_FILE = os.path.join(BASE_DIR, "audit_output.jsonl")
FIX_REPORT = os.path.join(BASE_DIR, "fix_report.jsonl")
RAW_LOG = os.path.join(BASE_DIR, "audit_raw.log")

WORKERS = 8
MAX_TOKENS = 16000
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 240
MAX_RETRIES = 4
FIX_CYCLES = 5
AUDIT_LIMIT = 0
FIX_LIMIT = 0
SHOW_FIRST_ERRORS = 3
HEARTBEAT_SEC = 30

CAP = {"thinking": True, "json_mode": True, "model": MODEL_NAME}

# ==================== ПРОМТЫ ====================

AUDIT_PROMPT = """Ты — математический эксперт и аудитор олимпиадных задач.

ЦЕЛЬ: определить, корректно ли УСЛОВИЕ задачи, и отдельно — верны ли ответ и решение.

УСЛОВИЕ НЕКОРРЕКТНО, если выполнено хотя бы одно:
- задача невыполнима: нет решения при естественной школьной интерпретации;
- задача неоднозначна: несколько прочтений дают разные ответы;
- в условии логическое противоречие;
- техническая ошибка в данных (числа, знак, коэффициент, диапазон, пропущен параметр);
- используются неопределённые объекты (нет обозначений, ссылка на отсутствующий рисунок).

ПРАВИЛА:
1. Решай задачу ЗАНОВО сам. Не доверяй полям answer и solution.
2. Если условие корректно, а неверен ответ или решение — условие считай корректным.
3. Рассуждай экономно, без длинных переборов.
4. Значения полей писать ЗАГЛАВНЫМИ: YES, NO, BORDERLINE, UNKNOWN.
5. Ответ — только json, без текста вокруг.

ФОРМАТ:
{"results": [{
  "task_uid": "...",
  "condition_correct": "YES|NO|BORDERLINE",
  "answer_correct": "YES|NO|UNKNOWN",
  "solution_correct": "YES|NO|UNKNOWN",
  "defects": ["дефекты"],
  "reason_condition": "1-2 предложения",
  "re_solved_answer": "твой ответ или UNSOLVABLE"
}]}
"""

FIX_CONDITION_PROMPT = """Ты — методист-составитель олимпиадных задач.

Дана задача с НЕКОРРЕКТНЫМ УСЛОВИЕМ и перечень дефектов.
Старое решение недействительно и отбрасывается.

РАБОТА:
1. Исправь УСЛОВИЕ минимальной правкой так, чтобы задача стала корректной,
   однозначной и имела решение.
2. Напиши НОВОЕ полное решение и ответ к исправленному условию.

ЖЁСТКИЕ ОГРАНИЧЕНИЯ:
- СЛОЖНОСТЬ НЕ МЕНЯЕТСЯ. Класс, уровень, тема, требуемые методы те же.
- Тип задачи и сюжет сохраняются. Не придумывай другую задачу.
- Правка минимальная: число, знак, слово, уточняющая фраза.
- Решение полное, по шагам, для школьника указанного класса.
- Ответ — только json, ровно один объект.

ФОРМАТ:
{"statement": "исправленное условие",
 "answer": "ответ",
 "solution": "полное решение по шагам",
 "what_changed": "что именно изменено в условии"}
"""

FIX_BORDERLINE_PROMPT = """Ты — методист-составитель олимпиадных задач.

Условие формально решаемо, но СОДЕРЖИТ ДВУСМЫСЛЕННОСТЬ.
Даны условие, текущее решение и описание проблемы.

РАБОТА:
1. Убери двусмысленность из УСЛОВИЯ минимальной уточняющей правкой.
2. Приведи решение и ответ в соответствие с уточнённым условием.

ЖЁСТКИЕ ОГРАНИЧЕНИЯ:
- СЛОЖНОСТЬ НЕ МЕНЯЕТСЯ. Класс, уровень, тема те же.
- Сюжет и числа сохраняются, если не были источником двусмысленности.
- Ответ — только json, ровно один объект.

ФОРМАТ:
{"statement": "уточнённое условие",
 "answer": "ответ",
 "solution": "решение по шагам",
 "what_changed": "какая двусмысленность устранена"}
"""

FIX_SOLUTION_PROMPT = """Ты — математический эксперт.

УСЛОВИЕ корректно, МЕНЯТЬ ЕГО КАТЕГОРИЧЕСКИ НЕЛЬЗЯ.
Неверны ответ и/или решение. Реши задачу заново с нуля.

ЖЁСТКИЕ ОГРАНИЧЕНИЯ:
- Условие возвращай СЛОВО В СЛОВО без изменений.
- Решение полное, по шагам, на уровне указанного класса.
- Ответ — только json, ровно один объект.

ФОРМАТ:
{"statement": "условие слово в слово как дано",
 "answer": "правильный ответ",
 "solution": "полное решение по шагам",
 "what_changed": "переписано решение и ответ"}
"""

VERIFY_PROMPT = """Ты — независимый проверяющий. Ты НЕ видел, как задачу составляли.

Даны условие, ответ и решение. Проверь:
1. Условие корректно и однозначно.
2. Решение математически верно, без пропусков и ложных шагов.
3. Ответ соответствует условию и следует из решения.
4. Задача посильна для указанного класса и уровня.

Реши задачу самостоятельно и сравни с предложенным ответом.
Не придирайся к стилю и оформлению: важна только математическая правильность
и однозначность условия.

ФОРМАТ (только json, ровно один объект, ключ verdict обязателен):
{"verdict": "CORRECT" | "INCORRECT",
 "my_answer": "твой независимый ответ",
 "problems": ["что именно не так, если INCORRECT"]}
"""

# ==================== СЕРВИС ====================

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

KEY = DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY")
WRITE_LOCK = threading.Lock()
ERR_LOCK = threading.Lock()
_errors_shown = [0]

_local = threading.local()
INFLIGHT = {}
INFLIGHT_LOCK = threading.Lock()


def session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"Connection": "close"})
        _local.s = s
    return s


def show_error(where, msg):
    with ERR_LOCK:
        if _errors_shown[0] < SHOW_FIRST_ERRORS:
            _errors_shown[0] += 1
            print(f"\n!!! ОШИБКА [{where}]:\n{str(msg)[:900]}\n", flush=True)


def log_raw(text):
    with WRITE_LOCK:
        with open(RAW_LOG, "a", encoding="utf-8") as f:
            f.write(text + "\n" + "-" * 70 + "\n")


def uid_of(t):
    return t.get("task_uid") or t.get("taskuid") or t.get("uid")


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def append_jsonl(path, rec):
    with WRITE_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def norm(v):
    return str(v).strip().upper() if v is not None else ""


def build_payload(messages, thinking, json_mode, model):
    p = {"model": model, "messages": messages, "max_tokens": MAX_TOKENS}
    if json_mode:
        p["response_format"] = {"type": "json_object"}
    if thinking:
        p["thinking"] = {"type": "enabled"}
        p["reasoning_effort"] = "high"
    return p


def raw_call(messages, thinking, json_mode, model):
    headers = {"Authorization": f"Bearer {KEY}",
               "Content-Type": "application/json",
               "Connection": "close"}
    payload = build_payload(messages, thinking, json_mode, model)
    tid = threading.get_ident()
    with INFLIGHT_LOCK:
        INFLIGHT[tid] = time.time()
    try:
        return session().post(API_URL, headers=headers, json=payload,
                              timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    finally:
        with INFLIGHT_LOCK:
            INFLIGHT.pop(tid, None)


# ==================== ПУЛЬС ====================

class Heartbeat(threading.Thread):
    def __init__(self, prog):
        super().__init__(daemon=True)
        self.prog = prog
        self.stop = threading.Event()

    def run(self):
        while not self.stop.wait(HEARTBEAT_SEC):
            with INFLIGHT_LOCK:
                ages = [time.time() - t for t in INFLIGHT.values()]
            n = len(ages)
            oldest = int(max(ages)) if ages else 0
            print(f"    ~ пульс: в работе {n} запросов, самый долгий {oldest} с, "
                  f"готово {self.prog.done}/{self.prog.total}", flush=True)


# ==================== САМОПРОВЕРКА ====================

def api_selftest():
    probe = [{"role": "user", "content": 'Ответь json: {"ok": 1}'}]
    print("Проверка API...", flush=True)

    if not KEY:
        sys.exit("Ключ не задан. Выполни: $env:DEEPSEEK_API_KEY = \"sk-...\"")

    try:
        r = raw_call(probe, False, False, MODEL_NAME)
        if r.status_code >= 400:
            print(f"  {MODEL_NAME}: HTTP {r.status_code}\n  {r.text[:400]}")
            if r.status_code in (401, 402, 403):
                sys.exit("Проблема с ключом или балансом.")
            r2 = raw_call(probe, False, False, FALLBACK_MODEL)
            if r2.status_code < 400:
                CAP["model"] = FALLBACK_MODEL
                print(f"  переключаюсь на {FALLBACK_MODEL}")
            else:
                sys.exit(f"{FALLBACK_MODEL}: HTTP {r2.status_code} {r2.text[:300]}")
        else:
            print(f"  {MODEL_NAME}: OK")
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"Нет связи с API: {e}")

    m = CAP["model"]
    r = raw_call(probe, False, True, m)
    CAP["json_mode"] = r.status_code < 400
    print(f"  response_format: {'OK' if CAP['json_mode'] else 'нет'}")

    r = raw_call(probe, True, CAP["json_mode"], m)
    CAP["thinking"] = r.status_code < 400
    print(f"  thinking: {'OK' if CAP['thinking'] else 'нет'}")

    print(f"Итог: {CAP['model']}, thinking={CAP['thinking']}, "
          f"json={CAP['json_mode']}, потоков={WORKERS}, "
          f"таймаут {CONNECT_TIMEOUT}/{READ_TIMEOUT} с\n", flush=True)


# ==================== ЗАПРОС ====================

def request_once(messages, thinking):
    r = raw_call(messages, thinking and CAP["thinking"], CAP["json_mode"],
                 CAP["model"])
    if r.status_code == 429:
        log_raw("HTTP 429")
        time.sleep(15)
        raise RuntimeError("429 rate limit")
    if r.status_code >= 400:
        txt = r.text[:600]
        log_raw(f"HTTP {r.status_code}\n{txt}")
        raise RuntimeError(f"HTTP {r.status_code}: {txt}")

    data = r.json()
    ch = data["choices"][0]
    content = (ch["message"].get("content") or "").strip()
    log_raw(f"finish={ch.get('finish_reason')} usage={data.get('usage')}\n"
            f"{content[:600]}")
    return content, ch.get("finish_reason")


def parse_json(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        p = raw.split("```")
        raw = p[1] if len(p) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        for a, b in (("{", "}"), ("[", "]")):
            s, e = raw.find(a), raw.rfind(b)
            if s != -1 and e != -1:
                try:
                    return json.loads(raw[s:e + 1])
                except json.JSONDecodeError:
                    continue
        raise


def as_obj(x):
    if isinstance(x, dict):
        if any(k in x for k in ("statement", "verdict", "answer", "solution")):
            return x
        for k in ("results", "result", "data", "items", "tasks"):
            v = x.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v[0]
            if isinstance(v, dict):
                return v
        return x
    if isinstance(x, list) and x and isinstance(x[0], dict):
        return x[0]
    raise ValueError("не объект")


def as_list(x):
    if isinstance(x, list):
        return [i for i in x if isinstance(i, dict)]
    if isinstance(x, dict):
        for k in ("results", "data", "items", "tasks", "audit"):
            v = x.get(k)
            if isinstance(v, list):
                return [i for i in v if isinstance(i, dict)]
        return [x]
    raise ValueError("непонятный формат")


def read_verdict(check):
    for k in ("verdict", "result", "status", "conclusion", "is_correct", "correct"):
        if k in check:
            v = check[k]
            if isinstance(v, bool):
                return "CORRECT" if v else "INCORRECT"
            v = norm(v)
            if v in ("CORRECT", "OK", "YES", "TRUE", "PASS", "APPROVE"):
                return "CORRECT"
            if v in ("INCORRECT", "NO", "FALSE", "FAIL", "REJECT", "BAD"):
                return "INCORRECT"
            if v:
                return v
    return ""


def ask(system, user, where="api"):
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": user}]
    err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            content, finish = request_once(msgs, thinking=True)
            if not content and finish == "length":
                content, finish = request_once(msgs, thinking=False)
            if not content:
                raise ValueError(f"пустой ответ, finish={finish}")
            return parse_json(content)
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as e:
            err = e
            show_error(where + "/сеть", e)
            _local.s = None
            time.sleep(4 * attempt)
        except Exception as e:
            err = e
            show_error(where, e)
            time.sleep(3 * attempt)
    raise RuntimeError(str(err))


def fmt_time(sec):
    h, m = divmod(int(sec) // 60, 60)
    return f"{h} ч {m} мин" if h else f"{m} мин"


def task_context(t):
    return (f"Класс: {t.get('grade')}\n"
            f"Уровень: {t.get('level')} ({t.get('level_name', '')})\n"
            f"Раздел: {t.get('section')}\n"
            f"Тема: {t.get('theme')}\n")


def audit_one(t):
    payload = {
        "task_uid": uid_of(t),
        "grade": t.get("grade"),
        "level": t.get("level"),
        "section": t.get("section"),
        "theme": t.get("theme"),
        "statement": t.get("statement"),
        "answer": t.get("answer"),
        "solution": t.get("solution"),
    }
    user = "Задача в формате json. Проверь её.\n\n" + json.dumps(
        [payload], ensure_ascii=False)
    recs = as_list(ask(AUDIT_PROMPT, user, where="audit"))
    r = recs[0] if recs else {}
    r.setdefault("task_uid", uid_of(t))
    for f in ("condition_correct", "answer_correct", "solution_correct"):
        r[f] = norm(r.get(f)) or "UNKNOWN"
    r["grade"] = t.get("grade")
    r["level"] = t.get("level")
    r["section"] = t.get("section")
    return r


class Progress:
    def __init__(self, total, label, step=2):
        self.total, self.label, self.step = total, label, step
        self.done = 0
        self.started = time.time()
        self.lock = threading.Lock()
        self.stat = {}

    def tick(self, key=None):
        with self.lock:
            self.done += 1
            if key:
                self.stat[key] = self.stat.get(key, 0) + 1
            n = self.done
            if n % self.step == 0 or n == self.total:
                el = time.time() - self.started
                eta = el / n * (self.total - n)
                s = " ".join(f"{k}:{v}" for k, v in sorted(self.stat.items()))
                print(f"[{self.label} {n}/{self.total} {100*n/self.total:.1f}%] "
                      f"осталось ~{fmt_time(eta)} | {s}", flush=True)

    def all_failed(self):
        return self.done >= 20 and self.stat.get("ERR", 0) == self.done


# ==================== АУДИТ ====================

def stage_audit():
    db = read_jsonl(IN_DB)
    if not db:
        sys.exit(f"Пустая база: {IN_DB}")

    done = {uid_of(r) for r in read_jsonl(AUDIT_FILE) if not r.get("error")}
    todo = [t for t in db if uid_of(t) not in done]
    if AUDIT_LIMIT:
        todo = todo[:AUDIT_LIMIT]

    print("=" * 64)
    print("ЭТАП 1: АУДИТ")
    print(f"Всего в базе : {len(db)}")
    print(f"Уже проверено: {len(done)}")
    print(f"К работе     : {len(todo)}")
    print("=" * 64, flush=True)

    if not todo:
        print("Аудит уже завершён.\n")
        return

    prog = Progress(len(todo), "audit")
    hb = Heartbeat(prog)
    hb.start()
    stop = threading.Event()

    def work(t):
        if stop.is_set():
            return
        try:
            r = audit_one(t)
            append_jsonl(AUDIT_FILE, r)
            prog.tick(r["condition_correct"])
        except Exception as e:
            append_jsonl(AUDIT_FILE, {"task_uid": uid_of(t), "error": str(e)})
            prog.tick("ERR")
            if prog.all_failed():
                stop.set()

    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(as_completed([ex.submit(work, t) for t in todo]))
    finally:
        hb.stop.set()

    if stop.is_set():
        print("\nВСЕ ЗАПРОСЫ ПАДАЮТ. Смотри ошибку выше и audit_raw.log.")
        return

    print(f"\nАудит за {fmt_time(time.time() - prog.started)} | {prog.stat}\n")


# ==================== ФИКС ====================

def build_fix_request(t, v, feedback=None):
    ctx = task_context(t)
    cc = norm(v.get("condition_correct")) or "YES"

    if cc == "NO":
        system = FIX_CONDITION_PROMPT
        body = (f"{ctx}\nУСЛОВИЕ (некорректное):\n{t.get('statement')}\n\n"
                f"ДЕФЕКТЫ: {json.dumps(v.get('defects', []), ensure_ascii=False)}\n"
                f"ПОЯСНЕНИЕ: {v.get('reason_condition', '')}\n\n"
                f"Старое решение отброшено.")
    elif cc == "BORDERLINE":
        system = FIX_BORDERLINE_PROMPT
        body = (f"{ctx}\nУСЛОВИЕ (двусмысленное):\n{t.get('statement')}\n\n"
                f"ТЕКУЩЕЕ РЕШЕНИЕ:\n{t.get('solution')}\n\n"
                f"ТЕКУЩИЙ ОТВЕТ: {t.get('answer')}\n\n"
                f"ПРОБЛЕМА: {v.get('reason_condition', '')}\n"
                f"ДЕФЕКТЫ: {json.dumps(v.get('defects', []), ensure_ascii=False)}")
    else:
        system = FIX_SOLUTION_PROMPT
        body = (f"{ctx}\nУСЛОВИЕ (менять нельзя):\n{t.get('statement')}\n\n"
                f"ОШИБОЧНЫЙ ОТВЕТ В БАЗЕ: {t.get('answer')}\n"
                f"ЗАМЕЧАНИЯ: {json.dumps(v.get('defects', []), ensure_ascii=False)}\n"
                f"ОТВЕТ НЕЗАВИСИМОГО РЕШЕНИЯ: {v.get('re_solved_answer', '')}")

    if feedback:
        body += ("\n\nПРЕДЫДУЩАЯ ПОПЫТКА ОТКЛОНЕНА.\n"
                 f"Замечания: {json.dumps(feedback, ensure_ascii=False)}\n"
                 "Учти их и сделай заново.")
    return system, body


def verify(t, cand):
    user = (f"{task_context(t)}\nУСЛОВИЕ:\n{cand.get('statement')}\n\n"
            f"ОТВЕТ: {cand.get('answer')}\n\nРЕШЕНИЕ:\n{cand.get('solution')}")
    return as_obj(ask(VERIFY_PROMPT, user, where="verify"))


def needs_fix(v):
    if not v:
        return False
    return (norm(v.get("condition_correct")) in ("NO", "BORDERLINE")
            or norm(v.get("answer_correct")) == "NO"
            or norm(v.get("solution_correct")) == "NO")


def fix_one(t, v):
    cc = norm(v.get("condition_correct")) or "YES"
    mode = {"NO": "переделка условия",
            "BORDERLINE": "снятие двусмысленности"}.get(cc, "переделка решения")
    history, ok, cand, feedback = [], False, None, None

    for cycle in range(1, FIX_CYCLES + 1):
        try:
            system, body = build_fix_request(t, v, feedback)
            cand = as_obj(ask(system, body, where="fix"))

            if cc not in ("NO", "BORDERLINE"):
                orig = t.get("statement")
                if not str(orig).strip():
                    raise ValueError("пустое statement в базе")
                cand["statement"] = orig

            for f in ("statement", "answer", "solution"):
                if not str(cand.get(f, "")).strip():
                    raise ValueError(f"пустое поле {f}")

            check = verify(t, cand)
            verdict = read_verdict(check)
            history.append({
                "cycle": cycle, "verdict": verdict,
                "my_answer": check.get("my_answer"),
                "problems": check.get("problems", []),
                "what_changed": cand.get("what_changed"),
            })
            if verdict == "CORRECT":
                ok = True
                break
            feedback = check.get("problems") or ["ответ не подтверждён"]
        except Exception as e:
            history.append({"cycle": cycle, "error": str(e)})
            feedback = [f"техническая ошибка: {e}"]
            time.sleep(2)

    out = dict(t)
    if ok and cand:
        out["statement"] = cand["statement"]
        out["answer"] = cand["answer"]
        out["solution"] = cand["solution"]
        out["_fix_status"] = "fixed"
    else:
        out["_fix_status"] = "fix_failed"
        if cand:
            out["_fix_candidate"] = cand
    out["_fix_mode"] = mode
    out["_fix_history"] = history
    out["_audit_verdict"] = v

    append_jsonl(FIX_REPORT, {
        "task_uid": uid_of(t), "mode": mode, "status": out["_fix_status"],
        "cycles_used": len(history),
        "old_statement": t.get("statement"), "new_statement": out.get("statement"),
        "old_answer": t.get("answer"), "new_answer": out.get("answer"),
        "history": history,
    })
    return out, out["_fix_status"]


def stage_fix():
    db = read_jsonl(IN_DB)
    verdicts = {}
    for r in read_jsonl(AUDIT_FILE):
        u = uid_of(r)
        if u and not r.get("error"):
            verdicts[u] = r

    already = {uid_of(r) for r in read_jsonl(OUT_DB)}
    todo = [t for t in db if uid_of(t) not in already]
    if FIX_LIMIT:
        todo = todo[:FIX_LIMIT]

    clean, broken, orphan = [], [], []
    for t in todo:
        v = verdicts.get(uid_of(t))
        if not v:
            orphan.append(t)
        elif needs_fix(v):
            broken.append(t)
        else:
            clean.append(t)

    print("=" * 64)
    print("ЭТАП 2: ФИКС")
    print(f"К обработке     : {len(todo)}")
    print(f"  чистых        : {len(clean)}")
    print(f"  требуют правки: {len(broken)}")
    print(f"  без вердикта  : {len(orphan)}")
    print("=" * 64, flush=True)

    if not todo:
        print("Фикс уже завершён.")
        return

    started = time.time()

    for t in clean:
        out = dict(t)
        out["_fix_status"] = "clean"
        out["_audit_verdict"] = verdicts.get(uid_of(t))
        append_jsonl(OUT_DB, out)
    print(f"Скопировано без изменений: {len(clean)}", flush=True)

    if orphan:
        print(f"Аудирую {len(orphan)} задач без вердикта...")
        p0 = Progress(len(orphan), "reaudit")
        hb0 = Heartbeat(p0)
        hb0.start()

        def reaudit(t):
            try:
                v = audit_one(t)
                append_jsonl(AUDIT_FILE, v)
                p0.tick(v["condition_correct"])
                return t, v
            except Exception:
                p0.tick("ERR")
                return t, None

        try:
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                for fut in as_completed([ex.submit(reaudit, t) for t in orphan]):
                    t, v = fut.result()
                    if v is None:
                        o = dict(t)
                        o["_fix_status"] = "audit_failed"
                        append_jsonl(OUT_DB, o)
                    elif needs_fix(v):
                        verdicts[uid_of(t)] = v
                        broken.append(t)
                    else:
                        o = dict(t)
                        o["_fix_status"] = "clean"
                        o["_audit_verdict"] = v
                        append_jsonl(OUT_DB, o)
        finally:
            hb0.stop.set()

    if not broken:
        print("Чинить нечего.")
        return

    print(f"\nЧиню {len(broken)} задач, до {FIX_CYCLES} циклов каждая...",
          flush=True)
    prog = Progress(len(broken), "fix", step=1)
    hb = Heartbeat(prog)
    hb.start()

    def work(t):
        try:
            out, status = fix_one(t, verdicts[uid_of(t)])
            append_jsonl(OUT_DB, out)
            prog.tick(status)
        except Exception as e:
            o = dict(t)
            o["_fix_status"] = "fix_error"
            o["_fix_error"] = str(e)
            append_jsonl(OUT_DB, o)
            prog.tick("fix_error")

    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(as_completed([ex.submit(work, t) for t in broken]))
    finally:
        hb.stop.set()

    print("\n" + "=" * 64)
    print("ФИКС ЗАВЕРШЁН")
    print(f"Без изменений : {len(clean)}")
    print(f"Результаты    : {prog.stat}")
    print(f"Время         : {fmt_time(time.time() - started)}")
    print(f"База    : {OUT_DB}")
    print(f"Протокол: {FIX_REPORT}")
    print("=" * 64)


# ==================== СТАТИСТИКА ====================

def stage_stats():
    db = read_jsonl(IN_DB)
    aud = read_jsonl(AUDIT_FILE)
    out = read_jsonl(OUT_DB)

    ok = [r for r in aud if not r.get("error")]
    uniq = {uid_of(r) for r in ok if uid_of(r)}
    cnt = {}
    for r in ok:
        k = norm(r.get("condition_correct"))
        cnt[k] = cnt.get(k, 0) + 1
    ans_no = sum(1 for r in ok if norm(r.get("answer_correct")) == "NO")

    print("=" * 64)
    print("СТАТИСТИКА")
    print(f"Задач в базе : {len(db)}")
    print(f"Аудировано   : {len(uniq)} уникальных "
          f"(строк с ошибкой {len(aud) - len(ok)})")
    for k in ("YES", "NO", "BORDERLINE", "UNKNOWN"):
        if cnt.get(k):
            print(f"  условие {k:<11}: {cnt[k]}")
    print(f"  ответ NO         : {ans_no}")
    if out:
        st = {}
        for r in out:
            k = r.get("_fix_status", "?")
            st[k] = st.get(k, 0) + 1
        print(f"\nВ итоговой базе: {len(out)}")
        for k, v in sorted(st.items()):
            print(f"  {k:<18}: {v}")
    print("=" * 64)


def main():
    what = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    print(f"run3 | модель {MODEL_NAME} | потоков {WORKERS} | "
          f"max_tokens {MAX_TOKENS}")
    print(f"База: {IN_DB}\n", flush=True)

    if not os.path.exists(IN_DB):
        sys.exit(f"НЕ НАЙДЕНА БАЗА:\n  {IN_DB}")

    if what == "stats":
        stage_stats()
        return

    api_selftest()

    if what == "test":
        print("Самопроверка пройдена.")
        return

    if what in ("all", "audit"):
        stage_audit()
    if what in ("all", "fix"):
        stage_fix()
    stage_stats()
    print("\nГОТОВО.")


if __name__ == "__main__":
    main()

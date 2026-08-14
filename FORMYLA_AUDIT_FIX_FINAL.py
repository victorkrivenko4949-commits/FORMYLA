#!/usr/bin/env python3
"""
FORMYLA: аудит + автоматический фикс базы задач. DeepSeek V4 Pro.

ЗАПУСК:
    python -u FORMYLA_AUDIT_FIX_FINAL.py            # аудит, затем фикс
    python -u FORMYLA_AUDIT_FIX_FINAL.py audit      # только аудит
    python -u FORMYLA_AUDIT_FIX_FINAL.py fix        # только фикс
    python -u FORMYLA_AUDIT_FIX_FINAL.py stats      # сводка без запросов к API

ЛОГИКА ФИКСА:
  условие NO         -> решение отброшено, условие правится минимально,
                        генерируется новое решение, затем независимая проверка
  условие BORDERLINE -> условие и решение идут вместе, снимается двусмысленность
  условие YES, но ответ/решение NO -> условие неприкосновенно, переписывается решение
  всё YES            -> запись копируется без изменений

До 5 попыток на задачу, замечания проверяющего идут в следующую попытку.
СЛОЖНОСТЬ НЕ МЕНЯЕТСЯ НИКОГДА.

ФАЙЛЫ НА ВЫХОДЕ:
  FORMYLA_L1_L3_FINAL_v4.jsonl  итоговая база, поле _fix_status у каждой записи
  fix_report.jsonl              протокол правок: было/стало и история циклов
  audit_output.jsonl            вердикты аудита (resume)
  audit_raw.log                 сырые ответы API
"""

import os
import sys
import json
import time
import requests

# ==================== НАСТРОЙКИ ====================

DEEPSEEK_API_KEY = "sk-ad477f779a1045cba3cc09100e908370"

API_URL = "https://api.deepseek.com/chat/completions"
MODEL_NAME = "deepseek-v4-pro"

BASE_DIR = r"C:\Users\Redmi\Desktop\Новая папка (2)"
IN_DB = os.path.join(BASE_DIR, "FORMYLA_L1_L3_FINAL_v3.jsonl")
OUT_DB = os.path.join(BASE_DIR, "FORMYLA_L1_L3_FINAL_v4.jsonl")
AUDIT_FILE = os.path.join(BASE_DIR, "audit_output.jsonl")
FIX_REPORT = os.path.join(BASE_DIR, "fix_report.jsonl")
RAW_LOG = os.path.join(BASE_DIR, "audit_raw.log")

MAX_TOKENS = 64000       # у V4 Pro лимит вывода 384000
TIMEOUT = 1200
MAX_RETRIES = 3          # сетевые повторы одного запроса
FIX_CYCLES = 5           # циклы починки одной задачи
PAUSE = 0.7              # пауза между задачами, сек
AUDIT_LIMIT = 0          # 0 = все
FIX_LIMIT = 0            # 0 = все

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
5. Ответ — только json.

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
   Если решение верное, сохрани его логику, поправив формулировки.

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

KEY = os.getenv("DEEPSEEK_API_KEY") or DEEPSEEK_API_KEY


def log_raw(text):
    with open(RAW_LOG, "a", encoding="utf-8") as f:
        f.write(text + "\n" + "-" * 70 + "\n")


def uid_of(t):
    return t.get("task_uid") or t.get("taskuid") or t.get("uid")


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
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
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()


def norm(val):
    return str(val).strip().upper() if val is not None else ""


def request_once(messages, thinking):
    headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled" if thinking else "disabled"},
    }
    if thinking:
        payload["reasoning_effort"] = "high"

    r = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
    if r.status_code == 429:
        log_raw("HTTP 429 rate limit")
        time.sleep(15)
        r.raise_for_status()
    if r.status_code >= 400:
        log_raw(f"HTTP {r.status_code}\n{r.text[:1500]}")
        r.raise_for_status()

    data = r.json()
    ch = data["choices"][0]
    content = (ch["message"].get("content") or "").strip()
    log_raw(f"think={thinking} finish={ch.get('finish_reason')} "
            f"usage={data.get('usage')}\n{content[:1200]}")
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
    raise ValueError(f"не объект: {type(x).__name__}")


def as_list(x):
    if isinstance(x, list):
        return [i for i in x if isinstance(i, dict)]
    if isinstance(x, dict):
        for k in ("results", "data", "items", "tasks", "audit"):
            v = x.get(k)
            if isinstance(v, list):
                return [i for i in v if isinstance(i, dict)]
        return [x]
    raise ValueError("непонятный формат ответа аудита")


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


def ask(system, user):
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": user}]
    err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            content, finish = request_once(msgs, thinking=True)
            if not content and finish == "length":
                print("      лимит съеден размышлениями -> без thinking", flush=True)
                content, finish = request_once(msgs, thinking=False)
            if not content:
                raise ValueError(f"пустой ответ, finish={finish}")
            return parse_json(content)
        except Exception as e:
            err = e
            print(f"      [retry {attempt}/{MAX_RETRIES}] {e}", file=sys.stderr, flush=True)
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
    user = "Задача в формате json. Проверь её.\n\n" + json.dumps([payload], ensure_ascii=False)
    recs = as_list(ask(AUDIT_PROMPT, user))
    r = recs[0] if recs else {}
    r.setdefault("task_uid", uid_of(t))
    for f in ("condition_correct", "answer_correct", "solution_correct"):
        r[f] = norm(r.get(f)) or "UNKNOWN"
    r["grade"] = t.get("grade")
    r["level"] = t.get("level")
    r["section"] = t.get("section")
    return r


# ==================== ЭТАП 1: АУДИТ ====================

def stage_audit():
    db = read_jsonl(IN_DB)
    if not db:
        sys.exit(f"Пустая или отсутствующая база: {IN_DB}")

    done = {uid_of(r) for r in read_jsonl(AUDIT_FILE) if not r.get("error")}
    todo = [t for t in db if uid_of(t) not in done]
    if AUDIT_LIMIT:
        todo = todo[:AUDIT_LIMIT]

    print("=" * 64)
    print("ЭТАП 1: АУДИТ")
    print(f"Всего в базе : {len(db)}")
    print(f"Уже проверено: {len(done)}")
    print(f"К работе     : {len(todo)}")
    print("=" * 64)

    if not todo:
        print("Аудит уже завершён.\n")
        return

    started = time.time()
    stat = {"NO": 0, "BORDERLINE": 0, "YES": 0, "err": 0}

    for i, t in enumerate(todo, 1):
        eta = (time.time() - started) / max(i - 1, 1) * (len(todo) - i + 1) if i > 1 else 0
        print(f"[audit {i}/{len(todo)}] {uid_of(t)}"
              + (f" | ~{fmt_time(eta)}" if eta else ""), flush=True)
        try:
            r = audit_one(t)
            stat[r["condition_correct"]] = stat.get(r["condition_correct"], 0) + 1
            append_jsonl(AUDIT_FILE, r)
        except Exception as e:
            stat["err"] += 1
            append_jsonl(AUDIT_FILE, {"task_uid": uid_of(t), "error": str(e)})

        if i % 25 == 0:
            print(f"    условий NO: {stat['NO']}, спорных: {stat['BORDERLINE']}, "
                  f"ошибок: {stat['err']}", flush=True)
        time.sleep(PAUSE)

    print(f"\nАудит завершён за {fmt_time(time.time() - started)}")
    print(f"NO: {stat['NO']} | BORDERLINE: {stat['BORDERLINE']} | "
          f"YES: {stat['YES']} | ошибок: {stat['err']}\n")


# ==================== ЭТАП 2: ФИКС ====================

def build_fix_request(t, v, feedback=None):
    ctx = task_context(t)
    cc = norm(v.get("condition_correct")) or "YES"

    if cc == "NO":
        system = FIX_CONDITION_PROMPT
        body = (f"{ctx}\nУСЛОВИЕ (некорректное):\n{t.get('statement')}\n\n"
                f"ДЕФЕКТЫ: {json.dumps(v.get('defects', []), ensure_ascii=False)}\n"
                f"ПОЯСНЕНИЕ: {v.get('reason_condition', '')}\n\n"
                f"Старое решение отброшено, не опирайся на него.")
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
                f"ЗАМЕЧАНИЯ АУДИТА: {json.dumps(v.get('defects', []), ensure_ascii=False)}\n"
                f"ОТВЕТ НЕЗАВИСИМОГО РЕШЕНИЯ: {v.get('re_solved_answer', '')}")

    if feedback:
        body += ("\n\nПРЕДЫДУЩАЯ ПОПЫТКА ОТКЛОНЕНА ПРОВЕРЯЮЩИМ.\n"
                 f"Замечания: {json.dumps(feedback, ensure_ascii=False)}\n"
                 "Учти их и сделай заново.")
    return system, body


def verify(t, cand):
    user = (f"{task_context(t)}\nУСЛОВИЕ:\n{cand.get('statement')}\n\n"
            f"ОТВЕТ: {cand.get('answer')}\n\nРЕШЕНИЕ:\n{cand.get('solution')}")
    return as_obj(ask(VERIFY_PROMPT, user))


def needs_fix(v):
    if not v:
        return False
    return (norm(v.get("condition_correct")) in ("NO", "BORDERLINE")
            or norm(v.get("answer_correct")) == "NO"
            or norm(v.get("solution_correct")) == "NO")


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

    plan = sum(1 for t in todo if needs_fix(verdicts.get(uid_of(t))))

    print("=" * 64)
    print("ЭТАП 2: ФИКС")
    print(f"Вердиктов аудита     : {len(verdicts)}")
    print(f"Уже в v4             : {len(already)}")
    print(f"К обработке          : {len(todo)}")
    print(f"Из них требуют правки: {plan}")
    print(f"Циклов на задачу     : {FIX_CYCLES}")
    print("=" * 64)

    if not todo:
        print("Фикс уже завершён.")
        return

    started = time.time()
    st = {"clean": 0, "fixed": 0, "failed": 0, "reaudited": 0}

    for i, t in enumerate(todo, 1):
        u = uid_of(t)
        v = verdicts.get(u)

        if not v:
            print(f"[fix {i}/{len(todo)}] {u} -> нет вердикта, аудирую", flush=True)
            try:
                v = audit_one(t)
                append_jsonl(AUDIT_FILE, v)
                st["reaudited"] += 1
            except Exception as e:
                out = dict(t)
                out["_fix_status"] = "audit_failed"
                out["_fix_error"] = str(e)
                append_jsonl(OUT_DB, out)
                continue

        if not needs_fix(v):
            out = dict(t)
            out["_fix_status"] = "clean"
            out["_audit_verdict"] = v
            append_jsonl(OUT_DB, out)
            st["clean"] += 1
            if i % 50 == 0:
                print(f"[fix {i}/{len(todo)}] чистых: {st['clean']}, "
                      f"исправлено: {st['fixed']}, провалов: {st['failed']}", flush=True)
            continue

        cc = norm(v.get("condition_correct")) or "YES"
        mode = {"NO": "переделка условия",
                "BORDERLINE": "снятие двусмысленности"}.get(cc, "переделка решения")
        eta = (time.time() - started) / max(i - 1, 1) * (len(todo) - i + 1) if i > 1 else 0
        print(f"[fix {i}/{len(todo)}] {u} -> {mode}"
              + (f" | ~{fmt_time(eta)}" if eta else ""), flush=True)

        history, ok, cand, feedback = [], False, None, None

        for cycle in range(1, FIX_CYCLES + 1):
            print(f"    цикл {cycle}/{FIX_CYCLES}", flush=True)
            try:
                system, body = build_fix_request(t, v, feedback)
                cand = as_obj(ask(system, body))

                if cc not in ("NO", "BORDERLINE"):
                    orig = t.get("statement")
                    if not str(orig).strip():
                        raise ValueError("в базе пустое statement")
                    cand["statement"] = orig

                for field in ("statement", "answer", "solution"):
                    if not str(cand.get(field, "")).strip():
                        raise ValueError(f"в ответе пустое поле {field}")

                check = verify(t, cand)
                verdict = read_verdict(check)
                history.append({
                    "cycle": cycle,
                    "verdict": verdict,
                    "my_answer": check.get("my_answer"),
                    "problems": check.get("problems", []),
                    "what_changed": cand.get("what_changed"),
                })

                if verdict == "CORRECT":
                    ok = True
                    print(f"    проверка пройдена, ответ: {cand.get('answer')}", flush=True)
                    break

                print(f"    отклонено ({verdict or 'нет вердикта'}): "
                      f"{check.get('problems')}", flush=True)
                feedback = check.get("problems") or ["ответ не подтверждён"]

            except Exception as e:
                history.append({"cycle": cycle, "error": str(e)})
                print(f"    сбой цикла: {e}", file=sys.stderr, flush=True)
                feedback = [f"техническая ошибка: {e}"]
                time.sleep(2)

        out = dict(t)
        if ok and cand:
            out["statement"] = cand["statement"]
            out["answer"] = cand["answer"]
            out["solution"] = cand["solution"]
            out["_fix_status"] = "fixed"
            st["fixed"] += 1
        else:
            out["_fix_status"] = "fix_failed"
            st["failed"] += 1
            if cand:
                out["_fix_candidate"] = cand

        out["_fix_mode"] = mode
        out["_fix_history"] = history
        out["_audit_verdict"] = v
        append_jsonl(OUT_DB, out)
        append_jsonl(FIX_REPORT, {
            "task_uid": u,
            "mode": mode,
            "status": out["_fix_status"],
            "cycles_used": len(history),
            "old_statement": t.get("statement"),
            "new_statement": out.get("statement"),
            "old_answer": t.get("answer"),
            "new_answer": out.get("answer"),
            "history": history,
        })
        time.sleep(PAUSE)

    print("\n" + "=" * 64)
    print("ФИКС ЗАВЕРШЁН")
    print(f"Без изменений        : {st['clean']}")
    print(f"Исправлено           : {st['fixed']}")
    print(f"Провал за {FIX_CYCLES} циклов : {st['failed']}")
    print(f"Доаудировано на месте: {st['reaudited']}")
    print(f"Время                : {fmt_time(time.time() - started)}")
    print(f"Итоговая база : {OUT_DB}")
    print(f"Протокол      : {FIX_REPORT}")
    print("=" * 64)


# ==================== СТАТИСТИКА ====================

def stage_stats():
    db = read_jsonl(IN_DB)
    aud = read_jsonl(AUDIT_FILE)
    out = read_jsonl(OUT_DB)

    ok = [r for r in aud if not r.get("error")]
    err = len(aud) - len(ok)
    cnt = {}
    for r in ok:
        k = norm(r.get("condition_correct"))
        cnt[k] = cnt.get(k, 0) + 1
    ans_no = sum(1 for r in ok if norm(r.get("answer_correct")) == "NO")

    print("=" * 64)
    print("СТАТИСТИКА")
    print(f"Задач в базе       : {len(db)}")
    print(f"Аудировано         : {len(ok)} (ошибок {err})")
    for k in ("YES", "NO", "BORDERLINE", "UNKNOWN"):
        if cnt.get(k):
            print(f"  условие {k:<11}: {cnt[k]}")
    print(f"  ответ NO         : {ans_no}")
    if out:
        st = {}
        for r in out:
            k = r.get("_fix_status", "?")
            st[k] = st.get(k, 0) + 1
        print(f"\nВ итоговой базе    : {len(out)}")
        for k, vv in sorted(st.items()):
            print(f"  {k:<18}: {vv}")
    print("=" * 64)


# ==================== MAIN ====================

def main():
    what = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    print(f"Модель: {MODEL_NAME} | max_tokens={MAX_TOKENS} | циклов фикса={FIX_CYCLES}")
    print(f"База  : {IN_DB}")
    print(f"Выход : {OUT_DB}\n")

    if not os.path.exists(IN_DB):
        sys.exit(f"НЕ НАЙДЕНА БАЗА:\n  {IN_DB}")

    if what == "stats":
        stage_stats()
        return
    if what in ("all", "audit"):
        stage_audit()
    if what in ("all", "fix"):
        stage_fix()

    stage_stats()
    print("\nГОТОВО.")


if __name__ == "__main__":
    main()

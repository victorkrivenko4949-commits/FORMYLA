#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерация решений для олимпиадных задач через DeepSeek с двойным проходом:
  генератор -> аудитор -> (при необходимости) регенерация.

Пишет напрямую в olympiads.py через JSON-сериализацию (без отдельного merge-шага).
LaTeX: DeepSeek получает инструкцию использовать \\(...\\) и \\[...\\];
на выходе конвертируется в $...$ и $$...$$ для совместимости с app.py (KaTeX).

Особенности:
  - Lockfile (.gen_solutions.lock) для предотвращения дублирования процессов
  - Атомарная запись olympiads.py через tempfile + os.replace
  - RAW-строки для промптов (нет SyntaxWarning на Python 3.13)
  - Пропускает задачи, у которых уже есть solution_status='generated' в olympiads.py
  - Resume support: можно прервать и запустить снова — продолжит с места остановки
"""
import os, sys, json, time, requests, io, re, tempfile, subprocess, traceback

# ── Configuration ───────────────────────────────────────────────────────────

DEEPSEEK_KEY = os.environ["DEEPSEEK_API_KEY"]
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OLYMPIADS_PATH = os.path.join(_SCRIPT_DIR, "olympiads.py")
TASKS_PATH = r"C:\Users\Victor\Downloads\tasks_need_solutions.json"
LOG_OK = os.path.join(_SCRIPT_DIR, "solutions_log.jsonl")
LOG_BROKEN = os.path.join(_SCRIPT_DIR, "solutions_broken.jsonl")
LOG_FAIL = os.path.join(_SCRIPT_DIR, "solutions_fail.jsonl")
LOCKFILE = os.path.join(_SCRIPT_DIR, ".gen_solutions.lock")
CHECKPOINT_INTERVAL = 5  # save every N accepted solutions


# ── Lockfile (Windows-compatible) ──────────────────────────────────────────

def _acquire_lock() -> bool:
    """Try to acquire lock. Returns True if acquired, False if another instance is running."""
    if os.path.exists(LOCKFILE):
        try:
            with open(LOCKFILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                pid = int(content)
                # Windows: check via tasklist
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True, timeout=10
                )
                if str(pid) in result.stdout:
                    print(f"Another instance running (PID {pid}). Exiting.")
                    return False
        except (ValueError, OSError, subprocess.TimeoutExpired):
            pass  # stale lockfile, will overwrite
    try:
        with open(LOCKFILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except OSError as e:
        print(f"ERROR: Cannot create lockfile: {e}")
        return False


def _release_lock() -> None:
    try:
        if os.path.exists(LOCKFILE):
            os.remove(LOCKFILE)
    except OSError:
        pass


# ── Load / Save olympiads.py ──────────────────────────────────────────────

def load_db() -> list:
    """Load olympiads.py and return the list of olympiad records."""
    if not os.path.exists(OLYMPIADS_PATH):
        print(f"ERROR: olympiads.py not found at {OLYMPIADS_PATH}")
        sys.exit(1)
    with open(OLYMPIADS_PATH, "r", encoding="utf-8") as f:
        src = f.read()
    start = src.index("[")
    return json.loads(src[start:])


def save_db(db: list) -> None:
    """Atomically save db to olympiads.py using tempfile + os.replace."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=_SCRIPT_DIR,
        prefix=".olympiads_tmp_", suffix=".py", delete=False
    )
    try:
        tmp.write("OLYMPIADS_DB = ")
        json.dump(db, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp.close()
        os.replace(tmp.name, OLYMPIADS_PATH)
    except Exception:
        # cleanup temp on failure
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise
    finally:
        try:
            tmp.close()
        except Exception:
            pass


# ── Matching: task record -> olympiad problem ──────────────────────────────

def _make_key(rec_or_oly: dict, num: str = None) -> tuple:
    """Build a comparable key from a task record or olympiad record + problem num."""
    return (
        str(rec_or_oly.get("olympiad", "")),
        str(rec_or_oly.get("year", "")),
        str(rec_or_oly.get("grade", "")),
        str(rec_or_oly.get("round", "")),
        str(num if num is not None else rec_or_oly.get("num", ""))
    )


def find_problem(db: list, task_rec: dict) -> tuple:
    """Find (olympiad_index, problem_index) in db matching task_rec.
    Returns (oly_idx, prob_idx) or (None, None) if not found.
    """
    task_key = _make_key(task_rec)
    for oi, oly in enumerate(db):
        for pi, prob in enumerate(oly.get("problems", [])):
            if _make_key(oly, prob.get("num", "")) == task_key:
                return oi, pi
    return None, None


# ── LaTeX conversion: DeepSeek format -> KaTeX format ──────────────────────

def _convert_latex(text: str) -> str:
    """Convert DeepSeek LaTeX \\(...\\) and \\[...\\] to $...$ and $$...$$."""
    if not text:
        return text
    text = re.sub(r"\\\(", "$", text)
    text = re.sub(r"\\\)", "$", text)
    text = re.sub(r"\\\[", "$$", text)
    text = re.sub(r"\\\]", "$$", text)
    return text


# ── Sanitize DeepSeek JSON ────────────────────────────────────────────────

def _escape_control_chars_in_strings(text: str) -> str:
    """Escape control chars (< 0x20) inside JSON strings.
    DeepSeek sometimes returns JSON with literal newlines/tabs inside string values.
    """
    result = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            result.append(ch)
            escape = False
            continue
        if ch == "\\":
            result.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ord(ch) < 0x20:
            if ch == "\n":
                result.append("\\n")
            elif ch == "\t":
                result.append("\\t")
            elif ch == "\r":
                result.append("\\r")
            else:
                result.append("\\u{:04x}".format(ord(ch)))
        else:
            result.append(ch)
    return "".join(result)


def _sanitize_json_content(content: str) -> dict:
    """Multi-step DeepSeek JSON sanitizer.
    Steps: raw -> escape control chars -> fix unescaped LaTeX backslashes -> brute force.
    """
    # Step 0: raw
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Step 1: escape control chars inside strings
    step1 = _escape_control_chars_in_strings(content)
    try:
        return json.loads(step1)
    except json.JSONDecodeError:
        pass

    # Step 2: fix unescaped LaTeX backslashes (e.g. \( instead of \\()
    step2 = re.sub(
        r'\\(?![\\"/bfnrtu]|u[0-9a-fA-F]{4})',
        r"\\\\",
        step1
    )
    try:
        return json.loads(step2)
    except json.JSONDecodeError:
        pass

    # Step 3: brute force - escape ALL backslashes
    step3 = step1.replace("\\", "\\\\")
    try:
        return json.loads(step3)
    except json.JSONDecodeError:
        pass

    return None


# ── Prompts (RAW strings — no SyntaxWarning on Python 3.13) ────────────────

GEN_SYSTEM = r"""Ты — эксперт по олимпиадной математике и составитель официальных решений (российские олимпиады 5-11 класс: ВсОШ, Турнир городов, Ломоносов, Покори Воробьёвы горы, Высшая проба, Физтех, Курчатов, СПбГУ, олимпиада Эйлера).

Тебе дают условие РЕАЛЬНОЙ олимпиадной задачи с её паспортом (олимпиада, год, класс, этап, номер). Твоя задача — дать ПОЛНОЕ, СТРОГОЕ и КОРРЕКТНОЕ решение именно этой задачи.

ТРЕБОВАНИЯ К РЕШЕНИЮ:
1. Решай ИМЕННО данную задачу по её условию. Ничего в условии не меняй и не «упрощай».
2. Решение пошаговое, с полным обоснованием каждого перехода (не «очевидно», а почему).
3. Для задач «докажите» — строгое доказательство. Для «найдите» — вывод + проверка ответа. Для «наибольшее/наименьшее» — обязательно оценка И пример (что значение достигается).
4. Если в задаче несколько случаев — разбери все.
5. В конце дай однозначный краткий ответ (или явное перечисление всех решений). Если задача — доказательство без числового ответа, в answer напиши «Доказательство» и суть утверждения.
6. Все формулы — в LaTeX, инлайн через \( ... \), выключенные через \[ ... \]. Не используй $...$ и $$...$$. Экранируй обратный слэш корректно в JSON.
7. НИКАКИХ заглушек: запрещены фразы «требует рисунок», «не удалось найти», «см. официальный источник», «не удалось восстановить». Если для решения нужен чертёж — опиши построение словами и введи координаты/обозначения.
8. Не выдумывай «официальную нумерацию/баллы». Только математика.

ФОРМАТ ОТВЕТА — строго один JSON-объект без текста вне JSON:
{
  "solution": "<полное пошаговое решение, LaTeX-инлайн \( ... \)>",
  "answer": "<краткий однозначный ответ или 'Доказательство: <суть>'>",
  "method_note": "<1 фраза: ключевая идея/метод решения>"
}"""


def gen_user(rec: dict) -> str:
    return f"""ПАСПОРТ ЗАДАЧИ (для контекста, не переписывай в ответ):
- Олимпиада: {rec.get('olympiad')}
- Год: {rec.get('year')}
- Класс: {rec.get('grade')}
- Этап/тур: {rec.get('round')}
- Номер задачи: {rec.get('num')}

УСЛОВИЕ:
{rec.get('problem_text')}

Дай полное решение и ответ строго в формате JSON."""


AUDIT_SYSTEM = r"""Ты — строгий рецензент олимпиадных решений. Тебе дают паспорт задачи, её условие и предложенное решение с ответом. Проверь ЧЕТЫРЕ вещи и верни строгий JSON.

ПРОВЕРКИ:
1. СООТВЕТСТВИЕ ЗАДАЧЕ: решение решает ИМЕННО это условие (та же задача — не подменена другой), и соответствует паспорту (олимпиада/год/класс/этап/номер не противоречат условию). Условие не искажено внутри решения.
2. LaTeX: все формулы в корректном LaTeX через \( ... \) или \[ ... \]; нет $...$ и $$...$$; нет незакрытых скобок/команд; JSON-экранирование не сломано.
3. МАТЕМАТИЧЕСКАЯ КОРРЕКТНОСТЬ: логика без дыр; для min/max есть и оценка, и пример; ответ согласован с решением; нет заглушек («требует рисунок», «не удалось найти» и т.п.).
4. ЦЕЛОСТНОСТЬ УСЛОВИЯ: если условие само по себе обрывочно/повреждено (нечитаемо, обрезано, бессмысленно) — пометь text_broken=true.

Верни строго JSON без текста вне него:
{
  "pass": <true|false>,
  "matches_task": <true|false>,
  "latex_ok": <true|false>,
  "math_ok": <true|false>,
  "text_broken": <true|false>,
  "issues": ["<кратко каждая проблема>"]
}
pass = true только если matches_task && latex_ok && math_ok && !text_broken."""


def audit_user(rec: dict, gen: dict) -> str:
    return f"""ПАСПОРТ: олимпиада={rec.get('olympiad')}, год={rec.get('year')}, класс={rec.get('grade')}, этап={rec.get('round')}, номер={rec.get('num')}.

УСЛОВИЕ:
{rec.get('problem_text')}

ПРЕДЛОЖЕННОЕ РЕШЕНИЕ:
{gen.get('solution')}

ОТВЕТ:
{gen.get('answer')}

Проверь и верни JSON."""


# ── Shared requests.Session (DNS caching via connection reuse) ─────────────

_SESSION = requests.Session()
_adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=20,
    max_retries=0  # manual retries
)
_SESSION.mount("https://", _adapter)


# ── API Call ───────────────────────────────────────────────────────────────

def _backoff_sleep(attempt: int, is_dns_error: bool = False) -> None:
    """Exponential backoff: DNS 30-120s, others 5-120s."""
    if is_dns_error:
        delay = min(30 * (2 ** (attempt - 1)), 120)
    else:
        delay = min(5 * (2 ** (attempt - 1)), 120)
    print(f"    Waiting {delay}s before retry {attempt+1}...")
    time.sleep(delay)


def call_deepseek(system: str, user: str, retries: int = 10) -> dict:
    """Call DeepSeek API with system+user prompts, return parsed JSON dict or None."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0.4,
        "response_format": {"type": "json_object"}
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json"
    }
    for attempt in range(1, retries + 1):
        try:
            r = _SESSION.post(API_URL, json=payload, headers=headers, timeout=180)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            result = _sanitize_json_content(content)
            if result is not None:
                return result
            print(f"    JSON parse failed after sanitization (attempt {attempt}/{retries})")
            if attempt < retries:
                _backoff_sleep(attempt, is_dns_error=False)
        except requests.exceptions.ConnectionError as e:
            is_dns = "getaddrinfo failed" in str(e) or "NameResolutionError" in str(e) or "Failed to resolve" in str(e)
            print(f"    Connection error (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                _backoff_sleep(attempt, is_dns_error=is_dns)
        except requests.exceptions.Timeout as e:
            print(f"    Timeout (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                _backoff_sleep(attempt, is_dns_error=False)
        except requests.exceptions.RequestException as e:
            print(f"    API error (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                _backoff_sleep(attempt, is_dns_error=False)
        except Exception as e:
            print(f"    Unexpected error (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                _backoff_sleep(attempt, is_dns_error=False)
    return None


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    global MODEL

    # stdout utf-8 for Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    # ── Lock ──
    if not _acquire_lock():
        sys.exit(0)

    try:
        print(f"DeepSeek Solution Generator v2 (direct write to olympiads.py)")
        print(f"Model: {MODEL}")
        print(f"Olympiads DB: {OLYMPIADS_PATH}")
        print(f"Tasks input: {TASKS_PATH}")
        print()

        # ── Load olympiads DB ──
        db = load_db()
        print(f"Loaded olympiads.py: {len(db)} olympiad records")

        # Count existing generated solutions
        gen_before = sum(
            1 for o in db for p in o.get("problems", [])
            if p.get("solution_status") == "generated"
        )
        print(f"Existing generated solutions: {gen_before}")

        # Build set of already-done task keys
        done_keys = set()
        for o in db:
            for p in o.get("problems", []):
                if p.get("solution_status") == "generated" and p.get("solution", "").strip():
                    k = _make_key(o, p.get("num", ""))
                    done_keys.add(k)
        print(f"Unique done task keys: {len(done_keys)}")

        # ── Load tasks ──
        if not os.path.exists(TASKS_PATH):
            print(f"ERROR: Tasks file not found: {TASKS_PATH}")
            return

        with open(TASKS_PATH, "r", encoding="utf-8") as f:
            tasks = json.loads(f.read().strip())
        print(f"Loaded {len(tasks)} tasks from input")

        # ── Open logs ──
        logf = open(LOG_OK, "a", encoding="utf-8")
        brokenf = open(LOG_BROKEN, "a", encoding="utf-8")
        failf = open(LOG_FAIL, "a", encoding="utf-8")

        ok_count = 0
        broken_count = 0
        fail_count = 0
        skip_count = 0
        total = len(tasks)

        for i, task in enumerate(tasks, 1):
            k = task.get("key", f"unknown_{i}")

            # ── Skip if already done ──
            if k in done_keys:
                print(f"[{i}/{total}] {k} SKIP (already in olympiads.py)")
                skip_count += 1
                continue

            # ── Find matching olympiad problem in DB ──
            oi, pi = find_problem(db, task)
            if oi is None:
                print(f"[{i}/{total}] {k} ERROR: not found in olympiads.py, skipping")
                fail_count += 1
                failf.write(json.dumps({
                    "key": k,
                    "olympiad": task.get("olympiad"),
                    "error": "not found in olympiads.py"
                }, ensure_ascii=False) + "\n")
                failf.flush()
                continue

            # ── Generate (up to 3 attempts) ──
            accepted = None
            last_audit = None
            last_gen = None

            for attempt in range(3):
                print(f"  [{i}/{total}] {k} generating (attempt {attempt+1}/3)...")
                gen = call_deepseek(GEN_SYSTEM, gen_user(task))
                if not gen or "solution" not in gen:
                    print(f"    Empty/invalid generation")
                    continue
                last_gen = gen

                print(f"    auditing...")
                audit = call_deepseek(AUDIT_SYSTEM, audit_user(task, gen))
                last_audit = audit

                if audit and audit.get("text_broken"):
                    print(f"    TEXT_BROKEN detected")
                    break

                if audit and audit.get("pass"):
                    accepted = gen
                    print(f"    PASS (audit accepted)")
                    break
                else:
                    issues = audit.get("issues", []) if audit else ["audit returned None"]
                    print(f"    AUDIT REJECTED: {issues}")

            # ── Handle TEXT_BROKEN ──
            if last_audit and last_audit.get("text_broken"):
                broken_count += 1
                brokenf.write(json.dumps({
                    "key": k,
                    "olympiad": task.get("olympiad"),
                    "audit": last_audit,
                    "gen": last_gen
                }, ensure_ascii=False) + "\n")
                brokenf.flush()
                print(f"  -> TEXT_BROKEN (manual review needed)")
                continue

            # ── Handle FAIL ──
            if not accepted:
                fail_count += 1
                failf.write(json.dumps({
                    "key": k,
                    "olympiad": task.get("olympiad"),
                    "last_gen": last_gen,
                    "last_audit": last_audit
                }, ensure_ascii=False) + "\n")
                failf.flush()
                print(f"  -> FAIL (not accepted after 3 attempts)")
                continue

            # ── ACCEPTED: write into olympiads.py ──
            solution_text = _convert_latex(accepted.get("solution", ""))
            answer_text = _convert_latex(accepted.get("answer", ""))

            # Modify the problem in-place
            db[oi]["problems"][pi]["solution"] = solution_text
            db[oi]["problems"][pi]["answer"] = answer_text
            db[oi]["problems"][pi]["solution_status"] = "generated"

            ok_count += 1
            done_keys.add(k)

            # Log
            logf.write(json.dumps({
                "key": k,
                "olympiad": task.get("olympiad"),
                "method_note": accepted.get("method_note", ""),
                "answer": accepted.get("answer", "")
            }, ensure_ascii=False) + "\n")
            logf.flush()
            print(f"  -> OK (method: {accepted.get('method_note', 'N/A')[:60]})")

            # ── Checkpoint: save olympiads.py ──
            if ok_count % CHECKPOINT_INTERVAL == 0:
                save_db(db)
                total_gen = sum(
                    1 for o in db for p in o.get("problems", [])
                    if p.get("solution_status") == "generated"
                )
                print(f"  [CHECKPOINT] Saved olympiads.py ({total_gen} generated solutions)")

        # ── Final save ──
        save_db(db)
        final_gen = sum(
            1 for o in db for p in o.get("problems", [])
            if p.get("solution_status") == "generated"
        )

        logf.close()
        brokenf.close()
        failf.close()

        print()
        print(f"{'=' * 50}")
        print(f"  RESULTS:")
        print(f"    Total tasks in input: {total}")
        print(f"    Skipped (already done): {skip_count}")
        print(f"    New OK:               {ok_count}")
        print(f"    TEXT_BROKEN:          {broken_count}")
        print(f"    FAIL:                 {fail_count}")
        print(f"    Total in olympiads.py: {final_gen}")
        print(f"{'=' * 50}")

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        traceback.print_exc()
        raise
    finally:
        _release_lock()


if __name__ == "__main__":
    main()

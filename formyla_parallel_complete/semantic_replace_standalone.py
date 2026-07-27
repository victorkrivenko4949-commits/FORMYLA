import os, re, json, time, threading, traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

ROOT = Path(".")
QUEUE_DIR = ROOT / "semantic_replace_queue"
OUT_DIR = ROOT / "semantic_replace_results_standalone"
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "worker_01_results.jsonl"

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
WORKERS = int(os.environ.get("SEMANTIC_WORKERS", "8"))
URL = "https://api.deepseek.com/chat/completions"

assert API_KEY, "DEEPSEEK_API_KEY не задан"

lock = threading.Lock()

def load_jobs():
    jobs = []
    for p in sorted(QUEUE_DIR.glob("formyla_worker_*_jobs.json")):
        obj = json.loads(p.read_text(encoding="utf-8"))
        jobs.extend(obj.get("jobs", []))
    return jobs

def completed_ids():
    done = set()
    if not OUT_FILE.exists():
        return done
    for line in OUT_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
            jid = r.get("job_id") or r.get("job", {}).get("job_id")
            if jid and r.get("status") == "ok":
                done.add(jid)
        except Exception:
            pass
    return done

def append_record(rec):
    with lock:
        with OUT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def min_solution_len(level):
    if level >= 8:
        return 1500
    if level >= 7:
        return 1100
    return 800

def forbidden(text):
    t = (text or "").lower()
    regs = [
        r"рукопожат",
        r"пожал[а-яё]* друг другу руки",
        r"доминошк",
        r"замостить.*домино",
        r"наибольший общий делитель",
        r"наименьшее общее кратное",
        r"мешке носки",
        r"пара одного цвета",
        r"общим дн[её]м рождения",
        r"от числа .* взяли",
        r"решите уравнение.*x\^2",
        r"решите уравнение.*x²",
        r"при делении на .* да[её]т остаток",
    ]
    return any(re.search(r, t, re.S | re.I) for r in regs)

def extract_json(content):
    s = content.strip()
    s = re.sub(r"^```(?:json)?", "", s, flags=re.I).strip()
    s = re.sub(r"```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    a = s.find("{")
    b = s.rfind("}")
    if a >= 0 and b > a:
        return json.loads(s[a:b+1])
    raise ValueError("no_json_object")

def prompt_for(job):
    bad = job.get("bad_task", {}) or {}
    grade = int(job.get("grade") or bad.get("grade") or 7)
    level = int(job.get("difficulty") or bad.get("difficulty") or 6)
    method_code = str(job.get("method_code") or bad.get("method_code") or bad.get("method") or "OLY")
    old_text = str(bad.get("task_text", ""))[:1200]

    return f"""
Ты составляешь оригинальную русскоязычную олимпиадную задачу для базы FORMYLA.

Нужно заменить плохую шаблонную задачу.

Параметры:
grade = {grade}
difficulty = {level}
method_code = {method_code}

Старая задача, которую нельзя копировать и нельзя перефразировать:
{old_text}

Жёсткие запреты:
- не использовать квадратное уравнение с готовыми корнями;
- не использовать НОД/НОК как основную идею;
- не использовать долю от числа;
- не использовать рукопожатия;
- не использовать домино-паритет;
- не использовать носки, дни рождения, простую клеточную раскраску;
- не использовать простые остатки CRT;
- не делать одношаговую формульную задачу.

Требования к уровню:
- L6: региональный уровень, минимум две идеи, неочевидный ход;
- L7: сложная региональная задача, нужна оценка, конструкция, инвариант или доказательство;
- L8: финальный уровень, несколько идей, доказательство оптимальности/невозможности или параметрический анализ.

Верни строго валидный JSON-объект без markdown и без пояснений вне JSON.

Формат:
{{
  "task_text": "полный текст новой задачи",
  "correct_answer": "краткий однозначный ответ",
  "solution": "полное решение на русском языке",
  "theme": "краткая тема",
  "subtopic": "краткая подтема",
  "method": "{method_code}"
}}

LaTeX пиши безопасно: используй \\( ... \\), не используй долларовые знаки.
"""

def call_model(job):
    messages = [
        {"role": "system", "content": "Ты опытный составитель олимпиадных задач. Отвечай только валидным JSON."},
        {"role": "user", "content": prompt_for(job)}
    ]
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.75,
        "max_tokens": 5000,
        "response_format": {"type": "json_object"},
    }
    r = requests.post(
        URL,
        headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=240,
    )
    if r.status_code >= 400:
        payload.pop("response_format", None)
        r = requests.post(
            URL,
            headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=240,
        )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def build_task(job, obj):
    bad = dict(job.get("bad_task", {}) or {})
    tid = str(job.get("replace_id") or bad.get("id") or job.get("job_id"))
    grade = int(job.get("grade") or bad.get("grade") or 7)
    level = int(job.get("difficulty") or bad.get("difficulty") or 6)
    method_code = str(job.get("method_code") or bad.get("method_code") or bad.get("method") or "OLY")

    task_text = str(obj.get("task_text", "")).strip()
    answer = str(obj.get("correct_answer") or obj.get("answer") or "").strip()
    solution = str(obj.get("solution", "")).strip()

    if not task_text or not answer or not solution:
        raise ValueError("empty_fields")
    if forbidden(task_text):
        raise ValueError("forbidden_template")
    if len(solution) < min_solution_len(level):
        raise ValueError(f"short_solution {len(solution)} < {min_solution_len(level)}")

    bad.update({
        "id": tid,
        "grade": grade,
        "method_code": method_code,
        "difficulty": level,
        "task_text": task_text,
        "correct_answer": answer,
        "solution": solution,
        "theme": str(obj.get("theme") or bad.get("theme") or "Олимпиадная задача").strip(),
        "subtopic": str(obj.get("subtopic") or bad.get("subtopic") or "Семантическая замена").strip(),
        "method": str(obj.get("method") or method_code).strip(),
    })
    if "answer" in bad:
        bad["answer"] = answer
    return bad

def process(job):
    jid = job.get("job_id")
    last_error = None
    for attempt in range(1, 5):
        try:
            content = call_model(job)
            obj = extract_json(content)
            task = build_task(job, obj)
            rec = {
                "status": "ok",
                "task": task,
                "job": job,
                "attempts": attempt,
                "job_id": jid,
            }
            append_record(rec)
            return rec
        except Exception as e:
            last_error = repr(e)
            time.sleep(2 * attempt)
    rec = {
        "status": "failed",
        "error": last_error,
        "job": job,
        "attempts": 4,
        "job_id": jid,
    }
    append_record(rec)
    return rec

def main():
    jobs = load_jobs()
    done = completed_ids()
    jobs = [j for j in jobs if j.get("job_id") not in done]

    print("MODEL", MODEL)
    print("WORKERS", WORKERS)
    print("PENDING", len(jobs))
    print("OUT", str(OUT_FILE))

    ok = 0
    bad = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(process, j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                r = fut.result()
                if r.get("status") == "ok":
                    ok += 1
                else:
                    bad += 1
            except Exception:
                bad += 1
                print(traceback.format_exc())
            print("PROGRESS", i, "/", len(jobs), "OK", ok, "FAILED", bad, flush=True)

    print("DONE OK", ok, "FAILED", bad)

if __name__ == "__main__":
    main()

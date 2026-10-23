import os, re, json, time, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

QUEUE_DIR = Path("semantic_replace_queue")
OUT_DIR = Path("semantic_replace_results_standalone"); OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "worker_01_results.jsonl"
TRASH_FILE = Path("semantic_replace_needs_manual.jsonl")
LOG = Path("semantic_pipeline_log.txt")

API_KEY = os.environ.get("DEEPSEEK_API_KEY","").strip()
MODEL = os.environ.get("DEEPSEEK_MODEL","deepseek-reasoner").strip() or "deepseek-reasoner"
WORKERS = int(os.environ.get("SEMANTIC_WORKERS","4"))
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS","3"))
URL = "https://api.deepseek.com/chat/completions"
assert API_KEY, "DEEPSEEK_API_KEY не задан"

lock = threading.Lock()
def log(msg):
    with lock:
        line = time.strftime("%H:%M:%S ")+msg
        print(line, flush=True)
        with LOG.open("a",encoding="utf-8") as f: f.write(line+"\n")

def load_jobs():
    j=[]
    for p in sorted(QUEUE_DIR.glob("formyla_worker_*_jobs.json")):
        j.extend(json.loads(p.read_text(encoding="utf-8")).get("jobs",[]))
    return j

def seen_ids():
    ok=set(); manual=set()
    if OUT_FILE.exists():
        for l in OUT_FILE.read_text(encoding="utf-8",errors="replace").splitlines():
            try:
                r=json.loads(l); jid=r.get("job_id") or r.get("job",{}).get("job_id")
                if jid and r.get("status")=="ok": ok.add(jid)
            except: pass
    if TRASH_FILE.exists():
        for l in TRASH_FILE.read_text(encoding="utf-8",errors="replace").splitlines():
            try:
                r=json.loads(l); jid=r.get("job_id")
                if jid: manual.add(jid)
            except: pass
    return ok, manual

def append(path, rec):
    with lock:
        with path.open("a",encoding="utf-8") as f:
            f.write(json.dumps(rec,ensure_ascii=False)+"\n")

def min_len(lv): return 900 if lv>=8 else (700 if lv>=7 else 500)

def forbidden(t):
    t=(t or "").lower()
    return any(re.search(p,t,re.S) for p in
      [r"рукопожат",r"доминошк",r"наибольший общий делитель",
       r"наименьшее общее кратное",r"мешке носки",r"общим дн[её]м рождения"])

def fix_bs(s): return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s)
def grab(s,k):
    m=re.search(r'"'+k+r'"\s*:\s*"((?:\\.|[^"\\])*)"',s,re.S)
    if not m: return ""
    v=m.group(1)
    try: return json.loads('"'+v+'"')
    except: return v.replace('\\n','\n')

def parse(content):
    s=re.sub(r"```$","",re.sub(r"^```(?:json)?","",content.strip(),flags=re.I).strip()).strip()
    a,b=s.find("{"),s.rfind("}"); core=s[a:b+1] if a>=0 and b>a else s
    for c in (core,fix_bs(core)):
        try: return json.loads(c)
        except: pass
    tt,ans,sol=grab(core,"task_text"),grab(core,"correct_answer") or grab(core,"answer"),grab(core,"solution")
    if tt and ans and sol:
        return {"task_text":tt,"correct_answer":ans,"solution":sol,
                "theme":grab(core,"theme"),"subtopic":grab(core,"subtopic"),"method":grab(core,"method")}
    raise ValueError("no_json_object")

def api(messages, max_tokens=8000):
    r=requests.post(URL,headers={"Authorization":"Bearer "+API_KEY,"Content-Type":"application/json"},
        json={"model":MODEL,"messages":messages,"temperature":0.7,"max_tokens":max_tokens},timeout=600)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def gen_prompt(job, harder_note, audit_note):
    bad=job.get("bad_task",{}) or {}
    grade=int(job.get("grade") or bad.get("grade") or 7)
    lv=int(job.get("difficulty") or bad.get("difficulty") or 6)
    mc=str(job.get("method_code") or bad.get("method_code") or bad.get("method") or "OLY")
    old=str(bad.get("task_text",""))[:1000]
    extra=""
    if harder_note: extra+="\nПРЕДЫДУЩАЯ БЫЛА ЛЕГЧЕ ЦЕЛИ. СДЕЛАЙ СЛОЖНЕЕ: "+harder_note
    if audit_note: extra+="\nИСПРАВЬ ОШИБКИ АУДИТА: "+audit_note
    return f"""Составь оригинальную русскоязычную олимпиадную задачу для замены шаблонной.
СТРОГО сохрани привязку: grade={grade}, difficulty={lv} (целевой уровень), method_code={mc} (метод менять нельзя).
Задача обязана соответствовать именно этому методу и именно этой сложности.
Старую копировать нельзя:
{old}
Запрещены шаблоны: квадратное уравнение с готовыми корнями, НОД/НОК, доля от числа, рукопожатия, домино-паритет, носки, дни рождения, простые остатки CRT, одношаговые формульные задачи.
L6: минимум две идеи; L7: оценка+конструкция/инвариант; L8: несколько идей и доказательство оптимальности/невозможности.{extra}
Верни СТРОГО валидный JSON без markdown, LaTeX-слэши экранируй двойными (\\\\leq,\\\\frac):
{{"task_text":"...","correct_answer":"...","solution":"...","theme":"...","subtopic":"...","method":"{mc}"}}"""

def check_difficulty(obj, target, mc):
    msg=[{"role":"system","content":"Ты строгий эксперт-оценщик олимпиадных задач. Отвечай только JSON."},
         {"role":"user","content":f"""Оцени задачу по шкале ВсОШ (6=регион,7=сложный регион,8=финал).
Целевой уровень={target}, целевой метод_код={mc}.
Верни JSON: {{"level":<число>,"method_ok":true/false,"harder_hint":"что усложнить если ниже цели"}}
ЗАДАЧА:
{obj.get('task_text','')}
РЕШЕНИЕ:
{obj.get('solution','')[:3000]}"""}]
    return parse(api(msg,3000))

def audit(obj, target, mc):
    msg=[{"role":"system","content":"Ты строгий аудитор. Проверь LaTeX, корректность решения, корректность ответа, отсутствие запрещённых шаблонов. Отвечай только JSON."},
         {"role":"user","content":f"""Целевой уровень={target}, метод={mc}.
Верни JSON: {{"ok":true/false,"issues":["список конкретных ошибок"]}}
ЗАДАЧА:
{obj.get('task_text','')}
ОТВЕТ: {obj.get('correct_answer','')}
РЕШЕНИЕ:
{obj.get('solution','')[:4000]}"""}]
    return parse(api(msg,3000))

def build(job,obj):
    bad=dict(job.get("bad_task",{}) or {})
    tid=str(job.get("replace_id") or bad.get("id") or job.get("job_id"))
    grade=int(job.get("grade") or bad.get("grade") or 7)
    lv=int(job.get("difficulty") or bad.get("difficulty") or 6)
    mc=str(job.get("method_code") or bad.get("method_code") or bad.get("method") or "OLY")
    tt=str(obj.get("task_text","")).strip(); ans=str(obj.get("correct_answer") or obj.get("answer") or "").strip(); sol=str(obj.get("solution","")).strip()
    if not tt or not ans or not sol: raise ValueError("empty_fields")
    if forbidden(tt): raise ValueError("forbidden_template")
    if len(sol)<min_len(lv): raise ValueError(f"short_solution {len(sol)}")
    bad.update({"id":tid,"grade":grade,"method_code":mc,"difficulty":lv,"task_text":tt,
                "correct_answer":ans,"solution":sol,
                "theme":(str(obj.get("theme") or bad.get("theme") or "Олимпиадная задача")).strip(),
                "subtopic":(str(obj.get("subtopic") or bad.get("subtopic") or "Семантическая замена")).strip(),
                "method":(str(obj.get("method") or mc)).strip()})
    if "answer" in bad: bad["answer"]=ans
    return bad

def process(job):
    jid=job.get("job_id")
    target=int(job.get("difficulty") or job.get("bad_task",{}).get("difficulty") or 6)
    mc=str(job.get("method_code") or job.get("bad_task",{}).get("method_code") or "OLY")
    harder=""; audit_note=""; last=None
    for attempt in range(1,MAX_ATTEMPTS+1):
        try:
            obj=parse(api([{"role":"system","content":"Отвечай только валидным JSON, экранируй LaTeX-слэши."},
                           {"role":"user","content":gen_prompt(job,harder,audit_note)}]))
            # проверка сложности
            d=check_difficulty(obj,target,mc)
            lv=int(d.get("level") or 0)
            if lv<target or not d.get("method_ok",True):
                harder=str(d.get("harder_hint") or "усложни ключевую идею, добавь оценку/доказательство")
                last=f"level {lv}<{target}"; log(f"{jid} try{attempt}: сложность {lv}<{target} -> перегенерация СЛОЖНЕЕ"); continue
            # аудит
            a=audit(obj,target,mc)
            if not a.get("ok",False):
                audit_note="; ".join(a.get("issues",[]))[:600]
                last="audit: "+audit_note; log(f"{jid} try{attempt}: аудит ошибки -> {audit_note[:120]}"); continue
            task=build(job,obj)
            append(OUT_FILE,{"status":"ok","task":task,"job":job,"attempts":attempt,"job_id":jid,"final_level":lv})
            log(f"{jid} OK на попытке {attempt}, level={lv}")
            return "ok"
        except requests.exceptions.RequestException as e:
            last=repr(e); time.sleep(3*attempt)
        except Exception as e:
            last=repr(e); audit_note=str(e)[:200]; time.sleep(2)
    append(TRASH_FILE,{"job_id":jid,"job":job,"last_error":last,"attempts":MAX_ATTEMPTS})
    log(f"{jid} -> МУСОР (needs_manual) после {MAX_ATTEMPTS} попыток: {last}")
    return "manual"

def main():
    ok_done,manual_done=seen_ids()
    jobs=[j for j in load_jobs() if j.get("job_id") not in ok_done and j.get("job_id") not in manual_done]
    log(f"START model={MODEL} workers={WORKERS} max_attempts={MAX_ATTEMPTS} pending={len(jobs)}")
    ok=man=0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs=[ex.submit(process,j) for j in jobs]
        for i,f in enumerate(as_completed(futs),1):
            r=f.result(); ok+=r=="ok"; man+=r=="manual"
            log(f"PROGRESS {i}/{len(jobs)} OK={ok} MANUAL={man}")
    log(f"DONE OK={ok} MANUAL={man}")

if __name__=="__main__":
    main()

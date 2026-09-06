# -*- coding: utf-8 -*-
"""Только шаг solver: DeepSeek через api.deepseek.com, запись JSON в файл.
Запускать в фоне. Модели по скорости: deepseek-chat (быстро), deepseek-reasoner (медленнее).
"""
import sys, os, json, time, re
import requests

SOLVER_PROMPT = open(
    "/home/user/workspace/uploaded_attachments/006e1718453e4391ab3581a8e4948f3d/data__figures__solver_task.txt",
    encoding="utf-8").read()
CONDITION = (
    "В треугольнике ABC проведена медиана BM (M — середина стороны AC). "
    "Медиана BM продолжена за точку M на отрезок MK, равный BM (K — новая точка). "
    "Докажите, что четырёхугольник ABCK является параллелограммом."
)
URL = "https://api.deepseek.com/v1/chat/completions"
KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODELS = ["deepseek-v4-pro", "deepseek-chat"]
OUT = "/home/user/workspace/e2e_out2/solver_parallelogram.json"
LOG = "/home/user/workspace/e2e_out2/solver_parallelogram.log"

def log(msg):
    print(msg, flush=True)
    open(LOG, "a", encoding="utf-8").write(msg + "\n")

def _extract_aux(content: str):
    """Извлечь aux_constructions из возможно обрезанного JSON."""
    # найдём начало массива aux_constructions
    idx = content.find('"aux_constructions"')
    if idx == -1:
        return []
    # найдём открывающую скобку массива
    b = content.find('[', idx)
    if b == -1:
        return []
    # сбалансированно найдём закрывающую скобку
    depth = 0
    in_str = False
    esc = False
    i = b
    end = -1
    while i < len(content):
        ch = content[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        i += 1
    if end == -1:
        # массив не закрыт — возьмём до конца и закроем
        arr_text = content[b:] + ']'
    else:
        arr_text = content[b:end+1]
    try:
        arr = json.loads(arr_text)
        return [a for a in arr if isinstance(a, dict) and a.get("op")]
    except Exception:
        # попробуем вытащить отдельные {op:...} объекты
        ops = re.findall(r'\{"op"\s*:\s*"([^"]+)"[^}]*\}', arr_text)
        return [{"op": o} for o in ops]

log(f"START key_len={len(KEY)} models={MODELS}")
messages = [
    {"role": "system", "content": SOLVER_PROMPT.replace("{condition_text}", CONDITION)},
    {"role": "user", "content": f"ЗАДАЧА:\n{CONDITION}\n\nВерни СТРОГО JSON."},
]
hdrs = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
last_err = None
for model in MODELS:
    payload = {"model": model, "messages": messages, "temperature": 0.1,
               "max_tokens": 32768, "response_format": {"type": "json_object"}}
    t0 = time.perf_counter()
    try:
        r = requests.post(URL, headers=hdrs, json=payload, timeout=(15, 240))
    except Exception as e:
        last_err = f"transport {model}: {type(e).__name__}: {e}"
        log(last_err); continue
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        last_err = f"http {r.status_code} {model}: {r.text[:300]}"
        log(f"{last_err} ({dt:.0f}с)")
        if r.status_code in (404, 400):
            continue
        if r.status_code == 401:
            break
        continue
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message", {}) or {}
    content = (msg.get("content") or "").strip()
    rcontent = (msg.get("reasoning_content") or "")
    finish = choice.get("finish_reason")
    log(f"  resp {model}: finish={finish} content_len={len(content)} reasoning_len={len(rcontent)} usage={data.get('usage',{})}")
    if not content and rcontent:
        content = rcontent.strip()  # reasoning-модель могла всё положить в reasoning_content
    content = content.strip()
    content = re.sub(r"^```(json)?\s*", "", content)
    content = re.sub(r"\s*```\s*$", "", content).strip()
    # сохраним сырой ответ для анализа
    open(f"/home/user/workspace/e2e_out2/solver_parallelogram_raw_{model}.txt","w",encoding="utf-8").write(content)
    try:
        result = json.loads(content)
    except Exception as e:
        last_err = f"bad json {model}: {e}; head={content[:200]}"
        log(last_err)
        # толерантное извлечение aux_constructions из частичного JSON
        aux = _extract_aux(content)
        if aux:
            result = {"solvable": True, "aux_constructions": aux, "steps": [],
                      "aux_needed": True, "answer": {"value": None},
                      "_partial": True, "_model": model}
            json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            log(f"PARTIAL OK model={model}: извлечено aux={len(aux)}")
            log(f"DONE"); sys.exit(0)
        continue
    result["_usage"] = data.get("usage", {}) or {}
    result["_model"] = model
    json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"OK model={model} за {dt:.0f}с  aux={len(result.get('aux_constructions',[]))} steps={len(result.get('steps',[]))}")
    log(f"DONE")
    sys.exit(0)
log(f"FAIL {last_err}")
sys.exit(1)

# -*- coding: utf-8 -*-
"""scripts/figures_diag.py — диагностика раздела FIGURES (CH15/CH16).

Только читает конфигурацию и делает LLM-вызовы. НЕ создаёт job, НЕ списывает
кредиты, НЕ пишет в БД.  Не печатает значения секретных ключей.

Запуск: python scripts/figures_diag.py
"""
import json
import os
import sys

# ── загрузить .env вручную (без импорта app, чтобы не тянуть Flask) ──
def _load_dotenv(path=".env"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_dotenv()

# ── повторить резолюцию моделей из routes/figures_generator.py ──
NOVITA_API_KEY = os.environ.get("NOVITA_API_KEY", "").strip()
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
NOVITA_REASONER_MODEL = os.environ.get(
    "NOVITA_REASONER_MODEL", "deepseek/deepseek-v3-0324"
).strip()
_REASONER_FALLBACK = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro").strip()
REASONER_MODEL = os.environ.get("FIGURE_MODEL", _REASONER_FALLBACK).strip()
FIGURE_BASE_MODEL = os.environ.get("FIGURE_BASE_MODEL", REASONER_MODEL).strip()
FIGURE_AUX_MODEL = os.environ.get("FIGURE_AUX_MODEL", REASONER_MODEL).strip()
FIGURE_REPAIR_MODEL = os.environ.get(
    "FIGURE_REPAIR_MODEL", os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
).strip()
FIGURE_AUDIT_MODEL = os.environ.get("FIGURE_AUDIT_MODEL", REASONER_MODEL).strip()

NOVITA_BASE_URL = "https://api.novita.ai/v3/openai/chat/completions"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1/chat/completions"

print("=" * 70)
print("STEP 1/3: КОНФИГУРАЦИЯ (факт наличия ключей, без значений)")
print("=" * 70)
print("NOVITA_API_KEY   :", "SET" if NOVITA_API_KEY else "UNSET")
print("DEEPSEEK_API_KEY :", "SET" if DEEPSEEK_API_KEY else "UNSET")
print("NOVITA_REASONER_MODEL:", NOVITA_REASONER_MODEL)
print("REASONER_MODEL   :", REASONER_MODEL)
print("FIGURE_BASE_MODEL:", FIGURE_BASE_MODEL)
print("FIGURE_AUX_MODEL :", FIGURE_AUX_MODEL)
print("FIGURE_REPAIR_MODEL:", FIGURE_REPAIR_MODEL)
print("FIGURE_AUDIT_MODEL:", FIGURE_AUDIT_MODEL)
print("CONDITION_SOLUTION_ENABLED:", os.environ.get(
    "FIGURE_CONDITION_SOLUTION_PIPELINE_ENABLED", "1"))
print("FIGURE_SEMANTIC_COLORS_ENABLED:", os.environ.get(
    "FIGURE_SEMANTIC_COLORS_ENABLED", "0"))
print("Novita base_url  :", NOVITA_BASE_URL)
print("DeepSeek base_url:", DEEPSEEK_BASE_URL)
print()
print("Модель, фактически используемая для base_thinking:", FIGURE_BASE_MODEL)
print("Endpoint при наличии NOVITA_API_KEY:", NOVITA_BASE_URL,
      "(модель из FIGURE_BASE_MODEL отправляется в Novita)")

# ── функция, повторяющая логику _call_deepseek (только чтение/вызов) ──
import requests  # noqa: E402


def call(model, messages, max_tokens=16):
    # Novita (приоритет), как в _call_deepseek
    if NOVITA_API_KEY:
        payload = {
            "model": model or NOVITA_REASONER_MODEL,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        try:
            resp = requests.post(
                NOVITA_BASE_URL,
                headers={"Authorization": f"Bearer {NOVITA_API_KEY}",
                         "Content-Type": "application/json"},
                json=payload, timeout=(15, 60),
            )
            return ("novita", resp)
        except Exception as e:
            print("  [novita transport error]", type(e).__name__, str(e)[:200])

    # DeepSeek fallback
    if not DEEPSEEK_API_KEY:
        return ("none", None)
    payload = {
        "model": model or REASONER_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    resp = requests.post(
        DEEPSEEK_BASE_URL,
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                 "Content-Type": "application/json"},
        json=payload, timeout=(15, 60),
    )
    return ("deepseek", resp)


def parse_body(resp):
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text[:500]}


print()
print("=" * 70)
print("STEP 2/3: PING (max_tokens=16)")
print("=" * 70)
provider, resp = call(FIGURE_BASE_MODEL,
                      [{"role": "user", "content": "ping"}], max_tokens=16)
if resp is None:
    print("нет ключа ни Novita, ни DeepSeek")
    sys.exit(0)
print("provider:", provider)
print("http_status:", resp.status_code)
body = parse_body(resp)
if "choices" in body and body["choices"]:
    msg = body["choices"][0].get("message", {}) or {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    print("content len:", len(content))
    print("reasoning_content len:", len(reasoning))
    print("content[:300]:", repr(content[:300]))
    print("reasoning[:300]:", repr(reasoning[:300]))
else:
    print("body keys:", list(body.keys()))
    print("body[:600]:", json.dumps(body, ensure_ascii=False)[:600])

print()
print("=" * 70)
print("STEP 3/3: РЕАЛЬНЫЙ base_planner вызов")
print("=" * 70)
# Загрузить base prompt и подставить condition_text (как _plan_call).
_prompt_path = os.path.join(
    os.path.dirname(__file__), "..", "data", "figures", "base_planner_task.txt")
with open(_prompt_path, "r", encoding="utf-8") as f:
    base_prompt = f.read()
condition_text = "В треугольнике ABC проведена медиана AM."
system_prompt = base_prompt.replace("{condition_text}", condition_text)
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "Верни строго JSON."},
]

provider, resp = call(FIGURE_BASE_MODEL, messages, max_tokens=4096)
if resp is None:
    print("нет ключа для base_planner вызова")
    sys.exit(0)
print("provider:", provider)
print("http_status:", resp.status_code)
body = parse_body(resp)
content = ""
reasoning = ""
if "choices" in body and body["choices"]:
    msg = body["choices"][0].get("message", {}) or {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
print("content len:", len(content))
print("reasoning_content len:", len(reasoning))
# имитация fallback из _call_deepseek: content пуст -> reasoning
effective = content or reasoning
print("effective content len:", len(effective))
print("RAW[:800]:", repr(effective[:800]))

# имитация _extract_json (упрощённо: greedy {.*})
import re  # noqa: E402
json_str = None
m = re.search(r"\{.*\}", effective, re.DOTALL)
if m:
    cand = m.group(0)
    try:
        json.loads(cand)
        json_str = cand
    except Exception:
        json_str = None
print("extract_json success:", json_str is not None)

if json_str:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from services.figure_plan_schemas import parse_base_plan
    from services.figure_validator import validate_figure_json
    plan = parse_base_plan(json_str)
    print("parse_base_plan result:", "OK" if plan is not None else "None")
    if plan is not None:
        v = validate_figure_json(plan)
        print("validate_figure_json:", v.get("valid"), v.get("errors"))

# -*- coding: utf-8 -*-
"""scripts/batch/audit_figures_opus.py — QA чертежей с доп. построением.

Берёт уже решённые solver_aux-задачи из БД, пересобирает aux-план через
исправленный services.aux_compiler, рендерит SVG → PNG и отправляет картинку
в Claude Opus 4.8 (vision) ЧЕРЕЗ OdiRouter (OpenAI-compatible endpoint).

Opus проверяет, ВСЕ ЛИ доп. построения сделаны и сделаны ли они ПРАВИЛЬНО.

Результат: scripts/batch/out/opus_audit.jsonl
Запуск:
    python scripts/batch/audit_figures_opus.py --limit 10
    python scripts/batch/audit_figures_opus.py --limit 10 --only-built
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import httpx  # noqa: E402

OUT_DIR = os.path.join(_SCRIPT_DIR, "out")
os.makedirs(OUT_DIR, exist_ok=True)
RESULTS_PATH = os.path.join(OUT_DIR, "opus_audit.jsonl")

# OdiRouter (OpenAI-compatible).  Модель Claude Opus 4.8, ключ и base из .env.
ODIROUTER_BASE = os.environ.get("GEMINI_API_BASE", "https://api.odirouter.ai/v1").strip().rstrip("/")
ODIROUTER_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
OPUS_MODEL = "claude-opus-4-8"


def _load_dotenv(path: str) -> None:
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


def _extract_json(text: str):
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            json.loads(m.group(0))
            return m.group(0)
        except Exception:
            pass
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end != -1:
            cand = text[start:end + 1]
            try:
                json.loads(cand)
                return cand
            except Exception:
                pass
        start = text.find("{", start + 1)
    return None


def _pick_jobs(limit: int, only_built: bool, specific_job: int = None):
    import sqlite3
    con = sqlite3.connect(os.path.join(_ROOT, "instance", "formyla.db"))
    cur = con.cursor()
    if specific_job is not None:
        cur.execute(
            "SELECT id, problem_text, solution_json, base_plan_json FROM figure_build_jobs "
            "WHERE id=? AND generation_mode='solver_aux' "
            "AND solution_json IS NOT NULL AND base_plan_json IS NOT NULL",
            (specific_job,),
        )
        rows = cur.fetchall()
        con.close()
        return rows
    statuses = ["AUX_BUILT"] if only_built else ["AUX_BUILT", "AUX_DROPPED", "AUX_BUILD_FAILED"]
    placeholders = ",".join("?" * len(statuses))
    # CH-fidelity: берём САМЫЕ СВЕЖИЕ задачи (id DESC) — они построены уже
    # исправленным конвейером, а не старые записи с багами.
    q = (
        "SELECT id, problem_text, solution_json, base_plan_json FROM figure_build_jobs "
        "WHERE generation_mode='solver_aux' AND aux_status IN (%s) "
        "AND solution_json IS NOT NULL AND base_plan_json IS NOT NULL "
        "ORDER BY id DESC" % placeholders
    )
    cur.execute(q, statuses)
    rows = cur.fetchall()
    con.close()
    return rows[:limit]


def _svg_to_png(svg: str):
    try:
        from services.figure_completeness_audit import svg_to_png_bytes
        # scale=1 (600x500) — меньше токенов на изображение, Opus успевает
        # выдать JSON до исчерпания output-бюджета.
        return svg_to_png_bytes(svg, scale=1)
    except Exception:
        return None


_OPUS_SYSTEM = (
    "Ты — строгий эксперт по школьной планиметрии. Тебе дают РИСУНОК чертежа "
    "(доп. построения нарисованы пунктиром), текст условия задачи и СПИСОК "
    "дополнительных построений, которые продиктовал решатель. "
    "Твоя задача — проверить ПОСТРОЕНИЯ ИЗ СПИСКА, а не придумывать свои.\n"
    "Проверь ДВА вопроса СТРОГО относительно списка:\n"
    "1) ВСЕ ЛИ построения из списка реально присутствуют на чертеже?\n"
    "2) Сделаны ли они ПРАВИЛЬНО (нет геометрических ошибок — неверный "
    "перпендикуляр, неверный центр окружности, неверная точка пересечения, "
    "неверная точка касания, неверная длина отложенного отрезка и т.п.)?\n\n"
    "Верни СТРОГО один JSON без markdown:\n"
    '{"correct": true/false, "score": 0..1, '
    '"missing": ["какие построения из списка отсутствуют"], '
    '"problems": ["какие построения сделаны неверно"], '
    '"comment": "краткий вердикт на русском"}'
)


# Порядок моделей для проверки.  Claude Opus 4.8 (по требованию) идёт первым;
# у него extended thinking, который на nginx OdiRouter часто упирается в 504
# Gateway Timeout на реальном чертеже.  Поэтому ниже — fallback-цепочка из
# быстрых моделей, реально возвращающих JSON на этом endpoint.
AUDIT_MODEL_CHAIN = [
    "claude-opus-4-8",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "gemini-3.7-flash",
]


def _call_vision(model: str, system: str, user_text: str, b64: str) -> Optional[dict]:
    """Один vision-вызов через OdiRouter.  Возвращает (status, body-json) или None."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ],
        "temperature": 0.0,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {ODIROUTER_KEY}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(
                f"{ODIROUTER_BASE}/chat/completions",
                headers=headers,
                json=payload,
            )
        if resp.status_code != 200:
            return {"_http": resp.status_code, "_body": resp.text[:200]}
        return resp.json()
    except Exception as e:
        return {"_error": str(e)}


def _opus_judge(svg_png: bytes, condition: str, declared_aux: list = None):
    if not ODIROUTER_KEY:
        return None
    b64 = base64.b64encode(svg_png).decode()
    # CH-fidelity: передаём Opus ПРОДИКТОВАННЫЙ DeepSeek список построений,
    # чтобы он проверял именно «всё ли из того, что сказал DeepSeek, выполнено».
    aux_block = ""
    if declared_aux:
        lines = []
        for idx, a in enumerate(declared_aux, 1):
            if not isinstance(a, dict):
                continue
            op = a.get("op", "?")
            pts = a.get("points") or a.get("segment") or a.get("to_line") or []
            quote = (a.get("quote") or "").strip()
            lines.append(f"{idx}. op={op}, points={pts}, quote=\"{quote}\"")
        if lines:
            aux_block = (
                "Список доп. построений, которые продиктовал решатель (DeepSeek):\n"
                + "\n".join(lines)
                + "\n\n"
            )
    user_text = (
        f"Условие задачи:\n{condition}\n\n"
        f"{aux_block}"
        "Проверь, что КАЖДОЕ построение из списка присутствует на чертеже и "
        "сделано правильно. Верни JSON."
    )

    last_reason = ""
    for model in AUDIT_MODEL_CHAIN:
        raw = _call_vision(model, _OPUS_SYSTEM, user_text, b64)
        if raw is None:
            last_reason = f"{model}: нет ответа"
            continue
        if "_http" in raw or "_error" in raw:
            last_reason = f"{model}: {raw}"
            print(f"  [audit] {model}: {last_reason}")
            # 504 Gateway Timeout — сразу переходим к следующей модели.
            if raw.get("_http") == 504 or raw.get("_http") == 502:
                continue
            continue
        content = (raw.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        finish = (raw.get("choices") or [{}])[0].get("finish_reason") or ""
        js = _extract_json(content)
        if js is None:
            last_reason = f"{model}: пустой/невалидный JSON (finish={finish})"
            print(f"  [audit] {last_reason}:", repr(content[:200]))
            continue
        verdict = json.loads(js)
        verdict["_judge_model"] = model
        return verdict

    print(f"  [audit] все модели не дали вердикт: {last_reason}")
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--only-built", action="store_true")
    ap.add_argument("--job", type=int, default=None, help="проверить конкретный job_id")
    args = ap.parse_args()

    _load_dotenv(os.path.join(_ROOT, ".env"))
    global ODIROUTER_BASE, ODIROUTER_KEY
    ODIROUTER_BASE = os.environ.get("GEMINI_API_BASE", ODIROUTER_BASE).strip().rstrip("/")
    ODIROUTER_KEY = os.environ.get("GEMINI_API_KEY", ODIROUTER_KEY).strip()

    print(f"OdiRouter: {ODIROUTER_BASE}, модель: {OPUS_MODEL}, ключ: {'есть' if ODIROUTER_KEY else 'НЕТ'}")

    jobs = _pick_jobs(args.limit, args.only_built, specific_job=args.job)
    print(f"Отобрано задач из БД: {len(jobs)}")

    from services.aux_compiler import compile_solver_aux, fidelity_report
    from services.figure_plan_validator import merge_base_aux
    from geometric_engine.engine import GeometricEngine, ConstructionError

    out = open(RESULTS_PATH, "a", encoding="utf-8")
    ok = 0
    bad = 0
    skipped = 0

    for i, (jid, cond, sol_raw, base_raw) in enumerate(jobs, 1):
        print(f"\n[{i}/{len(jobs)}] job={jid} | {(cond or '')[:70]}...")
        try:
            sol = json.loads(sol_raw)
            base = json.loads(base_raw)
        except Exception as e:
            print("  [skip] bad json", e)
            skipped += 1
            continue

        aux_plan, issues = compile_solver_aux(sol, base)
        fid = fidelity_report(sol, base)
        if not aux_plan.get("has_aux"):
            print("  [skip] aux пуст:", issues)
            out.write(json.dumps({"job": jid, "stage": "aux_empty", "issues": issues},
                                 ensure_ascii=False) + "\n")
            out.flush()
            skipped += 1
            continue

        merged = merge_base_aux(base, aux_plan)
        eng = GeometricEngine()
        eng.settings.semantic_colors = True
        eng.settings.auto_fit = True
        try:
            svg, _ctx = eng.build(merged)
        except ConstructionError as e:
            print("  [skip] render ConstructionError:", e)
            out.write(json.dumps({"job": jid, "stage": "render_failed",
                                  "issues": issues, "err": str(e)},
                                 ensure_ascii=False) + "\n")
            out.flush()
            skipped += 1
            continue
        except Exception as e:
            print("  [skip] render exc:", e)
            skipped += 1
            continue

        if not svg:
            print("  [skip] svg пуст")
            skipped += 1
            continue

        png = _svg_to_png(svg)
        if png is None:
            print("  [skip] svg->png fail")
            skipped += 1
            continue

        declared_aux = (sol or {}).get("aux_constructions") or []
        verdict = _opus_judge(png, cond, declared_aux=declared_aux)
        rec = {
            "job": jid,
            "condition": cond,
            "fidelity": fid,
            "issues": issues,
            "verdict": verdict,
        }
        print("  fidelity:", fid.get("ratio"), "| compile issues:", issues)
        if verdict:
            correct = bool(verdict.get("correct"))
            if correct:
                ok += 1
            else:
                bad += 1
            print("  opus correct=%s score=%s" % (correct, verdict.get("score")))
            print("  missing:", verdict.get("missing"))
            print("  problems:", verdict.get("problems"))
            print("  comment:", verdict.get("comment"))
        else:
            print("  opus: N/A (ошибка вызова)")
            skipped += 1
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out.flush()
        time.sleep(1.0)

    out.close()
    print(f"\nГотово. correct={ok} incorrect={bad} skipped={skipped}")
    print(f"Результаты: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
